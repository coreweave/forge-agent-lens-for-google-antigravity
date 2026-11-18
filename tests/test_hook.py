from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from forge_antigravity import hook
from forge_antigravity.exporter import ExportSummary


def _recording_export(captured: dict[str, object]):
    def export(payload: dict[str, object], **kwargs: object) -> ExportSummary:
        captured.update(kwargs)
        return ExportSummary(turns=0, spans=0, last_step=-1, conversation_id="conversation-1")

    return export


def test_main_always_prints_valid_neutral_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO("not json"))

    hook.main()

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"decision": "allow"}
    assert "invalid hook input" in captured.err


def test_unconfigured_and_non_idle_stops_do_not_export(monkeypatch, capsys) -> None:
    calls: list[object] = []
    monkeypatch.setattr(hook, "export_pending_turns", lambda *args, **kwargs: calls.append(args))

    assert hook.handle_hook({"fullyIdle": False}) == {"decision": "allow"}
    assert capsys.readouterr().err == ""
    assert hook.handle_hook({"fullyIdle": True}) == {"decision": "allow"}
    assert capsys.readouterr().err == (
        "forge-agent-lens-for-google-antigravity: FORGE_TRACE_PROJECT is not set and "
        "~/.forge-agent-lens-for-google-antigravity/settings.json has no project, "
        "so this turn was not exported\n"
    )
    monkeypatch.setenv("FORGE_TRACE_PROJECT", "team/project")
    assert hook.handle_hook({"fullyIdle": False}) == {"decision": "allow"}

    assert calls == []


@pytest.mark.parametrize(
    ("turns", "expected"),
    [
        (
            1,
            "forge-agent-lens-for-google-antigravity: View traces: "
            "https://wandb.ai/team/project/weave/agents/conversations/conversation-1\n",
        ),
        (0, ""),
    ],
)
def test_exported_turns_log_a_link_to_the_conversation(
    turns: int, expected: str, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("FORGE_TRACE_PROJECT", "team/project")
    monkeypatch.setattr(
        hook,
        "export_pending_turns",
        lambda payload, **kwargs: ExportSummary(
            turns=turns, spans=4 * turns, last_step=8, conversation_id="conversation-1"
        ),
    )

    assert hook.handle_hook({"fullyIdle": True}) == {"decision": "allow"}
    assert capsys.readouterr().err == expected


@pytest.mark.parametrize("value", ["0", "false", "NO", "off"])
def test_content_capture_can_be_disabled(value: str, monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("FORGE_TRACE_PROJECT", "team/project")
    monkeypatch.setenv("FORGE_ANTIGRAVITY_INCLUDE_CONTENT", value)
    monkeypatch.setattr(hook, "export_pending_turns", _recording_export(captured))

    assert hook.handle_hook({"fullyIdle": True}) == {"decision": "allow"}
    assert captured["project"] == "team/project"
    assert captured["include_content"] is False
    assert captured["stopped_at"].tzinfo is not None


def test_export_defaults_to_content_capture(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("FORGE_TRACE_PROJECT", " team/project ")
    monkeypatch.delenv("FORGE_ANTIGRAVITY_INCLUDE_CONTENT", raising=False)
    monkeypatch.setattr(hook, "export_pending_turns", _recording_export(captured))

    hook.handle_hook({"fullyIdle": True})

    assert captured["project"] == "team/project"
    assert captured["include_content"] is True


def test_export_failure_is_fail_open(monkeypatch, capsys) -> None:
    monkeypatch.setenv("FORGE_TRACE_PROJECT", "team/project")

    def fail(*args, **kwargs):
        raise RuntimeError("receiver unavailable")

    monkeypatch.setattr(hook, "export_pending_turns", fail)

    assert hook.handle_hook({"fullyIdle": True}) == {"decision": "allow"}
    assert "receiver unavailable" in capsys.readouterr().err


def test_main_accepts_an_object_and_rejects_other_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(hook, "handle_hook", lambda payload: {"decision": "allow"})
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO('{"value":1}'))
    hook.main()
    assert json.loads(capsys.readouterr().out) == {"decision": "allow"}

    monkeypatch.setattr(hook.sys, "stdin", io.StringIO("[]"))
    hook.main()
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"decision": "allow"}
    assert "must be a JSON object" in captured.err


def test_settings_file_configures_apps_started_outside_a_shell(
    settings_file: Path, monkeypatch
) -> None:
    settings_file.parent.mkdir()
    settings_file.write_text('{"project": "team/project", "include_content": false}')
    captured: dict[str, object] = {}
    monkeypatch.setattr(hook, "export_pending_turns", _recording_export(captured))

    assert hook.handle_hook({"fullyIdle": True}) == {"decision": "allow"}
    assert captured["project"] == "team/project"
    assert captured["include_content"] is False


def test_environment_overrides_the_settings_file(settings_file: Path, monkeypatch) -> None:
    settings_file.parent.mkdir()
    settings_file.write_text('{"project": "team/project", "include_content": false}')
    monkeypatch.setenv("FORGE_TRACE_PROJECT", "other/project")
    monkeypatch.setenv("FORGE_ANTIGRAVITY_INCLUDE_CONTENT", "true")
    captured: dict[str, object] = {}
    monkeypatch.setattr(hook, "export_pending_turns", _recording_export(captured))

    hook.handle_hook({"fullyIdle": True})

    assert captured["project"] == "other/project"
    assert captured["include_content"] is True


@pytest.mark.parametrize(
    ("content", "error"),
    [
        (
            "[]",
            "~/.forge-agent-lens-for-google-antigravity/settings.json must contain a JSON object",
        ),
        (
            '{"project": 7}',
            '"project" in ~/.forge-agent-lens-for-google-antigravity/settings.json '
            "must be a string",
        ),
        (
            '{"project": "team/project", "include_content": "no"}',
            '"include_content" in ~/.forge-agent-lens-for-google-antigravity/settings.json '
            "must be true or false",
        ),
    ],
)
def test_invalid_settings_file_skips_the_export_and_says_why(
    content: str, error: str, settings_file: Path, monkeypatch, capsys
) -> None:
    settings_file.parent.mkdir()
    settings_file.write_text(content)
    monkeypatch.setattr(hook, "export_pending_turns", lambda *args, **kwargs: pytest.fail())

    assert hook.handle_hook({"fullyIdle": True}) == {"decision": "allow"}
    assert capsys.readouterr().err == (
        f"forge-agent-lens-for-google-antigravity: {error}, so this turn was not exported\n"
    )


def test_output_printed_during_the_export_stays_out_of_the_hook_response(
    monkeypatch, capsys
) -> None:
    monkeypatch.setenv("FORGE_TRACE_PROJECT", "team/project")
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO('{"fullyIdle": true}'))

    def noisy_export(payload: dict[str, object], **kwargs: object) -> ExportSummary:
        print("library banner")
        return ExportSummary(turns=0, spans=0, last_step=-1, conversation_id="conversation-1")

    monkeypatch.setattr(hook, "export_pending_turns", noisy_export)

    hook.main()

    captured = capsys.readouterr()
    assert captured.out == '{"decision":"allow"}\n'
    assert captured.err == "library banner\n"
