# SPDX-License-Identifier: Apache-2.0
"""Build an exact committed Maven tree without changing the selected checkout."""

from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import xml.etree.ElementTree as ET
from run_support import environment


def git(source, *arguments, **kwargs):
    return subprocess.run(["git", "-C", str(source), *arguments],
                          env={**environment(), "GIT_OPTIONAL_LOCKS": "0"}, check=True, **kwargs)


def resolve_source(source, revision="HEAD"):
    source = Path(source).expanduser().resolve()
    root = Path(git(source, "rev-parse", "--show-toplevel", capture_output=True, text=True).stdout.strip())
    if source != root:
        raise ValueError("Select the root of the Maven Git checkout.")
    commit = git(source, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}",
                 capture_output=True, text=True).stdout.strip()
    pom = git(source, "show", commit + ":pom.xml", capture_output=True).stdout
    git(source, "cat-file", "-e", commit + ":apache-maven/pom.xml", capture_output=True)
    try:
        version = ET.fromstring(pom).findtext("{http://maven.apache.org/POM/4.0.0}version", "")
    except ET.ParseError as error:
        raise ValueError("The selected revision has an invalid root pom.xml.") from error
    if not re.fullmatch(r"4\.(1|2)\..+", version):
        raise ValueError("Select a Maven 4.1.x or 4.2.x source revision.")
    return {"checkout": str(source), "requested_ref": revision, "commit": commit, "project_version": version,
            "inputs": "committed tree only"}


def build_command(bootstrap, distribution, settings):
    return [bootstrap, "-B", "-ntp", "-Dstyle.color=never", "--settings", str(settings),
            "--global-settings", str(settings), "-Dmaven.test.skip=true", "-Drat.skip=true", "-Dspotless.skip=true",
            "-DdistributionTargetDir=" + str(distribution), "package"]


def build_maven(spec, output, bootstrap, lab):
    bootstrap = shutil.which(bootstrap)
    if not bootstrap or not Path(bootstrap).is_file():
        raise ValueError("Cannot find the bootstrap Maven executable.")
    bootstrap = str(Path(bootstrap).resolve())
    area = Path(output) / "maven-build"
    area.mkdir(exist_ok=False)
    source, distribution = area / "source", area / "distribution"
    source.mkdir()
    metadata = {**spec, "bootstrap_executable": bootstrap,
                "checks_skipped": ["Maven core tests and test compilation", "RAT", "Spotless"], "build_status": "started"}
    record = area / "build.json"
    record.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Building Maven commit {spec['commit']}.\nBuild log: {area / 'build.log'}", flush=True)
    try:
        metadata["bootstrap_version"] = subprocess.run([bootstrap, "--version"], env=environment(), check=True,
                                                       capture_output=True, text=True).stdout
        settings = Path(os.environ.get("DEMO_MAVEN_SETTINGS", str(Path(lab) / "demo-settings.xml"))).resolve()
        if not settings.is_file():
            raise ValueError("Cannot find the source build settings file.")
        command = build_command(bootstrap, distribution, settings)
        metadata["build_command"] = command
        record.write_text(json.dumps(metadata, indent=2) + "\n")
        archive = area / "source.tar"
        with archive.open("wb") as stream:
            git(spec["checkout"], "archive", "--format=tar", spec["commit"], stdout=stream, stderr=subprocess.PIPE)
        with tarfile.open(archive) as tar:
            # Maven source export must contain only regular files and directories.
            members = tar.getmembers()
            for member in members:
                path = Path(member.name)
                if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
                    raise ValueError("The source export contains an unsupported archive entry.")
            tar.extractall(source, members=members)
        archive.unlink()
        with (area / "build.log").open("w") as log:
            completed = subprocess.run(command, cwd=source, env=environment(), stdout=log, stderr=subprocess.STDOUT)
        metadata["exit_code"] = completed.returncode
        if completed.returncode:
            raise RuntimeError(f"Maven source build failed with exit {completed.returncode}. Inspect maven-build/build.log.")
        executable = distribution / "bin/mvn"
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise RuntimeError("The source build did not produce distribution/bin/mvn.")
        metadata.update(build_status="succeeded", maven_executable=str(executable),
                        launcher_sha256=hashlib.sha256(executable.read_bytes()).hexdigest())
        return str(executable), metadata
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        metadata.update(build_status="failed", error=str(error))
        raise
    finally:
        record.write_text(json.dumps(metadata, indent=2) + "\n")
