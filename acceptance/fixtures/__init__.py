# SPDX-License-Identifier: Apache-2.0
"""Explicit fixture registry shared by planning and execution."""

from fixtures.markers import create_fixture, create_nested, execution, pom, child_pom, PLUGIN
from fixtures.site import _create_fixture, _pom, SITE_VERSION, JAVADOC_VERSION
from model import Handler


def create_site(root, case):
    _create_fixture(root)


BUILDERS = {
    "markers": Handler(create_fixture, (create_nested, execution, pom, child_pom), (PLUGIN,)),
    "site": Handler(create_site, (_create_fixture, _pom), (SITE_VERSION, JAVADOC_VERSION)),
}


def build(root, case):
    BUILDERS[case.fixture_kind].function(root, case)
