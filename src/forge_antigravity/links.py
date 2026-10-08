from __future__ import annotations

import os
from urllib.parse import quote


def agents_url(project: str, conversation_id: str = "") -> str | None:
    entity, separator, name = project.partition("/")
    entity, name = entity.strip(), name.strip()
    if separator != "/" or not entity or not name or "/" in name:
        return None
    url = f"{_app_url()}/{quote(entity, safe='')}/{quote(name, safe='')}/weave/agents"
    if conversation_id:
        url += f"/conversations/{quote(conversation_id, safe='')}"
    return url


def _app_url() -> str:
    # Same API-to-app host mapping as wandb.util.app_url.
    if app_url := os.environ.get("WANDB_APP_URL", "").strip("/"):
        return app_url
    api_url = (os.environ.get("WANDB_BASE_URL") or "https://api.wandb.ai").rstrip("/")
    if api_url == "https://api.wandb.ai":
        return "https://forge.coreweave.com/wandb"
    if "://api.wandb." in api_url and "://api.wandb.test" not in api_url:
        return api_url.replace("://api.", "://")
    return api_url.replace("://api.", "://app.")
