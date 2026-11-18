---
name: agent-lens-setup
description: Verify, configure, or troubleshoot the CoreWeave Forge Agent Lens plugin, which sends each Antigravity turn to Agent Lens as a trace. Use when the user asks to check their Agent Lens setup, turn content capture on or off, or find out why traces are missing. Don't use for general coding, for adding tracing to the user's own application, or for W&B questions unrelated to this plugin.
---

# Agent Lens setup

After each agent turn, the plugin's Stop hook runs
`uvx forge-agent-lens-for-google-antigravity@<version>` and sends the turn to
Agent Lens. The hook reads its settings from environment variables first, then
from `~/.forge-agent-lens-for-google-antigravity/settings.json`:

| Setting | Environment variable | `settings.json` key |
|---|---|---|
| Agent Lens project, as `entity/project` | `FORGE_TRACE_PROJECT` | `project` |
| Content capture, on by default | `FORGE_ANTIGRAVITY_INCLUDE_CONTENT` | `include_content` (`true` or `false`) |

The W&B API key comes from `WANDB_API_KEY` or the W&B host's entry in
`~/.netrc`. Never read, print, or write the API key yourself, and never put it
in `settings.json`.

## Verify the setup

Run:

```bash
uvx forge-agent-lens-for-google-antigravity@latest status
```

Explain each line that starts with ✗:

- `uvx`: the user needs to install uv from
  https://docs.astral.sh/uv/getting-started/installation/.
- `Project`: offer to write the project to `settings.json`. Ask the user for
  the `entity/project` value.
- `W&B API key`: ask the user to run `uvx wandb login` in their own terminal,
  which saves the key to `~/.netrc`.
- `Settings file`: the file isn't valid JSON or has a value of the wrong type.
  Show the user the problem and offer to fix it.

If every line starts with ✓, tell the user to finish a turn and open the
`View traces` link from the output.

## Change content capture

Edit `settings.json` and keep its other keys. Create the file and its
directory if they don't exist. Set `"include_content": false` to send only
names and timing, or `true` to also send prompts, responses, reasoning, and
tool arguments and results. Then run `status` again: if the `Content capture`
line doesn't show the new value, `FORGE_ANTIGRAVITY_INCLUDE_CONTENT` is set in
the environment and overrides the file. The change applies from the next turn.

## Troubleshoot missing traces

1. Run `status` and fix any ✗ lines.
2. Read the hook's recent messages from the Antigravity CLI logs:

   ```bash
   grep -h "forge-agent-lens-for-google-antigravity:" ~/.gemini/antigravity-cli/log/cli-*.log | tail
   ```

   - `View traces: <url>`: the turn was exported. Give the user the link.
   - `FORGE_TRACE_PROJECT is not set and … has no project`: set the project.
   - `trace export failed: …`: the rest of the line names the error, such as
     a rejected API key or a project the user can't access.
   - No messages: the hook isn't running. Check that the plugin is enabled and
     that `uvx` is on the `PATH` Antigravity starts with.
3. The first time the plugin sees an existing conversation, it sends only the
   latest turn, so earlier turns are missing on purpose.
