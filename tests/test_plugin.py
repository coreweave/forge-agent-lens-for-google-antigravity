from __future__ import annotations

import json
import os
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

from forge_antigravity import __version__

ROOT = Path(__file__).parents[1]
PLUGIN = files("forge_antigravity") / "plugin"


def test_plugin_manifest_and_hooks_match_the_supported_contract() -> None:
    manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
    hooks = json.loads((PLUGIN / "hooks.json").read_text(encoding="utf-8"))

    assert manifest == {
        "$schema": "https://antigravity.google/schemas/v1/plugin.json",
        "name": "forge-agent-lens-for-google-antigravity",
        "description": (
            "Export Google Antigravity agent, model, tool, and sub-agent spans through "
            "the CoreWeave Forge SDK."
        ),
    }
    assert set(hooks) == {"forge-agentlens"}
    events = hooks["forge-agentlens"]
    assert set(events) == {"Stop"}
    assert events["Stop"][0] == {
        "type": "command",
        "command": "forge-agent-lens-for-google-antigravity",
        "timeout": 60,
    }


def test_package_and_plugin_versions_are_synchronized() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{__version__}"' in pyproject


def test_local_smoke_example_runs_end_to_end() -> None:
    completed = subprocess.run(
        [sys.executable, "examples/local_smoke_test.py"],
        capture_output=True,
        check=False,
        cwd=ROOT,
        env={**os.environ, "PATH": f"{Path(sys.executable).parent}:{os.environ['PATH']}"},
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Local hook-to-OTLP smoke test passed" in completed.stdout
    assert "execute_tool run_command" in completed.stdout


def test_repository_has_no_unresolved_work_markers() -> None:
    markers = ("TO" + "DO", "FIX" + "ME", "T" + "BD")
    tracked = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        check=True,
        cwd=ROOT,
        text=True,
    ).stdout.splitlines()
    offenders: list[str] = []
    for relative in tracked:
        path = ROOT / relative
        if not path.is_file() or path.suffix in {".lock", ".jsonl"}:
            continue
        content = path.read_text(encoding="utf-8")
        if any(marker in content for marker in markers):
            offenders.append(relative)
    assert offenders == []
