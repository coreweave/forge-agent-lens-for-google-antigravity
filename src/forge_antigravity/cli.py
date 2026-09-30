from __future__ import annotations

import argparse
import json
import netrc
import os
import shlex
import shutil

# The installer runs agy with a fixed argument list and never enables a shell.
import subprocess  # nosec B404
import sys
import sysconfig
import tempfile
from importlib.metadata import distribution
from importlib.resources import files
from pathlib import Path
from urllib.parse import unquote, urlparse

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
    if sys.stdin is not None and sys.stdin.isatty():
        parser.error(
            "expected a Stop hook payload on stdin; "
            f"to set up the plugin, run: {_EXECUTABLE} install"
        )
    hook.main()
    return 0


def install() -> int:
    agy = shutil.which("agy")
    if agy is None:
        print(
            f"{_EXECUTABLE}: agy is not on PATH; install the Antigravity CLI first", file=sys.stderr
        )
        return 1
    hook_command = _hook_command()
    with tempfile.TemporaryDirectory() as plugin:
        _write_plugin(Path(plugin), shlex.join(hook_command))
        completed = subprocess.run([agy, "plugin", "install", plugin], check=False)  # nosec B603
    if completed.returncode != 0:
        return completed.returncode

    print(f"Installed the Antigravity plugin ({_EXECUTABLE} {__version__}).")
    runner = shutil.which(hook_command[0])
    _report(
        runner is not None,
        "Hook command",
        shlex.join(hook_command) if runner else f"{hook_command[0]} not on PATH: install uv",
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
    if runner is None or url is None or key_source is None:
        print("Antigravity reads these settings from the environment it starts in.")
    return 0


def _hook_command() -> list[str]:
    direct_url = distribution(_EXECUTABLE).read_text("direct_url.json")
    if direct_url is None:
        return ["uvx", f"{_EXECUTABLE}@{__version__}"]
    origin = json.loads(direct_url)
    if origin.get("dir_info", {}).get("editable"):
        # An editable install is a live checkout, so the hook runs its environment in place.
        return [str(Path(sysconfig.get_path("scripts")) / _EXECUTABLE)]
    # Any other local build may live in uvx's temporary cache, so the hook reruns its source.
    source: str = origin["url"]
    if vcs := origin.get("vcs_info"):
        source = f"{vcs['vcs']}+{source}@{vcs['commit_id']}"
    elif source.startswith("file://"):
        source = unquote(urlparse(source).path)
    return ["uvx", "--from", source, _EXECUTABLE]


def _write_plugin(destination: Path, command: str) -> None:
    source = files("forge_antigravity") / "plugin"
    manifest = source.joinpath("plugin.json").read_text(encoding="utf-8")
    (destination / "plugin.json").write_text(manifest, encoding="utf-8")
    hooks = json.loads(source.joinpath("hooks.json").read_text(encoding="utf-8"))
    for handler in hooks["forge-agentlens"]["Stop"]:
        handler["command"] = command
    (destination / "hooks.json").write_text(json.dumps(hooks, indent=2) + "\n", encoding="utf-8")


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
