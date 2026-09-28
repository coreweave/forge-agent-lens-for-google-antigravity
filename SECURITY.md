# Security

## Reporting a vulnerability

Report suspected vulnerabilities in Forge Agent Lens for Google Antigravity
privately through GitHub's private vulnerability reporting on this repository
("Security" → "Report a vulnerability"). Please don't open a public issue or
pull request for a security problem.

## Scope

Forge Agent Lens for Google Antigravity is a local Antigravity plugin. Its
`Stop` hook runs on your machine, reads the conversation transcript, and
exports the completed turn through the CoreWeave Forge SDK using your W&B
credentials. Reports about the hook's handling of hook input, transcript
content, the content-capture setting, or export checkpoints are in scope.

The CoreWeave Forge SDK, Google Antigravity, and the W&B service are separate
projects with their own reporting channels.

## Known operating constraints

- Content capture is on by default. Prompts, responses, reasoning, and tool
  arguments and results, including anything a tool prints, are exported unless
  `FORGE_ANTIGRAVITY_INCLUDE_CONTENT=false` is set.
- Workspace paths and Stop metadata are exported even when content capture is
  disabled.
- Export checkpoints store transcript step indexes, not transcript content.
