# SPDX-License-Identifier: Apache-2.0
"""Build Maven commands without preparing fixtures or starting Maven."""


def build_command(case, root, maven, common):
    command = [maven, *common, "--builder", case.builder, f"-T{case.threads}"]
    if case.fixture_kind == "markers":
        command += [f"-Ddemo.eventRoot={root}", f"-Ddemo.contributors={case.contributors}"]
    if case.failure:
        command += [case.failure, "-Ddemo.failContributor=a"]
    if case.failure_stage:
        command += [f"-Ddemo.failureStage={case.failure_stage}"]
    if case.selection:
        command += ["-pl", case.selection]
    return [*command, case.lifecycle]
