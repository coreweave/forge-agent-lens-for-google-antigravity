# Forge Agent Lens for Google Antigravity

[![PyPI version](https://img.shields.io/pypi/v/forge-agent-lens-for-google-antigravity.svg)](https://pypi.org/project/forge-agent-lens-for-google-antigravity/)
[![CI](https://github.com/coreweave/forge-agent-lens-for-google-antigravity/actions/workflows/ci.yml/badge.svg)](https://github.com/coreweave/forge-agent-lens-for-google-antigravity/actions/workflows/ci.yml)
[![license](https://img.shields.io/pypi/l/forge-agent-lens-for-google-antigravity.svg)](https://github.com/coreweave/forge-agent-lens-for-google-antigravity/blob/main/LICENSE)
[![python](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fcoreweave%2Fforge-agent-lens-for-google-antigravity%2Fmain%2Fpyproject.toml)](https://github.com/coreweave/forge-agent-lens-for-google-antigravity/blob/main/pyproject.toml)

[CoreWeave Forge Agent Lens](https://docs.coreweave.com/products/agent-lens/what-is-agent-lens)
plugin for Google Antigravity™ that traces agent turns, model calls, tool
calls, and subagents.

When a turn finishes, the plugin's [Stop hook](https://antigravity.google/docs/hooks)
reads the conversation transcript and sends the turn to Agent Lens as one trace. Turns from the same Antigravity
conversation share a conversation ID, so Agent Lens shows them as one
conversation.

> [!WARNING]
> Content capture is on by default. Prompts, responses, reasoning, and tool
> arguments and results, including anything a tool prints, are sent to Agent
> Lens. Set `FORGE_ANTIGRAVITY_INCLUDE_CONTENT=false` to leave them out.

## Requirements

- macOS or Linux
- [Antigravity CLI](https://github.com/google-antigravity/antigravity-cli)
  1.1.10 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/), whose `uvx`
  command runs the hook
- Python 3.10 or newer
- A [W&B API key](https://forge.coreweave.com/wandb/authorize) and an Agent
  Lens project in `entity/project` form

## Install

Set your project and API key, then run the installer:

```bash
export FORGE_TRACE_PROJECT=<entity>/<project>
export WANDB_API_KEY=<your-api-key>
uvx forge-agent-lens-for-google-antigravity@latest install
```

`install` registers the plugin with `agy plugin install`, checks the settings
the hook needs, and prints where traces will appear:

```text
Installed the Antigravity plugin (forge-agent-lens-for-google-antigravity X.Y.Z).
✓ Hook command         uvx forge-agent-lens-for-google-antigravity@X.Y.Z
✓ FORGE_TRACE_PROJECT  my-team/antigravity-traces
✓ W&B API key          WANDB_API_KEY
View traces: https://wandb.ai/my-team/antigravity-traces/weave/agents
```

The hook runs with the environment that `agy` was started in, so set
`FORGE_TRACE_PROJECT` and the API key in your shell profile, or wherever you
start `agy`, and make sure `uvx` is on that `PATH`. Instead of
`WANDB_API_KEY`, the hook can read the key from the W&B host's entry in
`~/.netrc`.

Then start a new `agy` session. Each finished turn appears in Agent Lens.

## View traces

`install` prints your project's Agent Lens link. After each exported turn, the
hook also logs a link to that conversation:

```text
forge-agent-lens-for-google-antigravity: View traces: https://wandb.ai/my-team/antigravity-traces/weave/agents/conversations/<conversation-id>
```

Antigravity doesn't show hook output in its terminal UI or in `agy -p` output.
It writes the hook's messages, including these links and any export errors, to
its CLI logs:

```bash
grep -h "forge-agent-lens-for-google-antigravity:" ~/.gemini/antigravity-cli/log/cli-*.log | tail
```

On Dedicated Cloud or self-managed W&B, links use the app URL derived from
`WANDB_BASE_URL`, or `WANDB_APP_URL` if you set it.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `FORGE_TRACE_PROJECT` | required | Agent Lens project, as `entity/project` |
| `WANDB_API_KEY` | `~/.netrc` entry | W&B API key |
| `FORGE_ANTIGRAVITY_INCLUDE_CONTENT` | `true` | Set to `false` to leave out prompts, responses, reasoning, and tool arguments and results |
| `WANDB_BASE_URL` | `https://api.wandb.ai` | W&B API URL, for Dedicated Cloud or self-managed instances |
| `WANDB_APP_URL` | derived from `WANDB_BASE_URL` | W&B app URL used in trace links |
| `WF_TRACE_SERVER_URL` | derived from `WANDB_BASE_URL` | Overrides the trace server URL |

### Content capture

With `FORGE_ANTIGRAVITY_INCLUDE_CONTENT=false`, spans still include model,
tool, and subagent names, subagent roles, timing, workspace paths, and the Stop
hook's execution number and termination reason. The Forge SDK also adds your
OS and Python versions to every span. The plugin doesn't remove secrets or
personal data from captured content.

## What gets traced

Each turn becomes one trace:

```text
invoke_agent Antigravity     the turn, from your request until the agent stops
├─ chat <model>              each model response
├─ execute_tool <tool>       each tool call and its result
└─ invoke_agent <subagent>   each subagent started by invoke_subagent
```

Spans use the standard OpenTelemetry GenAI (`gen_ai.*`) attributes and are
timed from the transcript's step timestamps. Conversations are named after the
first workspace folder. Every span also carries:

| Attribute | Value |
|---|---|
| `forge.integration.name` | `antigravity` |
| `forge.integration.version` | Plugin version |
| `forge.integration.antigravity.workspace.paths` | Workspace paths from the hook |
| `forge.integration.antigravity.execution.number` | Stop hook execution number |
| `forge.integration.antigravity.termination.reason` | Why the agent stopped |

The plugin uses the [CoreWeave Forge SDK](https://pypi.org/project/coreweave/)
(`coreweave`, pinned to the `0.1.0b0` prerelease) for authentication and
export. The OTLP resource reports
`service.name = forge-agent-lens-for-google-antigravity` and
`wandb.sdk.name = forge`.

### When turns are exported

The first time the hook sees a conversation, it exports only the latest turn,
so earlier history isn't uploaded, not even as context for later model calls.
A checkpoint in the conversation's directory,
`~/.gemini/antigravity-cli/brain/<conversation-id>/.forge-antigravity/state.json`,
records which steps were exported (step numbers only, no content), so no turn
is exported twice.

If an export fails, the hook logs the error and lets the turn end normally. The
checkpoint doesn't advance, so the turn is retried the next time the agent
stops. The plugin registers only a Stop hook, and it never changes prompts,
permissions, or tool results.

### Limitations

- Antigravity's transcript doesn't record token usage, model request settings,
  or response IDs, so traces have no token counts or costs.
- A subagent appears as one `invoke_agent` span with its prompt and result.
  Its own model and tool calls aren't in the parent conversation's transcript,
  so they don't appear under that span.

## Troubleshooting

Find the hook's messages with the `grep` command under View traces.

| Problem | What to check |
|---|---|
| `install` shows `✗ Hook command` | Install [uv](https://docs.astral.sh/uv/getting-started/installation/) so that `uvx` is on `PATH`. |
| The log says `FORGE_TRACE_PROJECT is not set` | Set it where you start `agy`, then start a new session. |
| The log says `trace export failed` | The rest of the line names the error. Check the API key, your access to the project, and `WANDB_BASE_URL` on Dedicated Cloud or self-managed instances. |
| No log lines from the plugin | Run `agy plugin list` to check that the plugin is installed, and check that `uvx` is on the `PATH` that `agy` starts with. |

## Manage the plugin

Rerun the install command to upgrade; it replaces the installed plugin. To pin
a version, or switch to one, install from that version:

```bash
uvx forge-agent-lens-for-google-antigravity@X.Y.Z install
```

Disable, re-enable, or remove the plugin with
[`agy plugin`](https://antigravity.google/docs/plugins?tab=cli):

```bash
agy plugin disable forge-agent-lens-for-google-antigravity
agy plugin enable forge-agent-lens-for-google-antigravity
agy plugin uninstall forge-agent-lens-for-google-antigravity
```

If you set up 0.1.0 or 0.1.1 with `uv tool install`, upgrading leaves that
executable unused. Remove it with
`uv tool uninstall forge-agent-lens-for-google-antigravity`.

See the [changelog][changelog] for what changed in each release.

## Development

```bash
git clone https://github.com/coreweave/forge-agent-lens-for-google-antigravity.git
cd forge-agent-lens-for-google-antigravity
uv sync --locked --group test
uv run pytest
uv run python examples/local_smoke_test.py
```

The smoke test runs the hook against a sample transcript and an in-process
OTLP receiver, without contacting any external service. See
[CONTRIBUTING.md][contributing] for the full set of checks and for
[testing a change in Antigravity][test-in-antigravity].

## Contributing

See [CONTRIBUTING.md][contributing]. Contributions require agreeing to the
[CoreWeave CLA][cla]. Report vulnerabilities privately as described in
[SECURITY.md][security].

## License

[Apache License 2.0][license]

## Trademarks

Google Antigravity is a trademark of Google LLC. This project is not affiliated
with, sponsored by, or endorsed by Google.

[changelog]: https://github.com/coreweave/forge-agent-lens-for-google-antigravity/blob/main/CHANGELOG.md
[cla]: https://github.com/coreweave/forge-agent-lens-for-google-antigravity/blob/main/CLA.md
[contributing]: https://github.com/coreweave/forge-agent-lens-for-google-antigravity/blob/main/CONTRIBUTING.md
[license]: https://github.com/coreweave/forge-agent-lens-for-google-antigravity/blob/main/LICENSE
[security]: https://github.com/coreweave/forge-agent-lens-for-google-antigravity/blob/main/SECURITY.md
[test-in-antigravity]: https://github.com/coreweave/forge-agent-lens-for-google-antigravity/blob/main/CONTRIBUTING.md#test-a-change-in-antigravity
