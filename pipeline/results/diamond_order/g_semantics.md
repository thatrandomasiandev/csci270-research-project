# G semantics review (before any DIAMOND run)

Written before the G1 pilot and the G2 option sweep. No DIAMOND command has been run for this experiment. This file states what a later number is allowed to mean.

The system under test is TARE. The package on disk is still `acts`. DIAMOND 2.2.5 is the program whose output is being measured. Source commit cited by the earlier diagnosis is `6dc57174369ba131d35a21db9735a48ac01e6610` under `pipeline/data/reference_diamond_dx2/diamond-src`. The binary is the existing Mac build, md5 `711d4c7b29e24c3fd6ec6a288ec1d326`.

## Claim these runs can support

A full `blastp` of one fixed query file against Swiss-Prot 2026_03 can change when the same entries are presented in a different file order. Separately, on the already-diagnosed six-line subset miss, an option either brings those lines back in the subset search or it does not. A pilot number is not the measured result.

## What the code does

`FingerPrint::load` (`src/search/hamming/finger_print.h:146-158`, ARM NEON) reads `q-16`, `q`, and `q+16` with no clip at the sequence boundary. The stage-1 gate keeps a hit only when the identity count is at least `hamming_filter_id` (`src/search/hamming/kernel.h:39`). The default floor is 11 (`src/search/setup.cpp:46`, applied at line 559). Sequences are packed with one delimiter byte and 256 bytes of perimeter padding (`src/data/string_set.h:36`).

`DatabaseFile::make_db` (`src/legacy/dmnd/dmnd.cpp:267-287`) loads FASTA in file order, one block of `1e9` letters, and writes that order. Swiss-Prot 2026_03 is 209,017,843 letters, so it is one block. `makedb` also SEG-masks each sequence before writing. Masking is per sequence. It does not depend on the neighbor.

`Block::length_sorted` (`src/data/block/block.cpp:229-254`) reorders a loaded block by length, breaking ties by the original block id. `run_ref_chunk` calls it only when `lin_stage1_target` or `min_length_ratio > 0` (`src/run/double_indexed.cpp:113-116`). The dx3 command sets neither `--linsearch` nor `--min-len-ratio`. On that command the packed order is the FASTA order, and a shuffle of entries changes every neighbor. If a run log says "Length sorting reference", this assumption is false and the shuffle result is not interpreted as a pure file-order effect.

The same fingerprint is applied to queries. The query file is held byte-identical across arms. A query-order effect cannot explain a difference between two database arms.

## The dx3 command, and the laptop deviation

Stock dx3, from `exact_replay_dx2.s1` and the empty `extra` list on `e1_stock.m8.meta.json`:

```
blastp --db DB --query Q --out OUT --min-score 40 -k 0 --motif-masking 0
  -b 2.0 --comp-based-stats 1 --threads 8 --outfmt 6
  qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore
```

The subset replay adds `--dbsize 209017843`. That flag sets the printed E-value. It is not a stage-1 pin. `-k 0` is the unlimited target list used by dx3 (the 300-query stock file has 31,377 rows, so it is not a cap of 25). `-b 2.0` is larger than Swiss-Prot, so the database is one block. The log line `Block size = 2000000000` is the check. `--algo` defaults to double-indexed (`src/basic/config.cpp:912` when unset; the stock log says `Algorithm: Double-indexed`).

Laptop deviation, required by the shared-machine cap and disclosed in the result file: `--threads 2`, process priority `nice -n 10`, and `--tmpdir` pointed at `~/tmp/tare_g` so temporary files are not written next to the read-only inputs. `--tmpdir` does not change seeding. Threads can. The determinism control is two searches of the same database at threads 2, which must be byte-identical. dx2 B0 found threads 1 and 8 identical on its own queries. That is not this query file, so this pilot does not assume it.

No memory cap is passed to DIAMOND. `--memory-limit` changes the automatic block size (`src/basic/config.cpp:97-126`). The dx3 command pins `-b 2.0` and does not set `-M`. Adding `-M` would be a different command. The runner kills the process if resident set size exceeds 4 GiB and records the kill. A killed arm is not a checked arm.

## What can make a check fail for a reason other than database order

1. **makedb does not preserve order.** Then every shuffle has the same database and the same hits, and the test is blind. Detection: the original FASTA built twice must have the same `.dmnd` md5 (the header structs `ReferenceHeader` and `ReferenceHeader2` have no timestamp). Each shuffle's `.dmnd` md5 must differ from the original and from the other shuffles. The first FASTA id must occur as plaintext at different offsets. If the md5s match, the outcome is INCONCLUSIVE, not "order does not matter."

2. **Search is nondeterministic at threads 2.** A second search of the original database must be byte-identical to the first. If it is not, shuffle differences are not attributed to order. Outcome CONTROLS_FAILED.

3. **Line order only.** DIAMOND emits hits in subject order. Rows are compared by the multiset of lines keyed by `(qseqid, sseqid)`, using `classify` from `exact_replay_dx2.py`. `line_order_only` is a separate class. It is not a content change.

4. **Value changes that are not a different alignment.** Same query, same subject, same `qstart qend sstart send`, different score columns: `same_hsp_different_value`. Different coordinates: `different_hsp`. Both count as value-changed. Missing and extra are separate.

5. **E-value depends on database size.** Every arm has the same sequences and the same letter count. `--dbsize` is not added on the full-database arms. A score change is not a size change.

6. **Query composition.** The pilot draw is 300 records, seed `20261161`, from `GCF_001650275.1_protein.faa.gz` (5,176 proteins). That file is not the DX2 query genome `GCF_002853805.1`, the DX2 pilot genome `GCF_002090355.1`, the DX3 rate genome `GCF_001513615.1`, or the DX3 measured genome `GCF_001515725.1`. The measured draw, seed `20261162`, 2,000 records, is specified in the protocol and is not taken in the pilot. It will exclude the pilot ids. Seeds `20261168` and `20261169` are unused.

7. **Too few rows.** If the original-order search returns fewer than 1,000 rows, the outcome is INCONCLUSIVE. The floor is locked here, before the run. DX2's 300-query search returned 31,377 rows, so the floor is a power check, not a target.

8. **The boundary window is not the whole story.** Ranking can drop a later hit after an earlier seed decision. A changed row whose alignment sits in the middle of both sequences is not, by itself, evidence of the 16/32 window. The result file reports, for every changed row, whether the alignment starts at subject position ≤ 16 or ends within 32 residues of the subject end, and for a sample of at most 8 changed rows the murphy10 matches of the default shapes `111101110111` and `111011010010111` (`src/search/setup.cpp:298-300`, alphabet `src/stats/stats.cpp:48`). The scan only looks at seed starts that would read outside the entry. A miss means those shapes did not match there on the reduced alphabet. Neighbor context (predecessor tail, successor head) is reported beside the coordinates.

9. **Options that reorder at search time.** `--linsearch` and a positive `--min-len-ratio` enable `length_sorted`. They are in the G2 sweep because they change which bytes sit next to a seed. They are not pins of the default command.

10. **`--hamming-dist-boundary-check` does not edit stage 1.** `filter_hamming_boundary_crossings` (`src/align/load_hits.h:124-174`) recomputes the 16/32 window inside both sequences and drops seed hits that fail. It runs after stage 1 has already discarded hits. It can remove a line from the full database. It cannot put back a line stage 1 never emitted. "The lost lines return" and "the subset matches the full database under this option" are different outcomes and are both recorded.

11. **`--id2 0` is the unset sentinel.** `set_option` keeps the trait default when the flag equals its default (`src/search/setup.cpp:559`). `--id2 1` lowers the floor. DX3 already measured that this recovers the six lines and changes other rows. In G2 it is the positive control that the checker can see a returned line. It is not a pin of unmodified stage 1.

12. **`--approx-id` cannot lower the floor below 11.** `approx_id_to_hamming_id` maps 50 to 20 and 90 to 30, and the floor becomes `max(11, cutoff)`. `--approx-id 50` raises the floor. It is checked because it changes stage 1. It is not expected to restore the six lines.

13. **`--id` and `--query-cover` are reporting filters.** They cannot restore a line stage 1 dropped. They are checked because the review asked for the early identity and coverage filters. Their failure to restore a line does not say they were ignored.

14. **SEG masking at `makedb`.** Both orders are masked. A hit difference is not a masking difference unless the option under test changes `--masking` or `--soft-masking`.

## G1 controls

- Positive, build: original FASTA made into a database twice, same md5.
- Positive, search: that database searched twice, byte-identical tabular output.
- Positive, comparator: `classify` on a text against itself reports no missing, extra, or value change. A copy with one line deleted reports `row_missing = 1`. This runs before DIAMOND.
- Negative, blindness: five shuffle md5s must all differ from the original. Otherwise INCONCLUSIVE.
- The shuffle comparison itself is the measurement, not a control.

## G2 controls, on the dx2 six-line case

The case is the DX2 measured query file `e1_q.faa` and candidate FASTA `e1_U.faa` against Swiss-Prot 2026_03. The six keys, from `dx3_rootcause.json`:

| Query | Subject |
|---|---|
| WP_000107384.1 | sp\|Q00407\|VHUA_METVO |
| WP_000137873.1 | sp\|Q31S42\|RPAA_SYNE7 |
| WP_000256438.1 | sp\|Q0WWW9\|XYLL3_ARATH |
| WP_000493792.1 | sp\|Q39QB5\|NUOI2_GEOMG |
| WP_001026276.1 | sp\|A9BCC5\|CH10_PROM4 |
| WP_001026276.1 | sp\|Q5GST6\|CH10_WOLTR |

- Known-bad, must reproduce: at threads 2, those six keys are present in the full-database search and absent from the subset search with `--dbsize 209017843`. If they are not, G2 does not claim that an option restored the historical miss. The subset-versus-full table is still reported.
- Search determinism: the full database twice, byte-identical, and the subset twice, byte-identical.
- Positive checker: `--id2 1` on the subset must contain all six keys. If it does not, the checker is blind and no "lines did not return" claim is made.
- Negative checker: `--ignore-warnings` on the subset must be byte-identical to the default subset, and the six keys must stay absent. This flag is not a seeding option. It is not part of the sweep that the paper may cite as checked seed settings.

## G2 options that will be checked

Each is one change on the dx3 command. The subset arm also passes `--dbsize 209017843`, matching the known-bad replay. The full-database arm does not.

Sensitivity: `--faster`, `--fast`, `--mid-sensitive`, `--sensitive`, `--more-sensitive`, `--very-sensitive`, `--ultra-sensitive`, `--shapes-6x10`, `--shapes-30x10`.

Seeding and the first filter: `--masking none`, `--masking seg`, `--masking seg-all`, `--masking tantan`, `--motif-masking 1`, `--shapes 1`, `--seed-cut 0.9`, `--freq-masking`, `--freq-masking --freq-sd 10`, `--algo 0`, `--algo 1`, `--algo ctg`, `--id2 0`, `--id2 1`, `--approx-id 50`, `--hamming-dist-boundary-check`, `--linsearch`, `--soft-masking tantan`, `--soft-masking seg`.

Extension, which is after stage 1 but was asked for: `--ext banded-fast`, `--ext banded-slow`, `--ext full`, `--ext global`, `--ext none`.

Reporting filters that were asked for: `--id 30`, `--query-cover 20`, `--min-len-ratio 0.9`.

## G2 options that will not be checked

`--ignore-warnings` (control only). `--comp-based-stats`, `--no-ranking`, and `--dbsize` were already measured in `dx3_rootcause.json` and are not re-run; they are not cited as part of this sweep. `--evalue`, `--matrix`, gap penalties, `--top`, `--max-hsps`, `--range-culling`, and `--global-ranking` act at scoring or reporting. `--swipe` bypasses the seed filter by aligning every sequence; it is not run, because an exhaustive pass over Swiss-Prot can exceed the 4 GiB cap. `--iterate` only chains sensitivity rounds that are already separate arms. Taxonomy, strand, and frameshift options do not apply to this protein search.

An option that exits non-zero, times out, or is killed for memory is recorded and is not a checked option.

## Outcome rules for the pilot

Locked now. The pilot may not promote itself to a measured result.

- CONTROLS_FAILED: the double search is not byte-identical, or the comparator self-check fails.
- INCONCLUSIVE: fewer than 1,000 original-order rows, or the shuffle did not change the database bytes.
- Otherwise the pilot reports, per shuffle seed, missing, extra, and value-changed counts after the `(query, subject)` grouping, the affected query ids, and the boundary sample. A zero across all five seeds is a real zero on this 300-query draw, not a pass for the 2,000-query run.
