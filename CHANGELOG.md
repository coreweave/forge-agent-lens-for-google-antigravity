# Changelog

All notable changes to this project are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `forge-agent-lens-for-google-antigravity install` registers the plugin
  bundled with the executable through `agy plugin install`, checks the hook
  executable, destination, and W&B API key, and prints the project's Agent Lens
  link. Pin a version with `uv tool install forge-agent-lens-for-google-antigravity==X.Y.Z`.
- `forge-agent-lens-for-google-antigravity --version`.
- The hook logs a link to the conversation after each exported turn, and logs
  a warning instead of exiting silently when `FORGE_TRACE_PROJECT` is unset.

### Changed

- The plugin files moved from `plugin/` into the Python package
  (`src/forge_antigravity/plugin/`) so the wheel ships them. Release archive
  contents are unchanged.

## [0.1.1] - 2026-09-29

### Changed

- Release plugin archives are named without the version, so the latest plugin
  is always at `releases/latest/download/forge-agent-lens-for-google-antigravity-plugin.zip`.
- The README installs the hook executable from PyPI and the plugin from the
  latest GitHub release.

## [0.1.0] - 2026-09-29

### Added

- An Antigravity plugin that exports each newly completed turn from the
  fully-idle `Stop` hook.
- Forge SDK spans for the root agent, LLM chat, tool executions, and delegated
  sub-agents, with one trace per turn and a shared Antigravity conversation ID.
- `forge.integration.*` provenance and Antigravity workspace, execution, and
  termination attributes alongside Forge's standard `gen_ai.*` attributes.
- Transcript stabilization, retry-safe SDK-flush checkpoints, environment-based
  content controls, and fail-open export behavior.
- A network-isolated local smoke example and unit, integration, privacy,
  packaging, and plugin tests.
- CI across Python 3.10 through 3.14 and tag-triggered publishing to PyPI and
  GitHub Releases.

### Changed

- Install the Forge SDK from PyPI (`coreweave==0.1.0b0`) instead of a Git checkout.

### Export boundary

- Prompt, response, reasoning, tool, and sub-agent delegation content is
  exported only when it is present in Antigravity's transcript.
- Token usage, exact model request settings, response IDs, and delegated
  sub-agent internals are not exposed by the transcript and are not synthesized.

[Unreleased]: https://github.com/coreweave/forge-agent-lens-for-google-antigravity/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/coreweave/forge-agent-lens-for-google-antigravity/releases/tag/v0.1.1
[0.1.0]: https://github.com/coreweave/forge-agent-lens-for-google-antigravity/releases/tag/v0.1.0
