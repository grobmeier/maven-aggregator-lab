# Maven Aggregator Acceptance Lab

Run 26 aggregation cases and compare saved results.
Requires Bash, Python 3, JDK 17+, and Maven 4.1.x or 4.2.x.

## Interactive launcher

```bash
./run.sh
```

Use arrow keys and Enter to select Maven, cases, comparison, label, exit policy, and colors.
Browse folders or paste a path. Left opens the parent. Right opens a child.
Use **Show hidden folders** for paths such as `.sdkman`.
Select **Run**, **Preview commands only**, **Edit selections**, or **Cancel** before execution.
After a run, the launcher opens its HTML report in your default browser. Previews do not open reports.
Esc returns to the home menu. Ctrl+C exits. Python needs `curses`. No `sudo` needed.

The launcher remembers ten configurations. **Forget saved selections** preserves run evidence.
Preferences: `$XDG_STATE_HOME/maven-aggregator-lab/interactive.json`, defaulting to `~/.local/state/maven-aggregator-lab/interactive.json`.
Override the directory with `MAVEN_LAB_STATE_DIR`.
Arguments bypass menus: `./run.sh list`.

## Commands

```bash
./acceptance-suite.sh list --group ordering
./acceptance-suite.sh show seq-after-all
./acceptance-suite.sh run --set smoke --dry-run
./acceptance-suite.sh run --set smoke --maven /path/to/bin/mvn
```

`--maven` defaults to `MAVEN4`, then `mvn` from `PATH`.
Each run builds a private teaching plugin and fresh fixtures. Dependencies can download.
Set `DEMO_MAVEN_SETTINGS` for custom settings. Otherwise, the suite uses credential-free defaults.

Colors default to automatic. Use `--color always|never|auto`.
Automatic color respects redirection, `NO_COLOR`, and `TERM=dumb`. JSON, Markdown, and saved logs stay plain.
Green means met, red means unmet or failed, yellow means inconclusive or undefined, and grey means unrun.

## Run from Maven source

Select a local checkout and revision in the launcher, or use:

```bash
./acceptance-suite.sh run --maven-source /path/to/maven \
  --maven-ref my-branch --bootstrap-maven /path/to/bootstrap/bin/mvn \
  --set smoke
```

The suite resolves the revision to a full commit ID and builds an exported tree in the run directory.
It excludes uncommitted edits and preserves the checkout and index. It does not fetch or push.
Source revisions must declare Maven 4.1.x or 4.2.x. Their JDK and bootstrap requirements apply.
Each run builds a fresh distribution, uses the normal dependency cache, and can take several minutes.
Source builds use `demo-settings.xml` or `DEMO_MAVEN_SETTINGS`.

The build skips core tests, test compilation, RAT, and Spotless. Selected lab cases still run.
The report records the commit and links to build provenance and logs under `maven-build/`.
Build failures mark selected cases inconclusive. `--dry-run` prints case commands without building or saving run outputs.

## Save and compare

```bash
./acceptance-suite.sh run --maven /path/to/baseline/bin/mvn --run-name baseline --set smoke
./acceptance-suite.sh run --maven /path/to/prototype/bin/mvn --run-name prototype \
  --compare-to acceptance-runs/baseline --set smoke
./acceptance-suite.sh report --run-name prototype
```

Open `acceptance-runs/prototype/report.html` offline.
Runs require new directories. Without a name, the suite generates one. `--output-dir` selects another destination.
Saved runs remain ignored by Git. `acceptance-runs/latest.json` points to the latest run.

Checked gaps return 0. Preparation and case errors return 1.
`--require-all` returns 2 for unmet requirements. Invalid arguments and rejected preflight configurations also return 2.
Passing harness checks can report unmet requirements. Unrun cases imply no result.
Different source revisions can explain comparison differences. Lab results cover selected fixtures, not complete Maven correctness.
Existing flag-only commands and saved results remain supported.

## Reference

- [Cases](acceptance/CASES.md)
- [Extension guide](acceptance/EXTENDING.md)
- [Evidence and result states](acceptance/README.md)
- [Requirement coverage](coverage.md)

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s acceptance -p 'test_*.py'
```

[Apache License 2.0](LICENSE).
