#!/bin/bash
# Stage the DIAMOND second-tool run.
# Downloads happen on the transfer node. sbatch happens on discovery.
# Nothing here runs on a login node.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REMOTE=/project2/biyik_1165/jjt_373/csci270-star/pipeline-ref-second
HASH="$(git -C "${ROOT}" rev-parse HEAD)"

echo "git ${HASH}"

ssh carc-transfer "hostname; mkdir -p '${REMOTE}'/{bin,data/swissprot,results/reference_diamond,iseq} '${REMOTE}/pipeline'/{acts,scripts,jobs,docs,data/recurrence/A}"

# Committed tree only. A dirty acts/ from another session stays on the Mac.
git -C "${ROOT}" archive HEAD -- \
  pipeline/acts \
  pipeline/scripts/run_reference_diamond.py \
  pipeline/jobs/reference_diamond.job \
  pipeline/docs/REFERENCE_SECOND_TOOL_PROTOCOL.md \
| ssh carc-transfer "tar -x -C '${REMOTE}'"

# data/ is gitignored. The query file is the locked collection A genome, not a release download.
rsync -avz \
  "${ROOT}/pipeline/data/recurrence/A/GCF_002853805.1_protein.faa.gz" \
  "carc-transfer:${REMOTE}/pipeline/data/recurrence/A/"

printf '%s\n' "${HASH}" | ssh carc-transfer "cat > '${REMOTE}/results/reference_diamond/GIT_HASH'"

ssh carc-transfer "bash -s" << 'EOF'
set -euo pipefail
REMOTE=/project2/biyik_1165/jjt_373/csci270-star/pipeline-ref-second
cd "${REMOTE}"
echo "transfer host: $(hostname)"
case "$(hostname)" in
  *login*|*discovery*) echo "refusing to download on a login node"; exit 2 ;;
esac

if [[ ! -x bin/diamond ]]; then
  curl -L --fail -o /tmp/diamond-linux64.tar.gz \
    https://github.com/bbuchfink/diamond/releases/download/v2.2.5/diamond-linux64.tar.gz
  tar -xzf /tmp/diamond-linux64.tar.gz -C bin
  rm -f /tmp/diamond-linux64.tar.gz
fi
chmod +x bin/diamond
bin/diamond version

NEW=data/swissprot/uniprot_sprot_2026_03.fasta.gz
if [[ ! -f "${NEW}" ]]; then
  curl -L --fail -o "${NEW}" \
    https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/uniprot_sprot.fasta.gz
fi
echo "bc9d398533e6df582b563c6c03093bd0  ${NEW}" | md5sum -c -
test "$(stat -c %s "${NEW}")" = "93801562"

OLD=data/swissprot/uniprot_sprot_2026_01.fasta.gz
if [[ -f data/swissprot/OLD_PATH ]] && [[ -f "$(cat data/swissprot/OLD_PATH)" ]]; then
  echo "older fasta already staged: $(cat data/swissprot/OLD_PATH)"
elif [[ -f "${OLD}" ]]; then
  printf '%s\n' "${OLD}" > data/swissprot/OLD_PATH
else
  TAR=data/swissprot/uniprot_sprot-only2026_01.tar.gz
  curl -L --fail -o "${TAR}" \
    https://ftp.uniprot.org/pub/databases/uniprot/previous_releases/release-2026_01/knowledgebase/uniprot_sprot-only2026_01.tar.gz
  echo "6042adf20dad1ab62112c9053bdebd20  ${TAR}" | md5sum -c -
  member=$(tar -tzf "${TAR}" | awk '/uniprot_sprot\.fasta(\.gz)?$/ && $0 !~ /varsplic/' | head -n 1)
  echo "fasta member: ${member}"
  test -n "${member}"
  tar -xzf "${TAR}" -C data/swissprot "${member}"
  extracted="data/swissprot/${member}"
  if [[ "${extracted}" != "${OLD}" && "${member}" == *.gz ]]; then
    mv "${extracted}" "${OLD}"
    extracted="${OLD}"
  fi
  rm -f "${TAR}"
  find data/swissprot -mindepth 1 -type d -empty -delete || true
  test ! -f "${TAR}"
  printf '%s\n' "${extracted}" > data/swissprot/OLD_PATH
fi
old_file=$(cat data/swissprot/OLD_PATH)
md5sum "${old_file}" | tee data/swissprot/uniprot_sprot_2026_01.md5
stat -c '%n %s' "${old_file}"

if command -v git >/dev/null 2>&1; then
  if [[ ! -d iseq/Incremental-Protein-Search/.git ]]; then
    git clone https://github.com/EESI/Incremental-Protein-Search.git iseq/Incremental-Protein-Search
    git -C iseq/Incremental-Protein-Search checkout 7e862bf3afa52b65b3cca4255de66ab4cb764fe3
  fi
  git -C iseq/Incremental-Protein-Search rev-parse HEAD
else
  echo "git is not on this host; the iSeqSearch arm will record that"
fi
EOF

ssh discovery "sbatch --export=ALL,ACTS_GIT_HASH=${HASH} '${REMOTE}/pipeline/jobs/reference_diamond.job'"
