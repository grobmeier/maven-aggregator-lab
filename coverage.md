# Requirement coverage

The [generated case reference](acceptance/CASES.md) is the current catalogue.
Use `./acceptance-suite.sh show CASE` to inspect a requirement, its evidence, limitations, artifacts, and related cases.

| Group | Cases | Scope |
|---|---:|---|
| Ordering | 9 | Builders, bindings, worker counts, standalone projects, and verification |
| Failure | 3 | Deliberate child failures, aggregate safety, and unresolved cleanup policy |
| Selection | 6 | Active contributors, root exclusion, and nested group boundaries |
| Inheritance | 3 | Inherited copies and explicit child declarations |
| Site | 4 | Hook timing and actual site/Javadoc rendering |

These fixtures cover bounded scenarios. They do not establish a complete fix for aggregator issue #47.
Requirement satisfaction is separate from harness assertion success. Use saved run reports for measured results.

The [extension guide](acceptance/EXTENDING.md) explains adding cases and preserving saved comparisons.
