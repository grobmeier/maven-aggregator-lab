# SPDX-License-Identifier: Apache-2.0
"""Generate a self-contained, offline report from real acceptance case JSON files."""

import argparse
from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import re
import shlex
from progress import STATES, compare_runs, read_results, state


STATUSES = {
    "met": ("✓", "Met in this fixture"),
    "known-gap": ("!", "Known requirement gap"),
    "expected-failure": ("!", "Expected failure reproduced"),
    "observation": ("i", "Observation only"),
    "unexpected": ("×", "Unexpected assertion failure"),
    "incomplete": ("…", "Incomplete or missing result"),
}

# Each pair changes one input in the controlled fixtures.
from catalogue import COMPARISONS


def outcome_reason(result, status):
    """Explain checked observations without assigning a cause to unexpected failures."""
    if result.get("requirement_reason"):
        return result["requirement_reason"]
    if status == "unexpected":
        return ("Inconclusive: the build or checker result differs from the expected diagnostic. "
                "Check the observed result and Maven log. No Maven scheduling cause is established.")
    if status == "incomplete":
        return "Inconclusive: a complete result is missing. Check case JSON and available logs before interpreting the experiment."
    name = result.get("case", "")
    events = result.get("events", [])
    expectation = result.get("expectation")
    builder = result.get("builder", "recorded")
    binding = result.get("end_binding", "recorded")
    if expectation == "child-failure" and "child-failure:a" in events:
        return ("Contributor a failed before producing its output. Cleanup and the end attempt still ran. "
                "The checked missing contribution prevented a successful aggregate.")
    if expectation == "false-success" and "child-failure:a" in events and "end-success:fixture-root" in events:
        return ("The trace records end success after the child failure. Available contribution files let the collector create a ZIP. "
                "Maven still exited with failure, so this end hook is not success-only.")
    if expectation == "no-root" and events == ["work:a"]:
        return ("The selection excludes the root that owns the hooks. Only child work is recorded. "
                "Root-bound hooks cannot act as session hooks in this selected build.")
    if expectation == "missing-b" and "work:a" in events:
        return ("Only a contributes, but the fixed contributor list still requires excluded b. "
                "The checked missing-b failure concerns contributor selection, not builder timing.")
    if expectation == "inherited-copies" and all("start:" + owner in events for owner in ("fixture-root", "a", "b")):
        return ("Root, a, and b each record start and finish hooks. Inheritance copied those bindings. "
                "The aggregator flag did not suppress the copies.")
    if expectation == "explicit-copies" and "start:a" in events:
        return ("Child a records its independently declared hooks despite disabled inheritance. "
                "Disabling inherited bindings does not remove a child's own executions.")
    if name == "partial-root-expansion" and "work:b" in events:
        return "The selection includes the root. Maven expanded that selection to its children, so both a and b contribute."
    if name.startswith("nested-") and "start:group" in events:
        return ("Group-owned hooks surround the selected group contributions. The checked ZIP excludes the outside sibling. "
                "This demonstrates the fixture's active-descendant convention.")
    if name == "inheritance-off" and "finish:fixture-root" in events:
        return "Only the root records start and finish hooks. Disabled inheritance prevents child copies in this fixture."
    if expectation == "real-site-rendering" and result.get("evidence", {}).get("aggregate_javadoc_execution_count") == 1:
        return ("One actual aggregate report contains both source classes. Root reporting precedes child sites. "
                "This checks source aggregation, not a completed-child-site barrier.")
    attempts = [i for i, event in enumerate(events) if event.startswith("end-attempt:")]
    work = [i for i, event in enumerate(events) if event.startswith("work:")]
    if status == "known-gap" and attempts and expectation in ("early", "timing-diagnostic"):
        if result.get("lifecycle") == "site":
            return (f"The root after:site attempt precedes child contributions with the {builder} builder. "
                    "This hook-only trace does not establish reactor-wide site ordering.")
        return (f"The root end attempt precedes required child contributions with the {builder} builder and {binding} binding. "
                "The exact missing-output diagnostic reproduces this timing gap.")
    if attempts and work and max(work) < attempts[0]:
        if result.get("single_project"):
            return "One project records its contribution between start and end. No cross-project child barrier is needed."
        if result.get("lifecycle") == "site":
            return ("This site trace places contributions before the end attempt. "
                    "A successful interleaving does not establish a site child barrier.")
        if builder == "concurrent" and binding == "after:all":
            return ("The trace places required contributions before the end attempt. "
                    "With concurrent after:all, this matches the child barrier checked by this fixture.")
    return "The saved diagnostic reports this outcome. Check the event trace and Maven log before assigning a more specific cause."


def comparison_links(name, selected):
    items = []
    for left, right, change in COMPARISONS:
        peer = right if name == left else left if name == right else None
        if peer is None:
            continue
        if peer in selected:
            metadata = selected[peer]
            context = f"{metadata.get('builder', 'builder not recorded')} · {metadata.get('end_binding', 'binding not recorded')}"
            target = f'<a class="case-link" href="#case-{peer}">{peer}</a>'
            items.append(f"<li>{safe_text(change)}: {target} <span class=\"note\">({safe_text(context)})</span></li>")
        else:
            items.append(f"<li>{safe_text(change)}: <code>{peer}</code> <span class=\"note\">(not selected)</span></li>")
    return '<div class="paired"><h3>Controlled comparisons</h3><ul>' + "".join(items) + "</ul></div>" if items else ""


def safe_text(value):
    """Redact runtime filesystem paths before HTML escaping."""
    text = str(value)
    text = re.sub(r"(?<!\w)/(?:[^\s<>\"']+)", "[local path]", text)
    text = re.sub(r"[A-Za-z]:\\[^\r\n<>\"']+", "[local path]", text)
    return escape(text, quote=True)


def status_for(result):
    if not result or result.get("assertions") not in ("passed", "FAILED"):
        return "incomplete"
    if result["assertions"] != "passed":
        return "unexpected"
    if "requirement_state" in result:
        return {"met": "met", "not_met": "known-gap", "inconclusive": "unexpected",
                "observation_only": "observation", "undefined_policy": "observation"}.get(result["requirement_state"], "incomplete")
    if result.get("expectation") == "child-failure":
        return "expected-failure"
    observation = result.get("observation", "")
    if observation.startswith("KNOWN GAP:"):
        return "known-gap"
    if observation.startswith("OBSERVED"):
        return "observation"
    if observation.startswith("REQUIREMENT MET IN FIXTURE:"):
        return "met"
    return "incomplete"


def public_command(command):
    tokens = []
    redact_next = False
    for index, token in enumerate(command):
        if index == 0:
            tokens.append("$MAVEN4")
        elif redact_next:
            tokens.append("demo-settings.xml")
            redact_next = False
        elif token in ("--settings", "--global-settings"):
            tokens.append(token)
            redact_next = True
        elif token.startswith("-Ddemo.eventRoot="):
            tokens.append("-Ddemo.eventRoot=<case-directory>")
        elif token.startswith("/") or re.match(r"[A-Za-z]:\\", token):
            tokens.append("<local-path>")
        else:
            tokens.append(token)
    return safe_text(shlex.join(tokens))


def load_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as error:
        return {"read_error": str(error)}


def progress_section(directory, manifest, compare_to=None):
    catalogue = manifest.get("catalogue", manifest.get("cases", []))
    records = []
    for spec in manifest.get("cases", []):
        if not re.fullmatch(r"[a-z0-9-]+", spec.get("case", "")):
            continue
        result_path = directory / spec["case"] / "result.json"
        record = load_json(result_path)
        if isinstance(record, dict) and record.get("case"):
            records.append(record)
        elif result_path.exists():
            records.append({"case": spec["case"], "requirement_state": "inconclusive",
                            "requirement_reason": "The saved case result is malformed."})
    if manifest.get("schema_version") != 2 and not any("requirement_state" in item for item in records):
        return ""
    if compare_to:
        baseline = {"directory": str(Path(compare_to).resolve()), "results": read_results(compare_to),
                    "version": (Path(compare_to) / "maven-version.txt").read_text()
                    if (Path(compare_to) / "maven-version.txt").exists() else "Not recorded"}
        (directory / "baseline.json").write_text(json.dumps(baseline, indent=2) + "\n")
    baseline = load_json(directory / "baseline.json")
    has_baseline = isinstance(baseline, dict) and isinstance(baseline.get("results"), list)
    comparison = compare_runs(records, baseline["results"] if has_baseline else [], catalogue)
    counts = Counter(state(item) for item in records)
    counts["not_run"] = len(catalogue) - len(records)
    comparison["requirement_counts"] = {key: counts[key] for key in STATES}
    comparison["has_baseline"] = has_baseline
    (directory / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
    summary = "".join(f'<span class="requirement-stat state-{key}"><b>{counts[key]}</b> {key.replace("_", " ")}</span>' for key in STATES)
    version = (baseline.get("version") or "Not recorded").splitlines()[0] if has_baseline else "No baseline selected"
    description = ("Baseline: " + safe_text(version) + ". Compare only matching fixture contracts. "
                   "Different source revisions can explain differences. Version numbers do not prove patch inclusion.")
    changes = " · ".join(f"{safe_text(key.replace('_', ' '))}: {count}" for key, count in comparison["counts"].items()) if has_baseline else "Single run. Select --compare-to SAVED_RUN to measure progress."
    rows = []
    for row in comparison["rows"]:
        name = row["case"]
        if not re.fullmatch(r"[a-z0-9-]+", name):
            continue
        target = f'<a class="case-link" href="#case-{name}">{name}</a>' if row["current"] != "not_run" else safe_text(name)
        change = row["change"] if has_baseline else "not compared"
        rows.append(f'<tr><th scope="row">{target}</th><td>{safe_text(row["baseline"]) if has_baseline else "—"}</td>'
                    f'<td class="state-{row["current"]}">{safe_text(row["current"])}</td><td>{safe_text(change)}</td></tr>')
    return f'''<section class="progress"><h2>Requirement progress</h2><p>{summary}</p>
<p class="note">Requirement counts are separate from harness assertions. Not run means no current measurement.</p>
<p>{description}</p><p><strong>{changes}</strong></p>
<p class="note">Inconclusive evidence cannot establish a regression or a fix. Changed fixture contracts are incomparable.
Failure safety and cleanup policy are separate. Undefined policy never counts as met.</p>
<div class="table-scroll"><table><thead><tr><th>Case</th><th>Baseline</th><th>Current</th><th>Change</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div><p><a href="comparison.json">Comparison JSON</a> · <a href="run.json">Run provenance</a>
{' · <a href="baseline.json">Saved baseline evidence</a>' if has_baseline else ''}</p></section>'''


def generate_report(directory, compare_to=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = load_json(directory / "manifest.json")
    specs = manifest.get("cases", []) if isinstance(manifest, dict) else []
    manifest_missing = not specs
    if not specs:
        specs = [{"case": path.parent.name} for path in sorted(directory.glob("*/result.json"))]
    selected = {spec.get("case"): spec for spec in specs}
    roadmap = progress_section(directory, manifest, compare_to) if isinstance(manifest, dict) else ""
    cards = []
    counts = Counter()
    assertion_count = 0
    completed_count = 0
    for spec in specs:
        name = spec.get("case", "")
        if not re.fullmatch(r"[a-z0-9-]+", name):
            continue
        path = directory / name / "result.json"
        result = load_json(path)
        if not isinstance(result, dict):
            result = {"read_error": "The result must be a JSON object."}
        merged = {**spec, **result}
        status = status_for(result)
        counts[status] += 1
        assertion_count += result.get("assertions") == "passed" and status != "incomplete"
        completed_count += status != "incomplete"
        icon, label = STATUSES[status]
        observation = result.get("observation", result.get("read_error", "This selected case has no complete result yet."))
        events = result.get("events", [])
        sequence = "".join(f"<li><code>{safe_text(event)}</code></li>" for event in events)
        if not sequence:
            sequence = "<li>No events recorded.</li>"
        links = []
        for relative, title in (("result.json", "Case JSON"), ("build.log", "Maven log"),
                                ("pom.xml", "Fixture POM"), ("target/events.txt", "Events")):
            if (directory / name / relative).is_file():
                links.append(f'<a href="{escape(name + "/" + relative, quote=True)}">{title}</a>')
        for artifact in result.get("artifact_links", []):
            relative = artifact.get("path", "")
            if relative and not Path(relative).is_absolute() and ".." not in Path(relative).parts:
                if (directory / name / relative).is_file():
                    links.append(f'<a href="{escape(name + "/" + relative, quote=True)}">{safe_text(artifact.get("label", "Generated artifact"))}</a>')
        binding = merged.get("end_binding", "Not recorded")
        selection = merged.get("selection") or ("one project" if merged.get("single_project") else "full reactor")
        details = f"""<dl>
<div><dt>Builder</dt><dd>{safe_text(merged.get('builder', 'Not recorded'))} · {safe_text(merged.get('threads', '?'))} worker</dd></div>
<div><dt>Lifecycle / end binding</dt><dd>{safe_text(merged.get('lifecycle', '?'))} / {safe_text(binding)}</dd></div>
<div><dt>Project scope</dt><dd>{safe_text(selection)}</dd></div>
<div><dt>Maven exit / assertions</dt><dd>{safe_text(result.get('exit_code', 'Not recorded'))} / {safe_text(result.get('assertions', 'Incomplete'))}</dd></div>
</dl>"""
        if result.get("plugin_versions"):
            versions = " · ".join(f"{safe_text(plugin)} {safe_text(version)}" for plugin, version in result["plugin_versions"].items())
            details += f'<p class="note">Report plugins: {versions}</p>'
        if result.get("limitations"):
            details += '<p class="note">Limits: ' + " ".join(safe_text(item) for item in result["limitations"]) + '</p>'
        if "requirement_state" in result:
            details += '<p><strong>Requirement: ' + safe_text(result["requirement_state"]) + '</strong></p>'
        reason = safe_text(outcome_reason(merged, status))
        diagnostic_title = "Historical diagnostic" if "requirement_state" in result else "Expected diagnostic"
        meaning = {
            "known-gap": "Diagnostic assertions passed. The intended requirement remains unmet in this case.",
            "expected-failure": "Diagnostic assertions passed for the deliberate failed build, not for successful aggregation.",
            "observation": "Diagnostic assertions passed for this trace. No broader scheduling guarantee follows.",
            "met": "Diagnostic assertions passed for the bounded fixture requirement.",
            "unexpected": "Unexpected result. This experiment does not establish the intended Maven behaviour.",
            "incomplete": "No complete diagnostic result. Do not treat this case as support or a known scheduling gap.",
        }[status]
        if result.get("requirement_state") == "undefined_policy":
            meaning = "Failure safety passed. Cleanup and end-attempt policy remains undefined, so this case does not count as met."
        cards.append(f"""<article id="case-{escape(name)}" data-case="{escape(name)}" data-status="{status}">
<header><h2>{safe_text(name)}</h2><span class="badge {status}">{icon} {label}</span></header>
<p class="purpose">{safe_text(merged.get('purpose', 'No purpose recorded.'))}</p>{details}
<div class="comparison"><div><h3>Intended requirement</h3><p>{safe_text(merged.get('intended_requirement', 'Not recorded.'))}</p>
<h3>{diagnostic_title}</h3><p>{safe_text(merged.get('expected_diagnostic', merged.get('expectation', 'Not recorded.')))}</p></div>
<div><h3>Observed result</h3><p>{safe_text(observation)}</p></div></div>
<div class="reason"><h3>Why this outcome?</h3><p>{reason}</p><p class="note">{meaning}</p></div>
{comparison_links(name, selected)}
<details><summary>Inspect events and command</summary><ol>{sequence}</ol>
<p class="note">Runtime paths are replaced with portable placeholders.</p>
<pre><code>{public_command(result.get('command', [])) or 'Command not recorded.'}</code></pre></details>
<footer>{' · '.join(links) or 'No case files available.'}</footer></article>""")
    version_lines = []
    version_path = directory / "maven-version.txt"
    if version_path.exists():
        for line in version_path.read_text().splitlines():
            if line.startswith("Apache Maven"):
                version_lines.append(line)
            elif line.startswith("Java version:"):
                version_lines.append(line.split(", runtime:")[0])
            elif line.startswith("OS name:"):
                version_lines.append(line)
    version = " · ".join(safe_text(line) for line in version_lines) or "Maven version metadata is missing."
    summary = "".join(f'<button data-filter="{key}" class="stat {key}"><strong>{counts[key]}</strong><span>{icon} {label}</span></button>'
                      for key, (icon, label) in STATUSES.items())
    warning = ""
    if manifest_missing:
        warning = '<p class="warning">The case manifest is missing. Expected coverage is unknown. Available results alone do not establish completeness.</p>'
    if not specs:
        warning += '<p class="warning">No case results are available. Run the acceptance suite to produce observations.</p>'
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="icon" href="data:,"><title>Maven Aggregator Lab — acceptance report</title>
<style>
:root{{color-scheme:light;--ink:#17243b;--muted:#536176;--line:#dce3ed;--paper:#fff;--bg:#f3f5f9}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,sans-serif}}
.masthead{{background:#14243c;color:#fff;padding:42px max(24px,calc((100vw - 1160px)/2)) 36px;border-bottom:5px solid #6495cf}}
.eyebrow{{text-transform:uppercase;letter-spacing:.13em;font-size:12px;color:#c1d1e5;font-weight:700}}h1{{font-size:clamp(28px,4vw,42px);line-height:1.15;margin:10px 0}}
.masthead p{{max-width:870px;margin:12px 0 0;color:#d8e2ef}}main{{max-width:1208px;padding:28px 24px 50px;margin:auto}}
.summary{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:20px 0}}button{{font:inherit;cursor:pointer}}
.stat{{text-align:left;border:1px solid var(--line);border-radius:12px;padding:16px;display:flex;flex-direction:column;gap:3px;background:white}}
.stat strong{{font-size:30px;line-height:1.2}}.stat span{{font-size:13px;font-weight:650}}button:focus-visible,a:focus-visible,summary:focus-visible{{outline:3px solid #2865a9;outline-offset:3px}}
.met{{background:#e8f5ec;color:#175d38}}.known-gap,.expected-failure{{background:#fff1cc;color:#715000}}.observation{{background:#e8f0fe;color:#244c82}}
.progress{{background:white;border:1px solid var(--line);border-radius:14px;padding:24px;margin:18px 0}}.requirement-stat{{display:inline-block;padding:8px;margin:3px;border-radius:6px}}
.state-met{{background:#e8f5ec;color:#175d38}}.state-not_met{{background:#fce8e8;color:#8f2525}}.state-inconclusive,.state-not_run{{background:#e9edf2;color:#354052}}
.state-observation_only,.state-undefined_policy{{background:#e8f0fe;color:#244c82}}.table-scroll{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{padding:9px;text-align:left;border-bottom:1px solid var(--line)}}
.unexpected{{background:#fce8e8;color:#8f2525}}.incomplete{{background:#e9edf2;color:#354052}}
.toolbar{{display:flex;align-items:center;justify-content:space-between;gap:15px;margin:22px 0}}.toolbar button{{border:1px solid #aebdd0;border-radius:8px;background:white;color:var(--ink);padding:7px 13px}}
a{{color:#23578d;text-decoration-thickness:1px;text-underline-offset:3px}}.note{{font-size:14px;color:var(--muted)}}.warning{{background:#fff1cc;border-left:4px solid #a07820;padding:12px 18px}}
article{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:24px;margin:18px 0;box-shadow:0 3px 12px #17243b05}}
article header{{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}}h2{{font-size:21px;line-height:1.3;margin:0}}h3{{font-size:12px;text-transform:uppercase;letter-spacing:.06em;margin:0 0 7px;color:var(--muted)}}
.badge{{display:inline-flex;border-radius:30px;font-size:12px;font-weight:700;padding:6px 11px}}.purpose{{margin:12px 0 18px}}
dl{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;padding:15px 0;border-block:1px solid var(--line);margin:0 0 18px}}dt{{font-size:12px;color:var(--muted)}}dd{{margin:4px 0 0;font-size:14px;overflow-wrap:anywhere}}
.comparison{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}.comparison p{{margin:0 0 14px}}details{{border-top:1px solid var(--line);margin-top:10px;padding-top:13px}}summary{{cursor:pointer;font-weight:650;font-size:14px}}ol{{padding-left:26px}}li{{margin:5px 0}}
.reason{{background:#f3f5f9;border-left:3px solid #9aadc5;padding:14px 16px;margin:8px 0 16px}}.reason p{{margin:0 0 7px}}.reason p:last-child{{margin-bottom:0}}.paired ul{{padding-left:20px}}article{{scroll-margin-top:18px}}
code{{font:13px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace}}pre{{background:#f3f5f9;padding:16px;border-radius:8px;white-space:pre-wrap;overflow-wrap:anywhere}}footer{{margin-top:16px;font-size:13px}}[hidden]{{display:none!important}}
@media(max-width:760px){{.summary{{grid-template-columns:repeat(2,minmax(0,1fr))}}dl{{grid-template-columns:1fr 1fr}}.comparison{{grid-template-columns:1fr;gap:8px}}article{{padding:18px}}}}
@media print{{body{{background:white}}.masthead{{background:white;color:var(--ink);padding:15px}}.masthead p,.eyebrow{{color:var(--ink)}}button{{cursor:default}}article{{break-inside:avoid;box-shadow:none}}.toolbar{{display:none}}}}
</style></head><body><header class="masthead"><div class="eyebrow">Local investigation · issue #47</div>
<h1>Maven Aggregator Lab</h1><p>Lifecycle acceptance report. Passing diagnostic assertions can expose known requirement gaps. Expected failures do not mean the feature works.</p></header>
<main><p><strong>{assertion_count} cases passed their diagnostic assertions.</strong> {completed_count} of {sum(counts.values())} selected cases have complete results.</p>
<p class="note">{version}<br>Report generated {generated}. Runtime paths are omitted from this HTML.</p>{warning}
{roadmap}
<section class="summary" aria-label="Case status counts">{summary}</section>
<p class="note">Green applies only to the fixture's bounded requirement. Amber identifies a gap or a reproduced failure. Blue records an observation. Red identifies unexpected assertions. Grey means incomplete.</p>
<div class="toolbar"><button data-filter="all">Show all cases</button><a href="results.json">Raw combined JSON</a><a href="../../coverage.md">Expert coverage map</a></div>
<section aria-label="Case results">{''.join(cards)}</section>
<p class="note">This local report does not establish a complete runtime fix. Raw JSON and logs retain local execution details.</p></main>
<script>document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{{const selected=button.dataset.filter;document.querySelectorAll('article[data-status]').forEach(card=>{{card.hidden=selected!=='all'&&card.dataset.status!==selected;}});}}));</script>
<script>document.querySelectorAll('a.case-link').forEach(link=>link.addEventListener('click',()=>{{document.querySelectorAll('article[data-status]').forEach(card=>{{card.hidden=false;}});}}));</script>
</body></html>"""
    output = directory / "report.html"
    output.write_text(html)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=Path(__file__).resolve().parents[1] / "target/acceptance")
    parser.add_argument("--compare-to", type=Path, help="Compare with a saved run without changing its evidence.")
    args = parser.parse_args()
    print(generate_report(args.results_dir, compare_to=args.compare_to))


if __name__ == "__main__":
    main()
