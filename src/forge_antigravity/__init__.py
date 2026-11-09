"""Forge Agent Lens integration for Google Antigravity."""

import json
from importlib.resources import files

__version__: str = json.loads(
    (files(__name__) / "plugin" / "plugin.json").read_text(encoding="utf-8")
)["version"]

__all__ = ["__version__"]
