# Maven Aggregator Acceptance Lab

Measure Maven aggregation requirements with 25 bounded cases. Compare saved runs to track improvements, regressions, and remaining gaps.

## Start here

Use Bash, Python 3, JDK 17 or later, and a Maven 4.1.x or 4.2.x executable.
Run these commands from this directory:

```bash
./acceptance-suite.sh list
./acceptance-suite.sh list --group ordering
./acceptance-suite.sh show seq-after-all
./acceptance-suite.sh run --set smoke --dry-run
./acceptance-suite.sh run --set smoke --maven /path/to/mvn
```

`--maven` selects the executable. Its default is `MAVEN4`, then `mvn` from `PATH`.
The suite builds a private copy of the teaching plugin and generates fresh case inputs.
Public dependencies can download. Set `DEMO_MAVEN_SETTINGS` if your network requires custom Maven settings.

## Terminal colors

Colors appear automatically in a terminal. Redirected output stays plain.
JSON and generated Markdown stay plain, even with `--color always`.

```bash
./acceptance-suite.sh run --set smoke --color always --maven /path/to/mvn
./acceptance-suite.sh list --color never
NO_COLOR=1 ./acceptance-suite.sh list
```

| Output | Color |
|---|---|
| Requirement met | Green |
| Requirement not met or harness failure | Red |
| Inconclusive result or undefined policy | Yellow |
| Observation or section label | Cyan |
| Case not run | Grey |

`--color auto` respects `NO_COLOR` and `TERM=dumb`. Explicit `always` and `never` override automatic detection.
Text labels remain visible without color. A passing harness check can still report an unmet requirement.

## Save and compare runs

```bash
./acceptance-suite.sh run --maven /path/to/baseline/mvn --run-name baseline --set smoke
./acceptance-suite.sh run --maven /path/to/prototype/mvn --run-name step-1 \
  --compare-to acceptance-runs/baseline --set smoke
./acceptance-suite.sh report --run-name step-1
```

Open `acceptance-runs/step-1/report.html`. The report works offline.
Every run reserves a fresh directory. Existing destinations cause rejection.
Without `--run-name`, the runner creates a unique name. `--output-dir` selects an exact new destination.
The latest run pointer is `acceptance-runs/latest.json`.

Requirement states are `met`, `not_met`, `inconclusive`, `observation_only`, `undefined_policy`, and `not_run`.
Partial runs do not imply that unrun cases passed or regressed. Unknown errors remain inconclusive.
Checked gaps return zero by default. Preparation and case errors return one.
`--require-all` returns two when a selected requirement is not met. Argument and rejected preflight configuration errors also return two.
A Maven version string does not establish patch inclusion. Different source revisions can explain comparison differences.

## Cases, extension, and verification

- [Case reference](acceptance/CASES.md): all registered cases, grouped by subject.
- [Extension guide](acceptance/EXTENDING.md): case definitions, module responsibilities, commands, and fingerprint compatibility.
- [Acceptance guide](acceptance/README.md): evidence, states, and limits.
- [Requirement coverage](coverage.md): current groups and bounded requirements.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s acceptance -p 'test_*.py' -v
```

The existing flag-only commands remain valid, including `--list`, `--case`, and `--report-only`.
The repository includes 25 cases and reviewed compatibility records. Generated runs remain local under ignored `acceptance-runs/`.

## Repository layout

```text
acceptance-suite.sh     Suite entry point
acceptance/            Cases, fixtures, assessment, runner, reports, and tests
demo-plugin/           Teaching plugin source used by the suite
demo-settings.xml      Credential-free default settings
acceptance-runs/       Ignored saved evidence and offline reports
```

The suite uses isolated run directories. The repository is independent of earlier local experiments.
All source files use the [Apache License 2.0](LICENSE).
