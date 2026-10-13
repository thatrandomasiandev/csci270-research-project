# DX2 Phase A — DIAMOND semantics review (no runs)

Source: DIAMOND tag `v2.2.5`, commit `6dc57174369ba131d35a21db9735a48ac01e6610`
(the commit the second-tool protocol already pinned). Line numbers are that
tree. S1 is the locked `blastp` argv: `--min-score 40`, `-k 0`,
`--motif-masking 0`, `-b 2.0`, `--comp-based-stats 1`, tabular outfmt.
This host runs with `--threads 8` because a parallel job may share the
machine. That count is the same on every arm of a comparison.

`--dbsize` is applied only in `score_matrix.set_db_letters`
(`src/run/double_indexed.cpp:926`): the printed E-value factor becomes
the flag value instead of the database letter count
(`src/stats/score_matrix.cpp:218-224`). For a `.dmnd` database,
`DatabaseFile::letters()` still returns the header letter count
(`src/legacy/dmnd/dmnd.cpp:544-546`). The pin does not replace that
count inside algorithm selection, seed histograms, or the ranking
heuristic. `--min-score` makes `report_cutoff` use the bit score
(`score_matrix.cpp:238-243`), which does not read `db_letters`. Under
S1 the pin changes the printed E-value. It does not change which
alignment passes the score cutoff.

## Behaviors that can make a sub-database differ from a full run

1. **Auto `--algo` by size.** `run_query_iteration`
   (`double_indexed.cpp:283-301`). `Algo::AUTO` becomes double-indexed
   when query letters exceed 32 MiB, or when database letters (else
   file size) are below `256 * (1 << 20)` = 268,435,456, or when the
   query seed table is large. Otherwise a small query against a large
   database becomes query-indexed. The wiki states the two algorithms
   are not exactly identical. S1 does not pass `--algo`. `--dbsize` is
   not the size this test reads. Full Swiss-Prot is 209,017,843 letters
   (D0), which is under 268,435,456, so AUTO is double-indexed on the
   full release and on every smaller subset. A difference would be a
   different HSP or a different row set, not an E-value-only change.
   Pilot: the `Algorithm:` line on stock, on R, and on R+. B3 forces
   `--algo 0` only if those lines disagree.

2. **Seed-frequency masking and database seed statistics.** Frequent-seed
   masking runs only inside `if (config.freq_masking …)`
   (`src/search/stage0.cpp:168`). S1 does not pass `--freq-masking`, and
   the flag defaults off. The complexity mask (`mask_seeds`) is
   per-seed, cutoff 0.8 for this sensitivity (`setup.cpp:129`), not a
   count of other entries. Motif masking is forced off by S1. No
   difference is predicted from these. Pilot: B1. A frequency effect
   would show up as `different_hsp` or a missing row on a subject that
   is in the sub-database. B3 does not turn frequency masking on.

3. **`-b` / `-c` chunking.** `-b 2.0` is 2e9 letters (`config.h` via
   `chunk_size * 1e9`). D0 letters are under 2e9, so the full release
   and every subset are one reference block. S1 sets `-b`. It does not
   set `-c`. `index_chunks` is then 4 for double-indexed and 1 for
   query-indexed (`double_indexed.cpp:313`, trait at `setup.cpp:126`).
   With (1) both sides stay double-indexed, so `-c` stays 4. A real
   block split would show up as a missing or different HSP that
   disappears when `-b` is raised. Pilot: `Block size =` on both logs.
   B3 does not retune `-b` when both logs show one block.

4. **Tie order.** Reported targets are sorted by E-value, then score,
   then `block_id` (`target.h:124-129`, `culling.cpp:92-93`).
   `block_id` is the position in the database being searched, so a
   sub-database renumbers it. Equal E-value and equal score can swap
   two rows. HSP culling at `--max-hsps 1` (the default, not passed by
   S1) sorts by score, then diagonal, then query start
   (`match.h:199-201`), which does not read other entries. An order
   swap is `line_order_only`: same lines, different sequence. Pilot:
   B0 (same database, twice) and B1 (full vs subset). B0 must be
   identical; an order-only B1 difference is a tie on `block_id`.

5. **Composition-based statistics.** S1 passes `--comp-based-stats 1`
   (Hauser). The adjustment is the query composition against that
   subject (`cbs.cpp`), not the other entries. The protocol already
   states this. A CBS-only effect cannot change a row whose alignment
   is the same. It can change `pident` / coordinates only if the
   extension path changes. Pilot: B1 class `same_hsp_different_value`
   versus `different_hsp`. A value-only change on the same interval
   with the pin set would implicate CBS or the E-value factor, not
   the hit list.

6. **E-value and `--dbsize`.** Printed E-value is proportional to the
   letter count unless `--dbsize` overrides it. S1 does not pass
   `--evalue`; the keep rule is `--min-score 40`. The ungapped filter
   for this sensitivity is an E-value of 10000 normalized to 1e9
   letters (`bitscore_norm`, `score_matrix.h:149-151`; trait
   `setup.cpp:123`), so it does not read the database size or the pin.
   The gapped filter trait is 0 (off). Without the pin, replay E-values
   must differ (B1 control). With the pin, an E-value-only change means
   the pin value was not the full-release letter count.

7. **`-k` and `--top`.** `-k 0` sets the per-query cap to `INT64_MAX`.
   S1 does not pass `--top`. The cap is not a top-25 cut. Ranking is a
   separate heuristic and is on by default: targets are extended in
   ungapped-score chunks of at most 400
   (`extend.cpp:114-128`, `MAX_CHUNK_SIZE = 400`), and a chunk that
   yields no new hit can stop the scan
   (`ranking_terminate`, `extend.cpp:148-156` and the outer loop at
   346). `--min-score` disables the E-value chunk extension
   (`extend.cpp:276`, `min_bit_score == 0` is false). The chunk size
   uses `ref_letters / 2e9`, which is 1 for Swiss-Prot and for any
   subset. The early stop still depends on which other targets sit in
   the score order. That can add a row for a query against a subject
   that only another query hit in the full run, drop a row, or change
   the reported HSP. S1 does not pass `--no-ranking`. This is the
   behavior the Independence Certificate is for. Pilot: B1 difference
   class, then B3 with `--no-ranking` on the replay only. A match under
   that flag is recorded. It is not an S1 flag unless the replay then
   matches the unmodified stock run.

8. **Threads and output order.** `seedp_bits` depends on
   `threads * 4 * index_chunks` (`setup.cpp:522-524`) and is at least 8.
   `query_bins` is `max(round(threads/8), 16)` (`setup.cpp:566`), so 1
   thread and 8 threads both use 16 bins. A thread effect would be a
   different row set or a different HSP between `--threads 1` and
   `--threads 8` on the same database. Pilot: B0. Any difference stops
   the pilot. Output order among unequal E-values follows the sort in
   (4), which is deterministic given the rows. B0 also runs stock twice
   at 8 threads.

## What the Independence Certificate sees

R is the pinned replay on candidate union U. R+ is the same pin on
U ∪ Pad. The stated pass rule is: every R body line occurs in R+ with
the same multiplicity, and R+ has no row whose subject is a Pad entry
for a replayed query. A changed or deleted R row fails (1). A hit on a
dropped subject fails (2) only when that subject was drawn into Pad.
An extra row whose subject is already in U does not fail either
condition. That hole is recorded, not patched before the pilot. B2's
negative control (drop 10% of true hit subjects, then the same Pad
draw) is what shows whether (2) can see an incomplete candidate set.
