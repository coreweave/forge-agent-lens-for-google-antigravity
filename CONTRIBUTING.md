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
agy plugin validate plugin
uv run python examples/local_smoke_test.py
```

Coverage must remain at or above 90% with branch measurement enabled. Tests
must not depend on a developer's W&B credentials, configuration, home directory,
or external network services. The local smoke example exercises the real Forge
SDK exporter against an in-process OTLP receiver.

## Pull requests

Use a Conventional Commit title such as `fix: retry failed SDK flushes`.
Call out privacy or compatibility changes in the pull request description, and
update the README and changelog when user-visible behavior changes. Do not
commit generated build artifacts or local configuration.

## Contributor License Agreement

Contributors must agree to the [CoreWeave CLA](./CLA.md) when pushing code to this project.

Agreement with the CoreWeave CLA must be signified by including a `Signed-off-by`
trailer in every submitted Git commit to this repository. By signing off, you certify that you have the right to submit the contribution and that you agree to and are bound by the CoreWeave Contributor License Agreement in effect at the date of your submission, found in [`CLA.md`](./CLA.md) in the root of this repository, which governs your submission. If you are contributing on behalf of an entity, you further certify that you are authorized to bind that entity to the CLA.

Sign each commit with the `--signoff` (`-s`) option to [`git commit`](https://git-scm.com/docs/git-commit#Documentation/git-commit.txt---signoff). Git has no configuration option that adds the trailer automatically; if you want it on every commit, use an alias such as `git config alias.ci "commit -s"` or a `prepare-commit-msg` hook.

## Licensing

This project is licensed under Apache-2.0 (see [`LICENSE`](./LICENSE)) and follows the [REUSE](https://reuse.software/) specification. REUSE requires the license text in [`LICENSES/Apache-2.0.txt`](./LICENSES/Apache-2.0.txt). Licensing metadata lives in [`REUSE.toml`](./REUSE.toml): its aggregate annotation covers every file by default, so new files need no SPDX header. If you add material under a different license or copyright, declare it with an inline SPDX header or a `REUSE.toml` annotation and include any additional license text in `LICENSES/<SPDX-License-Identifier>.txt`. Run `reuse lint` from the repository root before opening a PR.

## Releases

1. Update `CHANGELOG.md` and both version declarations in `pyproject.toml` and
   `src/forge_antigravity/__init__.py`.
2. Run the full local validation list above.
3. Merge the release commit to `main` and create an annotated `v<version>` tag.
4. Push the tag. The release workflow verifies the version, reruns checks,
   builds Python and plugin artifacts, generates SHA-256 checksums, publishes
   the wheel and sdist to PyPI through trusted publishing, and then creates the
   GitHub release.

Never reuse or move an existing release tag.
