# SPDX-License-Identifier: Apache-2.0
"""Read event traces and verify exact contribution outputs."""

from pathlib import Path
import re
import zipfile


def require(condition, message):
    if not condition:
        raise AssertionError(message)

def read_events(root):
    path = root / "target/events.txt"
    return path.read_text().splitlines() if path.exists() else []

def check_zip(root, contributors):
    archive = root / "target/contributions.zip"
    require(archive.is_file(), "The expected contribution ZIP does not exist.")
    with zipfile.ZipFile(archive) as output:
        expected = {(name if name != "." else "self") + "/contribution.txt": name for name in contributors}
        require(sorted(output.namelist()) == sorted(expected), "The ZIP has the wrong contributors or duplicate entries.")
        require(output.testzip() is None, "The ZIP failed its CRC check.")
        for entry, name in expected.items():
            require(output.read(entry) == (root / name / "target/contribution.txt").read_bytes(),
                    f"The contribution bytes differ: {entry}")

def check_missing(log, expected):
    observed = re.findall(r"DEMO_MISSING_CONTRIBUTIONS:([a-z,]+)(?=\s|$)", log)
    require(observed and all(value == expected for value in observed),
            f"Expected the exact missing-contribution marker {expected}, observed {observed}.")
