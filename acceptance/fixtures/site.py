# SPDX-License-Identifier: Apache-2.0
"""Render a real Maven site and aggregate Javadoc from two contributor source trees."""

from pathlib import Path
import re
from xml.dom.minidom import parseString


SITE_VERSION = "3.21.0"
JAVADOC_VERSION = "3.11.2"
CASE_NAME = "real-site-report"


def site_metadata():
    return {
        "case": CASE_NAME,
        "purpose": "Render an actual Maven site with one aggregate Javadoc report from two child source trees.",
        "builder": "singlethreaded",
        "threads": 1,
        "start_binding": "not applicable",
        "end_binding": "site reporting: aggregate-no-fork",
        "lifecycle": "site",
        "selection": "full reactor: root, a, b",
        "single_project": False,
        "contributor_policy": "The Javadoc report collects sources from both child modules.",
        "expectation": "real-site-rendering",
        "intended_requirement": "Generate real aggregate documentation and a rendered site from multiple module inputs.",
        "expected_diagnostic": "One aggregate Javadoc report contains both classes and the rendered site links to it.",
        "limitations": [
            "This report aggregates available source inputs. It does not consume completed child site outputs.",
            "The sequential root site executes before child sites. This case does not establish a site child barrier.",
            "This case does not validate coverage or PITest reporting.",
        ],
        "plugin_versions": {"maven-site-plugin": SITE_VERSION, "maven-javadoc-plugin": JAVADOC_VERSION},
    }


def _pom(body):
    document = f"""<project xmlns="http://maven.apache.org/POM/4.0.0"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
<modelVersion>4.0.0</modelVersion>{body}</project>"""
    return "\n".join(line for line in parseString(document).toprettyxml(indent="  ").splitlines() if line.strip()) + "\n"


def _create_fixture(root):
    root.mkdir(parents=True, exist_ok=False)
    # Identify the fixture root without requiring a machine-specific Maven configuration.
    (root / ".mvn").mkdir()
    (root / "pom.xml").write_text(_pom(f"""
<groupId>maven.aggregator.lab.site</groupId><artifactId>real-site-root</artifactId>
<version>1.0-SNAPSHOT</version><packaging>pom</packaging><name>Aggregator report acceptance</name>
<modules><module>a</module><module>b</module></modules>
<properties><project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
<maven.compiler.release>17</maven.compiler.release></properties>
<build><plugins><plugin><artifactId>maven-site-plugin</artifactId><version>{SITE_VERSION}</version></plugin></plugins></build>
<reporting><excludeDefaults>true</excludeDefaults><plugins><plugin>
<artifactId>maven-javadoc-plugin</artifactId><version>{JAVADOC_VERSION}</version><inherited>false</inherited>
<reportSets><reportSet><reports><report>aggregate-no-fork</report></reports></reportSet></reportSets>
</plugin></plugins></reporting>"""))
    content = root / "src/site/markdown"
    content.mkdir(parents=True)
    (content / "index.md").write_text(
        "# Aggregator site acceptance\n\n"
        "This rendered site includes aggregate documentation for Alpha and Beta.\n"
    )
    for name, class_name in (("a", "Alpha"), ("b", "Beta")):
        child = root / name
        child.mkdir()
        (child / "pom.xml").write_text(_pom(f"""
<parent><groupId>maven.aggregator.lab.site</groupId><artifactId>real-site-root</artifactId>
<version>1.0-SNAPSHOT</version></parent><artifactId>{name}</artifactId><name>Contributor {class_name}</name>"""))
        source = child / "src/main/java/maven/aggregator/lab/site"
        source.mkdir(parents=True)
        (source / f"{class_name}.java").write_text(f"""// SPDX-License-Identifier: Apache-2.0
package maven.aggregator.lab.site;

/** Contribution documentation for {class_name}. */
public final class {class_name} {{
    private {class_name}() {{}}

    /**
     * Return the contribution.
     * @return the contribution
     */
    public static String contribution() {{
        return "{class_name}";
    }}
}}
""")


def _require(condition, message):
    if not condition:
        raise AssertionError(message)


def _check(root, exit_code, log):
    _require(exit_code == 0, "The actual site/report build failed. Inspect build.log.")
    root_site_marker = f"--- site:{SITE_VERSION}:site (default-site) @ real-site-root ---"
    child_markers = [f"--- site:{SITE_VERSION}:site (default-site) @ {name} ---" for name in ("a", "b")]
    aggregate_pattern = rf'Generating "Javadoc" report\s+--- maven-javadoc-plugin:{re.escape(JAVADOC_VERSION)}:aggregate-no-fork'
    aggregate_markers = list(re.finditer(aggregate_pattern, log))
    _require(log.count(root_site_marker) == 1, "The root site goal must execute exactly once.")
    _require(len(aggregate_markers) == 1, "The actual aggregate Javadoc report must execute exactly once.")
    for marker in child_markers:
        _require(log.count(marker) == 1, "Each child site goal must execute exactly once.")
        _require(log.index(root_site_marker) < aggregate_markers[0].start() < log.index(marker),
                 "The recorded sequential site/report order changed.")

    site = root / "target/site"
    index = site / "index.html"
    reports = site / "project-reports.html"
    _require(index.is_file() and reports.is_file(), "The real Maven site pages do not exist.")
    _require("Aggregator site acceptance" in index.read_text(), "The Markdown input did not render into the root site.")
    _require("aggregate documentation for Alpha and Beta" in index.read_text(), "The rendered site lost its source content.")
    _require('href="apidocs/index.html"' in reports.read_text(), "The generated reports page does not link to aggregate Javadoc.")
    _require((site / "apidocs/index.html").is_file(), "The aggregate Javadoc index does not exist.")
    all_classes = site / "apidocs/allclasses-index.html"
    _require(all_classes.is_file(), "The aggregate class index does not exist.")
    class_index = all_classes.read_text()
    for name, class_name in (("a", "Alpha"), ("b", "Beta")):
        source = root / name / "src/main/java/maven/aggregator/lab/site" / f"{class_name}.java"
        page = site / "apidocs/maven/aggregator/lab/site" / f"{class_name}.html"
        _require(source.is_file() and page.is_file(), f"The actual class source or aggregate HTML is missing: {class_name}")
        _require(class_name in class_index, f"The aggregate class index omits {class_name}.")
        _require(f"Contribution documentation for {class_name}." in page.read_text(),
                 f"The aggregate HTML does not contain {class_name}'s source documentation.")
        _require("contribution()" in page.read_text(), f"The aggregate HTML omits {class_name}'s documented method.")
        _require((root / name / "target/site").is_dir(), f"The child site output is missing: {name}")
        _require(not (root / name / "target/site/apidocs").exists(), "The root-only report was unexpectedly copied to a child.")
    events = [(log.index(root_site_marker), "site:real-site-root"),
              (aggregate_markers[0].start(), "report:javadoc:aggregate-no-fork")]
    events.extend((log.index(marker), "site:" + name) for marker, name in zip(child_markers, ("a", "b")))
    return [event for _, event in sorted(events)]


def evaluate(case, execution):
    """Assess real site output without starting a process or changing saved results."""
    from model import Assessment
    root, log = execution.root, execution.log
    result = {"events": [], "artifact_links": []}
    try:
        result["events"] = _check(root, execution.exit_code, log)
        result["assertions"] = "passed"
        result["observation"] = (
            "REQUIREMENT MET IN FIXTURE: actual source-based Javadoc aggregation and Maven site rendering. "
            "The root report precedes child sites; this is not a child site completion barrier."
        )
        result["artifact_links"] = [
            {"path": "target/site/index.html", "label": "Rendered site"},
            {"path": "target/site/apidocs/index.html", "label": "Aggregated Javadoc"},
            {"path": "target/site/apidocs/allclasses-index.html", "label": "Combined class index"},
        ]
        result["evidence"] = {
            "root_site_execution_count": 1,
            "aggregate_javadoc_execution_count": 1,
            "child_site_execution_counts": {"a": 1, "b": 1},
            "documented_classes": ["Alpha", "Beta"],
            "source_inputs": ["a/src/main/java/maven/aggregator/lab/site/Alpha.java",
                              "b/src/main/java/maven/aggregator/lab/site/Beta.java"],
            "checks": ["rendered Markdown content", "reports-page Javadoc link", "combined class index",
                       "both class descriptions and documented methods", "one aggregate report", "no inherited child Javadoc reports",
                       "root/report/child site order from the Maven log"],
        }
    except (AssertionError, OSError) as error:
        result["assertions"] = "FAILED"
        result["observation"] = str(error)
    state = "met" if result["assertions"] == "passed" else "inconclusive"
    return Assessment(state, result["assertions"], result["observation"], result["observation"],
                      tuple(result.pop("events")), result)


def run_real_site(output, maven, common):
    """Retain the original entry point through the shared runner."""
    from catalogue import CASES
    from runner import run
    return run(next(case for case in CASES if case.name == CASE_NAME), Path(output), maven, common)
