# SPDX-License-Identifier: Apache-2.0
"""Prepare isolated suite runs while preserving saved evidence and user outputs."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid
import xml.etree.ElementTree as ET


def environment():
    result = os.environ.copy()
    for name in ("MAVEN_OPTS", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS"):
        if re.search(r"jdwp|Xdebug", result.get(name, "")):
            raise ValueError("Remove inherited JDWP flags before running non-debug acceptance cases.")
    for name in ("MAVEN_ARGS", "MAVEN_DEBUG_OPTS"):
        result.pop(name, None)
    return result


def preflight(requested):
    executable = shutil.which(requested)
    if not executable or not Path(executable).is_file():
        raise ValueError("Cannot find the requested Maven executable.")
    executable = str(Path(executable).resolve())
    version = subprocess.run([executable, "--version"], env=environment(), check=True,
                             capture_output=True, text=True).stdout
    plain = re.sub(r"\x1b\[[0-9;]*m", "", version)
    if not re.search(r"Apache Maven 4\.(1|2)\.", plain):
        raise ValueError("Use Maven 4.1.x or 4.2.x. The version does not establish prototype support.")
    return executable, plain


def reserve_output(lab, output_dir=None, run_name=None):
    if output_dir and run_name:
        raise ValueError("Use either --output-dir or --run-name.")
    if run_name and not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", run_name):
        raise ValueError("Use letters, digits, dots, hyphens, or underscores for the run name.")
    name = run_name or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    output = Path(output_dir).resolve() if output_dir else lab / "acceptance-runs" / name
    # Never clear or reuse a directory, including an empty one.
    output.mkdir(parents=True, exist_ok=False)
    return output


def prepare_plugin(lab, output, maven):
    tool = output / "tooling"
    tool.mkdir()
    source = lab / "demo-plugin"
    plugin = tool / "demo-plugin"
    plugin.mkdir()
    shutil.copy2(source / "pom.xml", plugin / "pom.xml")
    shutil.copytree(source / "src", plugin / "src",
                    ignore=shutil.ignore_patterns("target", ".git", ".idea", ".DS_Store", "__pycache__"))
    global_settings = tool / "global-settings.xml"
    shutil.copy2(lab / "demo-settings.xml", global_settings)
    settings = ET.Element("settings", xmlns="http://maven.apache.org/SETTINGS/1.2.0")
    cache = Path.home() / ".m2/repository"
    if cache.is_dir():
        profile = ET.SubElement(ET.SubElement(settings, "profiles"), "profile")
        ET.SubElement(profile, "id").text = "read-only-cache"
        for container, entry in (("repositories", "repository"), ("pluginRepositories", "pluginRepository")):
            repo = ET.SubElement(ET.SubElement(profile, container), entry)
            ET.SubElement(repo, "id").text = "read-only-cache"
            ET.SubElement(repo, "url").text = cache.as_uri()
            for policy in ("releases", "snapshots"):
                node = ET.SubElement(repo, policy)
                ET.SubElement(node, "enabled").text = "true"
                ET.SubElement(node, "checksumPolicy").text = "ignore"
        ET.SubElement(ET.SubElement(settings, "activeProfiles"), "activeProfile").text = "read-only-cache"
    user_settings = tool / "settings.xml"
    ET.ElementTree(settings).write(user_settings, encoding="utf-8", xml_declaration=True)
    custom = os.environ.get("DEMO_MAVEN_SETTINGS")
    if custom:
        user_settings = Path(custom).resolve()
        if not user_settings.is_file():
            raise ValueError("Cannot find DEMO_MAVEN_SETTINGS.")
    common = ["-B", "-ntp", "-Dstyle.color=never", f"-Dmaven.repo.local={tool / 'repository'}",
              "--settings", str(user_settings), "--global-settings", str(global_settings)]
    command = [maven, *common, "-f", str(plugin / "pom.xml"), "clean", "install"]
    (output / "preparation-command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (output / "plugin-build.log").open("w") as log:
        result = subprocess.run(command, cwd=tool, env=environment(), stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"Teaching plugin preparation failed with exit {result.returncode}. Inspect plugin-build.log.")
    return common


def latest_output(lab):
    pointer = lab / "acceptance-runs/latest.json"
    if pointer.is_file():
        return Path(json.loads(pointer.read_text())["directory"])
    return lab / "target/acceptance"


def update_latest(lab, output):
    parent = lab / "acceptance-runs"
    parent.mkdir(exist_ok=True)
    temporary = parent / (".latest-" + uuid.uuid4().hex + ".json")
    temporary.write_text(json.dumps({"directory": str(output)}, indent=2) + "\n")
    temporary.replace(parent / "latest.json")
