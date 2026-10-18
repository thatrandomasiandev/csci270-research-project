# DIAMOND database-order dependence: measured run

Pre-registered after the laptop pilot and before the measured run. The pilot is `pipeline/results/diamond_order/g1_pilot.json` (outcome `PILOT`, code commit `eaefdf862ee35205f4edaaaa5bb4f0ec9bc4800e`). It is not this result. Semantics: `pipeline/results/diamond_order/g_semantics.md`.

Submitted as Slurm job 13223637 on 2026-10-18, after `ssh -O check discovery` succeeded and `squeue -j 13208152` showed no PENDING task. The job writes `pipeline/results/diamond_order/g1_measured.json` on scratch. That file is not a result until the job finishes and the JSON is committed.

## What the pilot already showed

On 300 queries (seed `20261161`, `GCF_001650275.1`, 26,322 rows) every one of the five shuffles changed the tabular body. The changes were missing and extra rows, never a value change. Every changed alignment started within 16 residues of the subject start or ended within 32 of the subject end. A murphy10 match of a default shape sat inside that window and read past the entry (`g1_pilot.json` key `boundary_sample_note`). Example: `WP_000107391.1` against `sp|Q00407|VHUA_METVO` is missing in every shuffle; the alignment starts at subject position 3, one shape hit starts at subject index 9, and the predecessor's last 16 residues differ between the two orders. The original-order database built twice had md5 `efb59b8bd46494c4c1edf504b6a3bfc5`. Two searches of that database were byte-identical. The five shuffled databases had distinct md5s, all different from the original. Resident set size stayed under 1 GiB. The log said `Algorithm: Double-indexed` and `Block size = 2000000000`.

## Measured sample

Genome, unchanged: `pipeline/data/recurrence/A/GCF_001650275.1_protein.faa.gz` (md5 `69a2ef84c55d8fac05393b5023734505`, 5,176 records).

Draw, in file order:

1. Drop every id listed in `g1_pilot.json` key `query.ids` (the 300 pilot queries).
2. From what remains, `random.Random(20261162).sample(..., 2000)`, then sort the indices.
3. Write the query FASTA in that index order. Record its md5. Do not draw again.

The draw was executed once from this procedure, before the measured search, against the genome file above. The resulting query FASTA md5 is `001d44c99ebe6a56ed7aa116648ffc92` (2,000 records, none of them in `query.ids`). The CARC job recomputes that md5 and stops if it differs.

Seed `20261162` is used only for this draw. Shuffle seeds stay `20261163` through `20261167`. They define the same database permutations as the pilot. They are not a new sample. Seeds `20261168` and `20261169` stay unused.

## Command

Same argv as `g1_pilot.json` key `original_search.argv`, including `--threads 2`, `--min-score 40`, `-k 0`, `--motif-masking 0`, `-b 2.0`, `--comp-based-stats 1`, and the same `--outfmt 6` columns. DIAMOND 2.2.5, bytes 22,031,624, md5 `711d4c7b29e24c3fd6ec6a288ec1d326`. Swiss-Prot 2026_03, 575,748 entries, 209,017,843 letters. `makedb` is run on the FASTA in the order under test. No sensitivity flag, no `--hamming-dist-boundary-check`, no `--dbsize`.

Threads stay at 2 so the measured command is the pilot command. A larger thread count is a different run.

## Databases and controls

- Build release order twice. The two `.dmnd` md5s must match. Search that database twice. The tabular files must be byte-identical.
- Build the five shuffles. All five md5s must differ from each other and from the original. The first FASTA id of each file must occur at a different byte offset than in the original, as in the pilot.
- Compare each shuffle to the original after grouping lines by `(qseqid, sseqid)`. Report missing, extra, and value-changed counts, the affected query ids, and, for up to 8 changed rows, the same boundary fields the pilot wrote (`alignment_starts_within_16`, `alignment_ends_within_32`, raw shape hit, neighbor edge).
- If the original search has fewer than 10,000 rows, the outcome is INCONCLUSIVE. The pilot returned 26,322 rows on 300 queries, so this floor is a sanity check.
- If the double search differs, or the double build md5s differ, the outcome is CONTROLS_FAILED. Shuffle differences are not interpreted.
- If the databases are not distinct, the outcome is INCONCLUSIVE. A zero content change on a completed run is a real zero for these 2,000 queries. It is not a claim that the pilot's queries were unaffected.

## Where it runs

CARC, `ssh discovery` only, `sbatch` only, project `/project2/biyik_1165/jjt_373/csci270-star/`, scratch `/scratch1/$USER/`. A Swiss-Prot copy is under `pipeline-ref-second/data/swissprot/`. Check its md5 against `bc9d398533e6df582b563c6c03093bd0` before building. That checksum matched on 2026-10-18. Non-exclusive. Do not touch jobs 12864756 or 13208152. Do not submit while 13208152 has a PENDING task. Re-check that queue no more often than every 30 minutes.

The CARC binary is `pipeline-ref-second/bin/diamond`. Its version string is `diamond version 2.2.5` and its md5 is `7de14b7f9f4c440ddfb5142ad96b1d8b`. It is not the Mac binary named in the command section. The flags, the query draw, and the shuffle seeds are unchanged. The result records this file's bytes and md5. In the 2.2.5 source, the AVX-512, AVX2, SSE, and NEON implementations of `FingerPrint::load` all read 16 bytes before the seed.

The result JSON goes in `pipeline/results/diamond_order/` and carries the git commit, both seeds, the DIAMOND version, the argv, and the md5 of every database file and of the query FASTA.

## What this run does not decide

The option sweep is the separate pilot `g2_options.json`. This measured run does not repeat it. A claim that no option removes the dependence is limited to the options that file marks `checked`.
