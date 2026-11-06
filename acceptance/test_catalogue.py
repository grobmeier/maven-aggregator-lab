# SPDX-License-Identifier: Apache-2.0
"""Verify catalogue growth, legacy compatibility, discovery, and contract boundaries."""

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import assessment
import catalogue
import contracts
from fixtures import build, BUILDERS
from model import Case, Handler
from planning import build_command
from progress import compare_runs


LAB = Path(__file__).resolve().parents[1]
ORIGINAL = json.loads((LAB / "acceptance/compatibility/original-cases.json").read_text())


def changed_builder(root, case):
    raise RuntimeError("Synthetic changed fixture. Never execute this function.")


class CatalogueTests(unittest.TestCase):
    def test_all_original_case_ids_definitions_and_metadata_are_preserved(self):
        existing = {case.name: case for case in catalogue.CASES}
        self.assertEqual([case.name for case in catalogue.CASES[:25]], [item["definition"]["name"] for item in ORIGINAL])
        for record in ORIGINAL:
            case = existing[record["definition"]["name"]]
            for key, value in record["definition"].items():
                self.assertEqual(asdict(case)[key], value, (case.name, key))
            metadata = catalogue.case_metadata(case)
            for key, value in record["metadata"].items():
                self.assertEqual(metadata[key], value, (case.name, key))

    def test_all_original_fixture_inputs_are_identical(self):
        existing = {case.name: case for case in catalogue.CASES}
        with tempfile.TemporaryDirectory() as directory:
            for record in ORIGINAL:
                case = existing[record["definition"]["name"]]
                root = Path(directory) / case.name
                build(root, case)
                hashes = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sorted(root.rglob("*")) if path.is_file()}
                self.assertEqual(hashes, record["inputs"], case.name)
                if case.fixture_kind == "site":
                    self.assertTrue((root / ".mvn").is_dir())

    def test_groups_sets_and_case_union_preserve_catalogue_order(self):
        self.assertEqual([case.name for case in catalogue.select_cases(sets=["smoke"])],
                         ["seq-after-all", "concurrent-after-all", "single-seq"])
        names = [case.name for case in catalogue.select_cases(names=["site-seq"], sets=["smoke"], groups=["site"])]
        self.assertEqual(names, ["site-seq"])
        self.assertEqual(len(catalogue.select_cases(sets=["all"])), len(catalogue.CASES))
        self.assertIn("new-set", catalogue.named_sets([Case("new-case", sets=("new-set",))]))
        with self.assertRaises(ValueError):
            catalogue.select_cases(names=["missing"])

    def test_registration_rejects_duplicate_ids_unknown_handlers_and_broken_comparisons(self):
        case = Case("new-case")
        for cases in ([case, case], [replace(case, comparisons=(("missing", "Builder"),))],
                      [replace(case, fixture_kind="missing")], [replace(case, threads=0)]):
            with self.subTest(cases=cases), self.assertRaises(ValueError):
                catalogue.validate(cases)

    def test_new_ordinary_case_needs_only_a_definition(self):
        case = Case("new-ordinary-case", phase="verify", lifecycle="verify")
        catalogue.validate([case])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / case.name
            build(root, case)
            command = build_command(case, root, "mvn", [])
            self.assertEqual(command[-1], "verify")
            self.assertTrue((root / "a/pom.xml").is_file())
            self.assertIn("after-output", build_command(replace(case, failure_stage="after-output"), root, "mvn", [])[-2])

    def test_generated_reference_matches_registered_cases(self):
        self.assertEqual(catalogue.reference_markdown(), (LAB / "acceptance/CASES.md").read_text())


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.marker = next(case for case in catalogue.CASES if case.name == "seq-after-all")
        self.site = next(case for case in catalogue.CASES if case.name == "real-site-report")

    def test_catalogue_growth_and_display_changes_preserve_existing_contracts(self):
        before = contracts.requirement_contract(self.marker)
        with mock.patch.object(catalogue, "CASES", [*catalogue.CASES, Case("another-case")]):
            self.assertEqual(contracts.requirement_contract(self.marker), before)
        displayed = replace(self.marker, purpose="Explain this case differently.", group="another", sets=("other",), order=900)
        self.assertEqual(contracts.requirement_contract(displayed), before)

    def test_case_changes_and_shared_fixture_changes_invalidate_affected_contracts(self):
        marker, site = contracts.requirement_contract(self.marker), contracts.requirement_contract(self.site)
        self.assertNotEqual(contracts.requirement_contract(replace(self.marker, threads=2)), marker)
        changed = replace(BUILDERS["markers"], function=changed_builder)
        with mock.patch.dict(BUILDERS, {"markers": changed}):
            self.assertNotEqual(contracts.requirement_contract(self.marker), marker)
            self.assertEqual(contracts.requirement_contract(self.site), site)
            self.assertEqual(contracts.compatible_contracts(self.marker), [])

    def test_reviewed_legacy_contracts_compare_without_rewriting_saved_results(self):
        record = next(record for record in ORIGINAL if record["definition"]["name"] == self.marker.name)
        old = {"case": self.marker.name, "requirement_state": "not_met", "requirement_contract": record["contract"]}
        new = {"case": self.marker.name, "requirement_state": "met", "requirement_contract": contracts.requirement_contract(self.marker),
               "compatible_requirement_contracts": contracts.compatible_contracts(self.marker)}
        before = dict(old)
        compared = compare_runs([new], [old], [{"case": self.marker.name}])
        self.assertEqual(compared["rows"][0]["change"], "improved")
        self.assertEqual(old, before)
        unknown = {**old, "requirement_contract": "aggregation-fixture-v1:" + "0" * 64}
        self.assertEqual(compare_runs([new], [unknown], [{"case": self.marker.name}])["rows"][0]["change"], "incomparable")
        self.assertEqual(contracts.compatible_contracts(replace(self.marker, contract_version=2)), [])


class DiscoveryTests(unittest.TestCase):
    def call(self, *arguments):
        return subprocess.run(["bash", str(LAB / "acceptance-suite.sh"), *arguments], cwd=LAB,
                              text=True, capture_output=True, timeout=15)

    def test_legacy_list_and_new_list_are_equivalent(self):
        old = self.call("--list", "--json")
        new = self.call("list", "--json")
        self.assertEqual(old.returncode, 0, old.stderr)
        self.assertEqual(old.stdout, new.stdout)
        self.assertEqual(len(json.loads(new.stdout)), len(catalogue.CASES))

    def test_show_describes_requirement_checks_limits_and_execution(self):
        result = self.call("show", "seq-after-all", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        case = json.loads(result.stdout)
        self.assertIn("met", case["evidence"])
        self.assertIn("not_met", case["evidence"])
        self.assertIn("--case seq-after-all", case["execution"])
        self.assertTrue(case["limitations"])
        self.assertTrue(case["comparisons"])

    def test_dry_run_does_not_require_maven_or_change_existing_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / "keep.txt"
            sentinel.write_text("preserve")
            result = self.call("run", "--set", "smoke", "--dry-run", "--json", "--maven", "/missing/maven", "--output-dir", directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(json.loads(result.stdout)), 3)
            self.assertEqual(list(Path(directory).iterdir()), [sentinel])
            self.assertEqual(sentinel.read_text(), "preserve")

    def test_invalid_selection_fails_without_preparation(self):
        for arguments in (("show", "missing"), ("show",), ("run", "--group", "site", "--case", "seq-after-all")):
            with self.subTest(arguments=arguments):
                result = self.call(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Run directory:", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
