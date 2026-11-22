#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
lab_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ $# -gt 0 ]]; then
  exec "$lab_root/acceptance-suite.sh" "$@"
fi
exec python3 "$lab_root/acceptance/interactive.py"
