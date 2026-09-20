#!/usr/bin/env bash
# Fetch Suite B Illumina inputs + build the three locked indexes (nb10 / 2L10M / nfcore nb7).
# Idempotent: skips downloads/indexes that already exist.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SUITE="${ROOT}/bench/datasets/suiteB"
STOCK_BIN="${STOCK_BIN:-}"
THREADS_GG="${THREADS_GG:-8}"
N_PE_SUBSET="${N_PE_SUBSET:-50000}"  # i05–i10: first 50k PE pairs

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 1; }; }
need_cmd curl
need_cmd python3
need_cmd gzip

mkdir -p "${SUITE}"

resolve_stock() {
  if [[ -n "${STOCK_BIN}" && -x "${STOCK_BIN}" ]]; then
    echo "${STOCK_BIN}"; return
  fi
  for c in \
    "${ROOT}/src/STAR_stock_mac" \
    "${ROOT}/src/STAR_stock" \
    "${ROOT}/upstream/bin/Linux_x86_64_static/STAR" \
    "${ROOT}/upstream/source/STAR"
  do
    if [[ -x "$c" ]]; then echo "$c"; return; fi
  done
  echo "No stock STAR binary found. Build first (build_stock_opt.sh) or set STOCK_BIN." >&2
  exit 1
}

download() {
  local url="$1" dest="$2"
  if [[ -f "$dest" && -s "$dest" ]]; then
    echo "  exists $(basename "$dest")"
    return
  fi
  mkdir -p "$(dirname "$dest")"
  echo "  curl $url"
  curl -fL --retry 3 --retry-delay 2 -o "${dest}.partial" "$url"
  mv "${dest}.partial" "$dest"
}

# Subset gzipped FASTQ to first N PE pairs (4*N lines). Writes _R1/_R2 names.
subset_pe() {
  local in1="$1" in2="$2" out1="$3" out2="$4" n="$5"
  if [[ -f "$out1" && -f "$out2" && -s "$out1" ]]; then
    echo "  subset exists $(basename "$out1")"
    return
  fi
  mkdir -p "$(dirname "$out1")"
  local lines=$((n * 4))
  echo "  subset ${n} PE → $(basename "$out1")"
  # head may SIGPIPE gzip under pipefail; ignore that benign exit
  set +o pipefail
  gzip -dc "$in1" | head -n "$lines" | gzip -c > "${out1}.partial"
  gzip -dc "$in2" | head -n "$lines" | gzip -c > "${out2}.partial"
  set -o pipefail
  mv "${out1}.partial" "$out1"
  mv "${out2}.partial" "$out2"
}

# ---- i01–i04: csoneson teaching set (human chr1 1–10Mb) ----
echo "=== i01–i04 human teaching FASTQs + ref ==="
BASE_CS="https://raw.githubusercontent.com/csoneson/rnaseqworkflow_exampledata/master"
for id in i01 i02 i03 i04; do
  case "$id" in
    i01) a=SRR1039508 ;;
    i02) a=SRR1039509 ;;
    i03) a=SRR1039512 ;;
    i04) a=SRR1039513 ;;
  esac
  mkdir -p "${SUITE}/${id}/fastq"
  download "${BASE_CS}/FASTQ/${a}_R1.fastq.gz" "${SUITE}/${id}/fastq/${a}_R1.fastq.gz"
  download "${BASE_CS}/FASTQ/${a}_R2.fastq.gz" "${SUITE}/${id}/fastq/${a}_R2.fastq.gz"
done
mkdir -p "${SUITE}/i01/ref"
download "${BASE_CS}/reference/Ensembl.GRCh38.93/Homo_sapiens.GRCh38.dna.chromosome.1.1.10M.fa" \
  "${SUITE}/i01/ref/genome.fa"
download "${BASE_CS}/reference/Ensembl.GRCh38.93/Homo_sapiens.GRCh38.93.1.1.10M.gtf" \
  "${SUITE}/i01/ref/genes.gtf"
for id in i02 i03 i04; do
  ln -sfn "../i01/ref" "${SUITE}/${id}/ref"
done

# ---- i05–i08: ENA fly Illumina, first 50k PE ----
echo "=== i05–i08 fly ENA FASTQs (50k PE) ==="
for id in i05 i06 i07 i08; do
  case "$id" in
    i05) a=SRR948304 ;;
    i06) a=SRR948305 ;;
    i07) a=SRR948306 ;;
    i08) a=SRR948307 ;;
  esac
  rawdir="${SUITE}/${id}/_ena_raw"
  mkdir -p "${SUITE}/${id}/fastq" "$rawdir"
  # ENA layout: .../SRR948/SRR948304/SRR948304_{1,2}.fastq.gz
  download "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR948/${a}/${a}_1.fastq.gz" "${rawdir}/${a}_1.fastq.gz"
  download "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR948/${a}/${a}_2.fastq.gz" "${rawdir}/${a}_2.fastq.gz"
  subset_pe "${rawdir}/${a}_1.fastq.gz" "${rawdir}/${a}_2.fastq.gz" \
    "${SUITE}/${id}/fastq/${a}_R1.fastq.gz" "${SUITE}/${id}/fastq/${a}_R2.fastq.gz" \
    "${N_PE_SUBSET}"
done

# ---- fly 2L:1–10Mb teaching ref (Ensembl BDGP6.32 primary_assembly.2L) ----
echo "=== fly_ref_2L10M (chr 2L bases 1–10,000,000) ==="
FLY_REF="${SUITE}/fly_ref_2L10M"
mkdir -p "${FLY_REF}"
if [[ ! -f "${FLY_REF}/genome.fa" || ! -f "${FLY_REF}/genes.gtf" ]]; then
  TMP="${SUITE}/_fly_build"
  mkdir -p "$TMP"
  download \
    "https://ftp.ensembl.org/pub/release-109/fasta/drosophila_melanogaster/dna/Drosophila_melanogaster.BDGP6.32.dna.primary_assembly.2L.fa.gz" \
    "${TMP}/2L.fa.gz"
  download \
    "https://ftp.ensembl.org/pub/release-109/gtf/drosophila_melanogaster/Drosophila_melanogaster.BDGP6.32.109.chr.gtf.gz" \
    "${TMP}/dm.gtf.gz"
  python3 - "${TMP}/2L.fa.gz" "${TMP}/dm.gtf.gz" "${FLY_REF}/genome.fa" "${FLY_REF}/genes.gtf" <<'PY'
import gzip, sys
fna, gtf, out_fa, out_gtf = sys.argv[1:5]
buf = []
with gzip.open(fna, "rt") as fh:
    for line in fh:
        if line.startswith(">"):
            continue
        buf.append(line.strip())
seq = "".join(buf)[:10_000_000]
with open(out_fa, "w") as o:
    o.write(">2L\n")
    for i in range(0, len(seq), 60):
        o.write(seq[i : i + 60] + "\n")
with gzip.open(gtf, "rt") as fh, open(out_gtf, "w") as o:
    for line in fh:
        if line.startswith("#"):
            o.write(line)
            continue
        parts = line.split("\t")
        if len(parts) < 5 or parts[0] != "2L":
            continue
        start, end = int(parts[3]), int(parts[4])
        if end < 1 or start > 10_000_000:
            continue
        o.write(line)
print(f"wrote {out_fa} ({len(seq)} bp) and filtered GTF")
PY
fi
for id in i05 i06 i07 i08; do
  ln -sfn "../fly_ref_2L10M" "${SUITE}/${id}/ref"
done

# ---- i09–i10: nf-core rnaseq3 testdata, first 50k PE ----
echo "=== i09–i10 nf-core FASTQs + mini genome ==="
NF="https://raw.githubusercontent.com/nf-core/test-datasets/rnaseq3"
mkdir -p "${SUITE}/nfcore_ref"
download "${NF}/reference/genome.fasta" "${SUITE}/nfcore_ref/genome.fa"
download "${NF}/reference/genes.gtf.gz" "${SUITE}/nfcore_ref/genes.gtf.gz"
if [[ ! -f "${SUITE}/nfcore_ref/genes.gtf" ]]; then
  gzip -dc "${SUITE}/nfcore_ref/genes.gtf.gz" > "${SUITE}/nfcore_ref/genes.gtf"
fi
for id in i09 i10; do
  case "$id" in
    i09) a=SRR6357070 ;;
    i10) a=SRR6357071 ;;
  esac
  rawdir="${SUITE}/${id}/_nf_raw"
  mkdir -p "${SUITE}/${id}/fastq" "$rawdir"
  download "${NF}/testdata/GSE110004/${a}_1.fastq.gz" "${rawdir}/${a}_1.fastq.gz"
  download "${NF}/testdata/GSE110004/${a}_2.fastq.gz" "${rawdir}/${a}_2.fastq.gz"
  subset_pe "${rawdir}/${a}_1.fastq.gz" "${rawdir}/${a}_2.fastq.gz" \
    "${SUITE}/${id}/fastq/${a}_R1.fastq.gz" "${SUITE}/${id}/fastq/${a}_R2.fastq.gz" \
    "${N_PE_SUBSET}"
  ln -sfn "../nfcore_ref" "${SUITE}/${id}/ref"
done

# ---- Indexes (locked Nbases / overhangs) ----
STAR="$(resolve_stock)"
echo "=== genomeGenerate with ${STAR} ==="

gg() {
  local gdir="$1" fa="$2" gtf="$3" nbases="$4" overhang="$5"
  if [[ -f "${gdir}/Genome" ]]; then
    echo "  index exists ${gdir}"
    return
  fi
  mkdir -p "$gdir"
  echo "  building ${gdir} (Nbases=${nbases}, overhang=${overhang})"
  "${STAR}" --runMode genomeGenerate --runThreadN "${THREADS_GG}" \
    --genomeDir "$gdir" \
    --genomeFastaFiles "$fa" \
    --sjdbGTFfile "$gtf" \
    --sjdbOverhang "$overhang" \
    --genomeSAindexNbases "$nbases" \
    --outFileNamePrefix "${gdir}/gg_"
}

gg "${SUITE}/i01/genome_nb10" \
  "${SUITE}/i01/ref/genome.fa" "${SUITE}/i01/ref/genes.gtf" 10 100

gg "${SUITE}/fly_genome_2L10M_nb10" \
  "${SUITE}/fly_ref_2L10M/genome.fa" "${SUITE}/fly_ref_2L10M/genes.gtf" 10 47

gg "${SUITE}/nfcore_genome_nb7" \
  "${SUITE}/nfcore_ref/genome.fa" "${SUITE}/nfcore_ref/genes.gtf" 7 100

# Symlinks expected by run_bakeoff.sh
for id in i02 i03 i04; do
  ln -sfn "../i01/genome_nb10" "${SUITE}/${id}/genome_nb10"
done
for id in i05 i06 i07 i08; do
  ln -sfn "../fly_genome_2L10M_nb10" "${SUITE}/${id}/genome_nb10"
done
for id in i09 i10; do
  ln -sfn "../nfcore_genome_nb7" "${SUITE}/${id}/genome_nb10"
done

echo "FETCH_SUITEB_DONE → ${SUITE}"
