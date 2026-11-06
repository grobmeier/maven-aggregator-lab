# SPDX-License-Identifier: Apache-2.0
"""Immutable case definitions shared by the catalogue, runner, and checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class Case:
    name: str
    builder: str = "concurrent"
    threads: int = 1
    phase: str = "after:all"
    single: bool = False
    failure: str = ""
    selection: str = ""
    contributors: str = "selected"
    lifecycle: str = "package"
    expectation: str = "success"
    nested: bool = False
    inheritance: str = ""
    purpose: str = "Run start once before contributions, then aggregate once after them."
    order: int = 1000
    observation: str = ""
    group: str = "ordering"
    requirement_policy: str = "ordered"
    requirement: str = "Run one start before the intended contributors and one successful end after them."
    fixture_kind: str = "markers"
    assessment_kind: str = "markers"
    active_contributors: tuple[str, ...] = ()
    failure_stage: str = ""
    sets: tuple[str, ...] = ()
    comparisons: tuple[tuple[str, str], ...] = ()
    contract_version: int = 1
    limitations: tuple[str, ...] = ("This case measures one bounded fixture, not every Maven invocation.",)


@dataclass(frozen=True)
class Execution:
    root: Path
    command: tuple[str, ...]
    exit_code: int
    log: str


@dataclass(frozen=True)
class Assessment:
    state: str
    assertions: str
    observation: str
    reason: str
    events: tuple[str, ...]
    details: dict[str, Any] | None = None

    def fields(self):
        return {**(self.details or {}), "requirement_state": self.state,
                "assertions": self.assertions, "observation": self.observation,
                "requirement_reason": self.reason, "events": list(self.events)}


@dataclass(frozen=True)
class Handler:
    function: Callable
    dependencies: tuple[Callable, ...] = ()
    constants: tuple = ()
