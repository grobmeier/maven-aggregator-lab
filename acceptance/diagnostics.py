# SPDX-License-Identifier: Apache-2.0
"""Recognize historical traces independently from desired requirement states."""

from pathlib import Path
from evidence import require, read_events, check_zip, check_missing


def check(case, root, result, log):
    events = read_events(root)
    owner = "group" if case.nested else ("fixture-single" if case.single else "fixture-root")
    starts = events.count("start:" + owner)
    attempts = events.count("end-attempt:" + owner)
    ends = events.count("end-success:" + owner)
    cleanups = events.count("cleanup:" + owner)
    for event in set(events):
        require(events.count(event) == 1, f"The event executed more than once: {event}")
    if case.expectation == "no-root":
        require(result == 0, "The selected contributor build failed.")
        require(events == ["work:a"], "Unexpected root hooks or contributor events in the root-excluded build.")
        require(not (root / "target/contributions.zip").exists(), "A root aggregate exists despite root exclusion.")
        return "KNOWN GAP: root bindings do not provide hooks when the root is excluded.", events
    require(starts == 1, "The start hook must execute exactly once.")
    if not case.nested:
        require(events[0] == "start:" + owner, "A contributor or end hook ran before the start hook.")
    require(attempts <= 1 and ends <= 1 and cleanups <= 1, "A root hook executed more than once.")
    archive = root / "target/contributions.zip"
    if case.expectation == "false-success":
        require(result != 0 and "DEMO_CHILD_FAILURE:a" in log, "The deliberate verification failure did not occur.")
        require(events.count("child-failure:a") == 1, "Contributor a must fail exactly once after its output exists.")
        require(attempts == ends == cleanups == 1, "The expected false-success diagnostic changed.")
        for name in ("a", "b"):
            require(events.index("work:" + name) < events.index("end-attempt:" + owner), "An output was not ready at aggregation.")
        require(events.index("work:a") < events.index("child-failure:a") < events.index("end-attempt:" + owner),
                "The diagnostic must fail after output creation and before aggregation.")
        check_zip(root, ["a", "b"])
        return "KNOWN GAP: the build failed verification, but after:all still created a successful ZIP.", events
    if case.expectation == "child-failure":
        require(result != 0 and "DEMO_CHILD_FAILURE:a" in log, "The deliberate child failure did not occur.")
        require(events.count("child-failure:a") == 1, "Contributor a must fail exactly once.")
        require(not (root / "a/target/contribution.txt").exists(), "The failed contributor produced successful output.")
        require(not archive.exists() and ends == 0, "The failed build falsely produced a successful aggregate.")
        require(cleanups == attempts == 1, "The observed cleanup and end-attempt policy changed.")
        missing = ",".join(name for name in ("a", "b") if "work:" + name not in events[:events.index("end-attempt:" + owner)])
        check_missing(log, missing)
        require(events.index("child-failure:a") < events.index("cleanup:" + owner) < events.index("end-attempt:" + owner),
                "The cleanup and end hooks must follow the deliberate failure in this diagnostic.")
        if case.failure == "--fail-at-end":
            require("work:b" in events, "The independent contributor b did not complete with fail-at-end.")
        return f"FAILED BUILD DETECTED: cleanup={cleanups}, end-attempt={attempts}, end-success={ends}.", events
    if case.expectation in ("early", "missing-b", "timing-diagnostic") and result != 0:
        require(attempts == 1 and ends == 0, "The early aggregate did not execute exactly once without success.")
        expected = "b" if case.expectation == "missing-b" else "a,b"
        if case.expectation == "timing-diagnostic":
            expected = ",".join(name for name in ("a", "b") if "work:" + name not in events[:events.index("end-attempt:" + owner)])
            require(expected, "The timing diagnostic did not identify an absent contributor.")
        check_missing(log, expected)
        require(not archive.exists(), "The failed aggregation produced a ZIP.")
        return f"KNOWN GAP: aggregation ran before required contributions ({expected}).", events
    require(case.expectation not in ("early", "missing-b"), "A previously failing ordering case unexpectedly succeeded.")
    require(result == 0, "The lifecycle build failed. Inspect build.log.")
    require(attempts == ends == cleanups == 1, "Start, cleanup, and successful end must each execute exactly once.")
    if case.nested:
        contributors = ["group/a"] if case.selection else ["group/a", "group/b"]
        require("start:fixture-root" not in events, "The outer root must not own the group hooks.")
        if case.selection:
            require("work:b" not in events and "work:outside" not in events, "The selected group built excluded contributors.")
        else:
            require(events.count("work:outside") == 1, "The independent outside sibling did not execute.")
    else:
        contributors = list(case.active_contributors) if case.active_contributors else (["."] if case.single else ["a", "b"])
    for name in contributors:
        worker = "fixture-single" if name == "." else Path(name).name
        event = "work:" + worker
        require(event in events, f"The contributor did not execute: {worker}")
        require(events.index("start:" + owner) < events.index(event), "A required contributor ran before the group start.")
        require(events.index(event) < events.index("end-attempt:" + owner), "Aggregation started before a required contribution.")
    check_zip(root, contributors)
    if case.inheritance:
        actors = ["fixture-root"] + (["a", "b"] if case.inheritance == "on" else (["a"] if case.inheritance == "explicit" else []))
        for actor in ("fixture-root", "a", "b"):
            for action in ("start", "finish"):
                require(events.count(action + ":" + actor) == int(actor in actors), "The inherited or explicitly declared hook count differs.")
            if actor != "fixture-root" and actor in actors:
                require(events.index("start:" + actor) < events.index("work:" + actor) < events.index("finish:" + actor),
                        "The child's hooks must surround its own contribution.")
        if case.inheritance == "on":
            return "KNOWN GAP: aggregator=true did not suppress inherited start/finish copies; each ran in root, a, and b.", events
        if case.inheritance == "explicit":
            return "OBSERVED EXPLICIT COPIES: inheritance is disabled, but child a's own start/finish bindings still execute.", events
    if case.observation:
        return case.observation, events
    if case.expectation == "timing-diagnostic":
        return "OBSERVED SUCCESS: this execution order is not a guaranteed child barrier.", events
    return "REQUIREMENT MET IN FIXTURE: one start, ordered contributions, one successful end.", events
