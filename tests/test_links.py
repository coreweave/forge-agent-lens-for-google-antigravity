from __future__ import annotations

import pytest

from forge_antigravity.links import agents_url


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({}, "https://wandb.ai/acme/agents/weave/agents"),
        ({"WANDB_BASE_URL": "https://api.wandb.ai/"}, "https://wandb.ai/acme/agents/weave/agents"),
        (
            {"WANDB_BASE_URL": "https://acme.wandb.io"},
            "https://acme.wandb.io/acme/agents/weave/agents",
        ),
        (
            {"WANDB_BASE_URL": "https://api.example.com"},
            "https://app.example.com/acme/agents/weave/agents",
        ),
        (
            {"WANDB_BASE_URL": "https://api.wandb.test"},
            "https://app.wandb.test/acme/agents/weave/agents",
        ),
        (
            {"WANDB_BASE_URL": "https://acme.wandb.io", "WANDB_APP_URL": "https://ui.example.com/"},
            "https://ui.example.com/acme/agents/weave/agents",
        ),
    ],
)
def test_agents_url_follows_the_wandb_app_host(
    environment: dict[str, str], expected: str, monkeypatch
) -> None:
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    assert agents_url("acme/agents") == expected


def test_agents_url_links_a_conversation() -> None:
    assert agents_url(" acme / agents ", "conversation 1") == (
        "https://wandb.ai/acme/agents/weave/agents/conversations/conversation%201"
    )


@pytest.mark.parametrize("project", ["", "acme", "acme/", "/agents", "acme/agents/extra"])
def test_agents_url_rejects_projects_the_forge_sdk_rejects(project: str) -> None:
    assert agents_url(project) is None
