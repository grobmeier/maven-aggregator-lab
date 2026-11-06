# SPDX-License-Identifier: Apache-2.0
"""Compatibility entry point. Case definitions and execution live in dedicated modules."""

from pathlib import Path
from model import Case
from catalogue import CASES, case_metadata
from fixtures.markers import create_fixture, create_nested, execution, pom, child_pom
from diagnostics import check
from evidence import require, read_events, check_zip, check_missing
from assessment import assess, expected_contributors
from contracts import requirement_contract
from runner import run
from run_support import preflight, prepare_plugin, update_latest
import cli


def main():
    cli.main(lab=Path(__file__).resolve().parents[1], run_case=run, prepare=prepare_plugin,
             preflight_command=preflight, update=update_latest)


if __name__ == "__main__":
    main()
