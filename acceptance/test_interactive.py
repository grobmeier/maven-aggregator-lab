# SPDX-License-Identifier: Apache-2.0
"""Check saved preferences and menu actions."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import interactive
import source_build
from interactive_ui import Cancelled, TerminalUI, display


class InteractiveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="lab-interactive-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.executable = self.root / "Maven with spaces/bin/mvn"
        self.executable.parent.mkdir(parents=True)
        self.executable.write_text("#!/bin/sh\nexit 0\n")
        self.executable.chmod(0o755)
        self.selection = interactive.Selection(target=str(self.executable.parent.parent), cases=("seq-after-all",))
        self.state = self.root / "state/interactive.json"

    def test_preferences_are_private_deduplicated_and_bounded(self):
        for index in range(12):
            self.selection.label = "run-" + str(index)
            interactive.save_selection(self.state, interactive.load_state(self.state)["history"], self.selection)
        interactive.save_selection(self.state, interactive.load_state(self.state)["history"], self.selection)
        history = interactive.load_state(self.state)["history"]
        self.assertEqual(len(history), 10)
        self.assertEqual(history[0]["cases"], ["seq-after-all"])
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.state.parent.glob(".interactive-*")), [])

    def test_corrupt_or_invalid_preferences_are_ignored(self):
        self.state.parent.mkdir()
        for content in ("{", "[]", '{"version":1,"history":[{"target":42},{"unknown":true}]}'):
            self.state.write_text(content)
            self.assertEqual(interactive.load_state(self.state)["history"], [])

    def test_installation_paths_and_arguments_preserve_spaces(self):
        for path in (self.executable, self.executable.parent, self.executable.parent.parent):
            self.assertEqual(interactive.maven_executable(str(path)), str(self.executable))
        self.selection.scope = "cases"
        arguments, identity = interactive.arguments(self.selection)
        self.assertEqual(arguments[arguments.index("--maven") + 1], str(self.executable))
        self.assertEqual(arguments[-2:], ["--case", "seq-after-all"])
        self.assertEqual(identity, "")
        self.selection.cases = ("unknown",)
        with self.assertRaises(ValueError):
            interactive.arguments(self.selection)

    def test_source_ref_is_pinned_before_execution(self):
        self.selection.mode = "source"
        self.selection.bootstrap = str(self.executable)
        spec = {"checkout": str(self.root), "commit": "a" * 40}
        with mock.patch.object(source_build, "resolve_source", return_value=spec):
            arguments, identity = interactive.arguments(self.selection)
        self.assertEqual(identity, "a" * 40)
        self.assertEqual(arguments[arguments.index("--maven-ref") + 1], identity)

    def test_preview_saves_choices_and_cancel_does_not(self):
        ui = mock.Mock()
        ui.choose.side_effect = ["configure", "preview"]
        with mock.patch.object(interactive, "configure", return_value=self.selection):
            args = interactive.wizard(ui, self.root, self.state)
        self.assertIn("--dry-run", args)
        self.assertEqual(len(interactive.load_state(self.state)["history"]), 1)
        before = self.state.read_bytes()
        ui.choose.side_effect = ["last", "cancel", "quit"]
        self.assertIsNone(interactive.wizard(ui, self.root, self.state))
        self.assertEqual(self.state.read_bytes(), before)

    def test_escape_returns_home_and_forget_preserves_run_evidence(self):
        interactive.save_selection(self.state, [], self.selection)
        evidence = self.root / "results.json"
        evidence.write_text("[]")
        ui = mock.Mock()
        ui.choose.side_effect = [Cancelled(), "forget", True, "quit"]
        self.assertIsNone(interactive.wizard(ui, self.root, self.state))
        self.assertFalse(self.state.exists())
        self.assertEqual(evidence.read_text(), "[]")

    def test_folder_browser_selects_directory_and_handles_hidden_folders(self):
        ui = object.__new__(TerminalUI)
        child = self.root / ".hidden"
        child.mkdir()
        ui.choose = mock.Mock(side_effect=["hidden", child, "select"])
        self.assertEqual(ui.folder("Maven", self.root), child)
        self.assertNotIn((".hidden/", child), ui.choose.call_args_list[0].args[1])
        self.assertIn((".hidden/", child), ui.choose.call_args_list[1].args[1])
        self.assertEqual(display("bad\x1b[31m\npath"), "bad [31m path")

    def test_nonterminal_has_no_state_side_effects(self):
        with mock.patch.object(sys.stdin, "isatty", return_value=False), mock.patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(interactive.main(), 2)
        self.assertFalse(self.state.exists())




if __name__ == "__main__":
    unittest.main()
