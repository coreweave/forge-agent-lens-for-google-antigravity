from __future__ import annotations

import pytest

from forge_antigravity.links import agents_url


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({}, "https://forge.coreweave.com/wandb/my-team/antigravity-traces/weave/agents"),
        (
            {"WANDB_BASE_URL": "https://api.wandb.ai/"},
            "https://forge.coreweave.com/wandb/my-team/antigravity-traces/weave/agents",
        ),
        (
            {"WANDB_BASE_URL": "https://example.wandb.io"},
            "https://example.wandb.io/my-team/antigravity-traces/weave/agents",
        ),
        (
            {"WANDB_BASE_URL": "https://api.example.com"},
            "https://app.example.com/my-team/antigravity-traces/weave/agents",
        ),
        (
            {"WANDB_BASE_URL": "https://api.wandb.test"},
            "https://app.wandb.test/my-team/antigravity-traces/weave/agents",
        ),
        (
            {
                "WANDB_BASE_URL": "https://example.wandb.io",
                "WANDB_APP_URL": "https://ui.example.com/",
            },
            "https://ui.example.com/my-team/antigravity-traces/weave/agents",
        ),
    ],
)
def test_agents_url_follows_the_wandb_app_host(
    environment: dict[str, str], expected: str, monkeypatch
) -> None:
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    assert agents_url("my-team/antigravity-traces") == expected


def test_agents_url_links_a_conversation() -> None:
    assert agents_url(" my-team / antigravity-traces ", "conversation 1") == (
        "https://forge.coreweave.com/wandb/my-team/antigravity-traces"
        "/weave/agents/conversations/conversation%201"
    )


@pytest.mark.parametrize(
    "project",
    ["", "my-team", "my-team/", "/antigravity-traces", "my-team/antigravity-traces/extra"],
)
def test_agents_url_rejects_projects_the_forge_sdk_rejects(project: str) -> None:
    assert agents_url(project) is None
