from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

from examples.local_smoke_test import local_otlp_receiver, otel_attribute
from forge_antigravity import __version__, exporter
from forge_antigravity.exporter import _select_pending_turns, export_pending_turns
from forge_antigravity.state import ExportState, load_state
from forge_antigravity.transcript import (
    TranscriptStep,
    TranscriptToolCall,
    load_transcript,
    split_turns,
)

FIXTURE = Path(__file__).parent / "fixtures" / "transcript_full.jsonl"
ROOT = Path(__file__).parents[1]


@pytest.fixture(autouse=True)
def _skip_stability_delays(monkeypatch) -> None:
    monkeypatch.setattr(exporter.time, "sleep", lambda _: None)


def _payload(tmp_path: Path, *, conversation_id: str = "conversation-1") -> dict[str, object]:
    artifact = tmp_path / "artifact"
    logs = artifact / ".system_generated" / "logs"
    logs.mkdir(parents=True)
    shutil.copyfile(FIXTURE, logs / "transcript_full.jsonl")
    return {
        "conversationId": conversation_id,
        "artifactDirectoryPath": str(artifact),
        "transcriptPath": str(logs / "transcript.jsonl"),
        "workspacePaths": ["/workspace/demo"],
        "modelName": "gemini-test",
        "executionNum": 3,
        "terminationReason": "model_stop",
        "fullyIdle": True,
    }


def _request(requests: queue.Queue[bytes]) -> ExportTraceServiceRequest:
    return ExportTraceServiceRequest.FromString(requests.get(timeout=5))


def _spans(request: ExportTraceServiceRequest):
    return [
        span
        for resource_spans in request.resource_spans
        for scope_spans in resource_spans.scope_spans
        for span in scope_spans.spans
    ]


def test_export_builds_forge_conversation_and_checkpoints(tmp_path: Path, monkeypatch) -> None:
    payload = _payload(tmp_path, conversation_id="sdk-boundary")
    from coreweave.forge.agentlens import tracing

    initialized: list[tuple[str, dict[str, object]]] = []
    logged: list[dict[str, object]] = []
    lifecycle: list[str] = []
    session = SimpleNamespace(
        force_flush=lambda: lifecycle.append("force_flush") or True,
        shutdown=lambda: lifecycle.append("shutdown"),
    )

    def init(project: str, **kwargs: object):
        initialized.append((project, kwargs))
        return session

    def log_conversation(**kwargs: object):
        logged.append(kwargs)
        return SimpleNamespace(span_count=4, trace_ids=["trace"], root_span_ids=["root"])

    monkeypatch.setattr(tracing, "init", init)
    monkeypatch.setattr(tracing, "log_conversation", log_conversation)

    summary = export_pending_turns(
        payload,
        project="team/project",
        stopped_at=datetime(2026, 1, 2, 12, 2, tzinfo=timezone.utc),
    )

    assert initialized == [
        (
            "team/project",
            {
                "autopatch_integrations": False,
                "service_name": "forge-agent-lens-for-google-antigravity",
            },
        )
    ]
    assert len(logged) == 1
    assert logged[0]["conversation_id"] == "sdk-boundary"
    assert logged[0]["conversation_name"] == "demo"
    assert logged[0]["agent_name"] == "Antigravity"
    assert logged[0]["agent_version"] == __version__
    assert logged[0]["attributes"] == {
        "forge.integration.name": "antigravity",
        "forge.integration.version": __version__,
        "forge.integration.antigravity.workspace.paths": ["/workspace/demo"],
        "forge.integration.antigravity.execution.number": 3,
        "forge.integration.antigravity.termination.reason": "model_stop",
    }
    assert len(logged[0]["turns"]) == 1
    assert summary.conversation_id == "sdk-boundary"
    assert summary.trace_ids == ("trace",)
    assert lifecycle == ["force_flush", "shutdown"]
    assert load_state(payload).last_exported_step == 8

    again = export_pending_turns(payload, project="team/project")
    assert again.turns == 0
    assert len(logged) == 1


def test_first_observation_skips_history_and_retry_keeps_its_boundary() -> None:
    turns = split_turns(load_transcript(FIXTURE, conversation_id="conversation-1"))

    latest = _select_pending_turns(turns, ExportState())
    retry = _select_pending_turns(
        turns,
        ExportState(last_exported_step=-1, history_start_step=latest[0].start_step),
    )
    completed = _select_pending_turns(
        turns,
        ExportState(last_exported_step=8, history_start_step=latest[0].start_step),
    )

    assert [turn.start_step for turn in latest] == [5]
    assert [turn.start_step for turn in retry] == [5]
    assert completed == []


def test_stop_hook_continuation_exports_only_steps_after_the_first_stop(
    tmp_path: Path, monkeypatch
) -> None:
    payload = _payload(tmp_path, conversation_id="stop-continuation")
    steps = [
        TranscriptStep(
            step_index=0,
            source="USER_EXPLICIT",
            type="USER_INPUT",
            status="DONE",
            created_at=datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc),
            content="start the task",
        ),
        TranscriptStep(
            step_index=1,
            source="MODEL",
            type="PLANNER_RESPONSE",
            status="DONE",
            created_at=datetime(2026, 1, 2, 12, 0, 1, tzinfo=timezone.utc),
            content="first pass",
        ),
        TranscriptStep(
            step_index=2,
            source="SYSTEM",
            type="SYSTEM_MESSAGE",
            status="DONE",
            created_at=datetime(2026, 1, 2, 12, 0, 2, tzinfo=timezone.utc),
            content="continue hook reason",
        ),
        TranscriptStep(
            step_index=3,
            source="MODEL",
            type="PLANNER_RESPONSE",
            status="DONE",
            created_at=datetime(2026, 1, 2, 12, 0, 3, tzinfo=timezone.utc),
            content="second pass",
        ),
    ]
    snapshots = iter([steps[:2], steps])
    monkeypatch.setattr(
        exporter,
        "_load_stable_transcript",
        lambda *args, **kwargs: next(snapshots),
    )

    from coreweave.forge.agentlens import tracing

    logged: list[dict[str, object]] = []
    session = SimpleNamespace(force_flush=lambda: True, shutdown=lambda: None)
    monkeypatch.setattr(tracing, "init", lambda *args, **kwargs: session)
    monkeypatch.setattr(
        tracing,
        "log_conversation",
        lambda **kwargs: (
            logged.append(kwargs)
            or SimpleNamespace(span_count=2, trace_ids=["trace"], root_span_ids=["root"])
        ),
    )

    first = export_pending_turns(
        payload,
        project="team/project",
        stopped_at=datetime(2026, 1, 2, 12, 0, 1, tzinfo=timezone.utc),
    )
    continued = export_pending_turns(
        payload,
        project="team/project",
        stopped_at=datetime(2026, 1, 2, 12, 0, 3, tzinfo=timezone.utc),
    )

    first_turn = logged[0]["turns"][0]
    continued_turn = logged[1]["turns"][0]
    assert first.last_step == 1
    assert continued.last_step == 3
    assert first_turn.spans[0].output_messages[0].content == "first pass"
    assert continued_turn.messages == []
    assert continued_turn.output_messages[0].content == "second pass"
    assert len(continued_turn.spans) == 1
    assert continued_turn.spans[0].output_messages[0].content == "second pass"
    assert [message.content for message in continued_turn.spans[0].input_messages] == [
        "start the task",
        "first pass",
    ]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"conversationId": "conversation-1"}, "transcriptPath"),
        ({"transcriptPath": "/tmp/transcript.jsonl"}, "conversationId"),
    ],
)
def test_export_requires_hook_identifiers(payload, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        export_pending_turns(payload, project="team/project")


def _step(
    *,
    source: str = "MODEL",
    type: str = "GENERIC",
    status: str = "DONE",
    content: str = "result",
    created_at: datetime | None = None,
) -> TranscriptStep:
    return TranscriptStep(
        step_index=1,
        source=source,
        type=type,
        status=status,
        content=content,
        created_at=created_at,
    )


def _operation(result_step: TranscriptStep | None = None):
    planner = _step(
        type="PLANNER_RESPONSE",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    return exporter._Operation(
        call=TranscriptToolCall(name="run_command", arguments={}, call_id="call-1"),
        planner_step=planner,
        result_step=result_step,
    )


def test_exporter_helpers_cover_errors_timestamps_and_subagents() -> None:
    assert exporter._operation_result(_operation()) == ""
    assert exporter._operation_result(_operation(_step(status="ERROR", content=""))) == {
        "error": "Tool execution failed"
    }
    end = datetime(2026, 1, 1, tzinfo=timezone.utc)
    start, normalized_end = exporter._ordered_times(end + timedelta(seconds=1), end)
    assert start < normalized_end == end
    assert exporter._could_be_tool_result(_step()) is True
    assert exporter._could_be_tool_result(_step(status="RUNNING")) is False
    assert exporter._could_be_tool_result(_step(type="CHECKPOINT")) is False
    assert exporter._subagent_specs({"Subagents": [{"name": "one"}, 2]}) == [{"name": "one"}]
    assert exporter._subagent_name({}, 1) == "Antigravity subagent 2"


def test_flush_failure_preserves_retry_boundary_without_checkpoint(
    tmp_path: Path, monkeypatch
) -> None:
    payload = _payload(tmp_path, conversation_id="flush-failure")
    from coreweave.forge.agentlens import tracing

    lifecycle: list[str] = []
    session = SimpleNamespace(
        force_flush=lambda: lifecycle.append("force_flush") or False,
        shutdown=lambda: lifecycle.append("shutdown"),
    )
    monkeypatch.setattr(tracing, "init", lambda *args, **kwargs: session)
    monkeypatch.setattr(
        tracing,
        "log_conversation",
        lambda **kwargs: SimpleNamespace(span_count=1, trace_ids=["trace"], root_span_ids=["root"]),
    )

    with pytest.raises(RuntimeError, match="could not flush"):
        export_pending_turns(payload, project="team/project")

    assert load_state(payload) == ExportState(
        last_exported_step=-1,
        history_start_step=5,
    )
    assert lifecycle == ["force_flush", "shutdown"]


def test_sdk_session_shuts_down_when_logging_fails(tmp_path: Path, monkeypatch) -> None:
    payload = _payload(tmp_path, conversation_id="log-failure")
    from coreweave.forge.agentlens import tracing

    lifecycle: list[str] = []
    session = SimpleNamespace(
        force_flush=lambda: lifecycle.append("force_flush") or True,
        shutdown=lambda: lifecycle.append("shutdown"),
    )
    monkeypatch.setattr(tracing, "init", lambda *args, **kwargs: session)
    monkeypatch.setattr(
        tracing,
        "log_conversation",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("log failed")),
    )

    with pytest.raises(RuntimeError, match="log failed"):
        export_pending_turns(payload, project="team/project")
    assert lifecycle == ["shutdown"]
    assert load_state(payload).last_exported_step == -1


def test_stable_transcript_rejects_missing_and_continuously_changing_files(
    tmp_path: Path, monkeypatch
) -> None:
    with pytest.raises(FileNotFoundError):
        exporter._load_stable_transcript(
            str(tmp_path / "missing.jsonl"),
            conversation_id="conversation-1",
        )

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")

    def changing(path: Path, *, conversation_id: str = ""):
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        return []

    monkeypatch.setattr(exporter, "load_transcript", changing)
    with pytest.raises(RuntimeError, match="left uncheckpointed"):
        exporter._load_stable_transcript(
            str(transcript),
            conversation_id="conversation-1",
        )


def test_sequential_exports_preserve_only_observed_history(tmp_path: Path, monkeypatch) -> None:
    payload = _payload(tmp_path, conversation_id="sequential")
    transcript = Path(str(payload["transcriptPath"])).with_name("transcript_full.jsonl")
    records = FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)
    transcript.write_text("".join(records[:5]), encoding="utf-8")
    monkeypatch.setenv("WANDB_API_KEY", "test-key")

    with local_otlp_receiver() as (base_url, requests):
        monkeypatch.setenv("WF_TRACE_SERVER_URL", base_url)
        first = export_pending_turns(payload, project="team/project")
        assert first.turns == 1
        assert len(_spans(_request(requests))) == 4

        transcript.write_text("".join(records), encoding="utf-8")
        second = export_pending_turns(payload, project="team/project")
        second_spans = _spans(_request(requests))

    assert second.turns == 1
    inputs = [
        str(otel_attribute(span, "gen_ai.input.messages") or "")
        for span in second_spans
        if span.name == "chat gemini-test"
    ]
    assert any(
        "Run the greeting command." in value
        and "the command printed hello." in value
        and "Ask a reviewer to inspect the tests." in value
        for value in inputs
    )


def test_real_forge_sdk_exports_otlp_and_checkpoints_latest_turn(
    tmp_path: Path, monkeypatch
) -> None:
    payload = _payload(tmp_path)
    monkeypatch.setenv("WANDB_API_KEY", "test-key")

    with local_otlp_receiver() as (base_url, requests):
        monkeypatch.setenv("WF_TRACE_SERVER_URL", base_url)
        summary = export_pending_turns(
            payload,
            project="team/project",
            stopped_at=datetime(2026, 1, 2, 12, 1, 5, tzinfo=timezone.utc),
        )
        request = _request(requests)

        assert summary.turns == 1
        assert summary.spans == 4
        assert summary.last_step == 8
        assert len(summary.trace_ids) == len(summary.root_span_ids) == 1
        resource = request.resource_spans[0].resource
        assert otel_attribute(resource, "service.name") == "forge-agent-lens-for-google-antigravity"
        assert otel_attribute(resource, "wandb.sdk.name") == "forge"
        assert otel_attribute(resource, "wandb.entity") == "team"
        assert otel_attribute(resource, "wandb.project") == "project"

        spans = _spans(request)
        assert sorted(span.name for span in spans) == sorted(
            [
                "invoke_agent Antigravity",
                "chat gemini-test",
                "invoke_agent Reviewer",
                "chat gemini-test",
            ]
        )
        root = next(span for span in spans if not span.parent_span_id)
        assert root.trace_id.hex() == summary.trace_ids[0]
        assert root.span_id.hex() == summary.root_span_ids[0]
        assert otel_attribute(root, "gen_ai.agent.version") == __version__
        assert all(
            otel_attribute(span, "forge.integration.name") == "antigravity" for span in spans
        )
        assert all(
            otel_attribute(span, "forge.integration.version") == __version__ for span in spans
        )
        assert all(
            otel_attribute(span, "forge.integration.antigravity.execution.number") == 3
            for span in spans
        )
        assert all(
            otel_attribute(span, "forge.integration.antigravity.termination.reason") == "model_stop"
            for span in spans
        )
        workspace_paths = otel_attribute(root, "forge.integration.antigravity.workspace.paths")
        assert [value.string_value for value in workspace_paths.values] == ["/workspace/demo"]

        again = export_pending_turns(payload, project="team/project")
        assert again.turns == 0
        assert requests.empty()


def test_content_gate_keeps_transcript_payloads_off_the_wire(tmp_path: Path, monkeypatch) -> None:
    payload = _payload(tmp_path, conversation_id="redacted")
    monkeypatch.setenv("WANDB_API_KEY", "test-key")

    with local_otlp_receiver() as (base_url, requests):
        monkeypatch.setenv("WF_TRACE_SERVER_URL", base_url)
        export_pending_turns(
            payload,
            project="team/project",
            include_content=False,
        )
        body = requests.get(timeout=5)

    assert b"Inspect the tests" not in body
    assert b"The tests look good" not in body


def test_installed_hook_reaches_the_sdk_exporter(tmp_path: Path, monkeypatch) -> None:
    payload = _payload(tmp_path, conversation_id="installed-hook")
    with local_otlp_receiver() as (base_url, requests):
        executable_path = f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"
        executable = shutil.which("forge-agent-lens-for-google-antigravity", path=executable_path)
        assert executable is not None
        env = {
            **os.environ,
            "FORGE_TRACE_PROJECT": "team/project",
            "PATH": executable_path,
            "WANDB_API_KEY": "test-key",
            "WF_TRACE_SERVER_URL": base_url,
        }
        completed = subprocess.run(
            [executable],
            input=json.dumps(payload),
            capture_output=True,
            check=False,
            cwd=ROOT,
            env=env,
            text=True,
            timeout=15,
        )

        assert completed.returncode == 0
        assert json.loads(completed.stdout) == {"decision": "allow"}
        names = [span.name for span in _spans(_request(requests))]
        assert "invoke_agent Antigravity" in names
        assert "invoke_agent Reviewer" in names


def test_production_source_delegates_transport_to_forge_sdk() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "src").rglob("*.py"))
    assert "tracing.init(" in source
    assert "tracing.log_conversation(" in source
    for forbidden in ("OTLPSpanExporter", "requests.", "httpx.", "urllib.request"):
        assert forbidden not in source
