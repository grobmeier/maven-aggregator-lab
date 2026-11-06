#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Keep suite preparation separate from the original destructive demo preparation.
set -euo pipefail
lab_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 "$lab_root/acceptance/suite.py" "$@"
