from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from forge_antigravity import exporter
from forge_antigravity.exporter import build_spans
from forge_antigravity.transcript import (
    TranscriptStep,
    extract_user_request,
    load_transcript,
    parse_datetime,
    preferred_transcript,
    split_turns,
)

FIXTURE = Path(__file__).parent / "fixtures" / "transcript_full.jsonl"


def test_transcript_parses_turns_tools_and_wrapped_user_content() -> None:
    steps = load_transcript(FIXTURE, conversation_id="conversation-1")
    turns = split_turns(steps)

    assert len(turns) == 2
    assert turns[0].user_message == "Run the greeting command."
    assert turns[0].final_response == "Done — the command printed hello."
    tool_call = turns[0].planner_steps[0].tool_calls[0]
    assert tool_call.call_id == "conversation-1:2:0"
    assert tool_call.arguments == {
        "CommandLine": "printf hello",
        "Cwd": "/workspace/demo",
    }


def test_prefers_untruncated_transcript(tmp_path: Path) -> None:
    compact = tmp_path / "transcript.jsonl"
    full = tmp_path / "transcript_full.jsonl"
    compact.write_text("{}\n", encoding="utf-8")
    full.write_text("{}\n", encoding="utf-8")
    assert preferred_transcript(compact) == full


def test_prefers_compact_transcript_when_full_file_is_absent(tmp_path: Path) -> None:
    compact = tmp_path / "transcript.jsonl"
    compact.write_text("{}\n", encoding="utf-8")
    assert preferred_transcript(compact) == compact


def test_load_transcript_ignores_invalid_records_and_keeps_latest_snapshot(
    tmp_path: Path,
) -> None:
    transcript = tmp_path / "transcript.jsonl"
    records = [
        "not json",
        "[]",
        json.dumps({"source": "MODEL"}),
        json.dumps(
            {
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "RUNNING",
                "content": "partial",
            }
        ),
        json.dumps(
            {
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "content": "final",
            }
        ),
    ]
    transcript.write_text("\n".join(records), encoding="utf-8")

    steps = load_transcript(transcript)

    assert len(steps) == 1
    assert steps[0].status == "DONE"
    assert steps[0].content == "final"


def test_parser_normalizes_content_tool_ids_and_nested_json(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "step_index": "3",
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": "2026-01-02T12:00:00",
                "content": {"answer": 42},
                "thinking": ["reason"],
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "run_command",
                        "args": {
                            "number": "1",
                            "flag": "true",
                            "nested": '{"value":"[1,2]"}',
                            "plain": "hello",
                        },
                    },
                    {"name": ""},
                    "invalid",
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    step = load_transcript(transcript)[0]

    assert step.created_at == datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    assert step.content == '{"answer": 42}'
    assert step.thinking == '["reason"]'
    assert step.tool_calls[0].call_id == "call-1"
    assert step.tool_calls[0].arguments == {
        "number": 1,
        "flag": True,
        "nested": {"value": [1, 2]},
        "plain": "hello",
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("invalid", None),
        (
            "2026-01-02T12:00:00-08:00",
            datetime(2026, 1, 2, 20, 0, tzinfo=timezone.utc),
        ),
    ],
)
def test_parse_datetime_handles_invalid_and_offset_values(value, expected) -> None:
    assert parse_datetime(value) == expected


def test_extract_user_request_handles_wrapped_and_plain_content() -> None:
    assert (
        extract_user_request(" before <USER_REQUEST> do work </USER_REQUEST> after ") == "do work"
    )
    assert extract_user_request(" plain request ") == "plain request"


def test_split_turns_skips_in_progress_steps_and_caps_previous_end_time() -> None:
    steps = [
        TranscriptStep(
            step_index=0,
            source="USER_EXPLICIT",
            type="USER_INPUT",
            status="DONE",
            created_at=datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
            content="first",
        ),
        TranscriptStep(
            step_index=1,
            source="MODEL",
            type="PLANNER_RESPONSE",
            status="ACTIVE",
            created_at=datetime(2026, 1, 2, 12, 0, 1, tzinfo=timezone.utc),
            content="partial",
        ),
        TranscriptStep(
            step_index=2,
            source="MODEL",
            type="PLANNER_RESPONSE",
            status="DONE",
            created_at=datetime(2026, 1, 2, 12, 0, 5, tzinfo=timezone.utc),
            content="late",
        ),
        TranscriptStep(
            step_index=3,
            source="USER_EXPLICIT",
            type="USER_INPUT",
            status="DONE",
            created_at=datetime(2026, 1, 2, 12, 0, 4, tzinfo=timezone.utc),
            content="second",
        ),
    ]

    turns = split_turns(steps)

    assert len(turns) == 2
    assert turns[0].ended_at == datetime(2026, 1, 2, 12, 0, 4, tzinfo=timezone.utc)
    assert turns[0].final_response == "late"
    assert turns[1].end_step == 3


def test_builds_forge_llm_tool_and_subagent_models() -> None:
    from coreweave.forge.agentlens import tracing

    turns = split_turns(load_transcript(FIXTURE, conversation_id="conversation-1"))
    first_spans = build_spans(
        turns[0],
        model="gemini-test",
    )
    assert [type(span) for span in first_spans] == [tracing.LLM, tracing.Tool, tracing.LLM]

    first_llm = first_spans[0]
    assert first_llm.reasoning.content == "I should run the requested command."
    assert first_llm.output_messages[0].parts[0].name == "run_command"

    tool = first_spans[1]
    assert tool.name == "run_command"
    assert tool.arguments == '{"CommandLine": "printf hello", "Cwd": "/workspace/demo"}'
    assert tool.result.endswith("hello")
    assert tool.started_at.isoformat() == "2026-01-02T12:00:02+00:00"
    assert tool.ended_at.isoformat() == "2026-01-02T12:00:02.500000+00:00"

    final_llm = first_spans[2]
    assert final_llm.usage.input_tokens == 0
    assert [message.role for message in final_llm.input_messages] == [
        "user",
        "assistant",
        "tool",
    ]

    second_spans = build_spans(
        turns[1],
        model="gemini-test",
    )
    assert [type(span) for span in second_spans] == [
        tracing.LLM,
        tracing.SubAgent,
        tracing.LLM,
    ]
    subagent = second_spans[1]
    assert subagent.name == "Reviewer"
    assert subagent.agent_id == ""
    assert subagent.input_messages[0].content == "Inspect the tests"


def test_repeated_tool_calls_consume_results_in_transcript_order(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    records = [
        {
            "step_index": 0,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "status": "DONE",
            "created_at": "2026-01-02T12:00:00Z",
            "content": "Run both commands",
        },
        {
            "step_index": 1,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-01-02T12:00:01Z",
            "tool_calls": [
                {"name": "run_command", "args": {"CommandLine": "one"}},
                {"name": "run_command", "args": {"CommandLine": "two"}},
            ],
        },
        {
            "step_index": 2,
            "source": "MODEL",
            "type": "GENERIC",
            "status": "DONE",
            "created_at": "2026-01-02T12:00:02Z",
            "content": "one",
        },
        {
            "step_index": 3,
            "source": "MODEL",
            "type": "GENERIC",
            "status": "DONE",
            "created_at": "2026-01-02T12:00:03Z",
            "content": "two",
        },
    ]
    transcript.write_text(
        "".join(f"{json.dumps(record)}\n" for record in records),
        encoding="utf-8",
    )
    turn = split_turns(load_transcript(transcript, conversation_id="conversation-1"))[0]
    spans = build_spans(
        turn,
        model="gemini-test",
    )
    tools = [span for span in spans if type(span).__name__ == "Tool"]

    assert [tool.ended_at.isoformat() for tool in tools] == [
        "2026-01-02T12:00:02+00:00",
        "2026-01-02T12:00:03+00:00",
    ]
    assert tools[0].result == "one"
    assert tools[1].result == "two"


def test_transcript_stability_uses_two_file_snapshots(tmp_path: Path, monkeypatch) -> None:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    old = TranscriptStep(
        step_index=2,
        source="MODEL",
        type="PLANNER_RESPONSE",
        status="DONE",
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    current = TranscriptStep(
        step_index=6,
        source="MODEL",
        type="PLANNER_RESPONSE",
        status="DONE",
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    snapshots = iter([[old], [old, current]])
    calls = 0

    def load(*args, **kwargs):
        nonlocal calls
        calls += 1
        return next(snapshots)

    monkeypatch.setattr(exporter, "load_transcript", load)
    monkeypatch.setattr(exporter.time, "sleep", lambda _: None)

    result = exporter._load_stable_transcript(
        str(transcript),
        conversation_id="conversation-1",
    )

    assert calls == 2
    assert result[-1].step_index == 6
