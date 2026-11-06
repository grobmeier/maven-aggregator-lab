# SPDX-License-Identifier: Apache-2.0
"""Check the harness without building Maven, accessing the network, or changing lab outputs.

Run from the lab directory: python3 acceptance/test_harness.py
All test fixtures use temporary directories. Synthetic report records test the renderer,
not Maven runtime behaviour.
"""

from collections import Counter
from contextlib import redirect_stdout
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import report
import suite


class ReportParser(HTMLParser):
    """Read visible status counts and card classifications independently of the renderer."""

    def __init__(self, text):
        super().__init__()
        self.cards = {}
        self.counts = {}
        self.links = []
        self.scripts = []
        self.images = []
        self.current_filter = None
        self.in_strong = False
        self.feed(text)

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == "article" and "data-case" in attributes:
            self.cards[attributes["data-case"]] = attributes.get("data-status")
        if tag == "button":
            self.current_filter = attributes.get("data-filter")
        if tag == "strong" and self.current_filter:
            self.in_strong = True
        if tag == "a":
            self.links.append(attributes.get("href", ""))
        if tag == "script":
            self.scripts.append(attributes)
        if tag == "img":
            self.images.append(attributes)

    def handle_endtag(self, tag):
        if tag == "button":
            self.current_filter = None
        if tag == "strong":
            self.in_strong = False

    def handle_data(self, text):
        if self.in_strong and self.current_filter and text.strip().isdigit():
            self.counts[self.current_filter] = int(text.strip())


class TemporaryFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="aggregator-harness-")
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def write_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))




class OrderingOracleTests(TemporaryFixture):
    def setUp(self):
        super().setUp()
        self.case = next(case for case in suite.CASES if case.name == "seq-after-all")
        self.events = self.root / "target/events.txt"
        self.events.parent.mkdir()
        self.events.write_text("start:fixture-root\ncleanup:fixture-root\nend-attempt:fixture-root\n")

    def test_exact_expected_failure_has_a_positive_control(self):
        observation, events = suite.check(
            self.case, self.root, 1, "[ERROR] DEMO_MISSING_CONTRIBUTIONS:a,b -> build failed\n")
        self.assertTrue(observation.startswith("KNOWN GAP:"))
        self.assertEqual(len(events), 3)

    def test_an_unrelated_plugin_error_does_not_pass_the_diagnostic(self):
        with self.assertRaises(AssertionError):
            suite.check(self.case, self.root, 1, "[ERROR] Plugin resolution failed\n")

    def test_a_different_missing_contributor_does_not_pass_the_diagnostic(self):
        with self.assertRaises(AssertionError):
            suite.check(self.case, self.root, 1, "[ERROR] DEMO_MISSING_CONTRIBUTIONS:a -> build failed\n")

    def test_duplicate_hooks_fail_instead_of_being_ignored(self):
        self.events.write_text("start:fixture-root\nstart:fixture-root\ncleanup:fixture-root\nend-attempt:fixture-root\n")
        with self.assertRaisesRegex(AssertionError, "more than once"):
            suite.check(self.case, self.root, 1, "DEMO_MISSING_CONTRIBUTIONS:a,b\n")

    def test_work_before_start_fails_the_ordering_requirement(self):
        self.events.write_text("work:a\nstart:fixture-root\ncleanup:fixture-root\nend-attempt:fixture-root\n")
        with self.assertRaisesRegex(AssertionError, "before the start hook"):
            suite.check(self.case, self.root, 1, "DEMO_MISSING_CONTRIBUTIONS:a,b\n")


class ReportContractTests(TemporaryFixture):
    def setUp(self):
        super().setUp()
        self.results = self.root / "results"
        self.results.mkdir()

    def record(self, name, **changes):
        value = {
            "case": name, "purpose": "Inspect a bounded fixture.", "builder": "concurrent", "threads": 1,
            "lifecycle": "package", "end_binding": "after:all", "expectation": "success",
            "intended_requirement": "Run the end hook after the contributors.",
            "expected_diagnostic": "Check ordered output.", "assertions": "passed", "exit_code": 0,
            "observation": "REQUIREMENT MET IN FIXTURE: ordered output.", "events": ["start:fixture-root"],
            "command": ["mvn", "--builder", "concurrent", "package"],
        }
        value.update(changes)
        self.write_json(self.results / name / "result.json", value)
        return value

    def manifest(self, names):
        self.write_json(self.results / "manifest.json", {"cases": [{"case": name} for name in names]})

    def render(self):
        text = report.generate_report(self.results).read_text()
        return text, ReportParser(text)

    def test_status_labels_and_summary_counts_match_case_json(self):
        records = [
            self.record("met"),
            self.record("gap", observation="KNOWN GAP: aggregation ran early.", expectation="early", exit_code=1),
            self.record("expected", expectation="child-failure", exit_code=1,
                        observation="FAILED BUILD DETECTED: no success output."),
            self.record("observed", observation="OBSERVED SUCCESS: no barrier guarantee."),
            self.record("unexpected", assertions="FAILED", observation="The ZIP has the wrong contributors."),
        ]
        self.manifest([record["case"] for record in records] + ["pending"])
        text, parsed = self.render()
        self.assertEqual(parsed.cards, {
            "met": "met", "gap": "known-gap", "expected": "expected-failure",
            "observed": "observation", "unexpected": "unexpected", "pending": "incomplete",
        })
        actual = Counter(parsed.cards.values())
        self.assertEqual(parsed.counts, {status: actual[status] for status in parsed.counts})
        self.assertEqual(sum(parsed.counts.values()), len(records) + 1)
        self.assertIn("4 cases passed their diagnostic assertions", text)
        self.assertIn("5 of 6 selected cases have complete results", text)
        self.assertIn("Expected failure reproduced", text)
        self.assertNotEqual(parsed.cards["expected"], "met")
        self.assertTrue(all(not link.startswith(("/", "file:", "http:")) for link in parsed.links))

    def test_malformed_result_and_missing_manifest_do_not_look_complete(self):
        result = self.results / "broken/result.json"
        result.parent.mkdir()
        result.write_text("{invalid JSON")
        text, parsed = self.render()
        self.assertEqual(parsed.cards["broken"], "incomplete")
        self.assertIn("Expected coverage is unknown", text)
        self.assertIn("0 cases passed their diagnostic assertions", text)

    def test_empty_results_do_not_claim_success(self):
        text, parsed = self.render()
        self.assertEqual(parsed.cards, {})
        self.assertIn("No case results are available", text)
        self.assertIn("Expected coverage is unknown", text)

    def test_reasons_distinguish_builder_timing_from_a_site_observation(self):
        gap = self.record("seq-after-all", builder="singlethreaded", expectation="early", exit_code=1,
                          observation="KNOWN GAP: aggregation ran before required contributions.",
                          events=["start:fixture-root", "end-attempt:fixture-root"])
        reason = report.outcome_reason(gap, report.status_for(gap))
        self.assertIn("singlethreaded builder and after:all binding", reason)
        self.assertIn("missing-output diagnostic", reason)
        ordered = self.record("concurrent-after-all", events=["start:fixture-root", "work:a", "work:b", "end-attempt:fixture-root"])
        self.assertIn("matches the child barrier checked by this fixture", report.outcome_reason(ordered, report.status_for(ordered)))
        site = self.record("site-concurrent", lifecycle="site", end_binding="after:site",
                           observation="OBSERVED SUCCESS: no barrier guarantee.", events=ordered["events"])
        self.assertIn("successful interleaving does not establish a site child barrier", report.outcome_reason(site, report.status_for(site)))
        early_site = self.record("site-seq", builder="singlethreaded", lifecycle="site", end_binding="after:site",
                                 expectation="early", exit_code=1, observation="KNOWN GAP: missing outputs.", events=gap["events"])
        self.assertIn("hook-only trace does not establish reactor-wide site ordering", report.outcome_reason(early_site, report.status_for(early_site)))

    def test_unexpected_results_override_known_case_explanations(self):
        unexpected = self.record("seq-after-all", builder="singlethreaded", expectation="early", assertions="FAILED",
                                 exit_code=17, observation="UNEXPECTED_PLUGIN_RESOLUTION_FAILURE")
        reason = report.outcome_reason(unexpected, report.status_for(unexpected))
        self.assertIn("Inconclusive", reason)
        self.assertIn("No Maven scheduling cause is established", reason)
        self.assertNotIn("reproduces this timing gap", reason)
        self.manifest(["seq-after-all", "concurrent-after-all"])
        text, parsed = self.render()
        self.assertEqual(parsed.cards["seq-after-all"], "unexpected")
        self.assertEqual(parsed.cards["concurrent-after-all"], "incomplete")
        self.assertIn("a complete result is missing", text)
        self.assertIn("does not establish the intended Maven behaviour", text)

    def test_non_builder_gaps_explain_the_recorded_context(self):
        cases = [
            ("partial-no-root", "no-root", ["work:a"], "selection excludes the root"),
            ("partial-fixed", "missing-b", ["work:a", "end-attempt:fixture-root"], "contributor selection, not builder timing"),
            ("inheritance-on", "inherited-copies", ["start:fixture-root", "start:a", "start:b"], "Inheritance copied those bindings"),
            ("failure-fast", "child-failure", ["child-failure:a", "cleanup:fixture-root", "end-attempt:fixture-root"], "Cleanup and the end attempt still ran"),
            ("failure-after-output", "false-success", ["child-failure:a", "end-success:fixture-root"], "Maven still exited with failure"),
        ]
        for name, expectation, events, explanation in cases:
            with self.subTest(case=name):
                value = self.record(name, expectation=expectation, events=events, exit_code=1,
                                    observation="KNOWN GAP: the checked diagnostic was reproduced.")
                reason = report.outcome_reason(value, report.status_for(value))
                self.assertIn(explanation, reason)
                self.assertNotIn("reproduces this timing gap", reason)

    def test_controlled_comparisons_link_selected_peers_and_name_absent_peers(self):
        self.record("seq-after-all", builder="singlethreaded", expectation="early", exit_code=1,
                    observation="KNOWN GAP: missing outputs.")
        self.record("concurrent-after-all")
        self.write_json(self.results / "manifest.json", {"cases": [
            {"case": "seq-after-all", "builder": "singlethreaded", "end_binding": "after:all"},
            {"case": "concurrent-after-all", "builder": "concurrent", "end_binding": "after:all"},
        ]})
        text, parsed = self.render()
        self.assertIn('id="case-concurrent-after-all"', text)
        self.assertIn('href="#case-concurrent-after-all"', text)
        self.assertIn('href="#case-seq-after-all"', text)
        self.assertIn("Builder only", text)
        self.assertIn("concurrent · after:all", text)
        self.assertIn("End binding only", text)
        self.assertIn("<code>seq-package</code>", text)
        self.assertIn("(not selected)", text)
        self.assertNotIn('href="#case-seq-package"', text)
        self.assertEqual(sum(parsed.counts.values()), 2)

    def test_dynamic_html_is_escaped_and_private_paths_are_redacted(self):
        attack = '<img src=x onerror="DYNAMIC_PAYLOAD">'
        private = "/home/private-user/workspace/sensitive-project"
        self.record("escaped", purpose=attack + " " + private,
                    observation="KNOWN GAP: " + attack + " " + private,
                    events=[attack, "event:" + private], command=[private + "/bin/mvn", "--settings", private + "/settings.xml",
                        "-Ddemo.eventRoot=" + private, "package"])
        self.manifest(["escaped"])
        (self.results / "maven-version.txt").write_text(
            "Apache Maven 4.1.0-SNAPSHOT\nMaven home: " + private + "\n"
            "Java version: 21.0.1, vendor: Test, runtime: " + private + "\n")
        text, parsed = self.render()
        self.assertIn("&lt;img", text)
        self.assertIn("DYNAMIC_PAYLOAD", text)
        self.assertEqual(parsed.images, [])
        self.assertTrue(all("src" not in script for script in parsed.scripts))
        self.assertNotIn("private-user", text)
        self.assertNotIn("sensitive-project", text)
        self.assertIn("Apache Maven 4.1.0-SNAPSHOT", text)
        self.assertIn("Java version: 21.0.1", text)


class FailedRunReportTests(TemporaryFixture):
    def test_unexpected_maven_failure_still_produces_the_automatic_report(self):
        acceptance = self.root / "isolated lab/acceptance"
        acceptance.mkdir(parents=True)
        executable = self.root / "mvn"
        executable.write_text(
            "#!/usr/bin/env bash\n"
            "if [[ ${1:-} == --version ]]; then\n"
            "  printf '%s\\n' 'Apache Maven 4.1.0-SNAPSHOT'\n"
            "  exit 0\n"
            "fi\n"
            "printf '%s\\n' 'UNEXPECTED_PLUGIN_RESOLUTION_FAILURE' >&2\n"
            "exit 17\n"
        )
        executable.chmod(0o755)
        output = acceptance.parent / "acceptance-runs/test"
        arguments = ["acceptance-suite.sh", "--maven", str(executable), "--case", "seq-after-all", "--output-dir", str(output)]
        # Relocate the production runner's output root to the temporary test lab.
        with mock.patch.object(suite, "__file__", str(acceptance / "suite.py")), \
                mock.patch.object(sys, "argv", arguments), mock.patch.object(suite, "prepare_plugin", return_value=[]), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as stopped:
                suite.main()
        self.assertEqual(stopped.exception.code, 1)
        results = json.loads((output / "results.json").read_text())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["exit_code"], 17)
        self.assertEqual(results[0]["assertions"], "FAILED")
        self.assertIn("UNEXPECTED_PLUGIN_RESOLUTION_FAILURE", (output / "seq-after-all/build.log").read_text())
        parsed = ReportParser((output / "report.html").read_text())
        self.assertEqual(parsed.cards, {"seq-after-all": "unexpected"})
        self.assertEqual(parsed.counts["unexpected"], 1)
        self.assertEqual(parsed.counts["met"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
