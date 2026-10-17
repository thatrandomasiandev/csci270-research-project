#!/bin/bash
# Stage the measured headline array through discovery and sbatch it.
# Does not use carc-transfer. Does not run the scan on the login node.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="/project2/biyik_1165/jjt_373/csci270-star/headline_exact"
ACTS_COMMIT="d12515169eae5c8d4dbb555b33eabee1b815cbc7"
GIT_HEAD="$(git -C "${ROOT}" rev-parse HEAD)"
GENOMES="/project2/biyik_1165/jjt_373/csci270-star/pipeline/data/recurrence/A"

if ! git -C "${ROOT}" diff --quiet "${ACTS_COMMIT}" HEAD -- pipeline/acts; then
  echo "pipeline/acts differs from ${ACTS_COMMIT}; staging that tree"
  STAGE="$(mktemp -d)"
  git -C "${ROOT}" archive "${ACTS_COMMIT}" pipeline/acts | tar -x -C "${STAGE}"
  ACTS_SRC="${STAGE}/pipeline/acts"
  ACTS_NOTE="archived ${ACTS_COMMIT}"
else
  echo "pipeline/acts matches ${ACTS_COMMIT}"
  ACTS_SRC="${ROOT}/pipeline/acts"
  ACTS_NOTE="HEAD identical to ${ACTS_COMMIT}"
fi

python3 - "${ROOT}" "${GENOMES}" << 'PY'
import hashlib, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "pipeline"))
sys.path.insert(0, str(root / "pipeline" / "scripts"))
import headline_carc_measured as runner

remote = sys.argv[2]
listing = subprocess.check_output(
    ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "discovery",
     f"ls -1 {remote}/*_protein.faa.gz"],
    text=True,
)
stems = sorted(
    Path(line.strip()).name[: -len("_protein.faa.gz")]
    for line in listing.splitlines()
    if line.strip()
)
pool = [stem for stem in stems if stem not in runner.EXCLUDE_REASONS]
digest = hashlib.sha256("\n".join(pool).encode()).hexdigest()
if len(pool) != runner.POOL_N or digest != runner.POOL_SHA256:
    raise SystemExit(f"STOP: CARC pool {len(pool)} {digest} != {runner.POOL_N} {runner.POOL_SHA256}")
drawn = sorted(__import__("random").Random(runner.SEED).sample(pool, runner.N_DRAW))
if drawn != list(runner.DRAWS):
    raise SystemExit(f"STOP: CARC draw {drawn} != {list(runner.DRAWS)}")
print(f"CARC pool {len(pool)} {digest} matches; draw matches")
PY

if [[ -n "$(git -C "${ROOT}" status --porcelain -- pipeline/acts pipeline/scripts/headline_carc_measured.py pipeline/scripts/headline_analysis.py pipeline/jobs/headline_carc_measured.job)" ]]; then
  echo "STOP: staged paths are dirty" >&2
  exit 2
fi

ssh -o BatchMode=yes -o ConnectTimeout=20 discovery \
  "mkdir -p '${DEST}/acts' '${DEST}/scripts' '${DEST}/jobs' '${DEST}/results' '${DEST}/logs'"
rsync -a --delete --exclude '__pycache__' \
  "${ACTS_SRC}/" "discovery:${DEST}/acts/"
rsync -a \
  "${ROOT}/pipeline/scripts/headline_carc_measured.py" \
  "${ROOT}/pipeline/scripts/headline_analysis.py" \
  "discovery:${DEST}/scripts/"
rsync -a \
  "${ROOT}/pipeline/jobs/headline_carc_measured.job" \
  "discovery:${DEST}/jobs/headline_carc_measured.job"

python3 - "${ROOT}" "${DEST}" "${ACTS_COMMIT}" "${GIT_HEAD}" << 'PY'
import hashlib, subprocess, sys
from pathlib import Path

root, dest, acts_commit, git_head = sys.argv[1:]

def blob_sha(rev: str, path: str) -> str:
    data = subprocess.check_output(["git", "-C", root, "cat-file", "blob", f"{rev}:{path}"])
    return hashlib.sha256(data).hexdigest()

pairs = []
listed = subprocess.check_output(
    ["git", "-C", root, "ls-tree", "-r", "--name-only", acts_commit, "pipeline/acts"],
    text=True,
)
for path in listed.splitlines():
    if not path or path.endswith("/"):
        continue
    rel = path[len("pipeline/"):]
    pairs.append((blob_sha(acts_commit, path), rel, path))
for path in (
    "pipeline/scripts/headline_carc_measured.py",
    "pipeline/scripts/headline_analysis.py",
    "pipeline/jobs/headline_carc_measured.job",
):
    pairs.append((blob_sha(git_head, path), path[len("pipeline/"):], path))

quoted = " ".join("'" + rel.replace("'", "'\\''") + "'" for _expected, rel, _path in pairs)
remote = subprocess.check_output(
    ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "discovery",
     f"cd '{dest}' && sha256sum {quoted}"],
    text=True,
)
got = {}
for line in remote.splitlines():
    digest, rel = line.split(None, 1)
    got[rel] = digest
bad = []
for expected, rel, path in pairs:
    if got.get(rel) != expected:
        bad.append(f"{path}: remote {got.get(rel)} != git {expected}")
if bad:
    raise SystemExit("STOP: sha256 mismatch\n" + "\n".join(bad))
print(f"sha256 ok for {len(pairs)} files")
PY

printf '%s\n' "${GIT_HEAD}" | ssh -o BatchMode=yes discovery "cat > '${DEST}/GIT_HEAD'"
printf '%s\n' "${ACTS_COMMIT}" | ssh -o BatchMode=yes discovery "cat > '${DEST}/ACTS_COMMIT'"
echo "GIT_HEAD=${GIT_HEAD}"
echo "ACTS_COMMIT=${ACTS_COMMIT} (${ACTS_NOTE})"

ssh -o BatchMode=yes discovery \
  "export ACTS_GIT_HEAD='${GIT_HEAD}' ACTS_GIT_DIRTY='false' ACTS_COMMIT='${ACTS_COMMIT}'; sbatch --export=ALL,ACTS_GIT_HEAD='${GIT_HEAD}',ACTS_GIT_DIRTY='false',ACTS_COMMIT='${ACTS_COMMIT}' '${DEST}/jobs/headline_carc_measured.job'"
