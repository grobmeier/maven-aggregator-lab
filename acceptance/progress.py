# SPDX-License-Identifier: Apache-2.0
"""Compare saved requirement results without inferring success from Maven versions."""

from collections import Counter
import json
from pathlib import Path


STATES = ("met", "not_met", "inconclusive", "observation_only", "undefined_policy", "not_run")


def state(result):
    if not result:
        return "not_run"
    # Historical diagnostic success is not evidence for the new requirement contract.
    value = result.get("requirement_state", "inconclusive")
    return value if value in STATES else "inconclusive"


def contracts_match(old, new):
    left, right = old.get("requirement_contract"), new.get("requirement_contract")
    if not isinstance(left, str) or not isinstance(right, str) or not left or not right:
        return False
    if left == right:
        return True
    # Explicit migration aliases come from reviewed fixture and assessment equivalence.
    return ((left.startswith("aggregation-fixture-v1:") and right.startswith("aggregation-fixture-v2:")
             and left in new.get("compatible_requirement_contracts", []))
            or (right.startswith("aggregation-fixture-v1:") and left.startswith("aggregation-fixture-v2:")
                and right in old.get("compatible_requirement_contracts", [])))


def compare_runs(current, baseline, catalogue):
    """Keep absent cases separate from measured regressions."""
    now = {item["case"]: item for item in current}
    before = {item["case"]: item for item in baseline}
    rows = []
    for spec in catalogue:
        name = spec["case"]
        old, new = before.get(name), now.get(name)
        old_state, new_state = state(old), state(new)
        if old_state == "not_run" or new_state == "not_run":
            change = "not_run"
        elif not contracts_match(old, new):
            change = "incomparable"
        elif "inconclusive" in (old_state, new_state):
            change = "inconclusive"
        elif old_state == "not_met" and new_state == "met":
            change = "improved"
        elif old_state == "met" and new_state == "not_met":
            change = "regressed"
        elif old_state == new_state:
            change = "unchanged_unmet" if new_state == "not_met" else "unchanged"
        else:
            change = "policy_or_observation"
        rows.append({"case": name, "baseline": old_state, "current": new_state, "change": change})
    return {"rows": rows, "counts": dict(Counter(row["change"] for row in rows))}


def read_results(directory):
    value = json.loads((Path(directory) / "results.json").read_text())
    if not isinstance(value, list) or any(not isinstance(item, dict) or "case" not in item for item in value):
        raise ValueError("The saved results must contain a list of case objects.")
    if len({item["case"] for item in value}) != len(value):
        raise ValueError("The saved results contain duplicate case IDs.")
    return value
