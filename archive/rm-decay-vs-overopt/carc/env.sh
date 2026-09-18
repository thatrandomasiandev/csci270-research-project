# shellcheck shell=bash
# CARC environment for RM-Decay-vs-Overopt (standalone; not LIRALab).

export CARC_NETID="${CARC_NETID:-jjt_373}"
export CARC_HOST="${CARC_HOST:-discovery.usc.edu}"
export CARC_TRANSFER_HOST="${CARC_TRANSFER_HOST:-hpc-transfer1.usc.edu}"

export CARC_ACCOUNT="${CARC_ACCOUNT:-biyik_1165}"
export CARC_PARTITION="${CARC_PARTITION:-gpu}"
export CARC_DEBUG_PARTITION="${CARC_DEBUG_PARTITION:-debug}"

export CARC_PROJECT_ROOT="${CARC_PROJECT_ROOT:-/project2/biyik_1165}"
export CARC_REPO_DIR="${CARC_REPO_DIR:-${CARC_PROJECT_ROOT}/${CARC_NETID}/rm-decay-vs-overopt}"
export CARC_CONDA_DIR="${CARC_CONDA_DIR:-${CARC_PROJECT_ROOT}/${CARC_NETID}/miniconda3}"
export CARC_ENV_NAME="${CARC_ENV_NAME:-rmdiag}"

export CARC_GPU="${CARC_GPU:-v100:1}"
export CARC_CPUS="${CARC_CPUS:-8}"
export CARC_MEM="${CARC_MEM:-32G}"
export CARC_TIME="${CARC_TIME:-24:00:00}"
