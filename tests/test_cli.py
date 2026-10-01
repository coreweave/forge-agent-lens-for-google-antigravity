from __future__ import annotations

import io
import json
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest

from forge_antigravity import __version__, cli, hook

INSTALLED = (
    f"Installed the Antigravity plugin (forge-agent-lens-for-google-antigravity {__version__}).\n"
)
HOOK_COMMAND = f"uvx forge-agent-lens-for-google-antigravity@{__version__}"
PACKAGED_PLUGIN = files("forge_antigravity") / "plugin"


class _Distribution:
    def __init__(self, direct_url: str | None) -> None:
        self.direct_url = direct_url

    def read_text(self, filename: str) -> str | None:
        return self.direct_url if filename == "direct_url.json" else None


@pytest.fixture
def agy(monkeypatch, tmp_path: Path) -> list[tuple[list[str], dict[str, str]]]:
    calls: list[tuple[list[str], dict[str, str]]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((args, {path.name: path.read_text() for path in Path(args[-1]).iterdir()}))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(cli, "distribution", lambda name: _Distribution(None))
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/opt/bin/{name}")
    monkeypatch.setattr(cli.subprocess, "run", run)
    monkeypatch.setenv("HOME", str(tmp_path))
    return calls


def _hook_commands(plugin: dict[str, str]) -> list[str]:
    return [
        handler["command"]
        for handler in json.loads(plugin["hooks.json"])["forge-agentlens"]["Stop"]
    ]


def test_no_command_runs_the_stop_hook(monkeypatch, capsys) -> None:
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO('{"fullyIdle": false}'))

    assert cli.main([]) == 0
    assert json.loads(capsys.readouterr().out) == {"decision": "allow"}


class _Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_no_command_on_a_terminal_exits_instead_of_waiting_for_a_payload(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(cli.sys, "stdin", _Terminal())

    with pytest.raises(SystemExit) as exit_info:
        cli.main([])

    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines()[-1] == (
        "forge-agent-lens-for-google-antigravity: error: expected a Stop hook payload on stdin; "
        "to set up the plugin, run: forge-agent-lens-for-google-antigravity install"
    )


def test_no_command_with_closed_stdin_still_fails_open(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.sys, "stdin", None)

    assert cli.main([]) == 0
    assert json.loads(capsys.readouterr().out) == {"decision": "allow"}


def test_version_prints_the_package_version(capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out == f"{__version__}\n"


def test_install_registers_the_bundled_plugin_and_reports_a_ready_setup(
    agy, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("FORGE_TRACE_PROJECT", "my-team/antigravity-traces")
    monkeypatch.setenv("WANDB_API_KEY", "secret-key")

    assert cli.main(["install"]) == 0

    [(args, plugin)] = agy
    assert args[:3] == ["/opt/bin/agy", "plugin", "install"]
    assert plugin["plugin.json"] == PACKAGED_PLUGIN.joinpath("plugin.json").read_text()
    packaged_hooks = json.loads(PACKAGED_PLUGIN.joinpath("hooks.json").read_text())
    packaged_hooks["forge-agentlens"]["Stop"][0]["command"] = HOOK_COMMAND
    assert json.loads(plugin["hooks.json"]) == packaged_hooks
    assert capsys.readouterr().out == (
        INSTALLED
        + f"✓ Hook command         {HOOK_COMMAND}\n"
        + "✓ FORGE_TRACE_PROJECT  my-team/antigravity-traces\n"
        + "✓ W&B API key          WANDB_API_KEY\n"
        + "View traces: https://wandb.ai/my-team/antigravity-traces/weave/agents\n"
    )


def test_install_explains_missing_trace_settings(agy, capsys) -> None:
    assert cli.main(["install"]) == 0

    assert capsys.readouterr().out == (
        INSTALLED
        + f"✓ Hook command         {HOOK_COMMAND}\n"
        + "✗ FORGE_TRACE_PROJECT  not set: export FORGE_TRACE_PROJECT=entity/project\n"
        + "✗ W&B API key          not found: set WANDB_API_KEY or add api.wandb.ai to ~/.netrc\n"
        + "Antigravity reads these settings from the environment it starts in.\n"
    )


def test_install_rejects_a_project_without_an_entity(agy, monkeypatch, capsys) -> None:
    monkeypatch.setenv("FORGE_TRACE_PROJECT", "agents")
    monkeypatch.setenv("WANDB_API_KEY", "secret-key")

    assert cli.main(["install"]) == 0

    output = capsys.readouterr().out
    assert "✗ FORGE_TRACE_PROJECT  'agents' must be entity/project\n" in output
    assert "View traces" not in output


@pytest.mark.parametrize(
    ("netrc_host", "expected"),
    [
        ("example.wandb.io", "✓ W&B API key          ~/.netrc\n"),
        (
            "api.wandb.ai",
            "✗ W&B API key          not found: "
            "set WANDB_API_KEY or add example.wandb.io to ~/.netrc\n",
        ),
    ],
)
def test_install_reads_netrc_for_the_configured_wandb_host(
    netrc_host: str, expected: str, agy, tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("WANDB_BASE_URL", "https://example.wandb.io")
    netrc_file = tmp_path / ".netrc"
    netrc_file.write_text(f"machine {netrc_host}\n  login user\n  password secret-key\n")
    netrc_file.chmod(0o600)

    assert cli.main(["install"]) == 0

    assert expected in capsys.readouterr().out


def test_install_points_an_editable_checkout_hook_at_its_own_environment(
    agy, monkeypatch, capsys
) -> None:
    direct_url = '{"url": "file:///src/checkout", "dir_info": {"editable": true}}'
    monkeypatch.setattr(cli, "distribution", lambda name: _Distribution(direct_url))
    monkeypatch.setattr(cli.sysconfig, "get_path", lambda name: "/src/my checkout/.venv/bin")

    assert cli.main(["install"]) == 0

    command = "'/src/my checkout/.venv/bin/forge-agent-lens-for-google-antigravity'"
    assert _hook_commands(agy[0][1]) == [command]
    assert f"✓ Hook command         {command}\n" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("direct_url", "source"),
    [
        ('{"url": "file:///src/my%20checkout", "dir_info": {}}', "'/src/my checkout'"),
        (
            '{"url": "file:///src/dist/forge.whl", "archive_info": {"hash": "sha256=00"}}',
            "/src/dist/forge.whl",
        ),
        (
            '{"url": "https://example.com/forge.whl", "archive_info": {}}',
            "https://example.com/forge.whl",
        ),
        (
            '{"url": "https://github.com/coreweave/forge.git", '
            '"vcs_info": {"vcs": "git", "commit_id": "d27ddf4", "requested_revision": "main"}}',
            "git+https://github.com/coreweave/forge.git@d27ddf4",
        ),
    ],
    ids=["directory", "wheel", "url", "git"],
)
def test_install_reruns_a_non_editable_build_from_its_source(
    direct_url: str, source: str, agy, monkeypatch
) -> None:
    monkeypatch.setattr(cli, "distribution", lambda name: _Distribution(direct_url))

    assert cli.main(["install"]) == 0

    assert _hook_commands(agy[0][1]) == [
        f"uvx --from {source} forge-agent-lens-for-google-antigravity"
    ]


def test_install_flags_uvx_missing_from_path(agy, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/opt/bin/agy" if name == "agy" else None)

    assert cli.main(["install"]) == 0

    assert "✗ Hook command         uvx not on PATH: install uv\n" in capsys.readouterr().out


def test_install_requires_the_antigravity_cli(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    monkeypatch.setattr(cli.subprocess, "run", lambda *args, **kwargs: pytest.fail("ran agy"))

    assert cli.main(["install"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "agy is not on PATH" in captured.err


def test_install_stops_when_agy_rejects_the_plugin(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/opt/bin/{name}")
    monkeypatch.setattr(
        cli.subprocess, "run", lambda args, **kwargs: subprocess.CompletedProcess(args, 3)
    )

    assert cli.main(["install"]) == 3
    assert capsys.readouterr().out == ""
