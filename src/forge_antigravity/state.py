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


def load_state(payload: dict[str, Any]) -> ExportState:
    path = _state_path(payload)
    if path is None:
        return ExportState()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        last_step = int(value["last_exported_step"])
        history_start = int(value["history_start_step"])
    except (FileNotFoundError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return ExportState()
    if last_step < -1 or history_start < 0:
        return ExportState()
    return ExportState(last_exported_step=last_step, history_start_step=history_start)


def save_state(payload: dict[str, Any], state: ExportState) -> None:
    path = _state_path(payload)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(asdict(state)) + "\n", encoding="utf-8")
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
