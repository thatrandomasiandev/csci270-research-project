#!/bin/bash
# Stage a fresh DIAMOND code tree.
# Swiss-Prot, the v2.2.5 binary, the queries, and the iSeqSearch checkout
# stay on the verified tree and are passed by absolute path.
# Downloads are not repeated. Nothing here runs on a login node.
# Usage: stage_reference_diamond.sh
# Submit is separate, after the smoke run, so this script does not sbatch.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HASH="$(git -C "${ROOT}" rev-parse HEAD)"
DATA=/project2/biyik_1165/jjt_373/csci270-star/pipeline-ref-second
REMOTE=/project2/biyik_1165/jjt_373/csci270-star/pipeline-ref-diamond-${HASH}

OLD=${DATA}/data/swissprot/uniprot_sprot_2026_01.fasta.gz
NEW=${DATA}/data/swissprot/uniprot_sprot_2026_03.fasta.gz
QUERIES=${DATA}/pipeline/data/recurrence/A/GCF_002853805.1_protein.faa.gz
DIAMOND=${DATA}/bin/diamond
ISEQ=${DATA}/iseq/Incremental-Protein-Search

echo "git ${HASH}"
echo "code ${REMOTE}"
echo "data ${DATA}"

ssh carc-transfer "hostname; mkdir -p '${REMOTE}/results/reference_diamond' '${REMOTE}/results/reference_diamond_smoke'"

git -C "${ROOT}" archive HEAD -- \
  pipeline/acts \
  pipeline/scripts/run_reference_diamond.py \
  pipeline/scripts/absolute_inputs.sh \
  pipeline/scripts/create_diamond_venv.sh \
  pipeline/jobs/reference_diamond.job \
  pipeline/jobs/reference_diamond_smoke.job \
  pipeline/docs/REFERENCE_SECOND_TOOL_PROTOCOL.md \
  pipeline/requirements-diamond.txt \
| ssh carc-transfer "tar -x -C '${REMOTE}'"

printf '%s\n' "${HASH}" | ssh carc-transfer "tee '${REMOTE}/results/reference_diamond/GIT_HASH' > '${REMOTE}/results/reference_diamond_smoke/GIT_HASH'"

ssh carc-transfer "bash -s" << EOF
set -euo pipefail
case "\$(hostname)" in
  *login*|*discovery*) echo "refusing to stage on a login node"; exit 2 ;;
esac
test "\$(stat -c %s '${OLD}')" = "93457057"
test "\$(stat -c %s '${NEW}')" = "93801562"
test "\$(stat -c %s '${QUERIES}')" = "1074926"
test -x '${DIAMOND}'
test -f '${ISEQ}/source/main.py'
chmod +x '${REMOTE}/pipeline/scripts/create_diamond_venv.sh'
bash '${REMOTE}/pipeline/scripts/create_diamond_venv.sh' '${REMOTE}'
EOF

cat << EOF
staged ${REMOTE}
ACTS_CODE_ROOT=${REMOTE}
ACTS_OLD_FASTA=${OLD}
ACTS_NEW_FASTA=${NEW}
ACTS_QUERIES=${QUERIES}
ACTS_DIAMOND=${DIAMOND}
ACTS_ISEQ=${ISEQ}
ACTS_GIT_HASH=${HASH}
EOF
