from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch) -> None:
    for variable in (
        "FORGE_ANTIGRAVITY_INCLUDE_CONTENT",
        "FORGE_TRACE_PROJECT",
        "WANDB_API_KEY",
        "WANDB_APP_URL",
        "WANDB_BASE_URL",
        "WF_TRACE_SERVER_URL",
    ):
        monkeypatch.delenv(variable, raising=False)
