#!/usr/bin/env bash
# Local Linux/amd64 bake-off when CARC VPN is down (needs Docker Desktop running).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMG="${STAR_DOCKER_IMAGE:-gcc:11}"
THREADS="${THREADS:-1}"  # Zhang fairness: default 1 thread for timed bake-off
N_READS="${N_READS:-2000000}"
RUNS="${RUNS:-3}"

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon not running. Open Docker Desktop, approve the privilege prompt, then re-run." >&2
  exit 1
fi

mkdir -p "${ROOT}/src" "${ROOT}/bench/results" "${ROOT}/bench/datasets"

# Mount repo into container; build optimized STAR + run baseline vs optimized.
docker run --rm --platform linux/amd64 \
  -v "${ROOT}:/work" -w /work \
  -e THREADS="${THREADS}" -e N_READS="${N_READS}" -e RUNS="${RUNS}" \
  "${IMG}" bash -lc '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq zlib1g-dev xxd python3 time >/dev/null

# Regenerated defaults (xxd already on host; refresh inside too)
cd /work/upstream/source
xxd -i parametersDefault > parametersDefault.xxd
make -C htslib clean >/dev/null 2>&1 || true
make -C htslib lib-static -j"$(nproc)"
make STARstatic -j"$(nproc)" || make STAR -j"$(nproc)"
cp -f ./STAR /work/src/STAR_optimized
./STAR --version
cd /work

# Scale synthetic data if needed
python3 bench/scripts/gen_synthetic_rnaseq.py \
  --out-dir bench/datasets --n-genes 300 --n-reads "${N_READS}" --read-len 100

GENOME_DIR=bench/datasets/genome
mkdir -p "${GENOME_DIR}"
if [[ ! -f "${GENOME_DIR}/Genome" ]]; then
  upstream/bin/Linux_x86_64_static/STAR --runMode genomeGenerate \
    --runThreadN "${THREADS}" \
    --genomeDir "${GENOME_DIR}" \
    --genomeFastaFiles bench/datasets/raw/genome.fa \
    --sjdbGTFfile bench/datasets/raw/genes.gtf \
    --sjdbOverhang 99 \
    --genomeSAindexNbases 8
fi

export GENOME_DIR READ1=bench/datasets/reads_1.fastq.gz READ2=bench/datasets/reads_2.fastq.gz
export THREADS RUNS
export STAR_BIN=/work/upstream/bin/Linux_x86_64_static/STAR
bash bench/scripts/run_baseline.sh

export STAR_BIN=/work/src/STAR_optimized
# Zhang fairness: identical CLI on both sides, so readFilesCommand must match baseline (zcat).
export READCMD=zcat
bash bench/scripts/run_optimized.sh

python3 bench/scripts/compare_timings.py \
  bench/results/baseline_timings.csv \
  bench/results/optimized_timings.csv

echo "=== quality ==="
paste \
  <(grep "Uniquely mapped reads %" bench/results/baseline_Log.final.out) \
  <(grep "Uniquely mapped reads %" bench/results/optimized_Log.final.out)
echo DOCKER_BAKEOFF_DONE
'
