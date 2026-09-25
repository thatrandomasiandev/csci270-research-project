# Second Method — census 2026-09-24

**Parked.** The research front door is now Survivor 1 (`python3 -m acts`), not an EGAS transfer study. This page stays so we do not re-open a “second Method” hunt without the five artifacts.

**Claim we wanted to test:** EGAS ships MATCH + min_pair ≥ 2, or writes refuse/narrow, on a scientific Method that is not STAR and not `fat_copy`.

**Result:** no such Method is on disk. The driver records **INCOMPLETE**, not a speedup.

This is not a finding that the protocol is reusable. It is the named non-claim in `SCOPE.md` still holding.

## What a Method must have

From `SCOPE.md`: stock binary, opt binary, identical-machine fairness, a MATCH oracle you can write, a per-symbol profile, held-out workloads.

## Census

| Candidate | Why it is or is not a Method |
|-----------|------------------------------|
| `star` / Suite B | First Method. Stock/opt exist under `star/src/`. Out of scope for “second.” |
| `fat_copy` | In-repo smoke fixture. Proves the driver. Explicitly not a paper Method. |
| `2048` (`Desktop/Coding Projects/2048`) | TypeScript 2048 + expectimax. No stock/opt pair, no perf profile, no MATCH oracle for a locked scientific workload. Rejected. |
| BWA / Bowtie2 / minimap2 / HISAT2 / kallisto / salmon | Not on `PATH` (2026-09-24). Not in this repo. |

No other command-line scientific binary in the ACTS tree has a stock/opt pair plus a MATCH definition plus a profile.

## What we did not do

- Did not invent a 2× 2048 “optimization” to fill the slot.
- Did not copy `fat_copy` and rename it.
- Did not implement Speculative Semantic Execution or a unified-memory LLM pipeline.

## Contract and driver record

- Contract: `contracts/second_method.toml` (fairness knobs only; no profile, no binaries).
- Fixture: `fixtures/second_method_absent/` (empty on purpose).
- Decision: `egas_out/second_method/decision.txt` after `check` → `gate` → `propose` → `run`.

`gate` exits 2 (no profile). `run` / `propose` write **INCOMPLETE** with the artifact-absent reason. That is the pipeline working.

## What would change this page

A second Method appears with all five pieces, then `check` → `gate` → `propose` → `run` either ships or writes refuse/narrow. Until then, STAR 10/10 is still one Method.
