from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from forge_antigravity import __version__
from forge_antigravity.state import ExportState, load_state, save_state
from forge_antigravity.transcript import (
    TranscriptStep,
    TranscriptToolCall,
    TranscriptTurn,
    load_transcript,
    preferred_transcript,
    split_turns,
)


@dataclass
class _Operation:
    call: TranscriptToolCall
    planner_step: TranscriptStep
    result_step: TranscriptStep | None = None


@dataclass
class _Invocation:
    step: TranscriptStep
    operations: list[_Operation]


@dataclass(frozen=True)
class ExportSummary:
    turns: int
    spans: int
    last_step: int
    trace_ids: tuple[str, ...] = ()
    root_span_ids: tuple[str, ...] = ()


def export_pending_turns(
    payload: dict[str, Any],
    *,
    project: str,
    include_content: bool = True,
    stopped_at: datetime | None = None,
) -> ExportSummary:
    transcript_path = payload.get("transcriptPath")
    conversation_id = str(payload.get("conversationId", "")).strip()
    if not isinstance(transcript_path, str) or not transcript_path.strip():
        raise ValueError("Antigravity hook payload did not include transcriptPath")
    if not conversation_id:
        raise ValueError("Antigravity hook payload did not include conversationId")

    state = load_state(payload)
    turns = split_turns(_load_stable_transcript(transcript_path, conversation_id=conversation_id))
    pending = _select_pending_turns(turns, state)
    if not pending:
        return ExportSummary(turns=0, spans=0, last_step=state.last_exported_step)

    history_start = state.history_start_step
    if history_start is None:
        history_start = pending[0].start_step
        save_state(payload, ExportState(history_start_step=history_start))

    from coreweave.forge.agentlens import tracing

    model = _text(payload.get("modelName")) or "unknown"
    raw_workspace_paths = payload.get("workspacePaths", [])
    workspace_paths = (
        [value for value in raw_workspace_paths if isinstance(value, str) and value]
        if isinstance(raw_workspace_paths, list)
        else []
    )
    attributes: dict[str, Any] = {
        "forge.integration.name": "antigravity",
        "forge.integration.version": __version__,
    }
    if workspace_paths:
        attributes["forge.integration.antigravity.workspace.paths"] = workspace_paths
    execution_number = payload.get("executionNum")
    if isinstance(execution_number, int) and not isinstance(execution_number, bool):
        attributes["forge.integration.antigravity.execution.number"] = execution_number
    termination_reason = _text(payload.get("terminationReason"))
    if termination_reason:
        attributes["forge.integration.antigravity.termination.reason"] = termination_reason
    stopped_at = stopped_at or datetime.now(timezone.utc)
    forge_turns = []
    for index, turn in enumerate(pending):
        prior_turns = _turn_history_before(
            turns,
            history_start_step=history_start,
            step_index=turn.start_step,
        )
        forge_turns.append(
            tracing.Turn(
                messages=[tracing.Message.user(turn.user_message)] if turn.user_message else [],
                output_messages=(
                    [tracing.Message.assistant(turn.final_response)] if turn.final_response else []
                ),
                spans=build_spans(
                    turn,
                    model=model,
                    prior_messages=_history_messages(prior_turns, tracing),
                ),
                started_at=turn.started_at,
                ended_at=stopped_at if index == len(pending) - 1 else turn.ended_at,
            )
        )

    session = tracing.init(
        project,
        service_name="forge-agent-lens-for-google-antigravity",
        autopatch_integrations=False,
    )
    try:
        result = tracing.log_conversation(
            turns=forge_turns,
            conversation_id=conversation_id,
            conversation_name=Path(workspace_paths[0]).name if workspace_paths else "Antigravity",
            agent_name="Antigravity",
            agent_version=__version__,
            model=model,
            include_content=include_content,
            attributes=attributes,
        )
        if not session.force_flush():
            raise RuntimeError("Forge SDK could not flush Antigravity spans")
    finally:
        session.shutdown()

    last_step = max(turn.end_step for turn in pending)
    save_state(
        payload,
        ExportState(last_exported_step=last_step, history_start_step=history_start),
    )
    return ExportSummary(
        turns=len(pending),
        spans=result.span_count,
        last_step=last_step,
        trace_ids=tuple(result.trace_ids),
        root_span_ids=tuple(result.root_span_ids),
    )


def build_spans(
    turn: TranscriptTurn,
    *,
    model: str,
    prior_messages: list[Any] | None = None,
) -> list[Any]:
    from coreweave.forge.agentlens import tracing

    spans: list[Any] = []
    history: list[Any] = list(prior_messages or [])
    if turn.user_message:
        history.append(tracing.Message.user(turn.user_message))

    boundary = turn.started_at
    for invocation in _collect_invocations(turn):
        started_at, ended_at = _ordered_times(
            boundary,
            invocation.step.created_at or turn.ended_at,
        )
        output_message = _invocation_output_message(invocation, tracing)
        spans.append(
            tracing.LLM(
                model=model,
                provider_name="google",
                input_messages=list(history),
                output_messages=[output_message],
                reasoning=tracing.Reasoning(content=invocation.step.thinking),
                finish_reasons=["tool_calls" if invocation.operations else "stop"],
                started_at=started_at,
                ended_at=ended_at,
            )
        )
        history.append(output_message)

        for operation in invocation.operations:
            operation_spans, result = _operation_spans(operation, model=model, tracing=tracing)
            spans.extend(operation_spans)
            history.append(tracing.Message.tool_result(operation.call.call_id, result))

        timestamps = [
            operation.result_step.created_at
            for operation in invocation.operations
            if operation.result_step is not None and operation.result_step.created_at is not None
        ]
        boundary = max(timestamps, default=ended_at)

    return spans


def _history_messages(turns: list[TranscriptTurn], tracing: Any) -> list[Any]:
    history: list[Any] = []
    for turn in turns:
        if turn.user_message:
            history.append(tracing.Message.user(turn.user_message))
        for invocation in _collect_invocations(turn):
            history.append(_invocation_output_message(invocation, tracing))
            for operation in invocation.operations:
                history.append(
                    tracing.Message.tool_result(
                        operation.call.call_id,
                        _operation_result(operation),
                    )
                )
    return history


def _invocation_output_message(invocation: _Invocation, tracing: Any) -> Any:
    return tracing.Message.assistant(
        invocation.step.content,
        tool_calls=[
            tracing.ToolCallPart(
                id=operation.call.call_id,
                name=operation.call.name,
                arguments=operation.call.arguments,
            )
            for operation in invocation.operations
        ],
    )


def _collect_invocations(turn: TranscriptTurn) -> list[_Invocation]:
    invocations: list[_Invocation] = []
    outstanding: list[_Operation] = []
    for step in turn.steps:
        if step.source == "MODEL" and step.type == "PLANNER_RESPONSE":
            operations = [_Operation(call=call, planner_step=step) for call in step.tool_calls]
            invocations.append(_Invocation(step=step, operations=operations))
            outstanding.extend(operations)
        elif outstanding and _could_be_tool_result(step):
            outstanding.pop(0).result_step = step
    return invocations


def _operation_spans(operation: _Operation, *, model: str, tracing: Any) -> tuple[list[Any], Any]:
    result = _operation_result(operation)
    started_at, ended_at = _ordered_times(
        operation.planner_step.created_at,
        operation.result_step.created_at if operation.result_step else None,
    )
    if operation.call.name == "invoke_subagent":
        return [
            tracing.SubAgent(
                name=_subagent_name(spec, index),
                model=model,
                agent_description=_text(spec.get("Role") or spec.get("role")),
                input_messages=[
                    tracing.Message.user(_text(spec.get("Prompt") or spec.get("prompt")))
                ],
                output_messages=(
                    [tracing.Message.assistant(result)]
                    if isinstance(result, str) and result
                    else []
                ),
                tool_name=operation.call.name,
                tool_call_id=operation.call.call_id,
                tool_call_arguments=spec,
                tool_call_result=result,
                started_at=started_at,
                ended_at=ended_at,
            )
            for index, spec in enumerate(_subagent_specs(operation.call.arguments))
        ], result

    return [
        tracing.Tool(
            name=operation.call.name,
            arguments=operation.call.arguments,
            result=result,
            tool_call_id=operation.call.call_id,
            tool_type="builtin",
            started_at=started_at,
            ended_at=ended_at,
        )
    ], result


def _operation_result(operation: _Operation) -> Any:
    step = operation.result_step
    if step is None:
        return ""
    if step.status == "ERROR":
        return {"error": step.content or "Tool execution failed"}
    return step.content


def _ordered_times(
    started_at: datetime | None,
    ended_at: datetime | None,
) -> tuple[datetime, datetime]:
    end = ended_at or started_at or datetime.now(timezone.utc)
    start = started_at or end - timedelta(microseconds=1)
    if start > end:
        start = end - timedelta(microseconds=1)
    return start, end


def _could_be_tool_result(step: TranscriptStep) -> bool:
    return (
        step.status in {"DONE", "ERROR"}
        and step.type
        not in {"USER_INPUT", "PLANNER_RESPONSE", "CONVERSATION_HISTORY", "CHECKPOINT"}
        and step.source in {"MODEL", "SYSTEM"}
        and bool(step.content or step.status == "ERROR")
    )


def _subagent_specs(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    raw = arguments.get("Subagents", arguments.get("subagents"))
    if isinstance(raw, list):
        specs = [value for value in raw if isinstance(value, dict)]
        if specs:
            return specs
    return [arguments]


def _subagent_name(spec: dict[str, Any], index: int) -> str:
    for key in ("TypeName", "type_name", "name", "Role", "role"):
        value = spec.get(key)
        if isinstance(value, str) and value:
            return value
    return f"Antigravity subagent {index + 1}"


def _load_stable_transcript(path: str, *, conversation_id: str) -> list[TranscriptStep]:
    source = preferred_transcript(path)
    previous_signature: tuple[int, int] | None = None
    latest: list[TranscriptStep] = []
    observed = False
    for delay in (0.0, 0.1, 0.4, 1.0):
        if delay:
            time.sleep(delay)
        try:
            stat = source.stat()
            latest = load_transcript(source, conversation_id=conversation_id)
        except FileNotFoundError:
            previous_signature = None
            continue
        observed = True
        signature = (stat.st_size, stat.st_mtime_ns)
        if signature == previous_signature:
            return latest
        previous_signature = signature
    if not observed:
        raise FileNotFoundError(source)
    raise RuntimeError(
        "Antigravity transcript did not stabilize before the hook deadline; "
        "the turn was left uncheckpointed for a later retry"
    )


def _select_pending_turns(
    turns: list[TranscriptTurn],
    state: ExportState,
) -> list[TranscriptTurn]:
    if not turns:
        return []
    if state.history_start_step is None:
        return turns[-1:]
    pending: list[TranscriptTurn] = []
    for turn in turns:
        if turn.start_step < state.history_start_step or turn.end_step <= state.last_exported_step:
            continue
        if turn.start_step > state.last_exported_step:
            pending.append(turn)
            continue

        # Another Stop hook can continue a fully-idle turn by injecting a
        # system message. Export only the work appended after our last Stop.
        appended_steps = tuple(
            step for step in turn.steps if step.step_index > state.last_exported_step
        )
        if not appended_steps:
            continue
        timestamps = [step.created_at for step in appended_steps if step.created_at is not None]
        pending.append(
            TranscriptTurn(
                start_step=appended_steps[0].step_index,
                end_step=turn.end_step,
                user_message="",
                steps=appended_steps,
                started_at=min(timestamps) if timestamps else None,
                ended_at=turn.ended_at,
            )
        )
    return pending


def _turn_history_before(
    turns: list[TranscriptTurn],
    *,
    history_start_step: int,
    step_index: int,
) -> list[TranscriptTurn]:
    history: list[TranscriptTurn] = []
    for turn in turns:
        if turn.start_step < history_start_step or turn.start_step >= step_index:
            continue
        if turn.end_step < step_index:
            history.append(turn)
            continue

        earlier_steps = tuple(step for step in turn.steps if step.step_index < step_index)
        timestamps = [
            value
            for value in [turn.started_at, *(step.created_at for step in earlier_steps)]
            if value is not None
        ]
        history.append(
            TranscriptTurn(
                start_step=turn.start_step,
                end_step=max(
                    [turn.start_step, *(step.step_index for step in earlier_steps)],
                ),
                user_message=turn.user_message,
                steps=earlier_steps,
                started_at=turn.started_at,
                ended_at=max(timestamps) if timestamps else None,
            )
        )
    return history


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""
