# Contributing

- Specs under `docs/blueprint/` are normative; code follows them, never the reverse. A behaviour change to IGX/1 is a new spec version.
- Baseline directories under `isongraph-ext/src/isongraph_ext/baselines/<core_commit>/` are immutable once released.
- `vectors/**` and baseline files are byte-exact: read them as bytes; never let an editor rewrite line endings.
- Tests first (`pytest`), then implementation. CI must be green before a PR is merged.
