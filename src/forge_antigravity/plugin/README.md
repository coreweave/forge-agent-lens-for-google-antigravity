# CoreWeave Forge Agent Lens

Sends each Antigravity agent turn to
[CoreWeave Agent Lens](https://docs.coreweave.com/products/agent-lens/what-is-agent-lens)
as a trace, with its model calls, tool calls, and subagents.

> [!WARNING]
> **What this plugin sends.** While the plugin is enabled, a Stop hook runs
> after every agent turn in every workspace. By default it sends your prompts,
> the agent's responses and reasoning, and tool arguments and results,
> including anything a tool prints, to Agent Lens. It doesn't remove secrets
> or personal data. To send only names and timing, turn off content capture
> (see [Content capture](#content-capture)), or disable the plugin before you
> work in sensitive workspaces.

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/). The hook runs
  through `uvx`, which must be on the `PATH` that Antigravity starts with.
- A [W&B API key](https://forge.coreweave.com/wandb/authorize) and an Agent
  Lens project in `entity/project` form.

## Set up

1. Save your API key to `~/.netrc` by running `uvx wandb login`. The hook also
   reads `WANDB_API_KEY`, but only when Antigravity is started from a shell
   that exports it.
2. Create `~/.forge-agent-lens-for-google-antigravity/settings.json` with your
   project:

   ```json
   {
     "project": "my-team/antigravity-traces",
     "include_content": true
   }
   ```

   The environment variables `FORGE_TRACE_PROJECT` and
   `FORGE_ANTIGRAVITY_INCLUDE_CONTENT` override these settings. The file
   matters when you start the Antigravity app from the Dock or Start menu,
   because then the app doesn't see variables exported in your shell profile.
3. Check the setup:

   ```bash
   uvx forge-agent-lens-for-google-antigravity@latest status
   ```

   Every line should start with ✓. The output ends with your project's Agent
   Lens link.
4. Finish an agent turn, then open the link to see it as a trace.

You can also ask the agent to *verify my CoreWeave Agent Lens setup*. The
plugin's setup skill runs the check above and explains anything that's
missing.

## Content capture

To leave out prompts, responses, reasoning, and tool arguments and results,
set `"include_content": false` in `settings.json`, or set
`FORGE_ANTIGRAVITY_INCLUDE_CONTENT=false`. Spans still record model, tool, and
subagent names, subagent roles, timing, and workspace paths.

The content of a turn exported while content capture is off isn't exported
later. If you turn capture back on in the same conversation, the message
history on later model calls starts after that turn.

## Troubleshooting

The hook writes its messages, including export errors and a link to each
exported conversation, to stderr, which the Antigravity CLI saves to its logs:

```bash
grep -h "forge-agent-lens-for-google-antigravity:" ~/.gemini/antigravity-cli/log/cli-*.log | tail
```

| Message or symptom | What to do |
|---|---|
| `FORGE_TRACE_PROJECT is not set and … has no project` | Add `project` to `settings.json`. |
| `trace export failed: …` | The rest of the line names the error. Check the API key and your access to the project. |
| No messages from the plugin | Check that the plugin is enabled and that `uvx` is on the `PATH` Antigravity starts with. |

The first time the plugin sees an existing conversation, it sends only the
latest turn.

## More information

- [Full documentation](https://github.com/coreweave/forge-agent-lens-for-google-antigravity#readme)
- [Changelog](https://github.com/coreweave/forge-agent-lens-for-google-antigravity/blob/main/CHANGELOG.md)
- [Report a problem](https://github.com/coreweave/forge-agent-lens-for-google-antigravity/issues)
- [Security policy](https://github.com/coreweave/forge-agent-lens-for-google-antigravity/blob/main/SECURITY.md)
- License: [Apache 2.0](https://github.com/coreweave/forge-agent-lens-for-google-antigravity/blob/main/LICENSE)

CoreWeave and the CoreWeave logo are trademarks of CoreWeave, Inc. Google
Antigravity is a trademark of Google LLC. This project is not affiliated with,
sponsored by, or endorsed by Google.
