# Add or change acceptance cases

Run commands from the lab root. [CASES.md](CASES.md) is the generated case reference.
The registered definitions under `cases/` are the authoritative case registry.

## Find and execute cases

Use `./run.sh` for interactive menus, folder browsing, and remembered selections.
The [lab guide](../README.md#run-from-maven-source) describes source revision builds and their evidence.
The menus obtain case IDs and groups from the registry.

```bash
./acceptance-suite.sh list
./acceptance-suite.sh list --group ordering
./acceptance-suite.sh show seq-after-all
./acceptance-suite.sh run --set smoke --maven /path/to/mvn
./acceptance-suite.sh run --group selection --dry-run
./acceptance-suite.sh run --case seq-after-all --dry-run --json
./acceptance-suite.sh report --run-name step-1
```

Groups are `ordering`, `failure`, `selection`, `inheritance`, and `site`.
Sets are `all`, `smoke`, and each group name. The smoke set contains three ordering cases.
Additional set names come from the `sets` fields in registered case definitions.
Repeated `--case` and `--set` options combine their selections. `--group` then filters that combined selection.
Without case or set options, the runner selects all cases before applying group filters.
An empty selection causes an error. List, show, reference, and dry-run commands do not start Maven or reserve run directories.
Dry-run prints the reactor commands and a preparation note. Runtime paths appear as placeholders.

The existing options remain valid: `--list`, `--case`, `--report-only`, `--maven`, `--run-name`, and `--output-dir`.
The existing `MAVEN4` environment default, saved run layout, requirement states, and exit codes remain available.
Terminal output supports `--color auto|always|never`. Automatic color respects `NO_COLOR`, `TERM=dumb`, and redirected output.
JSON and generated Markdown stay plain. Color settings do not affect requirement fingerprints or saved evidence.
Checked gaps return zero by default. Preparation and case errors return one. `--require-all` returns two for selected requirements that are not met.
Argument errors and rejected preflight configuration also return two.

## Add an ordinary variant

1. Add one `Case` definition to the relevant module under `cases/`.
2. Add a focused test for the new requirement or variation.
3. Regenerate the reference with the command below.
4. Inspect the case and its dry-run command before executing Maven.

For example, add this definition to `cases/ordering.py`:

```python
Case(
    "seq-verify",
    builder="singlethreaded",
    lifecycle="verify",
    group="ordering",
    purpose="Check sequential aggregation after verification.",
    requirement="Run one start before contributions and one successful end after verification.",
    comparisons=(("verify-success", "Builder only"),),
)
```

The registry automatically includes entries from the registered family modules. It checks IDs, handlers, and comparison references.
The default order appends a new case after the existing cases. Existing numeric order values preserve historical case ordering.
The runner, command planner, report comparison links, and discovery commands require no case-ID branches.
Declare `active_contributors` when a selection excludes contributors. Declare `failure_stage` when the invocation deliberately fails after output creation.

`requirement_policy` declares the intended interpretation: ordered output, observation, failure safety, success-only aggregation, or real site rendering.
`expectation` identifies a recognized historical diagnostic. It does not declare that a requirement must remain broken.
The assessment checks complete success evidence first. Unknown errors remain inconclusive, independent of the Maven version.
Use `show CASE` to inspect the positive evidence, counterexamples, limitations, artifacts, and related cases.

```bash
./acceptance-suite.sh reference > acceptance/CASES.md
./acceptance-suite.sh show seq-verify
./acceptance-suite.sh run --case seq-verify --dry-run
python3 -m unittest discover -s acceptance -p 'test_*.py' -v
```

## Add a distinct fixture or assessment

An ordinary variant uses the existing marker fixture and assessment. A different project shape requires a fixture builder.

- Add the builder under `fixtures/`. Its signature is `create(root, case)`. It creates only the supplied fresh case directory.
- Register it explicitly in `fixtures.BUILDERS` with a `Handler`.
- Add a new evaluator only when the existing assessment cannot express the requirement.
- Register that evaluator in `assessment.EVALUATORS`. Its signature is `evaluate(case, execution)`.
- Select those registered keys through the case's `fixture_kind` and `assessment_kind` fields.

`Execution` contains the command, exit code, log text, and fixture directory.
An evaluator returns `Assessment`, including the requirement state, harness result, reason, events, and optional evidence details.
It reads evidence without starting Maven or rewriting saved results. Unknown or incomplete evidence must return an inconclusive assessment.
The shared runner owns process execution and result serialization for marker and real-site cases.

Each handler declares its helper dependencies and relevant constants. Include every local helper and external version that affects its meaning.
For file-based dependencies, include their content hashes among the declared constants.
The case fingerprint includes those dependencies. New fixture types require an explicit review of their fingerprint inputs.
There is no automatic module or plugin discovery.

## Module responsibilities

| Module | Responsibility |
|---|---|
| `cases/*.py` | Case definitions, requirement policy, limitations, sets, and comparison relationships |
| `catalogue.py` | Explicit registration, validation, selection, metadata, and generated reference |
| `model.py` | Immutable case, execution, assessment, and handler records |
| `fixtures/` | Disposable input generation and real-site evidence checks |
| `planning.py` | Maven command construction without process execution |
| `evidence.py` | Event reading and exact contribution output checks |
| `diagnostics.py` | Recognition of historical traces |
| `assessment.py` | Requirement interpretation and evaluator registration |
| `runner.py` | Shared process execution and case result serialization |
| `run_support.py` | Maven preflight, isolated plugin preparation, and saved run reservation |
| `contracts.py` | Case and dependency fingerprints, plus reviewed compatibility aliases |
| `progress.py` | Saved requirement comparisons |
| `report.py` | Offline report rendering and historical report compatibility |
| `cli.py` | Discovery commands and saved run orchestration |
| `suite.py`, `site_render.py` | Compatibility entry points for existing callers |

## Preserve saved comparisons

The v2 fingerprint covers the case semantics, planned command, selected fixture and evaluator helpers, relevant constants, and marker plugin inputs.
Adding an unrelated case or changing discovery text does not change existing fingerprints.
Changing a shared marker dependency invalidates affected marker comparisons. It does not invalidate an unrelated site fixture.
A semantic change to a specific case invalidates that case's comparison. Increase `contract_version` when its intended requirement changes.

The migration preserves reviewed v1 comparisons through `compatibility/contracts-v1.json`.
The review checked all 25 original fixture inputs and reproduced 54 saved case assessments.
An alias applies only while the new case fingerprint matches the reviewed migration fingerprint.
Any affected semantic change disables that alias. Unknown legacy fingerprints remain incomparable.
Existing result files retain their original contracts. Report regeneration uses their recorded evidence without rewriting it.
Old diagnostic-only records remain readable, but cannot establish a requirement transition without requirement evidence.

`compatibility/original-cases.json` preserves the original definitions, metadata, fixture hashes, and original contract identifiers.
Tests use it to protect existing cases during refactoring. New case definitions do not require changes to that historical snapshot.
Do not regenerate either compatibility file merely to make a failing test pass.
