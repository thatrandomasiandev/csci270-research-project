# ACTS strategies

Front door: **record memoization** (Survivor 1). Run a tool on distinct records, cache, reassemble, accept only on **byte-identical** MATCH. No source edits.

The graded STAR ≥2× stays in `star/`. EGAS stays as the source-edit driver that produced that patch. Neither is deleted.

Orientation: [`../WHAT_WE_ARE_BUILDING.md`](../WHAT_WE_ARE_BUILDING.md) · claim lock: [`SCOPE.md`](SCOPE.md)

## Quick start

```bash
cd pipeline
export PYTHONPATH="$PWD"

# Incremental headline (run_b reuses run_a's cache)
python3 -m acts run --cache /tmp/acts.jsonl --kind lines \
  --input fixtures/line_memo/run_a.txt -- cat
python3 -m acts run --cache /tmp/acts.jsonl --kind lines \
  --input fixtures/line_memo/run_b.txt -- cat

# Line-oriented within-file smoke
python3 -m acts run --strategy record_memo --kind lines \
  --input fixtures/line_memo/input.txt -- cat

# STAR: refuses identity (BAM is not a per-read function)
python3 -m acts run -- STAR --runThreadN 1

# Suite B PE uniqueness (kill test for the STAR *instance*)
python3 -m acts probe-suiteB
# → results/suiteB_dups.csv  (best 1.15× if per-read, on i03)
python3 -m acts overlap --suiteb
# → results/suiteB_overlap.csv  (incremental kill: recall_in_new)

# VEP/SnpEff (tools not on PATH yet). Protocol first:
# pipeline/docs/VEP_PROTOCOL.md
bash scripts/setup_vep_chr22.sh
```

## EGAS (kept)

```bash
python3 -m egas -c contracts/star_suiteB.toml check
python3 -m egas -c contracts/fat_copy.toml run --workloads held
```

EGAS is not Survivor 1. Do not rebrand it as a new optimizer.

## Tests

```bash
./run_tests.sh
```
