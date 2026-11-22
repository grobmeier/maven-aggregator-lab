# SPDX-License-Identifier: Apache-2.0
"""Check source exports, build evidence, and failure reporting."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import source_build
import cli


class SourceBuildTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="lab-source-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.spec = {"checkout": str(self.root), "requested_ref": "branch", "commit": "a" * 40}
        (self.root / "demo-settings.xml").write_text("<settings/>")
        self.bootstrap = self.root / "bootstrap"
        self.bootstrap.write_text("#!/bin/sh\nexit 0\n")
        self.bootstrap.chmod(0o755)

    def archive(self, *args, **kwargs):
        with tarfile.open(fileobj=kwargs["stdout"], mode="w") as archive:
            entry = tarfile.TarInfo("pom.xml")
            entry.size = 4
            archive.addfile(entry, io.BytesIO(b"test"))

    def execute(self, command, **kwargs):
        if "package" in command:
            distribution = next(value.split("=", 1)[1] for value in command if value.startswith("-DdistributionTargetDir="))
            launcher = Path(distribution) / "bin/mvn"
            launcher.parent.mkdir(parents=True)
            launcher.write_text("#!/bin/sh\nexit 0\n")
            launcher.chmod(0o755)
        return subprocess.CompletedProcess(command, 0, stdout="Apache Maven bootstrap")

    def test_export_build_and_provenance_without_git_mutation(self):
        with mock.patch.object(source_build, "git", side_effect=self.archive) as git, mock.patch.object(source_build.subprocess, "run", side_effect=self.execute), redirect_stdout(io.StringIO()):
            executable, evidence = source_build.build_maven(self.spec, self.root, str(self.bootstrap), self.root)
        self.assertTrue(Path(executable).is_file())
        self.assertEqual(evidence["build_status"], "succeeded")
        self.assertEqual(evidence["commit"], self.spec["commit"])
        self.assertEqual(len(evidence["launcher_sha256"]), 64)
        self.assertEqual(git.call_args.args[1:], ("archive", "--format=tar", self.spec["commit"]))
        self.assertEqual((self.root / "maven-build/source/pom.xml").read_text(), "test")
        self.assertFalse((self.root / "maven-build/source.tar").exists())
        with self.assertRaises(FileExistsError):
            source_build.build_maven(self.spec, self.root, str(self.bootstrap), self.root)

    def test_failure_keeps_log_and_failure_record(self):
        def failed(command, **kwargs):
            if "package" in command:
                kwargs["stdout"].write("build failed\n")
                return subprocess.CompletedProcess(command, 1)
            return self.execute(command, **kwargs)
        with mock.patch.object(source_build, "git", side_effect=self.archive), mock.patch.object(source_build.subprocess, "run", side_effect=failed), redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):
                source_build.build_maven(self.spec, self.root, str(self.bootstrap), self.root)
        evidence = json.loads((self.root / "maven-build/build.json").read_text())
        self.assertEqual(evidence["build_status"], "failed")
        self.assertEqual(evidence["exit_code"], 1)
        self.assertEqual((self.root / "maven-build/build.log").read_text(), "build failed\n")

    def test_archive_rejects_paths_outside_export(self):
        def unsafe(*args, **kwargs):
            with tarfile.open(fileobj=kwargs["stdout"], mode="w") as archive:
                entry = tarfile.TarInfo("../../escaped")
                entry.size = 0
                archive.addfile(entry, io.BytesIO())
        with mock.patch.object(source_build, "git", side_effect=unsafe), mock.patch.object(source_build.subprocess, "run", side_effect=self.execute), redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):
                source_build.build_maven(self.spec, self.root, str(self.bootstrap), self.root)
        self.assertFalse((self.root / "escaped").exists())

    def test_resolve_requires_root_supported_version_and_commit_ref(self):
        pom = b'<project xmlns="http://maven.apache.org/POM/4.0.0"><version>4.2.0-SNAPSHOT</version></project>'
        responses = [subprocess.CompletedProcess([], 0, str(self.root)), subprocess.CompletedProcess([], 0, "a" * 40),
                     subprocess.CompletedProcess([], 0, pom), subprocess.CompletedProcess([], 0)]
        with mock.patch.object(source_build, "git", side_effect=responses) as git:
            spec = source_build.resolve_source(self.root, "--bad")
        self.assertEqual(spec["commit"], "a" * 40)
        self.assertIn("--end-of-options", git.call_args_list[1].args)
        with mock.patch.object(source_build, "git", return_value=subprocess.CompletedProcess([], 0, str(self.root.parent))):
            with self.assertRaises(ValueError):
                source_build.resolve_source(self.root)

    def test_cli_build_failure_marks_cases_inconclusive_without_running_them(self):
        output = self.root / "evidence"
        runner, prepare = mock.Mock(), mock.Mock()
        argv = ["acceptance-suite.sh", "run", "--maven-source", str(self.root), "--case", "seq-after-all",
                "--output-dir", str(output)]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(source_build, "resolve_source", return_value=self.spec), mock.patch.object(source_build, "build_maven", side_effect=RuntimeError("source failed")), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as stopped:
                cli.main(self.root, runner, prepare, mock.Mock(), mock.Mock())
        self.assertEqual(stopped.exception.code, 1)
        runner.assert_not_called()
        prepare.assert_not_called()
        results = json.loads((output / "results.json").read_text())
        self.assertEqual(results[0]["requirement_state"], "inconclusive")
        self.assertEqual(results[0]["execution_stage"], "source-build")
        self.assertIn(self.spec["commit"], (output / "report.html").read_text())


if __name__ == "__main__":
    unittest.main()
