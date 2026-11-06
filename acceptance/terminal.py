# SPDX-License-Identifier: Apache-2.0
"""Apply terminal colors without changing saved evidence or machine-readable output."""

from contextvars import ContextVar
import os
import sys


_mode = ContextVar("acceptance_color_mode", default="auto")
COLORS = {"met": "32", "not_met": "31", "inconclusive": "33", "undefined_policy": "33",
          "observation_only": "36", "not_run": "90", "passed": "32", "FAILED": "31",
          "title": "1;36", "note": "2", "error": "31"}


def configure(mode):
    if mode not in ("auto", "always", "never"):
        raise ValueError("Select auto, always, or never for terminal colors.")
    _mode.set(mode)


def paint(text, role, stream=None):
    stream = sys.stdout if stream is None else stream
    enabled = _mode.get() == "always" or (_mode.get() == "auto" and "NO_COLOR" not in os.environ
              and os.environ.get("TERM") != "dumb" and stream.isatty())
    return f"\033[{COLORS[role]}m{text}\033[0m" if enabled else str(text)
