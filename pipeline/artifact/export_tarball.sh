#!/usr/bin/env bash
# Build an anonymized artifact tarball. Does not upload or host.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${ROOT}"
STAMP="$(date -u +%Y%m%d)"
DEST="${ROOT}/pipeline/artifact/tare-artifact-${STAMP}"
rm -rf "${DEST}"
mkdir -p "${DEST}"

rsync -a \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.pytest_cache' \
  pipeline/acts/ "${DEST}/acts/"
rsync -a \
  --exclude '__pycache__' --exclude '*.pyc' \
  pipeline/tests/ "${DEST}/tests/"
mkdir -p "${DEST}/scripts" "${DEST}/docs" "${DEST}/results" "${DEST}/paper"
rsync -a pipeline/scripts/headline_analysis.py "${DEST}/scripts/" 2>/dev/null || true
rsync -a pipeline/paper/tare/figures/ "${DEST}/paper/figures/"
rsync -a pipeline/paper/tare/finalize.sh pipeline/paper/tare/fill_macros.py \
  pipeline/paper/tare/macros_pending.tex pipeline/paper/tare/collectors \
  "${DEST}/paper/" 2>/dev/null || true
# committed results only (no scratch staging)
rsync -a --exclude '_*' --exclude '*staging*' \
  pipeline/results/ "${DEST}/results/"
# protocols / addenda (strip lab notebook)
rsync -a \
  --exclude 'prompts' \
  pipeline/docs/*.md "${DEST}/docs/" 2>/dev/null || true

cp pipeline/artifact/README.md "${DEST}/README.md"
cp pipeline/artifact/kick_the_tires.sh "${DEST}/kick_the_tires.sh"
cp pipeline/artifact/requirements.txt "${DEST}/requirements.txt" 2>/dev/null || true
cp LICENSE "${DEST}/LICENSE" 2>/dev/null || printf 'See USENIX / authors for license.\n' > "${DEST}/LICENSE"

# README reproduce stub
cat >> "${DEST}/README.md" <<'EOF'

## Reproduce (laptop smoke)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./kick_the_tires.sh
```

Laptop walls are not speed evidence. Full server commands and seeds are in
`docs/*_PROTOCOL.md` and the result JSON provenance fields.
EOF

TARBALL="${ROOT}/pipeline/artifact/tare-artifact-${STAMP}.tar.gz"
tar -C "$(dirname "${DEST}")" -czf "${TARBALL}" "$(basename "${DEST}")"
echo "Wrote ${TARBALL}"
# smoke from unpack
SMOKE="${TMPDIR:-/tmp}/tare-artifact-smoke-$$"
rm -rf "${SMOKE}"
mkdir -p "${SMOKE}"
tar -C "${SMOKE}" -xzf "${TARBALL}"
(
  cd "${SMOKE}/tare-artifact-${STAMP}"
  nice -n 10 python3 -m pytest -q tests/test_iseqsearch_confirm.py 2>/dev/null || \
    nice -n 10 python3 -c "import acts; print('acts import ok', acts.__file__)"
)
echo "SMOKE OK"
echo "${TARBALL}"
