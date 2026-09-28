from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_USER_REQUEST_RE = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.DOTALL)


@dataclass(frozen=True)
class TranscriptToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str


@dataclass(frozen=True)
class TranscriptStep:
    step_index: int
    source: str
    type: str
    status: str
    created_at: datetime | None
    content: str = ""
    thinking: str = ""
    tool_calls: tuple[TranscriptToolCall, ...] = ()


@dataclass(frozen=True)
class TranscriptTurn:
    start_step: int
    end_step: int
    user_message: str
    steps: tuple[TranscriptStep, ...]
    started_at: datetime | None
    ended_at: datetime | None

    @property
    def planner_steps(self) -> list[TranscriptStep]:
        return [
            step
            for step in self.steps
            if step.source == "MODEL" and step.type == "PLANNER_RESPONSE"
        ]

    @property
    def final_response(self) -> str:
        for step in reversed(self.planner_steps):
            if step.content:
                return step.content
        return ""


def preferred_transcript(path: str | Path) -> Path:
    compact = Path(path).expanduser()
    full = compact.with_name("transcript_full.jsonl")
    return full if full.is_file() else compact


def load_transcript(path: str | Path, *, conversation_id: str = "") -> list[TranscriptStep]:
    source = preferred_transcript(path)
    by_index: dict[int, tuple[int, TranscriptStep]] = {}
    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                # Antigravity may be appending the final line while Stop fires.
                continue
            if not isinstance(raw, dict):
                continue
            step = _parse_step(raw, conversation_id=conversation_id)
            if step is None:
                continue
            # A live step can be written more than once. The latest snapshot is
            # authoritative for that step index.
            by_index[step.step_index] = (line_number, step)
    return [
        value[1]
        for value in sorted(by_index.values(), key=lambda item: (item[1].step_index, item[0]))
    ]


def split_turns(steps: list[TranscriptStep]) -> list[TranscriptTurn]:
    turns: list[TranscriptTurn] = []
    current_user: TranscriptStep | None = None
    current_steps: list[TranscriptStep] = []

    def finish(next_started_at: datetime | None = None) -> None:
        nonlocal current_user, current_steps
        if current_user is None:
            return
        timestamps = [
            step.created_at
            for step in [current_user, *current_steps]
            if step.created_at is not None
        ]
        ended_at = max(timestamps) if timestamps else current_user.created_at
        if next_started_at is not None and (ended_at is None or ended_at > next_started_at):
            ended_at = next_started_at
        end_step = max(
            [current_user.step_index, *(step.step_index for step in current_steps)],
        )
        turns.append(
            TranscriptTurn(
                start_step=current_user.step_index,
                end_step=end_step,
                user_message=extract_user_request(current_user.content),
                steps=tuple(current_steps),
                started_at=current_user.created_at,
                ended_at=ended_at,
            )
        )
        current_user = None
        current_steps = []

    for step in steps:
        if step.status in {"CLEARED", "RUNNING", "ACTIVE"}:
            continue
        if step.source == "USER_EXPLICIT" and step.type == "USER_INPUT":
            finish(step.created_at)
            current_user = step
            continue
        if current_user is not None:
            current_steps.append(step)
    finish()
    return turns


def extract_user_request(content: str) -> str:
    match = _USER_REQUEST_RE.search(content)
    return match.group(1).strip() if match else content.strip()


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_step(raw: dict[str, Any], *, conversation_id: str) -> TranscriptStep | None:
    try:
        step_index = int(raw["step_index"])
    except (KeyError, TypeError, ValueError):
        return None

    tool_calls: list[TranscriptToolCall] = []
    raw_calls = raw.get("tool_calls", [])
    if isinstance(raw_calls, list):
        for ordinal, value in enumerate(raw_calls):
            if not isinstance(value, dict):
                continue
            name = value.get("name")
            if not isinstance(name, str) or not name:
                continue
            args = value.get("args", {})
            decoded_args = _decode_json_values(args) if isinstance(args, dict) else {}
            raw_id = value.get("id") or value.get("call_id")
            call_id = (
                str(raw_id)
                if raw_id
                else f"{conversation_id or 'antigravity'}:{step_index}:{ordinal}"
            )
            tool_calls.append(
                TranscriptToolCall(name=name, arguments=decoded_args, call_id=call_id)
            )

    content = raw.get("content", "")
    thinking = raw.get("thinking", "")
    return TranscriptStep(
        step_index=step_index,
        source=str(raw.get("source", "")),
        type=str(raw.get("type", "")),
        status=str(raw.get("status", "")),
        created_at=parse_datetime(raw.get("created_at")),
        content=content if isinstance(content, str) else json.dumps(content, default=str),
        thinking=thinking if isinstance(thinking, str) else json.dumps(thinking, default=str),
        tool_calls=tuple(tool_calls),
    )


def _decode_json_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _decode_json_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_json_values(item) for item in value]
    if not isinstance(value, str):
        return value
    candidate = value.strip()
    if not candidate:
        return value
    try:
        decoded = json.loads(candidate)
    except json.JSONDecodeError:
        return value
    # Antigravity's transcript encodes many argument values one extra time.
    # Only accept scalar/container JSON that consumed the complete string.
    return _decode_json_values(decoded) if decoded != value else decoded
