from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

SETTINGS_DISPLAY_PATH = "~/.forge-agent-lens-for-google-antigravity/settings.json"
_PROJECT_VARIABLE = "FORGE_TRACE_PROJECT"
_CONTENT_VARIABLE = "FORGE_ANTIGRAVITY_INCLUDE_CONTENT"
_FALSE_VALUES = {"0", "false", "no", "off"}

Source = Literal["environment", "settings file", "default"]


@dataclass(frozen=True)
class Settings:
    project: str
    project_source: Source
    include_content: bool
    include_content_source: Source


def load_settings() -> Settings:
    saved = _read_saved()
    project = os.environ.get(_PROJECT_VARIABLE, "").strip()
    project_source: Source = "environment"
    if not project:
        project = _saved_project(saved)
        project_source = "settings file" if project else "default"

    content_value = os.environ.get(_CONTENT_VARIABLE, "").strip()
    if content_value:
        include_content = _parse_flag(content_value)
        include_content_source: Source = "environment"
    elif (saved_content := _saved_include_content(saved)) is not None:
        include_content = saved_content
        include_content_source = "settings file"
    else:
        include_content = True
        include_content_source = "default"
    return Settings(project, project_source, include_content, include_content_source)


def save_environment_settings() -> bool:
    updates: dict[str, Any] = {}
    if project := os.environ.get(_PROJECT_VARIABLE, "").strip():
        updates["project"] = project
    if content_value := os.environ.get(_CONTENT_VARIABLE, "").strip():
        updates["include_content"] = _parse_flag(content_value)
    if not updates:
        return False
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**_read_saved(), **updates}, indent=2) + "\n", encoding="utf-8")
    return True


def _settings_path() -> Path:
    return Path.home() / ".forge-agent-lens-for-google-antigravity" / "settings.json"


def _read_saved() -> dict[str, Any]:
    path = _settings_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        raise ValueError(f"could not read {SETTINGS_DISPLAY_PATH}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{SETTINGS_DISPLAY_PATH} must contain a JSON object")
    return value


def _saved_project(saved: dict[str, Any]) -> str:
    value = saved.get("project", "")
    if not isinstance(value, str):
        raise ValueError(f'"project" in {SETTINGS_DISPLAY_PATH} must be a string')
    return value.strip()


def _saved_include_content(saved: dict[str, Any]) -> bool | None:
    value = saved.get("include_content")
    if value is not None and not isinstance(value, bool):
        raise ValueError(f'"include_content" in {SETTINGS_DISPLAY_PATH} must be true or false')
    return value


def _parse_flag(value: str) -> bool:
    return value.lower() not in _FALSE_VALUES
