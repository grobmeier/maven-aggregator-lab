# SPDX-License-Identifier: Apache-2.0
"""Case definitions for inheritance."""

from model import Case


CASES = [
    Case(
        'inheritance-off',
        inheritance='off',
        purpose='Disable inherited hook bindings. Check one root start and finish.',
        group='inheritance',
        requirement_policy='ordered',
        requirement='Run one start before the intended contributors and one successful end after them.',
        comparisons=(('inheritance-on', 'Inheritance flag only'), ('explicit-child-hooks', 'Explicit child hook declarations')),
        order=18,
    ),
    Case(
        'inheritance-on',
        inheritance='on',
        expectation='inherited-copies',
        purpose='Change only inheritance from inheritance-off. Count copies despite aggregator=true.',
        group='inheritance',
        requirement_policy='ordered',
        requirement='Run one start before the intended contributors and one successful end after them.',
        order=19,
    ),
    Case(
        'explicit-child-hooks',
        inheritance='explicit',
        expectation='explicit-copies',
        purpose='Keep inheritance disabled, then add independent start and finish bindings in child a.',
        group='inheritance',
        requirement_policy='observation',
        requirement='Observe independently declared child hooks. Duplicate suppression policy is undefined for explicit declarations.',
        order=20,
    ),
]
