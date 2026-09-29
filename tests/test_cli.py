from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

from forge_antigravity import __version__, cli, hook

INSTALLED = (
    f"Installed the Antigravity plugin (forge-agent-lens-for-google-antigravity {__version__}).\n"
)
EXECUTABLE = "✓ Hook executable      /opt/bin/forge-agent-lens-for-google-antigravity\n"


@pytest.fixture
def agy(monkeypatch, tmp_path: Path) -> list[tuple[list[str], set[str]]]:
    calls: list[tuple[list[str], set[str]]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((args, {path.name for path in Path(args[-1]).iterdir()}))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/opt/bin/{name}")
    monkeypatch.setattr(cli.subprocess, "run", run)
    monkeypatch.setenv("HOME", str(tmp_path))
    return calls


def test_no_command_runs_the_stop_hook(monkeypatch, capsys) -> None:
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO('{"fullyIdle": false}'))

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

    assert [(args[:3], files) for args, files in agy] == [
        (["/opt/bin/agy", "plugin", "install"], {"plugin.json", "hooks.json"})
    ]
    assert capsys.readouterr().out == (
        INSTALLED
        + EXECUTABLE
        + "✓ FORGE_TRACE_PROJECT  my-team/antigravity-traces\n"
        + "✓ W&B API key          WANDB_API_KEY\n"
        + "View traces: https://wandb.ai/my-team/antigravity-traces/weave/agents\n"
    )


def test_install_explains_missing_trace_settings(agy, capsys) -> None:
    assert cli.main(["install"]) == 0

    assert capsys.readouterr().out == (
        INSTALLED
        + EXECUTABLE
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


def test_install_flags_a_hook_executable_missing_from_path(agy, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/opt/bin/agy" if name == "agy" else None)

    assert cli.main(["install"]) == 0

    assert (
        "✗ Hook executable      not on PATH: "
        "uv tool install forge-agent-lens-for-google-antigravity\n"
    ) in capsys.readouterr().out


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
