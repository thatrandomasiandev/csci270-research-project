#!/bin/bash
# Create the DIAMOND job's venv once, in the code tree.
# Re-running is a no-op when the pins already match.
# Do not invoke this from the measurement job.
set -euo pipefail

ROOT="${1:?usage: create_diamond_venv.sh CODE_ROOT}"
REQ="${ROOT}/pipeline/requirements-diamond.txt"
PY="${ROOT}/venv/bin/python"

if [[ ! -f "${REQ}" ]]; then
  echo "STOP_INPUTS: pin file is missing: ${REQ}" >&2
  exit 2
fi

pins_match() {
  "${PY}" - "${REQ}" <<'PY'
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

bad = False
for raw in Path(sys.argv[1]).read_text().splitlines():
    line = raw.split("#", 1)[0].strip()
    if not line:
        continue
    name, pin = line.split("==", 1)
    try:
        got = version(name.strip())
    except PackageNotFoundError:
        got = "MISSING"
    if got != pin.strip():
        print(f"{name.strip()} {got} != {pin.strip()}", file=sys.stderr)
        bad = True
sys.exit(1 if bad else 0)
PY
}

if [[ -x "${PY}" ]] && pins_match; then
  echo "venv pins already match ${REQ}"
  exit 0
fi

if [[ -f /etc/profile.d/modules.sh ]]; then
  # shellcheck disable=SC1091
  source /etc/profile.d/modules.sh
fi
module load python/3.11.9 || module load python
rm -rf "${ROOT}/venv"
python3 -m venv "${ROOT}/venv"
"${ROOT}/venv/bin/pip" install --disable-pip-version-check -r "${REQ}"
pins_match
echo "venv ready ${ROOT}/venv"
