# Forge Agent Lens for Google Antigravity

[![CI](https://github.com/coreweave/forge-agent-lens-for-google-antigravity/actions/workflows/ci.yml/badge.svg)](https://github.com/coreweave/forge-agent-lens-for-google-antigravity/actions/workflows/ci.yml)

Forge Agent Lens tracing for the Google Antigravity™ coding harness. When an
agent turn becomes fully idle, the plugin translates its transcript into typed
Forge agent spans.

```text
Antigravity Stop hook + transcript
  -> Forge Turn, LLM, Tool, and SubAgent models
  -> Forge SDK OpenTelemetry exporter
  -> Agent Lens
```

This repository is only the Antigravity adapter. It has no Agent Lens client,
trace-query client, or transport implementation. The CoreWeave Forge SDK
(`coreweave==0.1.0b0`, installed from PyPI) owns W&B credential discovery,
endpoint selection, OpenTelemetry encoding, export, flushing, and shutdown.

The `forge-agent-lens-for-google-antigravity` executable is the plugin's Stop
hook: with no arguments it reads a hook payload on stdin. Its `install` command
sets up the plugin.

## Requirements

- macOS or Linux.
- Python 3.10 or newer.
- Antigravity CLI 1.1.10 or newer; the current release is recommended.
- A W&B API key and destination in `entity/project` form.
- [`uv`](https://docs.astral.sh/uv/) to install the hook executable.

See Google's official [hook reference](https://antigravity.google/docs/hooks),
[plugin documentation](https://antigravity.google/docs/plugins?tab=cli), and
[CLI repository](https://github.com/google-antigravity/antigravity-cli).

## Install

```bash
uv tool install forge-agent-lens-for-google-antigravity && forge-agent-lens-for-google-antigravity install
```

`install` registers the plugin bundled with the executable through
`agy plugin install`, then checks what the hook needs and prints where traces
will appear:

```text
Installed the Antigravity plugin (forge-agent-lens-for-google-antigravity X.Y.Z).
✓ Hook executable      /Users/you/.local/bin/forge-agent-lens-for-google-antigravity
✓ FORGE_TRACE_PROJECT  my-team/antigravity-traces
✓ W&B API key          WANDB_API_KEY
View traces: https://wandb.ai/my-team/antigravity-traces/weave/agents
```

The executable must be on `PATH` in the environment that launches Antigravity.
Set the destination there too. The Forge SDK reads `WANDB_API_KEY` directly or
resolves it from the W&B entry in `.netrc`.

```bash
export FORGE_TRACE_PROJECT=entity/project
export WANDB_API_KEY=...
agy
```

To install a specific version, pin it. This also switches an existing install
to that version:

```bash
uv tool install forge-agent-lens-for-google-antigravity==X.Y.Z && forge-agent-lens-for-google-antigravity install
```

`uv tool upgrade forge-agent-lens-for-google-antigravity` moves to the latest
release; an unpinned `uv tool install` keeps the installed version. Rerun
`install` after changing versions. Antigravity copies the plugin during
installation, and installing over an existing plugin replaces it.

`install` needs 0.1.2 or newer. With 0.1.0 or 0.1.1, install the plugin from
the latest release archive, which works with every version:

```bash
curl -fsSLO https://github.com/coreweave/forge-agent-lens-for-google-antigravity/releases/latest/download/forge-agent-lens-for-google-antigravity-plugin.zip
unzip -qo forge-agent-lens-for-google-antigravity-plugin.zip -d forge-agent-lens-plugin
agy plugin install forge-agent-lens-plugin
```

To try unreleased changes, run `uv tool install --reinstall .` in a checkout,
then `forge-agent-lens-for-google-antigravity install`.

## View traces

Traces appear in W&B under `https://wandb.ai/<entity>/<project>/weave/agents`,
where `entity/project` is `FORGE_TRACE_PROJECT`. For a dedicated or
self-managed instance, links follow `WANDB_BASE_URL`, or `WANDB_APP_URL` when
set. After each exported turn, the hook logs a link to that conversation:

```text
forge-agent-lens-for-google-antigravity: View traces: https://wandb.ai/my-team/antigravity-traces/weave/agents/conversations/<conversation-id>
```

Antigravity shows hook output neither in its terminal UI nor in `agy -p`
output. It writes the hook's stderr to its CLI logs, so conversation links,
export errors, and the warning logged when `FORGE_TRACE_PROJECT` is unset are
all there:

```bash
grep -h "JSON hook command stderr" ~/.gemini/antigravity-cli/log/cli-*.log | tail
```

## How export works

The plugin registers one observability-only `Stop` hook. It waits for
`fullyIdle=true`, reads the untruncated sibling `transcript_full.jsonl` when
available, and maps the completed turn through Forge SDK models:

| Antigravity record | Forge span |
|---|---|
| User request through fully-idle stop | `invoke_agent Antigravity` |
| `PLANNER_RESPONSE` | `chat <model>` |
| Tool request and following result | `execute_tool <tool>` |
| `invoke_subagent` request and result | nested `invoke_agent <subagent>` |

Forge emits one trace per turn and links those traces with the hook's
`conversationId`. User and assistant text, reasoning, tool names, arguments,
and results are preserved when present; step timestamps bound the spans. The
transcript does not currently expose token usage, exact model request settings
or response IDs, or a delegated subagent's internal LLM and tool activity, so
the adapter does not synthesize those fields. The delegation itself is still
exported as a nested subagent span.

Forge supplies the standard `gen_ai.*` fields from its typed models. The
adapter adds only integration provenance and Antigravity metadata without a
semantic-convention equivalent:

| Attribute | Value |
|---|---|
| `forge.integration.name` | `antigravity` |
| `forge.integration.version` | Installed adapter version |
| `forge.integration.antigravity.workspace.paths` | Hook `workspacePaths` |
| `forge.integration.antigravity.execution.number` | Stop-hook execution attempt |
| `forge.integration.antigravity.termination.reason` | Stop reason |

The adapter calls `tracing.init()`, `log_conversation()`, and the returned
session's `force_flush()` and `shutdown()`. Production code never constructs an
HTTP request or OpenTelemetry exporter.

The first observed stop exports only the newest turn, so installing the plugin
does not upload earlier conversation history. A small checkpoint under the
conversation's Antigravity artifact directory prevents duplicate export. Later
turns include history observed after installation. The checkpoint advances only
after the Forge SDK reports a successful flush; a failed export stays eligible
for retry.

## Configuration and privacy

| Variable | Owner | Purpose |
|---|---|---|
| `FORGE_TRACE_PROJECT` | adapter | Required destination in `entity/project` form |
| `FORGE_ANTIGRAVITY_INCLUDE_CONTENT` | adapter | Set to `false` to omit prompts, outputs, reasoning, and tool payloads |
| `WANDB_API_KEY` | Forge SDK | W&B authentication; `.netrc` is also supported |
| `WANDB_BASE_URL` | Forge SDK | W&B base URL for endpoint derivation |
| `WF_TRACE_SERVER_URL` | Forge SDK | Explicit trace-server override |
| `WANDB_APP_URL` | adapter | W&B app URL for trace links; derived from `WANDB_BASE_URL` by default |

Content capture defaults to enabled. For sensitive workspaces, set:

```bash
export FORGE_ANTIGRAVITY_INCLUDE_CONTENT=false
```

Workspace paths and Stop metadata remain queryable when content capture is
disabled.

Runtime export failures are fail-open: the entrypoint logs the error, returns a
neutral stop decision, and never extends the agent loop. The plugin registers
no tool or invocation hooks and does not alter permissions, prompts, or results.

## Validate

The example runs the installed hook entrypoint against a synthetic transcript
and an in-process OTLP receiver. It exercises the parser, Forge models, and the
real Forge SDK exporter without contacting an external service:

```bash
uv sync --locked --group test
uv run python examples/local_smoke_test.py
```

Run the release checks:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run coverage run -m pytest
uv run coverage report
uvx --from bandit==1.8.6 bandit -q -r src examples
AUDIT_SITE_PACKAGES="$(uv run python -c 'import site; print(site.getsitepackages()[0])')"
uvx --from pip-audit==2.9.0 pip-audit --path "$AUDIT_SITE_PACKAGES" --skip-editable
uvx --from zizmor==1.30.1 zizmor --pedantic .
uvx --from 'reuse[charset-normalizer]==6.2.0' reuse lint
uv build
uvx --from twine==7.0.0 twine check dist/*
agy plugin validate src/forge_antigravity/plugin
```

To test against a local Forge SDK checkout without changing the lockfile:

```bash
uv run --with-editable /path/to/forge-sdk/python pytest
```

CI runs Python 3.10 through 3.14, enforces branch coverage of at least 90%, and
validates release artifacts. See [CONTRIBUTING.md][contributing] and
[CHANGELOG.md][changelog].

## Contributing

See [CONTRIBUTING.md][contributing]. Contributions require agreeing to the
[CoreWeave CLA][cla]. Report vulnerabilities privately as described in
[SECURITY.md][security].

## License

Apache 2.0. See [LICENSE][license].

## Trademarks

Google Antigravity is a trademark of Google LLC. This project is not affiliated
with, sponsored by, or endorsed by Google.

[changelog]: https://github.com/coreweave/forge-agent-lens-for-google-antigravity/blob/main/CHANGELOG.md
[cla]: https://github.com/coreweave/forge-agent-lens-for-google-antigravity/blob/main/CLA.md
[contributing]: https://github.com/coreweave/forge-agent-lens-for-google-antigravity/blob/main/CONTRIBUTING.md
[license]: https://github.com/coreweave/forge-agent-lens-for-google-antigravity/blob/main/LICENSE
[security]: https://github.com/coreweave/forge-agent-lens-for-google-antigravity/blob/main/SECURITY.md
