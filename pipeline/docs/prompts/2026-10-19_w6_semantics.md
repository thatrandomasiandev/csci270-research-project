# W6 semantics review — row keys and mixed columns

Written 2026-10-19 before any code change and before any run. Worktree
`ACTS-w6`, branch `exp/w6-row-keys`, starting commit
`1c65571538afcc139af560156147e4276905f9b4`. The system is TARE. The
package is still `acts`. This note does not change a locked result.

## Where the row key is built

`acts/reference_fit.py` is the shipped gate.

- `parse_table_text` splits a data line on whitespace. A `#` line is
  metadata, not a row. There is no program-specific parser.
- `infer_key_columns` picks the record column and the entry column by
  token overlap with the record ids and the entry ids.
- `row_key` is the triple `(record cell, entry cell, index cell)`.
  The index cell is empty when `index_col` is `None`.
- `index_candidates` chooses that index column. If `(record, entry)`
  is already unique it returns `[None]`. Otherwise it returns columns
  that make `(record, entry, column)` unique on the table it was
  shown, integers first, then everything else. If no such column
  exists it raises `duplicate rows have no row-index column`.
- `index_rows` inserts that triple into a dict. A second row with the
  same triple raises `duplicate row key {key}`.
- `_bundle_table` takes the first candidate, then replaces it when a
  later candidate aligns strictly more rows (`_shared_key_count`).
  Both the scan and the final index call `index_rows`. A column that
  is unique on the whole table and repeated on a part aborts the fit
  while that later candidate is being scored, even when an earlier
  column already aligns the rows.
- The same raise is copied in `acts/infer_knobs.py` (`_index_table`)
  and in `scripts/run_reference_diamond.py` (`index_out_file`).

The recorded HMMER refusals use this raise. The third field is an
E-value, so the column being indexed was that E-value, not a
coordinate:

| Accession | Key | Record |
| --- | --- | --- |
| `GCF_015290725.1` | `('WP_000726974.1', 'Gly-zipper_OmpA', '1.2e-06')` | `pipeline/results/exact_replay/headline_measured/headline_measured_13208152_3.json` |
| `GCF_002078355.1` | `('WP_196795573.1', 'TPR_17', '2.4e-08')` | `pipeline/results/diverse_genomes/carc/measured_small_03_GCF_002078355.1.json` |
| `GCF_000284335.1` | `('WP_014453168.1', 'DNA_gyraseA_C', '1.6e-12')` | `pipeline/results/diverse_genomes/carc/measured_small_22_GCF_000284335.1.json` |
| `GCF_001017655.1` | `('WP_052881759.1', 'Hexapep_2', '1.4e-05')` | `pipeline/results/diverse_genomes/carc/measured_small_24_GCF_001017655.1.json` |

The protocol already says the protein and the family each occur once
in the input (`docs/EXACT_REPLAY_PROTOCOL.md`, addendum 2026-10-18).
The collision is two data rows, not two inputs.

BLAST+ refuses one step earlier. `docs/BLAST_PIN_PROTOCOL.md` and
`results/blast_diagnosis/pin_pilot.json` record
`duplicate rows have no row-index column` from `index_candidates`.
No single column makes `(qseqid, sseqid, column)` unique, so the fit
never reaches a pin.

## Where "mixed numeric and text" is decided

`_fit_column` collects the printed tokens of one column from the whole
table and from every part. `parse_finite` accepts a token when
`float(token)` is finite.

- No token parses: role `byte` (pass-through).
- Every token parses: role `numeric`, then the closed normalizer family.
- Some parse and some do not: status `mixed`. `fit_observations`
  appends `{table}: column {i} is mixed numeric and text` and the
  decision is REFUSE.

`parse_table_text` does not collapse a trailing field. The fit's width
is the shortest aligned row. Tokens past that width are checked as one
joined tail (`trailing tokens are not byte-identical`). The token at
the minimum width is still a column, so the first word of a free-text
tail is fitted. On the HMMER per-target table that token is column 18.
Two updates refused there, and the replay body was still byte-identical
to stock:

| Accession | Reason |
| --- | --- |
| `GCF_000001215.4` | `tblout: column 18 is mixed numeric and text` |
| `GCA_001817145.1` | `tblout: column 18 is mixed numeric and text` |

A description word that happens to parse as a float (`42`) makes the
column mixed. The rest of the description is not a normalizer.

## What will change, and the exact rules

No program name enters `acts/`.

**Row-occurrence index.** `index_rows` keeps every row. Rows that share
a base key `(record, entry, index token)` are numbered in file order.
Occurrence 0 keeps the base key, so a table that was already unique is
unchanged. Occurrence `k > 0` stores
`(record, entry, f"{index}\\x1f{k}")`. The separator is not a whitespace
token. `index_candidates` returns `[None]` instead of raising when no
column uniques the rows; occurrence inside `(record, entry)` is then
the index. A candidate that repeats on a part is scored with those
keys. It does not abort the scan. The cells are not rewritten, so a
replay that prints the tool's own lines does not gain a column and
does not change order.

**Pass-through text.** On the aligned tokens of one column, let
`n_num` be how many `parse_finite` accepts and `n_text` how many it
rejects.

- `n_text > n_num`: pass-through text (role `byte`). Not fitted.
- `n_text == n_num > 0`, or `n_num > n_text > 0`: still mixed, still REFUSE.
- `n_text == 0`: numeric, as before.

**Trailing free-text column.** Let `W` be the shortest aligned row. If
any aligned row is longer than `W`, column `W - 1` is the trailing
free-text column (the first token of the unparsed tail). It is
pass-through text even when `n_num >= n_text`. The tokens after `W`
stay on the existing tail check. A last column of an equal-width table
is not trailing; a numeric last column stays numeric.

Byte-identical pass-through cells are required, as for every other
`byte` column. A wrong pairing from occurrence order fails that check
or the row-key set check. It does not become a silent ship.
