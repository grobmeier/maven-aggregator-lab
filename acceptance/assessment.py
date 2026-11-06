# SPDX-License-Identifier: Apache-2.0
"""Assess declared requirements from concrete events and output evidence."""

from dataclasses import replace
from pathlib import Path
import zipfile
from diagnostics import check
from evidence import require, read_events, check_zip, check_missing
from model import Handler


def expected_contributors(case):
    if case.active_contributors:
        return list(case.active_contributors)
    if case.nested:
        return ["group/a"] if case.selection else ["group/a", "group/b"]
    if case.single:
        return ["."]
    return ["a", "b"]

def assess(case, root, result, log):
    """Recognize checked requirements and known counterexamples with one fixed oracle."""
    events = read_events(root)
    # First check the intended successful trace, even for historically failing cases.
    selection = ".,a,!b" if case.expectation == "no-root" else case.selection
    normalized = replace(case, expectation="success", selection=selection,
                         inheritance="off" if case.inheritance == "on" else case.inheritance)
    try:
        observation, _ = check(normalized, root, result, log)
        owner = "group" if case.nested else "fixture-single" if case.single else "fixture-root"
        require(not any(event.startswith("child-failure:") for event in events), "A successful trace contains a child failure.")
        workers = {"fixture-single" if name == "." else Path(name).name for name in expected_contributors(case)}
        if case.nested and not case.selection:
            workers.add("outside")
        require({event.split(":", 1)[1] for event in events if event.startswith("work:")} == workers,
                "The contribution trace has the wrong selected scope.")
        if case.inheritance != "explicit":
            for action in ("start", "cleanup", "end-attempt", "end-success"):
                require([event for event in events if event.startswith(action + ":")] == [action + ":" + owner],
                        "The hooks must execute only once at their owner.")
        require(events.index("cleanup:" + owner) < events.index("end-attempt:" + owner) < events.index("end-success:" + owner),
                "Cleanup, end attempt, and end success have the wrong order.")
        if case.inheritance and case.inheritance != "explicit":
            work_positions = [index for index, event in enumerate(events) if event.startswith("work:")]
            require(work_positions and max(work_positions) < events.index("finish:" + owner),
                    "The owner finish hook ran before the contributions.")
        if case.failure:
            raise AssertionError("The deliberate child failure did not occur.")
        state = "observation_only" if case.requirement_policy == "observation" else "met"
        return state, "passed", observation, "Ordered contributions, exact hook counts, and matching ZIP contents passed."
    except (AssertionError, OSError, zipfile.BadZipFile, ValueError):
        pass

    # Failure aggregation has a defined safety requirement. Cleanup policy remains separate.
    if case.failure and result != 0 and "DEMO_CHILD_FAILURE:a" in log and events.count("child-failure:a") == 1:
        owner = "fixture-root"
        archive = root / "target/contributions.zip"
        start = "start:" + owner
        failure_stage_valid = ((events.count("work:a") == 1 and events.index("work:a") < events.index("child-failure:a")
                                and (root / "a/target/contribution.txt").is_file()) if case.requirement_policy == "success_only"
                               else "work:a" not in events and not (root / "a/target/contribution.txt").exists())
        independent_work_valid = case.failure != "--fail-at-end" or events.count("work:b") == 1
        if (failure_stage_valid and independent_work_valid and events.count(start) == 1
                and events[0] == start and len(events) == len(set(events))):
            if not archive.exists() and not any(event.startswith("end-success:") for event in events):
                # Reject unrelated errors after the deliberate failure when no end diagnostic explains them.
                errors = [line for line in log.splitlines() if line.startswith("[ERROR] Failed to execute goal")]
                if all("DEMO_CHILD_FAILURE:a" in line or "DEMO_MISSING_CONTRIBUTIONS:" in line for line in errors):
                    state = "met" if case.requirement_policy == "success_only" else "undefined_policy"
                    reason = "The deliberate child failure produced no successful aggregate. Cleanup and end-attempt policy remains undefined."
                    return state, "passed", reason, reason

    # A complete output trace can establish a count/order violation without a build error.
    if result == 0 and not case.failure:
        contributors = expected_contributors(case)
        try:
            check_zip(root, contributors)
            require(all(events.count("work:" + ("fixture-single" if name == "." else Path(name).name)) == 1
                        for name in contributors), "The contribution trace is incomplete.")
            # Package timing and explicit child declarations remain observations.
            if case.requirement_policy != "observation" and not case.inheritance:
                reason = "Complete contribution outputs exist, but the required hook counts or event order did not pass."
                return "not_met", "passed", reason, reason
        except (AssertionError, OSError, zipfile.BadZipFile):
            pass

    # The old diagnostic is a recognized counterexample, never a green requirement.
    try:
        observation, _ = check(case, root, result, log)
        if case.expectation in ("early", "timing-diagnostic", "missing-b") and result != 0:
            owner = "group" if case.nested else "fixture-root"
            cutoff = events.index("end-attempt:" + owner)
            required = ["a", "b"] if case.expectation != "missing-b" else ["b"]
            require(any("work:" + worker not in events[:cutoff] for worker in required),
                    "The missing-output diagnostic does not match the event order.")
        state = "observation_only" if case.requirement_policy == "observation" else "not_met"
        if case.requirement_policy == "failure_safety":
            state = "undefined_policy"
        return state, "passed", observation, observation
    except (AssertionError, OSError, zipfile.BadZipFile, ValueError) as error:
        diagnostic_error = str(error)
    # A previously passing ordering case can regress to the same exact early-output failure.
    if result != 0 and not case.failure and not case.nested and not case.single and not case.inheritance:
        try:
            observation, _ = check(replace(case, expectation="timing-diagnostic"), root, result, log)
            reason = "Checked early-output counterexample: " + observation
            return "not_met", "passed", reason, reason
        except (AssertionError, OSError, zipfile.BadZipFile, ValueError):
            pass
    reason = "Unrecognized or incomplete evidence: " + diagnostic_error
    return "inconclusive", "FAILED", reason, reason


def evaluate_markers(case, execution):
    from model import Assessment
    state, assertions, observation, reason = assess(case, execution.root, execution.exit_code, execution.log)
    return Assessment(state, assertions, observation, reason, tuple(read_events(execution.root)))


# New assessment families require explicit registration, never case-ID branches.
from fixtures.site import evaluate as evaluate_site
from fixtures.site import _check as check_site, _require as require_site, SITE_VERSION, JAVADOC_VERSION
EVALUATORS = {
    "markers": Handler(evaluate_markers, (assess, expected_contributors, check, require, read_events, check_zip, check_missing)),
    "site": Handler(evaluate_site, (check_site, require_site), (SITE_VERSION, JAVADOC_VERSION)),
}


def evaluate(case, execution):
    return EVALUATORS[case.assessment_kind].function(case, execution)


POLICY_EVIDENCE = {
    "ordered": {
        "met": "Require a successful exit, exact owner hook counts, ordered active contributions, and matching ZIP bytes.",
        "not_met": "Require a checked missing-output trace or complete outputs with a concrete hook or scope violation.",
        "inconclusive": "Unrelated failures, corrupt ZIPs, and incomplete traces cannot establish the requirement.",
    },
    "observation": {
        "observation_only": "Check the declared timing, selection, or explicit-hook trace without claiming an agreed barrier requirement.",
        "inconclusive": "An unrecognized trace or unrelated build failure remains inconclusive.",
    },
    "failure_safety": {
        "undefined_policy": "Verify the deliberate failure stage and absence of successful aggregation. Cleanup policy remains unresolved.",
        "inconclusive": "Unrelated failures or an incorrect deliberate failure stage remain inconclusive.",
    },
    "success_only": {
        "met": "Verify failure after output creation and absence of successful aggregation.",
        "not_met": "Verify a ZIP and end-success marker after the deliberate verification failure.",
        "inconclusive": "Require the exact deliberate failure and output evidence before assigning a requirement result.",
    },
    "rendered_site": {
        "met": "Check rendered content, both documented classes, one aggregate report, and actual log execution counts.",
        "inconclusive": "Missing pages or failed rendering remain inconclusive. This case does not measure a child-site barrier.",
    },
}
