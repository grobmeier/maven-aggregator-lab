# SPDX-License-Identifier: Apache-2.0
"""Case definitions for failure."""

from model import Case


CASES = [
    Case(
        'failure-fast',
        failure='--fail-fast',
        expectation='child-failure',
        purpose='Fail contributor a. Distinguish cleanup and attempted aggregation from success.',
        group='failure',
        requirement_policy='failure_safety',
        requirement='Allow the start hook, distinguish cleanup, and prevent successful aggregation for a failed build.',
        comparisons=(('failure-end', 'Failure policy only'),),
        order=8,
    ),
    Case(
        'failure-end',
        failure='--fail-at-end',
        expectation='child-failure',
        purpose='Change only the failure policy from failure-fast. Check independent contributor b.',
        group='failure',
        requirement_policy='failure_safety',
        requirement='Allow the start hook, distinguish cleanup, and prevent successful aggregation for a failed build.',
        order=9,
    ),
    Case(
        'failure-after-output',
        lifecycle='verify',
        failure='--fail-fast',
        expectation='false-success',
        purpose='Fail verification after contributions exist. Check whether after:all still creates a ZIP.',
        group='failure',
        requirement_policy='success_only',
        requirement='Allow the start hook, distinguish cleanup, and prevent successful aggregation for a failed build.',
        failure_stage='after-output',
        order=11,
    ),
]
