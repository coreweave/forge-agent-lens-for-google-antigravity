from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from typing import Any

from forge_antigravity.exporter import export_pending_turns
from forge_antigravity.links import agents_url
from forge_antigravity.settings import SETTINGS_DISPLAY_PATH, load_settings

_NEUTRAL_RESPONSE = {"decision": "allow"}


def handle_hook(payload: dict[str, Any]) -> dict[str, str]:
    if payload.get("fullyIdle") is not True:
        return _NEUTRAL_RESPONSE
    try:
        settings = load_settings()
    except ValueError as error:
        _log(f"{error}, so this turn was not exported")
        return _NEUTRAL_RESPONSE
    if not settings.project:
        _log(
            f"FORGE_TRACE_PROJECT is not set and {SETTINGS_DISPLAY_PATH} has no project, "
            "so this turn was not exported"
        )
        return _NEUTRAL_RESPONSE

    try:
        summary = export_pending_turns(
            payload,
            project=settings.project,
            include_content=settings.include_content,
            stopped_at=datetime.now(timezone.utc),
        )
    except Exception as error:
        _log(f"trace export failed: {type(error).__name__}: {error}")
        return _NEUTRAL_RESPONSE
    if summary.turns and (url := agents_url(settings.project, summary.conversation_id)):
        _log(f"View traces: {url}")
    return _NEUTRAL_RESPONSE


def main() -> None:
    # Antigravity parses stdout as the hook response, so stray library output goes to stderr.
    with redirect_stdout(sys.stderr):
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
