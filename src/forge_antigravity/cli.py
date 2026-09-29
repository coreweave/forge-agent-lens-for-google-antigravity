from __future__ import annotations

import argparse
import netrc
import os
import shutil

# The installer runs agy with a fixed argument list and never enables a shell.
import subprocess  # nosec B404
import sys
from importlib.resources import as_file, files
from urllib.parse import urlparse

from forge_antigravity import __version__, hook
from forge_antigravity.links import agents_url

_EXECUTABLE = "forge-agent-lens-for-google-antigravity"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=_EXECUTABLE,
        description=(
            "Forge Agent Lens tracing for Google Antigravity. "
            "Without a command, runs the plugin's Stop hook on stdin."
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", metavar="command")
    commands.add_parser("install", help="install the Antigravity plugin and check trace settings")
    if parser.parse_args(argv).command == "install":
        return install()
    hook.main()
    return 0


def install() -> int:
    agy = shutil.which("agy")
    if agy is None:
        print(
            f"{_EXECUTABLE}: agy is not on PATH; install the Antigravity CLI first", file=sys.stderr
        )
        return 1
    with as_file(files("forge_antigravity") / "plugin") as plugin:
        command = [agy, "plugin", "install", str(plugin)]
        completed = subprocess.run(command, check=False)  # nosec B603
    if completed.returncode != 0:
        return completed.returncode

    print(f"Installed the Antigravity plugin ({_EXECUTABLE} {__version__}).")
    executable = shutil.which(_EXECUTABLE)
    _report(
        executable is not None,
        "Hook executable",
        executable or f"not on PATH: uv tool install {_EXECUTABLE}",
    )

    project = os.environ.get("FORGE_TRACE_PROJECT", "").strip()
    url = agents_url(project)
    if url:
        detail = project
    elif project:
        detail = f"{project!r} must be entity/project"
    else:
        detail = "not set: export FORGE_TRACE_PROJECT=entity/project"
    _report(url is not None, "FORGE_TRACE_PROJECT", detail)

    host = urlparse(os.environ.get("WANDB_BASE_URL", "https://api.wandb.ai")).netloc
    key_source = _api_key_source(host)
    _report(
        key_source is not None,
        "W&B API key",
        key_source or f"not found: set WANDB_API_KEY or add {host} to ~/.netrc",
    )

    if url:
        print(f"View traces: {url}")
    if executable is None or url is None or key_source is None:
        print("Antigravity reads these settings from the environment it starts in.")
    return 0


def _report(ok: bool, label: str, detail: str) -> None:
    print(f"{'✓' if ok else '✗'} {label:<20} {detail}")


def _api_key_source(host: str) -> str | None:
    # Mirrors the Forge SDK's lookup: WANDB_API_KEY, then the .netrc entry for the W&B host.
    if os.environ.get("WANDB_API_KEY"):
        return "WANDB_API_KEY"
    try:
        credentials = netrc.netrc().authenticators(host)
    except (OSError, netrc.NetrcParseError):
        return None
    return "~/.netrc" if credentials and credentials[2] else None
