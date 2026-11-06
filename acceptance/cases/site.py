# SPDX-License-Identifier: Apache-2.0
"""Case definitions for site."""

from model import Case


CASES = [
    Case(
        'site-seq',
        builder='singlethreaded',
        phase='after:site',
        lifecycle='site',
        expectation='early',
        purpose='Check root before:site and after:site hooks in a multi-module site lifecycle.',
        group='site',
        requirement_policy='ordered',
        requirement='Run one start before the intended contributors and one successful end after them.',
        comparisons=(('site-concurrent', 'Builder only'),),
        order=21,
    ),
    Case(
        'site-concurrent',
        phase='after:site',
        lifecycle='site',
        expectation='timing-diagnostic',
        purpose='Change only the builder from site-seq. Observe site child ordering.',
        group='site',
        requirement_policy='ordered',
        requirement='Run one start before the intended contributors and one successful end after them.',
        order=22,
    ),
    Case(
        'site-single',
        builder='singlethreaded',
        single=True,
        phase='after:site',
        lifecycle='site',
        purpose='Check the site hooks in one project without a child-ordering requirement.',
        group='site',
        requirement_policy='ordered',
        requirement='Run one start before the intended contributors and one successful end after them.',
        order=23,
    ),
    Case(
        'real-site-report',
        builder='singlethreaded',
        lifecycle='site',
        expectation='real-site-rendering',
        purpose='Render an actual Maven site and one aggregate Javadoc report from two child source trees.',
        group='site',
        requirement_policy='rendered_site',
        requirement='Generate real aggregate documentation and a rendered site from multiple module inputs.',
        fixture_kind='site',
        assessment_kind='site',
        order=24,
    ),
]
