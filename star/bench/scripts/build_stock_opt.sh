#!/usr/bin/env bash
# Build stock STAR 2.7.11b + optimized (S1–S8 + jemalloc + optional PGO/LTO).
# Produces: star/src/STAR_stock  and  star/src/STAR_opt
# On macOS also copies to STAR_stock_mac / STAR_opt_mac_s8_pgo for harness defaults.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="${ROOT}/upstream/source"
TAG="${STAR_TAG:-2.7.11b}"
JOBS="${JOBS:-$( (sysctl -n hw.ncpu 2>/dev/null || nproc) )}"
WITH_PGO="${WITH_PGO:-1}"
WITH_JEMALLOC="${WITH_JEMALLOC:-1}"
# Portable graded builds: leave empty. Set NATIVE=1 to allow -mcpu/-march=native.
NATIVE="${NATIVE:-0}"

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }

OS="$(uname -s)"
if [[ "$OS" == Darwin ]]; then
  # Official STAR mac path: Homebrew gcc
  CXX_BIN="${CXX_BIN:-}"
  if [[ -z "$CXX_BIN" ]]; then
    for c in g++-16 g++-15 g++-14 g++-13 g++-12; do
      if command -v "$c" >/dev/null 2>&1; then CXX_BIN="$c"; break; fi
    done
  fi
  [[ -n "$CXX_BIN" ]] || { echo "Install Homebrew gcc (e.g. brew install gcc jemalloc)" >&2; exit 1; }
  MAKE_TARGET="STARforMacStatic"
  CXXFLAGS_SIMD=""
  JEMALLOC_LIBDIR="${JEMALLOC_LIBDIR:-/opt/homebrew/lib}"
  JEMALLOC_INCDIR="${JEMALLOC_INCDIR:-/opt/homebrew/include}"
else
  CXX_BIN="${CXX_BIN:-g++}"
  need_cmd "$CXX_BIN"
  MAKE_TARGET="STARstatic"
  CXXFLAGS_SIMD=""
  JEMALLOC_LIBDIR="${JEMALLOC_LIBDIR:-/usr/lib}"
  JEMALLOC_INCDIR="${JEMALLOC_INCDIR:-/usr/include}"
fi

echo "=== ensure upstream ${TAG} ==="
if [[ ! -d "${ROOT}/upstream/.git" ]]; then
  need_cmd git
  git clone --depth 1 --branch "${TAG}" https://github.com/alexdobin/STAR.git "${ROOT}/upstream"
else
  git -C "${ROOT}/upstream" fetch --depth 1 origin "refs/tags/${TAG}:refs/tags/${TAG}" 2>/dev/null || true
  git -C "${ROOT}/upstream" checkout -f "${TAG}"
fi

mkdir -p "${ROOT}/src"

build_htslib() {
  make -C "${SRC}/htslib" clean >/dev/null 2>&1 || true
  if [[ "$OS" == Darwin ]]; then
    make -C "${SRC}/htslib" lib-static -j"${JOBS}" CC=gcc
  else
    make -C "${SRC}/htslib" lib-static -j"${JOBS}"
  fi
}

# --- Stock (pristine tree) ---
echo "=== stock binary ==="
git -C "${ROOT}/upstream" checkout -f "${TAG}" -- source
# refresh embedded defaults if needed
if command -v xxd >/dev/null 2>&1; then
  (cd "${SRC}" && xxd -i parametersDefault > parametersDefault.xxd) || true
fi
build_htslib
if [[ "$OS" == Darwin ]]; then
  make -C "${SRC}" "${MAKE_TARGET}" CXX="${CXX_BIN}" CXXFLAGS_SIMD="${CXXFLAGS_SIMD}" -j"${JOBS}"
else
  make -C "${SRC}" "${MAKE_TARGET}" -j"${JOBS}" || make -C "${SRC}" STAR -j"${JOBS}"
fi
cp -f "${SRC}/STAR" "${ROOT}/src/STAR_stock"
cp -f "${SRC}/STAR" "${ROOT}/src/STAR_stock_mac"
"${ROOT}/src/STAR_stock" --version

# --- Optimized (patch + jemalloc + optional PGO) ---
echo "=== apply star-2x-verified.patch ==="
git -C "${ROOT}/upstream" checkout -f "${TAG}" -- source
git -C "${ROOT}/upstream" apply --check "${ROOT}/src/star-2x-verified.patch"
git -C "${ROOT}/upstream" apply "${ROOT}/src/star-2x-verified.patch"
if command -v xxd >/dev/null 2>&1; then
  (cd "${SRC}" && xxd -i parametersDefault > parametersDefault.xxd) || true
fi

EXTRA_CXX=()
EXTRA_LD=()
if [[ "${WITH_JEMALLOC}" == "1" ]]; then
  if [[ -f "${JEMALLOC_LIBDIR}/libjemalloc.a" || -f "${JEMALLOC_LIBDIR}/libjemalloc.dylib" || -f "${JEMALLOC_LIBDIR}/libjemalloc.so" ]]; then
    EXTRA_CXX+=("-I${JEMALLOC_INCDIR}")
    EXTRA_LD+=("-L${JEMALLOC_LIBDIR}" "-ljemalloc")
  else
    echo "WARN: jemalloc not found under ${JEMALLOC_LIBDIR}; building without it (speedup may drop)." >&2
  fi
fi
if [[ "${NATIVE}" == "1" ]]; then
  if [[ "$OS" == Darwin ]]; then
    EXTRA_CXX+=("-mcpu=native")
  else
    EXTRA_CXX+=("-march=native")
  fi
fi

CXXFLAGSextra="$(printf '%s ' "${EXTRA_CXX[@]}")"
LDFLAGSextra="$(printf '%s ' "${EXTRA_LD[@]}")"

build_htslib

do_make() {
  local extra_cxx="$1" extra_ld="$2"
  if [[ "$OS" == Darwin ]]; then
    make -C "${SRC}" "${MAKE_TARGET}" CXX="${CXX_BIN}" CXXFLAGS_SIMD="${CXXFLAGS_SIMD}" \
      CXXFLAGSextra="${extra_cxx}" LDFLAGSextra="${extra_ld}" -j"${JOBS}"
  else
    make -C "${SRC}" "${MAKE_TARGET}" \
      CXXFLAGSextra="${extra_cxx}" LDFLAGSextra="${extra_ld}" -j"${JOBS}" \
      || make -C "${SRC}" STAR CXXFLAGSextra="${extra_cxx}" LDFLAGSextra="${extra_ld}" -j"${JOBS}"
  fi
}

if [[ "${WITH_PGO}" == "1" ]]; then
  echo "=== PGO generate (no -flto) ==="
  do_make "${CXXFLAGSextra} -fprofile-generate" "${LDFLAGSextra} -fprofile-generate"
  # Train on i01 if present; otherwise skip use-phase and keep generate binary
  GDIR="${ROOT}/bench/datasets/suiteB/i01/genome_nb10"
  R1="${ROOT}/bench/datasets/suiteB/i01/fastq/SRR1039508_R1.fastq.gz"
  R2="${ROOT}/bench/datasets/suiteB/i01/fastq/SRR1039508_R2.fastq.gz"
  if [[ -f "${GDIR}/Genome" && -f "$R1" && -f "$R2" ]]; then
    if command -v gzcat >/dev/null 2>&1; then RC=gzcat; else RC=zcat; fi
    PGO_OUT="${ROOT}/bench/results/_pgo_train"
    rm -rf "${PGO_OUT}"; mkdir -p "${PGO_OUT}"
    "${SRC}/STAR" --runThreadN 1 --genomeDir "${GDIR}" \
      --readFilesIn "$R1" "$R2" --readFilesCommand "$RC" \
      --outFileNamePrefix "${PGO_OUT}/" \
      --outSAMtype BAM SortedByCoordinate \
      --limitBAMsortRAM 4000000000 \
      --outBAMcompression 0 >/dev/null || true
    echo "=== PGO use + LTO ==="
    make -C "${SRC}" clean >/dev/null 2>&1 || true
    build_htslib
    do_make "${CXXFLAGSextra} -fprofile-use -flto" "${LDFLAGSextra} -fprofile-use -flto"
  else
    echo "WARN: Suite B i01 missing — skipping PGO train; binary is profile-generate only." >&2
    echo "      Re-run after fetch_suiteB.sh for full PGO." >&2
  fi
else
  do_make "${CXXFLAGSextra} -flto" "${LDFLAGSextra} -flto"
fi

cp -f "${SRC}/STAR" "${ROOT}/src/STAR_opt"
cp -f "${SRC}/STAR" "${ROOT}/src/STAR_opt_mac_s8_pgo"
"${ROOT}/src/STAR_opt" --version
echo "BUILD_DONE stock=${ROOT}/src/STAR_stock  opt=${ROOT}/src/STAR_opt"
