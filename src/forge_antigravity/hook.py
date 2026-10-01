from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from forge_antigravity.exporter import export_pending_turns
from forge_antigravity.links import agents_url

_NEUTRAL_RESPONSE = {"decision": "allow"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def handle_hook(payload: dict[str, Any]) -> dict[str, str]:
    if payload.get("fullyIdle") is not True:
        return _NEUTRAL_RESPONSE
    project = os.environ.get("FORGE_TRACE_PROJECT", "").strip()
    if not project:
        _log("FORGE_TRACE_PROJECT is not set, so this turn was not exported")
        return _NEUTRAL_RESPONSE

    include_content = (
        os.environ.get("FORGE_ANTIGRAVITY_INCLUDE_CONTENT", "true").strip().lower()
        not in _FALSE_VALUES
    )
    try:
        summary = export_pending_turns(
            payload,
            project=project,
            include_content=include_content,
            stopped_at=datetime.now(timezone.utc),
        )
    except Exception as error:
        _log(f"trace export failed: {type(error).__name__}: {error}")
        return _NEUTRAL_RESPONSE
    if summary.turns and (url := agents_url(project, summary.conversation_id)):
        _log(f"View traces: {url}")
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
