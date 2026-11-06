# SPDX-License-Identifier: Apache-2.0
"""Fingerprint case semantics and selected shared helpers, independently from the CLI."""

from dataclasses import asdict
import hashlib
import inspect
import json
from pathlib import Path
from assessment import EVALUATORS
from fixtures import BUILDERS
from planning import build_command


DISPLAY_FIELDS = {"purpose", "order", "observation", "group", "sets", "comparisons", "limitations"}
COMPATIBILITY = Path(__file__).with_name("compatibility") / "contracts-v1.json"


def handler_contract(handler):
    return {"sources": [inspect.getsource(function) for function in (handler.function, *handler.dependencies)],
            "constants": handler.constants}


def requirement_contract(case):
    semantics = {key: value for key, value in asdict(case).items() if key not in DISPLAY_FIELDS}
    payload = {"schema": 2, "case": semantics,
               "command": build_command(case, Path("<case>"), "<maven>", []),
               "fixture": handler_contract(BUILDERS[case.fixture_kind]),
               "assessment": handler_contract(EVALUATORS[case.assessment_kind])}
    # The marker plugin participates in marker fixtures. Site rendering has separate plugin versions.
    if case.fixture_kind == "markers":
        plugin = Path(__file__).resolve().parents[1] / "demo-plugin"
        paths = [plugin / "pom.xml", *sorted((plugin / "src").rglob("*"))]
        payload["plugin"] = {str(path.relative_to(plugin)): hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in paths if path.is_file() and path.name != ".DS_Store"}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return "aggregation-fixture-v2:" + digest


def compatible_contracts(case):
    if not COMPATIBILITY.is_file():
        return []
    migration = json.loads(COMPATIBILITY.read_text()).get(case.name, {})
    # The alias stops applying when this case or any selected semantic dependency changes.
    return migration.get("legacy", []) if migration.get("current") == requirement_contract(case) else []
