#!/usr/bin/env bash
# VEP/SnpEff chr22 setup. Does not download the full human VEP cache.
# Protocol: pipeline/docs/VEP_PROTOCOL.md
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${VEP_DATA:-$ROOT/data/vep_chr22}"
FETCH=0
if [[ "${1:-}" == "--fetch-vcf" ]]; then
  FETCH=1
fi

VCF_NAME="ALL.chr22.shapeit2_integrated_snvindels_v2a_27022019.GRCh38.phased.vcf.gz"
VCF_URL="https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000_genomes_project/release/20190312_biallelic_SNV_and_INDEL/${VCF_NAME}"
# Two CEU samples; -c1 so overlap is carried ALTs, not the joint site list.
S1="${SAMPLE1:-HG00096}"
S2="${SAMPLE2:-HG00097}"

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "MISSING: $1" >&2
    return 1
  fi
}

echo "protocol: $ROOT/docs/VEP_PROTOCOL.md"
echo "data dir: $DATA"
mkdir -p "$DATA"

ok=1
need bcftools || ok=0
if ! command -v vep >/dev/null 2>&1; then
  echo "MISSING: vep  (identity rung blocked; SnpEff is the fallback)"
  ok=0
fi
if ! command -v snpeff >/dev/null 2>&1 && ! command -v snpEff >/dev/null 2>&1; then
  echo "MISSING: snpeff (optional second tool)"
fi

if [[ "$FETCH" -eq 1 ]]; then
  if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
    echo "MISSING: curl or wget" >&2
    exit 2
  fi
  dest="$DATA/$VCF_NAME"
  if [[ ! -f "$dest" ]]; then
    echo "fetching chr22 VCF (~177MB) → $dest"
    if command -v curl >/dev/null 2>&1; then
      curl -L --fail -o "$dest" "$VCF_URL"
      curl -L --fail -o "$dest.tbi" "${VCF_URL}.tbi" || true
    else
      wget -O "$dest" "$VCF_URL"
    fi
  else
    echo "already have $dest"
  fi
else
  echo "skip fetch (pass --fetch-vcf for 1000G chr22 ~177MB)"
fi

if [[ "$ok" -eq 0 ]]; then
  echo "INCOMPLETE: install bcftools + vep (or snpeff) and re-run. Do not invent overlap."
  exit 2
fi

joint="$DATA/$VCF_NAME"
if [[ ! -f "$joint" ]]; then
  echo "INCOMPLETE: no joint VCF at $joint (re-run with --fetch-vcf)"
  exit 2
fi

echo "extracting $S1 and $S2 with bcftools view -s … -c1 (carried ALTs only)"
bcftools view -s "$S1" -c1 -Oz -o "$DATA/${S1}.c1.vcf.gz" "$joint"
bcftools view -s "$S2" -c1 -Oz -o "$DATA/${S2}.c1.vcf.gz" "$joint"
bcftools index -t "$DATA/${S1}.c1.vcf.gz"
bcftools index -t "$DATA/${S2}.c1.vcf.gz"
echo "wrote $DATA/${S1}.c1.vcf.gz and $DATA/${S2}.c1.vcf.gz"
echo "next: stock VEP twice on ${S1}.c1 → diff header vs body (MATCH is body). Then overlap -c1 extracts."
echo "forbidden: haplo, haplotype plugins, --check_svs. locked: --offline --cache --vcf --no_stats --fork 1"
