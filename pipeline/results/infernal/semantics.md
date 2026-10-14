# Test I semantics review (no cmscan runs)

Written before any `cmscan` in this test. Source is the Infernal 1.1.5
tree unpacked from `https://eddylab.org/software/infernal/infernal.tar.gz`
(`pipeline/data/infernal/src/infernal-1.1.5`, gitignored). The tarball is
31,300,142 bytes, md5 `780bab55b34cfa6f090f4a4badfd1ed8`, sha256
`ad4ddae02f924ca7c85bc8c4a79c9f875af8df96aeb726702fa985cbe752497f`.
The same byte length was returned for the `http://eddylab.org` alias.
The archive's top directory is `infernal-1.1.5/`. The built binary
banners `# INFERNAL 1.1.5 (Sep 2023)`. Line numbers are that tree.
Checksums for the source, both Rfam releases, and the 100 genomes are
`results/infernal/inputs.tsv`.

Body lines, here and in the pilot, are lines that do not start with `#`.

## What this review is deciding

Two argv variants, both on `cmscan` against a pressed Rfam CM file.
The documented genome-annotation command (Rfam Help, "Genome
annotation", the Methanobrevibacter example) is

```
cmscan -Z <Mb> --cut_ga --rfam --nohmmonly --tblout T --fmt 2 --clanin Rfam.clanin Rfam.cm queries.fa
```

`<Mb>` is `(2 * total residues) / 1e6` for that sequence file. The task
sketch omitted `-Z`; the documented command includes it, and the source
below says why that argument is the search space. The no-clan variant
is that command without `--fmt 2` and without `--clanin` (and without
`--oskip` / `--oclan`, which the documented command also does not pass).
`cmscan` refuses an unpressed file (`src/cmscan.c:483`).

## (a) What sets Z

There is no `--Z` option. The options table has `-Z` only
(`src/cmscan.c:130`): "set search space size in *Mb* to `<x>` for
E-value calculations".

If `-Z` is not set, `cfg->Z` is `cmfp->ssi->nprimary`, the number of
models in the pressed file, and `Z_setby` is
`CM_ZSETBY_SSI_AND_QLENGTH` (`src/cmscan.c:491-498`). For each query,
`qZ` is the query length, or twice that length unless `--toponly` or
`--bottomonly` (`src/cmscan.c:588-592`). The pipeline is created with
`cfg->Z * qZ` (`src/cmscan.c:598`). So the default search space is

```
Z = (number of CMs) * (query length) * (2, unless one strand)
```

It is both the CM-database cardinality and the query length. It is not
the sum of model lengths.

If `-Z` is set, `cm_pipeline_Create` overwrites that product
(`src/cm_pipeline.c:376-390`):

```
pli->Z = (int64_t)(esl_opt_GetReal(go, "-Z") * 1000000)
```

The megabase value becomes a residue count. It is not multiplied by the
model count or by the query length. Every query in the file shares that
one Z. That is the quantity the Rfam annotation page tells the user to
pass.

The printed E-value is `pvalue * eZ` (`src/cm_tophits.c:932-939`). For a
CM-mode hit, `eZ` is `cur_eff_dbsize`
(`src/cmscan.c:919-920`). `UpdateExpsForDBSize` sets

```
cur_eff_dbsize = (dbsize / exp->dbsize) * nrandhits
```

with `dbsize = pli->Z` (`src/stats.c:538-546`, called from
`src/cm_pipeline.c:1073`). `exp->dbsize` and `nrandhits` are stored on
the model (the calibration block, `ECMLI` and its siblings). They do
not read the rest of the CM file.

**How a wrong Z shows up.** Bytes differ in the E-value field. Tokens
differ. Class: value-only. A hit set can also change, but only when the
reporting threshold reads E. `--cut_ga` does not (next section). Under
the default pipeline, filter thresholds do read Z (section f); `--rfam`
does not.

**How the pilot detects it.** Stock-vs-stock uses one `-Z` string and
must be byte-identical. The same scan with `-Z` omitted, or with `-Z`
replaced by the model count, must be value-only on the E-value field if
this reading is right. The string passed as `-Z` is checked, before any
comparison, so that `(int64_t)(atof(s) * 1e6)` equals `2 * residues`.
A truncated conversion is a one-residue Z and is not used.

## (b) `--cut_ga`: registered, reported, included

`--cut_ga` turns E-value reporting off and selects the model's GA bit
cutoff (`src/cm_pipeline.c:286-291`). `cm_pli_NewModelThresholds` sets
`pli->T = pli->incT = cm->ga` (`src/cm_pipeline.c:1117-1120`).
`cm_pli_TargetReportable` is then `score >= pli->T`
(`src/cm_pipeline.c:852-857`). Inclusion uses the same bit score
(`src/cm_pipeline.c:865-869`), so included and reported are the same set.

The final CM search is called with that threshold
(`src/cm_pipeline.c:3682`). A hit below GA is not added. A hit that is
added is flagged `CM_HIT_IS_REPORTED` and `CM_HIT_IS_INCLUDED` in the
scan pipeline, before the model is discarded
(`src/cm_pipeline.c:3770-3799`). `cm_tophits_Threshold` does not
re-threshold when `use_bit_cutoffs` is set; it only counts hits that
are not removed duplicates (`src/cm_tophits.c:1427-1447`).

The one exception inside a model: overlapping windows of the same
model, sequence, and strand. The first overlap pass removes the lower
scoring duplicate and clears its reported flag
(`src/cm_tophits.c:1027-1031`, `src/cmscan.c:671-673`). That duplicate
is the same model. It is not another family.

**How a wrong gate shows up.** Extra or missing rows, or an `inc` token
of `?` where stock printed `!`. Class: missing, extra, or value-only.

**Pilot.** Token comparison includes `inc`. Stock-vs-stock must match
it. There is no separate inclusion arm.

## (c) Column widths

Infernal's tabular writers are the HMMER tophits lineage
(`src/cm_tophits.c:2232-2235` cites `p7_tophits.c`). Format 1
(`src/cm_tophits.c:2253-2257`) and format 2
(`src/cm_tophits.c:2358-2367`) set

- target-name width = `ESL_MAX(20, cm_tophits_GetMaxNameLength(th))`
- target-accession width = `ESL_MAX(9, cm_tophits_GetMaxAccessionLength(th))`
- query-name width = `ESL_MAX(20, strlen(qname))` for this query only
- format 2 also takes index widths from `th->N`, a clan-name width, a
  model-length width, and a source-length width

`GetMaxNameLength` walks `h->unsrt[0 .. h->N)` and does not test
`CM_HIT_IS_REPORTED` (`src/cm_tophits.c:637-662`). The comment states
the same side effect as HMMER: a caller that prints a subset can see a
different width than the width over all registered hits. Printing emits
a row only when `CM_HIT_IS_REPORTED` (`src/cm_tophits.c:2290`,
`2489-2491`).

Under `--cut_ga`, a hit is registered only when its score already
passed GA, and that hit is marked reported, except a same-model window
duplicate whose reported flag was cleared. That duplicate carries the
same name. A model with no GA hit contributes no name. Query-name width
does not read the CM file.

Format 2's index width is `integer_textwidth(th->N)`
(`src/cm_tophits.c:2363-2364`). `th->N` counts every registered hit,
including same-model duplicates. Another family's hit increases `N` and
can widen the index field of every row.

**How a width bug shows up.** Bytes differ, `split()` tokens do not.
Class: whitespace-only. If an unreported hit also changes a printed
number, the class is value-only, and that is a failure of the claim.

**Pilot.** Every comparison records a byte check and a token check.
Stock-vs-stock must be byte-identical. An oracle replay whose model set
is exactly the models with a registered hit must be byte-identical if
the width is a function of that set. The 5% deletion must not be
classified as whitespace-only: those families' rows are missing.

## (d) Sort, ties, and query order

Output order is per query, then E-value. `cmscan` reads the sequence
file in order and writes that query's tblout before the next query
(`src/cmscan.c:579-730`). Within a query, `cm_tophits_SortByEvalue`
(`src/cmscan.c:680-681`) orders by E-value ascending, then bit score
descending, then `seq_idx`, then start, then `pass_idx`
(`src/cm_tophits.c:193-216`). The comparator returns 0 when all five
match. `qsort` is not stable on that tie. `cm_idx` is not an output
key. Thread results are merged and then sorted
(`src/cmscan.c:651-654`), so a total order does not depend on `--cpu`.

**How it shows up.** Class: order, if two hits tie on all five keys, or
if a Z change reorders by E-value. **Pilot.** Stock-vs-stock at
`--cpu 4`. An order class on that pair stops the arm: the tool is not
deterministic at the locked width, and no later replay is scored.

## (e) `--fmt 2`, clans, and overlap

`--fmt` requires `--tblout` (`src/cmscan.c:135`). `--clanin`, `--oclan`,
and `--oskip` require `--fmt 2` (`src/cmscan.c:2138-2156`). `--oclan`
also requires `--clanin` (`src/cmscan.c:174`).

After the per-query scan, two passes run (`src/cmscan.c:671-677`).

1. `cm_tophits_SortForOverlapRemoval` then
   `cm_tophits_RemoveOrMarkOverlaps(..., FALSE)`. The removal sort is
   by model index, and removal is only among hits that share a model,
   sequence, and strand (`src/cm_tophits.c:1174-1185`, `1239-1240`).
   This pass deletes same-model window duplicates. It does not read
   another family.

2. `cm_tophits_SortForOverlapMarkup(..., --oclan)` then
   `cm_tophits_RemoveOrMarkOverlaps(..., --oclan)`. With `--oclan`
   false, which is the documented command, the second pass groups hits
   that share a sequence and a strand and marks overlaps across models
   (`src/cm_tophits.c:1193-1195`, `1237-1250`). Marking sets
   `CM_HIT_IS_MARKED_OVERLAP` and the overlap indices. It does not clear
   `CM_HIT_IS_REPORTED` (`src/cm_tophits.c:1146-1148`).

Format 2 exists to print that markup: whether a hit has a higher
scoring overlap, the output index of that overlap, and the overlap
fractions, plus the clan name when `--clanin` was read
(`src/cm_tophits.c:2336-2346`, `2474-2479`). `--oskip` omits a reported
hit whose `win_oidx` is set (`src/cm_tophits.c:2450-2452`). The
documented command does not pass `--oskip`, so the overlapping row is
still printed and its overlap columns still name the other hit.
`--clanin` stores `clan_idx` on the hit (`src/cm_pipeline.c:3710`). The
scan does not skip a model because a clan mate already hit. Clan
membership changes the markup grouping only when `--oclan` is set.

So overlap resolution between families does read other models' hits.
It reads registered hits, not the models that produced none. A model
below GA is absent from the hit list and cannot move another family's
row. A replay whose CM file contains exactly the models with a
registered hit, in file order, sees the same hit list and the same
markup. A replay that drops a hitting model changes the survivor's
overlap columns (value-only) and drops that model's rows (missing).
Format 1 does not print the markup, so the same drop is missing rows,
and value-only only if Z or a width changes.

**Pilot.** Both variants. The oracle replay (every model that has a
registered hit) must be byte-identical if this containment holds. The
5% family drop must differ: missing rows, and on format 2 also
value-only on at least one surviving row if any dropped family
overlapped a survivor. If the complete-hit-set replay is not
byte-identical, the containment claim is false and the clan variant is
REFUSE, not EXACT.

## (f) Filters, `--nohmmonly`, nondeterminism

The filter choice is fixed before any model is scored
(`src/cm_pipeline.c:376-379`, `402-416`).

- `--rfam` sets F1=0.06, F2=F2b=0.02, F3=F3b=F4=F4b=F5=F5b=0.0002,
  F6=0.0001 (`src/cm_pipeline.c:479-487`). Those are the thresholds of
  a database of at least 20 Gb. They do not read `pli->Z`.
- The default strategy, used when none of `--max`, `--nohmm`, `--mid`,
  `--rfam` is set, picks the F thresholds from `Z` in megabases
  (`src/cm_pipeline.c:489-559`). A smaller CM file then changes which
  windows survive. That strategy is not the documented command.
- `--FZ` overrides the Z used for those default thresholds. It is
  incompatible with `--rfam` (`src/cmscan.c:2295`).

`--nohmmonly` sets `do_hmmonly_never` (`src/cm_pipeline.c:614-616`).
Without it, a model with zero base pairs takes the HMM-only pipeline
(`src/cm_pipeline.c:1021-1030`), and its E-value uses
`pli->Z / om->max_length` instead of `cur_eff_dbsize`
(`src/cmscan.c:919-920`). The documented command passes `--nohmmonly`
so every model, including a zero-base-pair model, is scored with the CM
and with the GA cutoff that was calibrated in CM mode. The Rfam page
states that reason.

The RNG seed defaults to 181 (`src/cmscan.c:257`). The pipeline reseeds
before a stochastic trace unless the seed is 0, in which case the seed
is `time()` (`src/cm_pipeline.c:216-222`). Seed 0 is nondeterministic.
The default is not. `--cpu` changes the worker count and the default
block size (`src/cmscan.c:525-540`). It does not change the per-model
search. Stock-vs-stock is the check that this is true at `--cpu 4`.

**How a size-dependent filter would show up.** Missing or extra rows on
a subset replay even with `-Z` held and `--cut_ga` set, if `--rfam` were
absent. **Pilot.** The argv includes `--rfam`. A row-set difference on
the complete-hit-set replay is this failure, or the overlap failure in
(e), and is not called EXACT.

## What ACTS should infer

The documented `-Z` is the sequence file's residue count, not the CM
count. Under that argv the printed E-value does not move when models
are added or removed, and `--rfam` keeps the filters off Z. The GA gate
is a per-model bit score. That is an identity normalizer for the CM
database: no further pin.

`-Z {entry_count}` is the wrong pin. It would replace the sequence-size
search space with the model count in megabases
(`src/cm_pipeline.c:383-385`). The pilot's known-bad pin, if inference
emits it, must not be byte-identical.

The clan variant is not a reason to refuse before the replay. The
second overlap pass reads other families, and format 2 prints that
reading, but only registered hits are in the list. The candidate set
of an exact replay is those hits. The pilot is the test of that
containment. If the complete set is byte-identical, the variant is
eligible for EXACT and the inference is still "no pin". If it is not,
the variant is REFUSE: the coupling is not contained by the hit set,
and no pin repairs a printed overlap index.

The shipped knob rule is narrower than that sentence. A contract with
no fitted size member is reported as `no knob`, and exact mode then
refuses (`acts/infer_knobs.py`, `no fitted size member`). A CLI
`REFUSE_PIN` on a body that the oracle replay matched is a needless
refusal, recorded as such. It is not an EXACT result, and it is not a
reason to invent a pin.

`parse_reference_text` accepts a profile only when the first token is
`HMMER3/f` (`acts/reference_formats.py:17`, `228`). An Rfam CM file
starts with `INFERNAL1/a` and ends each model at `//`, with `CLEN`
rather than `LENG`. The shipped CLI cannot split that file. If the
pilot's E2 needs the split, the parser grows a second block grammar
without a tool name: a magic token, a `//` terminator, and a length
tag. HMMER fixtures stay on `HMMER3/f` and `LENG`.

## Genomes, locked before any cmscan

Pool: the 100 accessions in `results/infernal/inputs.tsv`, sorted.
Pilot seed `20261041`, one draw, not reused:

1. `GCF_049949635.1`

Measured seed `20261042`, ten draws from the pool without the pilot,
then sorted. This list is not resized after a scan. The row floor is
2,000 tblout body lines summed across these ten files. A byte match
below that floor is INCONCLUSIVE.

1. `GCF_003956185.1`
2. `GCF_013168095.1`
3. `GCF_022846215.1`
4. `GCF_028743355.1`
5. `GCF_030515405.1`
6. `GCF_030708175.1`
7. `GCF_037287675.1`
8. `GCF_054510725.1`
9. `GCF_055382035.1`
10. `GCF_059615465.1`

## Releases

Rfam 15.0 and 15.1, the newest consecutive pair on
`ftp.ebi.ac.uk/pub/databases/Rfam/`. Family counts are the README
history rows and the pressed model counts, which agree.

| Release | README | Pressed models | `Rfam.cm.gz` md5 |
|---|---:|---:|---|
| 15.0 | 4,178 (`README` history, the 15.0 row; the introduction still says 14.10 / 4,170) | 4,178 | `db43d57e6d20349ea734729d40eed31b` |
| 15.1 | 4,227 (introduction and history) | 4,227 | `29d2124803afbfaddbbb3c722b2ad972` |

`Rfam.clanin` md5 `04fa477aad9af3ff177127ec0db7732e` (15.0, 5,418 bytes)
and `9c526f544f0b2789f8e15f5de746f92a` (15.1, 5,778 bytes). R is 15.0.
R+1 is 15.1.
