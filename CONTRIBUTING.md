# Contributing

- Specs under `docs/blueprint/` are normative; code follows them, never the reverse. A behaviour change to IGX/1 is a new spec version.
- Baseline directories under `isongraph-ext/src/isongraph_ext/baselines/<core_commit>/` are immutable once released.
- `vectors/**` and baseline files are byte-exact: read them as bytes; never let an editor rewrite line endings.
- Tests first (`pytest`), then implementation. CI must be green before a PR is merged.

## Releasing

Publishing uses PyPI Trusted Publishing (GitHub OIDC): no tokens are stored. The publisher registered on pypi.org and test.pypi.org names owner `ISON-format`, repository `isongraph-ext`, workflow `publish-pypi.yml`, and the GitHub environment `pypi` / `testpypi` respectively. The `pypi` environment requires manual approval by a designated reviewer and accepts only `v*` tags.

1. Set the version in `isongraph-ext/pyproject.toml` and `src/isongraph_ext/__init__.py`, add the CHANGELOG entry, merge to `main` with CI green.
2. Tag the merge commit `vX.Y.Z` and push the tag. The workflow refuses a tag that does not equal `v` + the package version, or a tagged commit that is not on `main`.
3. Rehearse: run **Publish Python package** (`workflow_dispatch`, `ref = vX.Y.Z`, `target = testpypi`), install from TestPyPI in a fresh environment and run the examples.
4. Publish a GitHub release (a pre-release while the project is alpha) for the tag. The workflow builds, then waits for approval of the `pypi` deployment.
5. After approval, verify the PyPI page and install the published version in a fresh environment. A bad release is yanked on PyPI and fixed forward as the next patch version.
