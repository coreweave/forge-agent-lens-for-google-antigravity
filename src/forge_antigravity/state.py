from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExportState:
    last_exported_step: int = -1
    history_start_step: int | None = None
    # Content of steps up to this index must never be exported.
    content_excluded_through_step: int = -1
    # A state file exists but is unusable, so what it excluded is unknown. Not saved.
    corrupted: bool = False


def load_state(payload: dict[str, Any]) -> ExportState:
    path = _state_path(payload)
    if path is None:
        return ExportState()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        last_step = int(value["last_exported_step"])
        history_start = int(value["history_start_step"])
    except FileNotFoundError:
        return ExportState()
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return ExportState(corrupted=True)
    if last_step < -1 or history_start < 0:
        return ExportState(corrupted=True)
    # A file written before this field existed doesn't say which exported turns
    # had content excluded, so treat all of them as excluded.
    excluded_through = value.get("content_excluded_through_step", last_step)
    if (
        not isinstance(excluded_through, int)
        or isinstance(excluded_through, bool)
        or excluded_through < -1
    ):
        return ExportState(
            last_exported_step=last_step,
            history_start_step=history_start,
            corrupted=True,
        )
    return ExportState(
        last_exported_step=last_step,
        history_start_step=history_start,
        content_excluded_through_step=excluded_through,
    )


def save_state(payload: dict[str, Any], state: ExportState) -> None:
    path = _state_path(payload)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    value = asdict(state)
    del value["corrupted"]
    temporary.write_text(json.dumps(value) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _state_path(payload: dict[str, Any]) -> Path | None:
    artifact = payload.get("artifactDirectoryPath")
    if isinstance(artifact, str) and artifact.strip():
        root = Path(artifact).expanduser()
    else:
        transcript = payload.get("transcriptPath")
        if not isinstance(transcript, str) or not transcript.strip():
            return None
        path = Path(transcript).expanduser()
        if len(path.parents) < 3:
            return None
        root = path.parents[2]
    return root / ".forge-antigravity" / "state.json"
