# Acceptance suite

Use [CASES.md](CASES.md) for the generated catalogue and [EXTENDING.md](EXTENDING.md) for execution and extension instructions.
The registry contains 26 cases grouped by ordering, failure, selection, inheritance, and site.

```bash
./acceptance-suite.sh list --group ordering
./acceptance-suite.sh show seq-after-all
./acceptance-suite.sh run --set smoke --dry-run
./acceptance-suite.sh run --set smoke --maven /path/to/mvn
```

Run commands from the lab root. Add `--color always` to force terminal colors or `--color never` to disable them.
Automatic color respects redirected output, `NO_COLOR`, and `TERM=dumb`. JSON and generated Markdown never contain color codes.

## Evidence and results

Each run reserves a fresh directory under `acceptance-runs/` or the requested `--output-dir`.
Each case retains its generated inputs, command, Maven log, result JSON, and available output artifacts.
The run also retains a manifest, combined results, Maven version, provenance, comparison JSON, and offline HTML report.
Existing destinations cause rejection. Report regeneration does not rewrite raw case results.

Requirement states are `met`, `not_met`, `inconclusive`, `observation_only`, `undefined_policy`, and `not_run`.
A checked early-output counterexample remains unmet even when the harness assertions pass.
Successful aggregation requires concrete order, count, scope, and output checks. An unexpected successful exit alone is insufficient.
Unrelated build errors and corrupt evidence remain inconclusive.

Package timing, root selection expansion, and explicit child declarations remain observations.
Failure safety is separate from unresolved cleanup policy. Undefined policy does not count as met.
The real site case checks source aggregation and rendering. It does not establish a completed-child-site barrier.

```bash
./acceptance-suite.sh report --run-name step-1
./acceptance-suite.sh --report-only
python3 acceptance/report.py --results-dir acceptance-runs/step-1
```

The old flag-only commands and saved result formats remain supported.
The [extension guide](EXTENDING.md#preserve-saved-comparisons) describes reviewed fingerprint compatibility and its limits.
The [coverage index](../coverage.md) describes the current groups and their limits.
