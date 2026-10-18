# Diverse-genome semantics review (no hmmscan runs)

Written before any scan in this experiment, and before the pilot.
Source is the HMMER 3.4 tree at `pipeline/builds/hmmer-3.4-src` in the
shared checkout (gitignored; line numbers are that tree). The same
tree is the one reviewed in `results/exact_replay/e1scale_semantics.md`.
This note does not repeat that review as a new claim. It records the
writers again where a diverse proteome can break a stitching or width
assumption that two bacterial genomes did not exercise.

Body lines are lines that do not start with `#`. The compared files are
tblout and domtblout. The human-readable report is not compared.

The local Pfam 38.2 file scanned for name lengths is
`pipeline/data/hmmer/Pfam-A.hmm.gz` in the shared checkout. Its longest
`NAME` is 30 characters (`Bacteriocin_streptolysin_S_pre`). Its longest
`ACC` is 10 characters (`PF10417.15`). The scan listed 147 `NAME`s
longer than 20. Those lengths are input facts about the reference, not
hmmscan results. The md5 of that file is in `pfam_name_lengths.json`.

## What is per query, and what is not

`hmmscan` reads one query, builds that query's hit list, writes that
query's tabular rows, and destroys the list before the next query
(`src/hmmscan.c:427-507`). Tabular output is written before the next
`esl_sqio_Read` (`src/hmmscan.c:496-497`). The writers say the tables
are designed to be concatenated across queries
(`src/p7_tophits.c:1601-1602`, `1705-1706`). Header lines are written
only when `nquery == 1` inside that process, and they start with `#`.
The tail, written once after the loop, also starts with `#`
(`src/hmmscan.c:517-518`).

So a body line does not depend on a later query, and it does not depend
on an earlier query's hit list. A file-wide column width is not what
these writers compute. Two queries in one process can pad to different
widths. Putting their body lines back in input order keeps each query's
bytes. It does not recompute a width.

TARE's stitcher (`acts/replay_batch.py` `merge_bodies`) does that and
only that. It keeps the original line. It groups lines by whitespace
column `record_col`, which for this command is the query name (tblout
column 2, domtblout column 3, counting from 0). The record key is the
FASTA name (`acts/reference_formats.py` `read_records`), the same token
HMMER stores.

## (a) Target-name and target-accession width

`p7_tophits_TabularTargets` and `p7_tophits_TabularDomains` set

- target-name width = `ESL_MAX(20, p7_tophits_GetMaxNameLength(th))`
- target-accession width = `ESL_MAX(10, p7_tophits_GetMaxAccessionLength(th))`
- query-name width = `ESL_MAX(20, strlen(qname))` for this query only
- query-accession width = `ESL_MAX(10, strlen(qacc))`, or 10 if there is no accession

(`src/p7_tophits.c:1612-1615`, `1717-1720`).

`GetMaxNameLength` walks every registered hit and does not test
`p7_IS_REPORTED` (`src/p7_tophits.c:577-594`). The comment states the
side effect: a caller that prints a subset can see a different width
than the width over all registered hits. Printing emits a row only when
`p7_IS_REPORTED` (`src/p7_tophits.c:1643-1644`, `1736-1737`).

Under `--cut_ga`, a hit is created only when
`p7_pli_TargetReportable` is true (`src/p7_pipeline.c:832-840`). With
bit cutoffs that predicate is `score >= pli->T`
(`src/p7_pipeline.c:414-415`). `p7_pli_NewModelThresholds` sets
`T = incT = GA1` and `domT = incdomT = GA2`
(`src/p7_pipeline.c:540-545`). The same hit is then flagged
`p7_IS_REPORTED` and, because `incT == T`, `p7_IS_INCLUDED`
(`src/p7_pipeline.c:913-919`). `p7_tophits_Threshold` does not
re-threshold when `use_bit_cutoffs` is set; it counts
(`src/p7_tophits.c:933-963`).

Registered and reported are the same set. The width is the longest
reported target name on this query, with a floor of 20. It is not the
longest name in the file, and it is not the longest name in Pfam unless
this query hit that model.

Pfam 38.2 has target names longer than the floor. A query that hits
`Bacteriocin_streptolysin_S_pre` (30) and any shorter family pads every
row of that query to 30. A query that hits only short names stays at
20. Those two queries differ in spacing. A replay that drops the
30-character family shrinks the surviving rows of that query only.

**How it shows up.** Bytes differ, `split()` tokens do not. Class:
whitespace-only, on the surviving rows of that query, plus missing rows
for the dropped family. Other queries are unchanged. If an omitted hit
also changes a printed number, the class is value-only, and that is a
failure of exactness when the decision is `SHIP`.

**How the pilot detects it.** Stock-vs-stock is byte-identical, so a
width that depends on thread interleaving fails before any replay.
TARE versus stock is byte-identical, not token-identical. The injected
5% model drop must not be classified as whitespace-only alone: the
dropped families' rows are missing. Whitespace-only on the survivors is
recorded when it happens. It is not required.

Accession width is the same shape with floor 10. The longest Pfam 38.2
accession in the scanned file is 10, so the accession field stays at
the floor for every query unless a later press disagrees. The pilot
records the pressed accession lengths only if a row's accession token
is longer than 10. No remedy is adopted. The three remedies in the
E1-scale note stay unadopted. This experiment does not spend the
redesign.

## (b) Query-name width, and the description that is not in the table

Query-name width is `strlen` of this query's name. It does not read the
model database and it does not read other queries. Easel stores the
FASTA name as the first whitespace-delimited token and grows the buffer
by doubling (`easel/esl_sqio_ascii.c:3033-3042`). `eslSQ_NAMECHUNK` (32)
is the allocation unit, not a cap (`easel/esl_sq.h:150`). A long protein
id is not truncated. It widens only that query's rows, on both the stock
run and the replay, as long as both see the same name token.

The description printed in tblout and domtblout is the target
description, `hit->desc`, filled from the HMM (`src/p7_pipeline.c:846-848`,
printed at `src/p7_tophits.c:1689` and `1778`). It is the last `%s`.
It is not width-limited. The query's own FASTA description is written
only on the human-readable stream (`src/hmmscan.c:448`), which the
locked argv sends to `/dev/null`. A long protein description does not
appear in either compared table.

**How a query-name bug shows up.** If the stitcher groups on a token
other than the FASTA name, every line of a long-named query falls
through to the unknown bucket and is appended after the known records.
Class: order, and a byte mismatch. If TARE rewrote the FASTA name, the
query-name token itself changes. Class: value-only, or missing plus
extra. Stock-vs-stock cannot see a TARE rewrite. The TARE-versus-stock
byte compare does.

**How a description bug shows up.** It does not, in these two tables,
unless the target description changes. A null target description is the
token `-` (`src/p7_tophits.c:1689`, `1778`). That is value-only. Spaces
inside a target description add `split()` tokens to the right of the
query-name column. They do not move column 2 of tblout or column 3 of
domtblout. The stitcher, which reads a fixed column from the left, still
sees the query name. A parser that assumed a fixed number of fields and
took the description as one field would split it. The byte compare does
not need that parser.

NCBI protein accessions are often shorter than 20, so the query-name
width stays at the floor and this stress is not automatically present.
The draw records the longest FASTA name it can see without downloading a
proteome, and the protocol requires a full-header scan after approval
and before any hmmscan. If every drawn name is at most 20 characters,
the query-name width was at the floor. That fact is reported. It is not
a failure of exactness. The target-name width above is still exercised
wherever a drawn protein hits a Pfam name longer than 20.

## (c) Fixed-width integers that grow

tblout prints the domain-count fields with `%3d`
(`src/p7_tophits.c:1670`). domtblout prints the domain index and the
`of` count with `%3d`, and the coordinates and lengths with `%5d` or
`%5` PRId64 (`src/p7_tophits.c:1755`). Those are minimum widths. A count
of 1000 or more, or a coordinate of 100000 or more, prints extra
digits and shifts the description.

A protein with more than 20 domains of one family still fits in three
digits. The multi-domain stress at 20 is not an overflow. The overflow
thresholds are 1000 reported domains of one family, and 100000 residues
in a coordinate. Human titin is the reason the human reference proteome
is in the draw: it is a long multi-domain protein, not because it is
known here to cross 1000. The stock domtblout, once the run exists, is
what records the maximum domain count and the maximum protein length.
If no protein has more than 20 reported domains, that stress was not
exercised and the genome set is reported as such. Exactness is a
separate rule.

**How overflow shows up.** The count token changes, so it is value-only
against a three-digit value, not whitespace-only. A coordinate that
grows from 5 digits to 6 does the same. Padding below the minimum is
whitespace-only.

## (d) Per-query statistics

`domZ`, when `--domZ` is not on the command line, is `th->nreported`
for this query (`src/p7_tophits.c:962-963`). The domain conditional
E-value is `exp(lnP) * pli->domZ` (`src/p7_tophits.c:1767`). Sequence
E-values use `pli->Z` (`src/p7_tophits.c:1675`, `1762`). `-Z` fixes `Z`
before the scan (`src/p7_pipeline.c:194-198`). `p7_pli_NewModel`
replaces `Z` with the running model count only when `Z` was not set
that way (`src/p7_pipeline.c:498`).

`nreported` counts reported targets, not domain rows. A protein with
many Pfam families has a large `domZ`. Omitting one family decrements
it, and every remaining domain row's c-Evalue can change. Repeated
domains of one family increment the domain index, not `domZ`.

**How it shows up.** Missing rows for the omitted family, and
value-only on surviving domtblout rows when `domZ` changes. tblout
E-values do not move when `-Z` is still the full release count.

**Pilot.** The injected control deletes 5% of the candidate models, at
least one, and reruns the pinned replay. The body must differ, and the
shipped check must refuse. A byte-identical drop is underpowered
(INCONCLUSIVE), not a pass. A check that passes on a differing body is
a failure of the claim.

Inclusion equals reporting under `--cut_ga`, as in the E1-scale note.
A mismatch of the inclusion flag is value-only and is a failed byte
compare. There is no separate inclusion arm.

## (e) Sort, threads, and duplicate names

`hit_sorter_by_sortkey` orders by bit score descending, then model
name, then strand, then alignment start (`src/p7_tophits.c:310-328`).
Under `--cut_ga` the sort key is the bit score. `hmmscan` sorts once
per query after merging worker threads (`src/hmmscan.c:480-490`).
Distinct model names make that order a function of the hit set. The
comparator returns 0 when name, strand, and start all match. `qsort`
is not stable on a tie.

**How it shows up.** Same row keys, different sequence: class order.
Stock-vs-stock at `--cpu 8` is the detector. An order class on that
pair stops the arm. The tool is not deterministic at the locked width,
and no later replay is scored. That stop is indeterminism, not an
exactness result.

Duplicate FASTA names are a stitcher problem, not an HMMER problem.
`merge_bodies` keeps one list per name and emits it once for every
occurrence of that name in the record order. Two records with the same
name have their lines pooled and then written twice. Class: extra, and
order. A proteome with a repeated name is reported. If TARE's decision
is `SHIP` and the bytes differ, that is `UNSAFE`. It is not dropped
from the draw to hide the case.

## (f) The stream that is not compared

`--textw` defaults to 120 and `--notextw` removes the limit
(`src/hmmscan.c:68-69`, `355-356`). That width is passed to the
human-readable target and domain reports (`src/hmmscan.c:493-494`).
It is not an argument of `p7_tophits_TabularTargets` or
`p7_tophits_TabularDomains`. The locked argv sends the human-readable
report to `/dev/null`, as the headline command does. A wrapping
difference on stdout is not a body difference.

## (g) Residue budget on a few-record input

The shipped check is unchanged. `residue_cap_binds` is true when one
record is longer than half the residues in that layer, compared as
`2 * length > total` (`acts/audit.py`). When it binds, the audit is
skipped and the three random pads are skipped. Both decision lines are
`skipped, input below record granularity`. The neighbor pad still runs
on every replayed record. The in-situ check at fill still runs.

A skipped layer has miss probability 1 for a coupling the neighbor pad
does not cover. On a proteome the cap usually does not bind: one
protein is not half the residues. On a few-record FASTA, one contig-scale
protein can be half the file, and both layers skip. A skip is reported
per genome. It is not a pass of the skipped layer, and it is not a
failure of exactness by itself.

The audit draw stays inclusion probability 0.02 and floor 20 records.
When the record count is at most 20 and the cap does not bind, the
floor takes every record, so a difference on at least one record is
seen. This experiment does not window proteins. The Infernal addendum
already says why a sub-window is not a stock row; the same decision
stands here.

## Whole-file bytes are not the identity check

The tabular tail includes the date (`src/p7_tophits.c:2059`), the
working directory, and the option line (`src/p7_tophits.c:2051-2060`).
Two stock runs of one FASTA differ in that tail even when every body
line matches. A compare of the whole file would call a deterministic
tool nondeterministic. Stock-vs-stock and TARE-versus-stock in this
test are body lines only.

## Source file hashes

The line numbers above are `pipeline/builds/hmmer-3.4-src` in the
shared checkout.

- `src/p7_tophits.c` `19b21f090039c80286a641960ee4854ce90285a3d4b32c4d49ec8fef6511267e`
- `src/hmmscan.c` `c60310614e0a748d3e07ee99be19fba94ec0d2b9a4248ec50a65a57f07e1237e`
- `src/p7_pipeline.c` `9823e50269b74cf14ee6bcf9dd6290a1b8d28f720731f61c87b8430c7422388d`
- `src/p7_domaindef.c` `25e4911f7492ddaba2d5612891592bc29fb4a0e9dcacc7b8296caa302e82eb71`
- `easel/esl_sqio_ascii.c` `0da25ad0aa547f030335cfb1faccd5e81b9e95d19c3d2948fd9f466615471f1f`

