# SPDX-License-Identifier: Apache-2.0
"""Verify terminal color policy and preserve machine-readable evidence."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import runner
import suite
from terminal import configure, paint


LAB = Path(__file__).resolve().parents[1]


class TTY(io.StringIO):
    def isatty(self):
        return True


class TerminalTests(unittest.TestCase):
    def setUp(self):
        configure("auto")
        self.addCleanup(configure, "auto")

    def test_auto_uses_semantic_colors_only_for_terminals(self):
        with mock.patch.dict(os.environ, {"TERM": "xterm"}, clear=True):
            self.assertEqual(paint("met", "met", TTY()), "\033[32mmet\033[0m")
            self.assertEqual(paint("not_met", "not_met", TTY()), "\033[31mnot_met\033[0m")
            self.assertEqual(paint("inconclusive", "inconclusive", TTY()), "\033[33minconclusive\033[0m")
            self.assertEqual(paint("met", "met", io.StringIO()), "met")

    def test_auto_respects_no_color_and_dumb_terminals(self):
        for environment in ({"TERM": "xterm", "NO_COLOR": ""}, {"TERM": "dumb"}):
            with self.subTest(environment=environment), mock.patch.dict(os.environ, environment, clear=True):
                self.assertEqual(paint("met", "met", TTY()), "met")

    def test_explicit_modes_override_automatic_detection(self):
        with mock.patch.dict(os.environ, {"NO_COLOR": "1", "TERM": "dumb"}, clear=True):
            configure("always")
            self.assertIn("\033[", paint("met", "met", io.StringIO()))
            configure("never")
            self.assertEqual(paint("met", "met", TTY()), "met")

    def call(self, *arguments):
        return subprocess.run(["bash", str(LAB / "acceptance-suite.sh"), *arguments],
                              cwd=LAB, capture_output=True, text=True, timeout=15)

    def test_json_and_generated_markdown_stay_plain_when_color_is_forced(self):
        for arguments in (("list", "--json"), ("show", "seq-after-all", "--json"),
                          ("run", "--set", "smoke", "--dry-run", "--json"), ("reference",)):
            with self.subTest(arguments=arguments):
                result = self.call(*arguments, "--color", "always")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("\033[", result.stdout)
                if "--json" in arguments:
                    json.loads(result.stdout)

    def test_text_output_supports_forced_and_disabled_colors(self):
        colored = self.call("list", "--color", "always")
        plain = self.call("list", "--color", "never")
        automatic = self.call("list")
        self.assertIn("\033[", colored.stdout)
        self.assertNotIn("\033[", plain.stdout)
        self.assertEqual(automatic.stdout, plain.stdout)

    def test_colored_requirement_and_harness_results_do_not_contaminate_evidence(self):
        with tempfile.TemporaryDirectory(prefix="color-evidence-") as directory:
            for mode, state, assertions, code in (("gap", "not_met", "passed", 0), ("error", "inconclusive", "FAILED", 1)):
                with self.subTest(mode=mode):
                    output = Path(directory) / mode
                    def execute(command, **kwargs):
                        root = Path(kwargs["cwd"])
                        (root / "target").mkdir()
                        (root / "target/events.txt").write_text("start:fixture-root\ncleanup:fixture-root\nend-attempt:fixture-root\n")
                        kwargs["stdout"].write("DEMO_MISSING_CONTRIBUTIONS:a,b\n" if mode == "gap" else "Unrelated compiler error\n")
                        return subprocess.CompletedProcess(command, 1 if mode == "gap" else 17)
                    text = io.StringIO()
                    with mock.patch.object(suite, "preflight", return_value=("mvn", "Apache Maven 4.2.0")), \
                            mock.patch.object(suite, "prepare_plugin", return_value=[]), \
                            mock.patch.object(suite, "update_latest"), \
                            mock.patch.object(runner.subprocess, "run", side_effect=execute), \
                            mock.patch("sys.argv", ["suite", "run", "--case", "seq-after-all", "--output-dir", str(output), "--color", "always"]), \
                            redirect_stdout(text):
                        with self.assertRaises(SystemExit) as stopped:
                            suite.main()
                    self.assertEqual(stopped.exception.code, code)
                    self.assertIn(paint(state, state), text.getvalue())
                    self.assertIn(paint(assertions, assertions), text.getvalue())
                    result = json.loads((output / "seq-after-all/result.json").read_text())
                    self.assertEqual(result["requirement_state"], state)
                    self.assertEqual(result["assertions"], assertions)
                    for path in [output / "results.json", output / "seq-after-all/result.json", output / "seq-after-all/build.log"]:
                        self.assertNotIn("\033[", path.read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
