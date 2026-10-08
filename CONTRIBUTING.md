# Contributing to Forge Agent Lens for Google Antigravity

## Set up a development checkout

Use Python 3.10 or newer and install the locked test environment:

```bash
git clone https://github.com/coreweave/forge-agent-lens-for-google-antigravity.git
cd forge-agent-lens-for-google-antigravity
uv sync --locked --group test
```

The Forge SDK is installed from PyPI as `coreweave==0.1.0b0`, pinned in
`pyproject.toml` and `uv.lock`. To test a local Forge SDK checkout without
changing either file:

```bash
uv run --with-editable /path/to/forge-sdk/python pytest
```

## Make and validate a change

Keep hook processing fail-open and observability-only. Any new transcript shape
or lifecycle behavior needs a fixture or focused regression test.

Before opening a pull request, run:

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
uv run python examples/local_smoke_test.py
```

Coverage must remain at or above 90% with branch measurement enabled. Tests
must not depend on a developer's W&B credentials, configuration, home directory,
or external network services. The local smoke example exercises the real Forge
SDK exporter against an in-process OTLP receiver.

## Test a change in Antigravity

`install` points the hook at the build that ran it. Run from a checkout, it
registers this checkout's `.venv` executable, so Python edits take effect at the
next Stop hook. Rerun `install` after editing the plugin files, because
Antigravity copies them.

```bash
uv run forge-agent-lens-for-google-antigravity install
```

To test a built wheel or a pushed branch, run the installer from it. The hook
reruns the same source through `uvx`, and a git source stays pinned to the
commit it resolved to:

```bash
uvx --from dist/forge_agent_lens_for_google_antigravity-X.Y.Z-py3-none-any.whl forge-agent-lens-for-google-antigravity install
uvx --from git+https://github.com/coreweave/forge-agent-lens-for-google-antigravity@<branch> forge-agent-lens-for-google-antigravity install
```

Avoid `uvx --from .` for a checkout you're editing: uv caches that build and
doesn't rebuild it when Python files change.

Released build: run the installer from PyPI with `@latest` or a pinned version.

```bash
uvx forge-agent-lens-for-google-antigravity@latest install
```

## Pull requests

Use Conventional Commit titles, such as `fix: retry failed SDK flushes`, for
pull requests and commits. release-please writes the changelog from them, so
don't edit `CHANGELOG.md` by hand. Call out privacy or compatibility changes in
the pull request description, and update the README when user-visible behavior
changes. Do not commit generated build artifacts or local configuration.

## Contributor License Agreement

Contributors must agree to the [CoreWeave CLA](./CLA.md) when pushing code to this project.

Agreement with the CoreWeave CLA must be signified by including a `Signed-off-by`
trailer in every submitted Git commit to this repository. By signing off, you certify that you have the right to submit the contribution and that you agree to and are bound by the CoreWeave Contributor License Agreement in effect at the date of your submission, found in [`CLA.md`](./CLA.md) in the root of this repository, which governs your submission. If you are contributing on behalf of an entity, you further certify that you are authorized to bind that entity to the CLA.

Sign each commit with the `--signoff` (`-s`) option to [`git commit`](https://git-scm.com/docs/git-commit#Documentation/git-commit.txt---signoff). Git has no configuration option that adds the trailer automatically; if you want it on every commit, use an alias such as `git config alias.ci "commit -s"` or a `prepare-commit-msg` hook.

## Licensing

This project is licensed under Apache-2.0 (see [`LICENSE`](./LICENSE)) and follows the [REUSE](https://reuse.software/) specification. REUSE requires the license text in [`LICENSES/Apache-2.0.txt`](./LICENSES/Apache-2.0.txt). Licensing metadata lives in [`REUSE.toml`](./REUSE.toml): its aggregate annotation covers every file by default, so new files need no SPDX header. If you add material under a different license or copyright, declare it with an inline SPDX header or a `REUSE.toml` annotation and include any additional license text in `LICENSES/<SPDX-License-Identifier>.txt`. Run `reuse lint` from the repository root before opening a PR.

## Releases

release-please keeps a release PR open that bumps the version and changelog
from the Conventional Commits on `main`. The version changes in
`pyproject.toml`, `src/forge_antigravity/__init__.py`, and `uv.lock`. Merging
the PR tags `vX.Y.Z`, creates the GitHub release, and runs the release
workflow. That workflow reruns the checks, publishes the wheel and sdist to
PyPI through trusted publishing, and attaches them to the GitHub release with
the plugin archives and SHA-256 checksums. To choose the version, add a
`Release-As: X.Y.Z` footer to a commit.

If the release workflow fails on a transient error, rerun only the failed jobs:
find the run ID with `gh run list --workflow release.yml`, then run
`gh run rerun <run-id> --failed`. Rerunning a job that already published fails,
because PyPI rejects a version it already has. If it fails because of a bug,
fix it in a pull request to `main` and release the next version.

Never reuse or move an existing release tag.
