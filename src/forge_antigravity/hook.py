from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from forge_antigravity.exporter import export_pending_turns

_NEUTRAL_RESPONSE = {"decision": "allow"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def handle_hook(payload: dict[str, Any]) -> dict[str, str]:
    project = os.environ.get("FORGE_TRACE_PROJECT", "").strip()
    if payload.get("fullyIdle") is not True or not project:
        return _NEUTRAL_RESPONSE

    include_content = (
        os.environ.get("FORGE_ANTIGRAVITY_INCLUDE_CONTENT", "true").strip().lower()
        not in _FALSE_VALUES
    )
    try:
        export_pending_turns(
            payload,
            project=project,
            include_content=include_content,
            stopped_at=datetime.now(timezone.utc),
        )
    except Exception as error:
        _log(f"trace export failed: {type(error).__name__}: {error}")
    return _NEUTRAL_RESPONSE


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
        response = handle_hook(payload)
    except Exception as error:
        _log(f"invalid hook input: {type(error).__name__}: {error}")
        response = _NEUTRAL_RESPONSE
    sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _log(message: str) -> None:
    sys.stderr.write(f"forge-agent-lens-for-google-antigravity: {message}\n")
