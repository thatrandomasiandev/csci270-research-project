#!/usr/bin/env bash
# Image entrypoint: full unit suite, then the kick-the-tires path.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${ROOT}/pipeline"
./run_tests.sh
"${ROOT}/pipeline/artifact/kick_the_tires.sh"
