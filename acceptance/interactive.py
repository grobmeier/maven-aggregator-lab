# SPDX-License-Identifier: Apache-2.0
"""Guide local lab runs and remember selections outside the repository."""

from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
import uuid
from catalogue import CASES, GROUPS
from interactive_ui import Cancelled, TerminalUI
from progress import read_results


@dataclass
class Selection:
    mode: str = "installation"
    target: str = ""
    revision: str = "HEAD"
    bootstrap: str = "mvn"
    scope: str = "all"
    group: str = "ordering"
    cases: tuple = ()
    compare_to: str = ""
    label: str = ""
    require_all: bool = False
    color: str = "auto"


def state_path():
    override = os.environ.get("MAVEN_LAB_STATE_DIR")
    root = Path(override).expanduser() if override else Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "maven-aggregator-lab"
    return root / "interactive.json"


def load_state(path):
    try:
        data = json.loads(path.read_text())
        if data.get("version") != 1 or not isinstance(data.get("history"), list):
            return {"version": 1, "history": []}
        keys = {field.name for field in fields(Selection)}
        history = []
        for record in data["history"][:10]:
            if not isinstance(record, dict) or set(record) - keys:
                continue
            value = Selection(**record)
            if (value.mode not in ("installation", "source") or value.scope not in ("all", "smoke", "group", "cases")
                    or value.color not in ("auto", "always", "never") or not isinstance(value.target, str)
                    or not isinstance(value.revision, str) or not isinstance(value.bootstrap, str)
                    or not isinstance(value.compare_to, str) or not isinstance(value.label, str)
                    or not isinstance(value.require_all, bool) or not isinstance(value.cases, (list, tuple))
                    or not all(isinstance(name, str) for name in value.cases)):
                continue
            history.append(asdict(value))
        return {"version": 1, "history": history}
    except (OSError, ValueError, TypeError, AttributeError):
        return {"version": 1, "history": []}


def save_selection(path, history, selection):
    value = json.loads(json.dumps(asdict(selection)))
    records = [value, *[record for record in history if record != value]][:10]
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix=".interactive-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump({"version": 1, "history": records}, stream, indent=2)
            stream.write("\n")
        os.replace(name, path)
    finally:
        if Path(name).exists():
            Path(name).unlink()


def maven_executable(target):
    path = Path(target).expanduser()
    for candidate in (path / "bin/mvn", path / "mvn", path):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    resolved = shutil.which(target)
    if resolved:
        return resolved
    raise ValueError("Select a Maven installation folder, its bin folder, or an executable mvn file.")


def pick_path(ui, title, previous, start):
    options = [(previous, previous)] if previous else []
    picked = ui.choose(title, [*options, ("Browse folders", "browse"), ("Type or paste a path", "type")])
    if picked == "browse":
        return str(ui.folder(title, previous or start))
    if picked == "type":
        return ui.text(title, previous)
    return picked


def configure(ui, lab, selection):
    previous_mode = selection.mode
    selection.mode = ui.choose("Which Maven should the lab test?", [("Built Maven 4.1.x or 4.2.x installation", "installation"),
                              ("Git source checkout and revision", "source")], selection.mode)
    if selection.mode != previous_mode:
        selection.target = ""
    if not selection.target:
        if selection.mode == "installation":
            selection.target = shutil.which(os.environ.get("MAVEN4", "mvn")) or ""
        elif (lab.parent / "maven/.git").exists():
            selection.target = str(lab.parent / "maven")
    selection.target = pick_path(ui, "Where is your Maven installation?" if selection.mode == "installation" else "Where is your Maven source checkout?",
                                 selection.target, lab.parent)
    if selection.mode == "installation":
        maven_executable(selection.target)
    else:
        from source_build import git, resolve_source
        refs = git(selection.target, "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes",
                   capture_output=True, text=True).stdout.splitlines()
        names = list(dict.fromkeys([selection.revision, "HEAD", *refs]))
        revision = ui.choose("Choose a revision. Only committed files will be built.",
                             [(name, name) for name in names] + [("Type a branch, tag, or commit", "type")], selection.revision)
        selection.revision = ui.text("Git revision", selection.revision) if revision == "type" else revision
        resolve_source(selection.target, selection.revision)
        detected = shutil.which(selection.bootstrap) or shutil.which("mvn") or ""
        selection.bootstrap = maven_executable(pick_path(ui, "Which Maven should build the source?", detected, lab.parent))
    selection.scope = ui.choose("Which cases should run?", [("All 25 cases", "all"), ("Smoke set: 3 ordering cases", "smoke"),
                                ("One group", "group"), ("Select individual cases", "cases")], selection.scope)
    if selection.scope == "group":
        selection.group = ui.choose("Choose a group", [(name, name) for name in GROUPS], selection.group)
    elif selection.scope == "cases":
        selection.cases = tuple(ui.many("Choose cases", [(case.name + ": " + case.purpose, case.name) for case in CASES],
                                       selection.cases or ("seq-after-all",)))
    runs = []
    for directory in sorted((lab / "acceptance-runs").glob("*"), key=lambda p: p.name, reverse=True):
        if directory.is_dir() and (directory / "results.json").is_file():
            runs.append((directory.name, str(directory.resolve())))
    selection.compare_to = ui.choose("Compare with a saved run?", [("No comparison", ""), *runs, ("Choose another run folder", "browse")], selection.compare_to)
    if selection.compare_to == "browse":
        selection.compare_to = str(ui.folder("Choose a saved run folder", lab / "acceptance-runs"))
    if selection.compare_to:
        read_results(selection.compare_to)
    selection.label = ui.text("Run label: optional. A unique suffix is automatic.", selection.label).strip()
    if selection.label and not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", selection.label):
        raise ValueError("Use letters, digits, dots, hyphens, or underscores for the run label.")
    selection.require_all = ui.choose("How should unmet requirements affect the exit code?",
                        [("Report checked gaps normally", False), ("Require every selected requirement to be met", True)], selection.require_all)
    selection.color = ui.choose("Terminal colors", [("Automatic", "auto"), ("Always", "always"), ("Never", "never")], selection.color)
    return selection


def arguments(selection):
    if selection.scope not in ("all", "smoke", "group", "cases") or selection.mode not in ("installation", "source"):
        raise ValueError("Select a supported Maven target and case scope.")
    result = ["run", "--color", selection.color]
    identity = ""
    if selection.mode == "source":
        from source_build import resolve_source
        spec = resolve_source(selection.target, selection.revision)
        identity = spec["commit"]
        result += ["--maven-source", spec["checkout"], "--maven-ref", identity,
                   "--bootstrap-maven", maven_executable(selection.bootstrap)]
    else:
        result += ["--maven", maven_executable(selection.target)]
    if selection.scope in ("all", "smoke"):
        result += ["--set", selection.scope]
    elif selection.scope == "group":
        if selection.group not in GROUPS:
            raise ValueError("Select an available case group.")
        result += ["--group", selection.group]
    else:
        if not selection.cases or set(selection.cases) - {case.name for case in CASES}:
            raise ValueError("Select available case IDs.")
        for name in selection.cases:
            result += ["--case", name]
    if selection.compare_to:
        read_results(selection.compare_to)
        result += ["--compare-to", str(Path(selection.compare_to).resolve())]
    if selection.require_all:
        result.append("--require-all")
    if selection.label:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", selection.label):
            raise ValueError("Use a valid run label.")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
        result += ["--run-name", selection.label + "-" + stamp]
    return result, identity


def wizard(ui, lab, path):
    while True:
        history = load_state(path)["history"]
        options = []
        if history:
            options.append(("Run last selection", "last"))
        options += [("Configure a run", "configure")]
        if history:
            options += [("Choose a previous selection", "history"), ("Forget saved selections", "forget")]
        options.append(("Quit", "quit"))
        try:
            action = ui.choose("Maven Aggregator Lab", options)
            if action == "quit":
                return None
            if action == "forget":
                if ui.choose("Forget saved selections? Saved run evidence remains available.", [("Keep selections", False), ("Forget selections", True)]):
                    try:
                        path.unlink(missing_ok=True)
                    except OSError as error:
                        ui.message(str(error))
                continue
            record = history[0] if history else {}
            if action == "history":
                record = ui.choose("Previous selections", [(item["mode"] + ": " + item["target"] + " [" + item["scope"] + "]", item) for item in history])
            selection = Selection(**record)
            if action == "configure":
                selection = configure(ui, lab, selection)
            while True:
                args, identity = arguments(selection)
                lines = ["Review your run", "Target: " + selection.target]
                if identity:
                    lines += ["Commit: " + identity, "Build skips Maven core tests. The lab cases still run."]
                scope = selection.scope
                if scope == "group":
                    scope += " / " + selection.group
                elif scope == "cases":
                    scope += " / " + ", ".join(selection.cases)
                lines += ["Cases: " + scope, "Compare: " + (selection.compare_to or "none"),
                          "Label: " + (selection.label or "automatic"),
                          "Strict requirements: " + str(selection.require_all), "Colors: " + selection.color]
                review = "\n".join(lines)
                chosen = ui.choose(review, [("Run", "run"), ("Preview commands only", "preview"), ("Edit selections", "edit"), ("Cancel", "cancel")])
                if chosen == "edit":
                    selection = configure(ui, lab, selection)
                    continue
                if chosen == "cancel":
                    break
                try:
                    save_selection(path, history, selection)
                except OSError as error:
                    ui.message("Could not save selections: " + str(error))
                return args + (["--dry-run"] if chosen == "preview" else [])
        except Cancelled:
            continue
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            ui.message(str(error))


def main():
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("Run ./run.sh in a terminal for interactive menus. Use acceptance-suite.sh for scripts.", file=sys.stderr)
        return 2
    try:
        import curses
    except ImportError:
        print("Interactive menus require Python curses support. Use acceptance-suite.sh for scripts.", file=sys.stderr)
        return 2
    try:
        lab = Path(__file__).resolve().parents[1]
        args = curses.wrapper(lambda screen: wizard(TerminalUI(screen, curses), lab, state_path()))
        if args is None:
            return 0
        command = [str(lab / "acceptance-suite.sh"), *args]
        print("$ " + shlex.join(command), flush=True)
        return subprocess.run(command).returncode
    except (Cancelled, KeyboardInterrupt):
        print("Cancelled.")
        return 130
    except (curses.error, OSError) as error:
        print("Cannot open interactive menus: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
