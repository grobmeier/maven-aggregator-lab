# SPDX-License-Identifier: Apache-2.0
"""Execute one declared case through shared preparation and evidence handling."""

import json
from pathlib import Path
import shlex
import subprocess
from catalogue import case_metadata
from contracts import requirement_contract, compatible_contracts
from assessment import evaluate
from fixtures import build
from model import Execution
from planning import build_command
from run_support import environment
from terminal import paint


def run(case, output, maven, common):
    root = Path(output) / case.name
    build(root, case)
    command = build_command(case, root, maven, common)
    print("\n" + paint(case.name + ":", "title") + f" {case.purpose}\n$ {shlex.join(command)}", flush=True)
    (root / "command.txt").write_text(shlex.join(command) + "\n")
    with (root / "build.log").open("w") as log:
        completed = subprocess.run(command, cwd=root, env=environment(), stdout=log, stderr=subprocess.STDOUT)
    execution = Execution(root, tuple(command), completed.returncode, (root / "build.log").read_text())
    assessment = evaluate(case, execution)
    report = {**case_metadata(case), "command": command, "exit_code": execution.exit_code,
              **assessment.fields(), "requirement_contract": requirement_contract(case)}
    report["compatible_requirement_contracts"] = compatible_contracts(case)
    if case.fixture_kind == "site":
        events_path = root / "target/events.txt"
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text("\n".join(assessment.events) + ("\n" if assessment.events else ""))
    print("Requirement: " + paint(assessment.state, assessment.state) + " | Harness: " + paint(assessment.assertions, assessment.assertions)
          + f"\n{assessment.reason}\nEvents: "
          + ", ".join(assessment.events), flush=True)
    (root / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
