# Changelog

All notable changes to this project are documented here. The project follows
[Semantic Versioning](https://semver.org/).

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

[0.1.1]: https://github.com/coreweave/forge-agent-lens-for-google-antigravity/releases/tag/v0.1.1
[0.1.0]: https://github.com/coreweave/forge-agent-lens-for-google-antigravity/releases/tag/v0.1.0
