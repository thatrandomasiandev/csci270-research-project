#!/usr/bin/env bash
# Compare stock vs optimized BAM/SAM content (Zhang: same output).
# Normalizes headers that embed binary path (@PG) before diff.
set -euo pipefail
STOCK_BAM="${1:?stock bam}"
OPT_BAM="${2:?optimized bam}"
TMP="${TMPDIR:-/tmp}/star_outcmp_$$"
mkdir -p "${TMP}"

norm() {
  local in="$1" out="$2"
  if command -v samtools >/dev/null 2>&1; then
    samtools view -h "$in" 2>/dev/null | sed -E '/^@PG/d;/^@CO/d' > "$out"
  else
    # STAR can emit SAM if we pass SAM; for BAM without samtools, fail clearly
    echo "samtools required for BAM compare" >&2
    exit 2
  fi
}

norm "${STOCK_BAM}" "${TMP}/stock.sam"
norm "${OPT_BAM}" "${TMP}/opt.sam"

if cmp -s "${TMP}/stock.sam" "${TMP}/opt.sam"; then
  echo "OUTPUT_MATCH"
  rm -rf "${TMP}"
  exit 0
fi
echo "OUTPUT_DIFF"
# show brief diff stats
wc -l "${TMP}/stock.sam" "${TMP}/opt.sam"
diff -u "${TMP}/stock.sam" "${TMP}/opt.sam" | head -40 || true
rm -rf "${TMP}"
exit 1
