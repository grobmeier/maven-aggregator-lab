# SPDX-License-Identifier: Apache-2.0
"""Check requirement oracles, comparisons, run preservation, and offline reports."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

import progress
import report
import run_support
import suite


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="aggregation-progress-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.events = self.root / "target/events.txt"
        self.events.parent.mkdir()
        self.case = next(case for case in suite.CASES if case.name == "seq-after-all")

    def early(self):
        self.events.write_text("start:fixture-root\ncleanup:fixture-root\nend-attempt:fixture-root\n")
        return "DEMO_MISSING_CONTRIBUTIONS:a,b\n"

    def successful(self, extra=()):
        self.events.write_text("\n".join(["start:fixture-root", *extra, "work:a", "work:b", "cleanup:fixture-root",
                                         "end-attempt:fixture-root", "end-success:fixture-root"]) + "\n")
        with zipfile.ZipFile(self.root / "target/contributions.zip", "w") as archive:
            for name in ("a", "b"):
                path = self.root / name / "target/contribution.txt"
                path.parent.mkdir(parents=True)
                path.write_text(name + "\n")
                archive.write(path, name + "/contribution.txt")

    def test_baseline_gap_and_checked_improvement_use_one_requirement(self):
        gap = suite.assess(self.case, self.root, 1, self.early())
        self.assertEqual(gap[:2], ("not_met", "passed"))
        self.successful()
        fixed = suite.assess(self.case, self.root, 0, "")
        self.assertEqual(fixed[:2], ("met", "passed"))

    def test_unrelated_failure_and_incomplete_success_are_inconclusive(self):
        self.early()
        self.assertEqual(suite.assess(self.case, self.root, 17, "Plugin resolution failed")[:2], ("inconclusive", "FAILED"))
        self.assertEqual(suite.assess(self.case, self.root, 0, "BUILD SUCCESS")[:2], ("inconclusive", "FAILED"))

    def test_corrupt_zip_does_not_establish_improvement(self):
        self.successful()
        (self.root / "target/contributions.zip").write_bytes(b"not a zip")
        self.assertEqual(suite.assess(self.case, self.root, 0, "")[0], "inconclusive")

    def test_previously_passing_order_can_regress(self):
        case = next(case for case in suite.CASES if case.name == "concurrent-after-all")
        self.assertEqual(suite.assess(case, self.root, 1, self.early())[:2], ("not_met", "passed"))

    def test_complete_output_with_duplicate_start_is_unmet(self):
        self.successful(extra=["start:fixture-root"])
        self.assertEqual(suite.assess(self.case, self.root, 0, "")[:2], ("not_met", "passed"))

    def test_extra_child_hook_does_not_count_as_exactly_once(self):
        self.successful(extra=["start:a"])
        self.assertEqual(suite.assess(self.case, self.root, 0, "")[:2], ("not_met", "passed"))

    def test_inheritance_improvement_requires_root_only_hooks(self):
        case = next(case for case in suite.CASES if case.name == "inheritance-on")
        self.successful()
        self.events.write_text(self.events.read_text().replace("cleanup:fixture-root", "finish:fixture-root\ncleanup:fixture-root"))
        self.assertEqual(suite.assess(case, self.root, 0, "")[0], "met")
        events = ["start:fixture-root", "start:a", "work:a", "finish:a", "start:b", "work:b", "finish:b",
                  "finish:fixture-root", "cleanup:fixture-root", "end-attempt:fixture-root", "end-success:fixture-root"]
        self.events.write_text("\n".join(events) + "\n")
        self.assertEqual(suite.assess(case, self.root, 0, "")[:2], ("not_met", "passed"))

    def test_failure_safety_does_not_invent_cleanup_policy(self):
        case = next(case for case in suite.CASES if case.name == "failure-fast")
        self.events.write_text("start:fixture-root\nchild-failure:a\n")
        outcome = suite.assess(case, self.root, 1, "DEMO_CHILD_FAILURE:a")
        self.assertEqual(outcome[:2], ("undefined_policy", "passed"))
        case = next(case for case in suite.CASES if case.name == "failure-after-output")
        self.events.write_text("start:fixture-root\nwork:a\nchild-failure:a\n")
        contribution = self.root / "a/target/contribution.txt"
        contribution.parent.mkdir(parents=True)
        contribution.write_text("a\n")
        self.assertEqual(suite.assess(case, self.root, 1, "DEMO_CHILD_FAILURE:a")[:2], ("met", "passed"))

    def test_sequential_verification_failure_without_aggregate_is_met(self):
        case = next(case for case in suite.CASES if case.name == "seq-failure-after-output")
        self.events.write_text("start:fixture-root\nwork:a\nchild-failure:a\n")
        contribution = self.root / "a/target/contribution.txt"
        contribution.parent.mkdir(parents=True)
        contribution.write_text("a\n")
        self.assertEqual(suite.assess(case, self.root, 1, "DEMO_CHILD_FAILURE:a")[:2], ("met", "passed"))

    def test_sequential_failure_requires_output_before_the_deliberate_failure(self):
        case = next(case for case in suite.CASES if case.name == "seq-failure-after-output")
        for events, log in (("start:fixture-root\nchild-failure:a\n", "DEMO_CHILD_FAILURE:a"),
                            ("start:fixture-root\nwork:a\nchild-failure:a\n", "Unrelated plugin failure"),
                            ("start:fixture-root\nwork:a\nchild-failure:a\n", "DEMO_CHILD_FAILURE:a")):
            with self.subTest(events=events, log=log):
                self.events.write_text(events)
                self.assertEqual(suite.assess(case, self.root, 1, log)[:2], ("inconclusive", "FAILED"))

    def test_sequential_false_aggregate_success_remains_unmet(self):
        case = next(case for case in suite.CASES if case.name == "seq-failure-after-output")
        self.successful()
        self.events.write_text(self.events.read_text().replace("cleanup:fixture-root", "child-failure:a\ncleanup:fixture-root"))
        self.assertEqual(suite.assess(case, self.root, 1, "DEMO_CHILD_FAILURE:a")[:2], ("not_met", "passed"))

    def test_comparison_distinguishes_regression_missing_and_changed_contract(self):
        def record(name, state, contract="same"):
            return {"case": name, "requirement_state": state, "requirement_contract": contract}
        baseline = [record("fixed", "not_met"), record("regressed", "met"), record("pending", "met"),
                    record("gap", "not_met"), record("error", "not_met"), record("changed", "not_met")]
        current = [record("fixed", "met"), record("regressed", "not_met"), record("new", "met"),
                   record("gap", "not_met"), record("error", "inconclusive"), record("changed", "met", "other")]
        names = sorted({item["case"] for item in baseline + current})
        result = progress.compare_runs(current, baseline, [{"case": name} for name in names])
        changes = {row["case"]: row["change"] for row in result["rows"]}
        self.assertEqual(changes, {"fixed": "improved", "regressed": "regressed", "pending": "not_run", "new": "not_run",
                                   "gap": "unchanged_unmet", "error": "inconclusive", "changed": "incomparable"})

    def test_reservation_preserves_existing_baseline_and_sentinels(self):
        output = run_support.reserve_output(self.root, run_name="baseline")
        sentinel = output / "results.json"
        sentinel.write_text("preserve")
        with self.assertRaises(FileExistsError):
            run_support.reserve_output(self.root, run_name="baseline")
        self.assertEqual(sentinel.read_text(), "preserve")
        with self.assertRaises(ValueError):
            run_support.reserve_output(self.root, run_name="../escape")

    def test_preparation_failure_is_inconclusive_and_preserves_source_targets(self):
        lab = self.root / "lab"
        (lab / "acceptance").mkdir(parents=True)
        (lab / "demo-plugin/src").mkdir(parents=True)
        (lab / "demo-plugin/pom.xml").write_text("<project/>")
        (lab / "demo-settings.xml").write_text("<settings/>")
        sentinel = lab / "target/keep.txt"
        sentinel.parent.mkdir()
        sentinel.write_text("preserve")
        executable = self.root / "mvn"
        executable.write_text('#!/usr/bin/env bash\nif [[ ${1:-} == --version ]]; then\n'
                              '  echo "Apache Maven 4.2.0-SNAPSHOT"\n  exit 0\nfi\necho "Unrelated download failure"\nexit 17\n')
        executable.chmod(0o755)
        output = self.root / "failed-run"
        with mock.patch.object(suite, "__file__", str(lab / "acceptance/suite.py")), \
                mock.patch("sys.argv", ["suite", "--maven", str(executable), "--case", "seq-after-all", "--output-dir", str(output)]), \
                mock.patch.dict(os.environ, {"MAVEN_ARGS": "clean verify"}), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as stopped:
                suite.main()
        self.assertEqual(stopped.exception.code, 1)
        result = json.loads((output / "seq-after-all/result.json").read_text())
        self.assertEqual(result["requirement_state"], "inconclusive")
        self.assertEqual(result["execution_stage"], "preparation")
        self.assertEqual(result["assertions"], "FAILED")
        self.assertIn("exit 17", result["requirement_reason"])
        self.assertTrue((output / "report.html").is_file())
        self.assertEqual(sentinel.read_text(), "preserve")

    def test_comparison_report_is_offline_escaped_and_baseline_is_unchanged(self):
        current = self.root / "current"
        baseline = self.root / "baseline"
        current.mkdir()
        baseline.mkdir()
        record = {"case": "seq-after-all", "assertions": "passed", "requirement_state": "met", "requirement_contract": "same",
                  "requirement_reason": "<script>bad</script> /Users/private/file", "events": [], "command": []}
        (current / "seq-after-all").mkdir()
        (current / "seq-after-all/result.json").write_text(json.dumps(record))
        (current / "results.json").write_text(json.dumps([record]))
        (current / "manifest.json").write_text(json.dumps({"schema_version": 2, "cases": [{"case": "seq-after-all"}],
            "catalogue": [{"case": "seq-after-all"}, {"case": "pending"}]}))
        record = {**record, "requirement_state": "not_met"}
        (baseline / "results.json").write_text(json.dumps([record]))
        before = (baseline / "results.json").read_bytes()
        text = report.generate_report(current, compare_to=baseline).read_text()
        self.assertIn("improved", text)
        self.assertIn("not_run", text)
        self.assertIn("&lt;script&gt;bad&lt;", text)
        self.assertNotIn("/Users/private", text)
        self.assertNotIn('<script src=', text)
        self.assertNotIn('<link rel="stylesheet"', text)
        self.assertEqual(before, (baseline / "results.json").read_bytes())
        comparison = json.loads((current / "comparison.json").read_text())
        self.assertEqual(comparison["requirement_counts"]["met"], 1)
        self.assertEqual(comparison["requirement_counts"]["not_run"], 1)
        self.assertEqual(comparison["counts"]["improved"], 1)

    def test_require_all_has_separate_exit_code_from_harness_failure(self):
        for state, assertions, code in (("not_met", "passed", 2), ("met", "passed", 0), ("inconclusive", "FAILED", 1)):
            with self.subTest(state=state), mock.patch.object(suite, "preflight", return_value=("mvn", "Apache Maven 4.2.0")), \
                    mock.patch.object(suite, "prepare_plugin", return_value=[]), \
                    mock.patch.object(suite, "run", return_value={"case": "seq-after-all", "requirement_state": state, "assertions": assertions}), \
                    mock.patch("sys.argv", ["suite", "--case", "seq-after-all", "--require-all", "--output-dir", str(self.root / state)]), \
                    mock.patch.object(suite, "update_latest"), redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as stopped:
                    suite.main()
                self.assertEqual(stopped.exception.code, code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
