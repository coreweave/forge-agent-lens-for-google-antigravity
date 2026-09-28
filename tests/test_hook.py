from __future__ import annotations

import io
import json

import pytest

from forge_antigravity import hook


def test_main_always_prints_valid_neutral_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO("not json"))

    hook.main()

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"decision": "allow"}
    assert "invalid hook input" in captured.err


def test_unconfigured_and_non_idle_stops_do_not_export(monkeypatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(hook, "export_pending_turns", lambda *args, **kwargs: calls.append(args))

    monkeypatch.delenv("FORGE_TRACE_PROJECT", raising=False)
    assert hook.handle_hook({"fullyIdle": True}) == {"decision": "allow"}
    monkeypatch.setenv("FORGE_TRACE_PROJECT", "team/project")
    assert hook.handle_hook({"fullyIdle": False}) == {"decision": "allow"}

    assert calls == []


@pytest.mark.parametrize("value", ["0", "false", "NO", "off"])
def test_content_capture_can_be_disabled(value: str, monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("FORGE_TRACE_PROJECT", "team/project")
    monkeypatch.setenv("FORGE_ANTIGRAVITY_INCLUDE_CONTENT", value)
    monkeypatch.setattr(
        hook,
        "export_pending_turns",
        lambda payload, **kwargs: captured.update(kwargs),
    )

    assert hook.handle_hook({"fullyIdle": True}) == {"decision": "allow"}
    assert captured["project"] == "team/project"
    assert captured["include_content"] is False
    assert captured["stopped_at"].tzinfo is not None


def test_export_defaults_to_content_capture(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("FORGE_TRACE_PROJECT", " team/project ")
    monkeypatch.delenv("FORGE_ANTIGRAVITY_INCLUDE_CONTENT", raising=False)
    monkeypatch.setattr(
        hook,
        "export_pending_turns",
        lambda payload, **kwargs: captured.update(kwargs),
    )

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
