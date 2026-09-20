#!/usr/bin/env bash
# Build a ~300MB tarball Josh can send the professor: bit-identical Suite B inputs +
# scripts/docs/patch/reference CSV. Binaries are rebuilt on the professor's machine.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SUITE="${ROOT}/bench/datasets/suiteB"
OUT="${1:-${ROOT}/../STAR_suiteB_repro_$(date +%Y%m%d).tar.gz}"
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/star_repro.XXXXXX")"
trap 'rm -rf "${STAGE}"' EXIT

need() { [[ -e "$1" ]] || { echo "missing $1 — run bakeoffs locally first" >&2; exit 1; }; }

need "${ROOT}/src/star-2x-verified.patch"
need "${SUITE}/i01/genome_nb10/Genome"
need "${SUITE}/fly_genome_2L10M_nb10/Genome"
need "${SUITE}/nfcore_genome_nb7/Genome"

DEST="${STAGE}/STAR_2x_reproduce"
mkdir -p "${DEST}/star/bench/datasets/suiteB" \
         "${DEST}/star/bench/scripts" \
         "${DEST}/star/bench/results" \
         "${DEST}/star/src" \
         "${DEST}/star/docs"

# ROOT is star/; repo root is parent
REPO="$(cd "${ROOT}/.." && pwd)"
cp -a "${REPO}/STATUS.md" "${REPO}/README.md" "${REPO}/AGENTS.md" "${DEST}/"
cp -a "${ROOT}/docs/SCOPE.md" "${ROOT}/docs/OPTIMIZATION.md" "${ROOT}/docs/BUILD.md" \
      "${ROOT}/docs/REPRODUCE.md" "${DEST}/star/docs/"
cp -a "${ROOT}/src/star-2x-verified.patch" "${ROOT}/src/README.md" "${DEST}/star/src/"
cp -a "${ROOT}/bench/datasets/"*.md "${DEST}/star/bench/datasets/"
cp -a "${ROOT}/bench/scripts/"*.sh "${ROOT}/bench/scripts/"*.py "${DEST}/star/bench/scripts/"
chmod +x "${DEST}/star/bench/scripts/"*.sh

# Reference scoreboard CSV (expected layout / Josh numbers)
if [[ -f "${ROOT}/bench/results/illumina10_s8j_mac.csv" ]]; then
  cp -a "${ROOT}/bench/results/illumina10_s8j_mac.csv" "${DEST}/star/bench/results/"
fi

# Essential Suite B data (exclude full-fly archive + subset experiments)
copy_tree() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  rsync -a --copy-links "$src" "$dst"
}

echo "Staging Suite B essential data…"
for id in i01 i02 i03 i04 i05 i06 i07 i08 i09 i10; do
  mkdir -p "${DEST}/star/bench/datasets/suiteB/${id}"
  rsync -a "${SUITE}/${id}/fastq" "${DEST}/star/bench/datasets/suiteB/${id}/"
done
rsync -a "${SUITE}/i01/ref" "${DEST}/star/bench/datasets/suiteB/i01/"
rsync -a "${SUITE}/fly_ref_2L10M" "${DEST}/star/bench/datasets/suiteB/"
rsync -a "${SUITE}/nfcore_ref" "${DEST}/star/bench/datasets/suiteB/"
rsync -a "${SUITE}/i01/genome_nb10" "${DEST}/star/bench/datasets/suiteB/i01/"
rsync -a "${SUITE}/fly_genome_2L10M_nb10" "${DEST}/star/bench/datasets/suiteB/"
rsync -a "${SUITE}/nfcore_genome_nb7" "${DEST}/star/bench/datasets/suiteB/"

# Recreate symlinks inside the package (do not copy dangling absolute links)
(
  cd "${DEST}/star/bench/datasets/suiteB"
  for id in i02 i03 i04; do
    ln -sfn "../i01/ref" "${id}/ref"
    ln -sfn "../i01/genome_nb10" "${id}/genome_nb10"
  done
  for id in i05 i06 i07 i08; do
    ln -sfn "../fly_ref_2L10M" "${id}/ref"
    ln -sfn "../fly_genome_2L10M_nb10" "${id}/genome_nb10"
  done
  for id in i09 i10; do
    ln -sfn "../nfcore_ref" "${id}/ref"
    ln -sfn "../nfcore_genome_nb7" "${id}/genome_nb10"
  done
)

cat > "${DEST}/RUN_ME.sh" <<'EOF'
#!/usr/bin/env bash
# Professor one-liner after unpacking this tarball.
set -euo pipefail
cd "$(dirname "$0")"
echo "Dependencies: git, g++ (Linux) or Homebrew gcc+jemalloc (macOS), samtools, python3, curl"
echo "Building stock + optimized STAR, then running Suite B bake-off…"
SKIP_FETCH=1 bash star/bench/scripts/reproduce_all.sh
EOF
chmod +x "${DEST}/RUN_ME.sh"

echo "Creating ${OUT} …"
tar -C "${STAGE}" -czf "${OUT}" "$(basename "${DEST}")"
ls -lh "${OUT}"
echo "PACKAGE_DONE ${OUT}"
echo "Send that file; professor unpacks and runs:  bash RUN_ME.sh"
