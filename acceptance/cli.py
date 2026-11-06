# SPDX-License-Identifier: Apache-2.0
"""Parse commands and orchestrate immutable saved runs."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import shlex
from collections import Counter
from catalogue import CASES, GROUPS, SETS, case_metadata, select_cases, comparisons_for, reference_markdown
from contracts import requirement_contract
from planning import build_command
from assessment import POLICY_EVIDENCE
from progress import read_results
from report import generate_report
from run_support import latest_output, reserve_output
from terminal import configure, paint


def main(lab, run_case, prepare, preflight_command, update):
    parser = argparse.ArgumentParser(prog="acceptance-suite.sh", description="Measure bounded aggregation requirements and compare saved runs.")
    if hasattr(parser, "color"):
        parser.color = False
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto", help="Control terminal colors. Default: auto. JSON and reference output stay plain.")
    parser.add_argument("command", nargs="?", choices=("list", "show", "run", "report", "reference"), help="Select a command. Default: run.")
    parser.add_argument("case_id", nargs="?", help="Select the case for the show command.")
    parser.add_argument("--case", action="append", choices=[case.name for case in CASES], help="Run one case. Repeat to select more cases.")
    parser.add_argument("--group", action="append", choices=GROUPS, help="Filter by case group. Repeat to include more groups.")
    parser.add_argument("--set", dest="sets", action="append", choices=SETS, help="Select a named set. Cases and sets combine before group filtering.")
    parser.add_argument("--dry-run", action="store_true", help="Print case commands without starting Maven or writing outputs.")
    parser.add_argument("--json", action="store_true", help="Print discovery or planning output as JSON.")
    parser.add_argument("--list", action="store_true", help="List cases without starting Maven.")
    parser.add_argument("--report-only", action="store_true", help="Regenerate a saved report without starting Maven.")
    parser.add_argument("--maven", default=os.environ.get("MAVEN4", "mvn"), help="Select Maven 4.1.x or 4.2.x. Default: MAVEN4, then mvn.")
    parser.add_argument("--output-dir", type=Path, help="Reserve this new evidence directory. Existing directories are rejected.")
    parser.add_argument("--run-name", help="Reserve acceptance-runs/NAME. Existing names are rejected.")
    parser.add_argument("--compare-to", type=Path, help="Compare with a saved run directory. Preserve the baseline.")
    parser.add_argument("--require-all", action="store_true", help="Exit 2 if any selected requirement is not met. Harness errors exit 1.")
    parser.add_argument("--validate-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    configure("never" if args.json or args.command == "reference" else args.color)
    if args.case_id and args.command != "show":
        parser.error("A positional case ID is valid only with show.")
    if args.command == "show" and not args.case_id:
        parser.error("Use show CASE_ID.")
    if args.case_id and args.case_id not in {case.name for case in CASES}:
        parser.error("Unknown case ID: " + args.case_id)
    selected = select_cases(args.case, args.group, args.sets)
    if not selected:
        parser.error("The selection contains no cases.")
    if args.command == "reference":
        print(reference_markdown(), end="")
        return
    if args.list or args.command == "list":
        if args.json:
            print(json.dumps([case_metadata(case) for case in selected], indent=2))
        else:
            for case in selected:
                print(paint(f"{case.name:29}", "title") + f" {case.group:12} {case.purpose}")
        return
    if args.command == "show":
        case = next(case for case in CASES if case.name == args.case_id)
        metadata = {**case_metadata(case), "comparisons": comparisons_for(case),
                    "evidence": POLICY_EVIDENCE[case.requirement_policy],
                    "artifacts": (["target/site/index.html", "target/site/apidocs/allclasses-index.html"]
                                  if case.fixture_kind == "site" else ["target/events.txt", "target/contributions.zip"]),
                    "execution": f"./acceptance-suite.sh run --case {case.name} --maven /path/to/mvn"}
        if args.json:
            print(json.dumps(metadata, indent=2))
        else:
            for title, value in (("Case", case.name), ("Group", case.group), ("Purpose", case.purpose),
                                 ("Requirement", case.requirement), ("Policy", case.requirement_policy),
                                 ("Fixture / assessment", case.fixture_kind + " / " + case.assessment_kind),
                                 ("Historical diagnostic", metadata["expected_diagnostic"]),
                                 ("Evidence", " ".join(metadata["evidence"].values())),
                                 ("Artifacts", ", ".join(metadata["artifacts"])),
                                 ("Limits", " ".join(metadata.get("limitations", []))),
                                 ("Comparisons", ", ".join(peer + " (" + label + ")" for peer, label in comparisons_for(case))),
                                 ("Execute", metadata["execution"])):
                print(paint(title + ":", "title") + " " + value)
        return
    if args.dry_run:
        common = ["-B", "-ntp", "-Dstyle.color=never", "-Dmaven.repo.local=<private-repository>",
                  "--settings", "<settings-file>", "--global-settings", "<global-settings-file>"]
        plans = [{"case": case.name, "command": build_command(case, Path("<run-directory>") / case.name, args.maven, common)}
                 for case in selected]
        if args.json:
            print(json.dumps(plans, indent=2))
        else:
            for plan in plans:
                print(paint(plan["case"] + ":", "title") + "\n$ " + shlex.join(plan["command"]))
            print("Preparation: build a teaching-plugin copy and use a private repository during an actual run.")
        return
    if args.validate_only:
        return
    if args.output_dir and args.run_name:
        parser.error("Use either --output-dir or --run-name.")
    if args.report_only or args.command == "report":
        directory = args.output_dir or (lab / "acceptance-runs" / args.run_name if args.run_name else latest_output(lab))
        if not directory.is_dir():
            parser.error("The saved run directory does not exist.")
        print(paint(generate_report(directory, compare_to=args.compare_to), "title"))
        return
    baseline = None
    try:
        if args.compare_to:
            baseline = read_results(args.compare_to)
        maven, version = preflight_command(args.maven)
        output = reserve_output(lab, args.output_dir, args.run_name)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    catalogue = [case_metadata(case) for case in CASES]
    manifest = {"schema_version": 2, "cases": [case_metadata(case) for case in selected], "catalogue": catalogue}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "maven-version.txt").write_text(version)
    provenance = {"maven_executable": maven, "suite_command": sys.argv, "version": version,
                  "selected_cases": [case.name for case in selected],
                  "comparison_limit": "Different source revisions can explain differences. A Maven version does not prove patch inclusion."}
    (output / "run.json").write_text(json.dumps(provenance, indent=2) + "\n")
    if baseline is not None:
        (output / "baseline.json").write_text(json.dumps({"directory": str(args.compare_to.resolve()),
            "results": baseline, "version": (args.compare_to / "maven-version.txt").read_text()
            if (args.compare_to / "maven-version.txt").exists() else "Not recorded"}, indent=2) + "\n")
    reports = []
    def save():
        (output / "results.json").write_text(json.dumps(reports, indent=2) + "\n")
        generate_report(output)
    print(paint("Run directory:", "title") + " " + str(output), flush=True)
    try:
        common = prepare(lab, output, maven)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        for case in selected:
            root = output / case.name
            root.mkdir()
            result = {**case_metadata(case), "execution_stage": "preparation", "assertions": "FAILED",
                      "requirement_state": "inconclusive", "requirement_reason": str(error), "observation": str(error),
                      "requirement_contract": requirement_contract(case), "events": [], "command": []}
            (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            reports.append(result)
        save()
        update(lab, output)
        print(paint("ERROR: " + str(error), "error") + "\nReport: " + str(output / "report.html"), flush=True)
        sys.exit(1)
    try:
        for case in selected:
            try:
                reports.append(run_case(case, output, maven, common))
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                result = {**case_metadata(case), "assertions": "FAILED", "requirement_state": "inconclusive",
                          "observation": str(error), "requirement_reason": str(error),
                          "requirement_contract": requirement_contract(case), "events": []}
                root = output / case.name
                root.mkdir(exist_ok=True)
                (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
                reports.append(result)
            save()
    finally:
        save()
        update(lab, output)
        print(paint("HTML report:", "title") + " " + str(output / "report.html"), flush=True)
    failures = sum(report["assertions"] != "passed" for report in reports)
    unmet = sum(report["requirement_state"] != "met" for report in reports)
    print(paint(f"{len(reports) - failures}/{len(reports)} harness checks passed.", "FAILED" if failures else "passed")
          + " " + paint(f"{len(reports) - unmet}/{len(reports)} selected requirements met.", "met" if not unmet else "inconclusive"))
    counts = Counter(report["requirement_state"] for report in reports)
    print("Requirements: " + " | ".join(paint(f"{state}={count}", state) for state, count in counts.items()))
    print("Exit 0 permits checked gaps. --require-all exits 2 for requirements that are not met. Harness errors exit 1.")
    sys.exit(1 if failures else 2 if args.require_all and unmet else 0)
