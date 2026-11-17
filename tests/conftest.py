from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch, tmp_path: Path) -> None:
    for variable in (
        "FORGE_ANTIGRAVITY_INCLUDE_CONTENT",
        "FORGE_TRACE_PROJECT",
        "WANDB_API_KEY",
        "WANDB_APP_URL",
        "WANDB_BASE_URL",
        "WF_TRACE_SERVER_URL",
    ):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.fixture
def settings_file(tmp_path: Path) -> Path:
    return tmp_path / ".forge-agent-lens-for-google-antigravity" / "settings.json"
