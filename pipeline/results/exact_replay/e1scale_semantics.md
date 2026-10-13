# E1-scale semantics review (no runs)

Written before any E1-scale scan. Source is the HMMER 3.4 tree at
`pipeline/builds/hmmer-3.4-src` (gitignored; line numbers are that tree).
The binary under test is Homebrew `hmmscan`, `# HMMER 3.4 (Aug 2023)`.
Question under review: on `hmmscan --cut_ga`, can a model that is not a
replay candidate change tblout or domtblout bytes?

Body lines, here and in the pilot, are lines that do not start with `#`.

## (a) Name and accession widths

`p7_tophits_TabularTargets` (`src/p7_tophits.c:1613-1615`) and
`p7_tophits_TabularDomains` (`src/p7_tophits.c:1718-1720`) set

- target-name width = `ESL_MAX(20, p7_tophits_GetMaxNameLength(th))`
- target-accession width = `ESL_MAX(10, p7_tophits_GetMaxAccessionLength(th))`
- query-name width = `ESL_MAX(20, strlen(qname))` for this query only
- query-accession width = `ESL_MAX(10, strlen(qacc))`, or 10 if there is no accession

`GetMaxNameLength` (`src/p7_tophits.c:586-594`) and
`GetMaxAccessionLength` (`src/p7_tophits.c:605-613`) walk `h->unsrt[0 .. h->N)`.
That is every registered hit. The functions do not test `p7_IS_REPORTED`
or `p7_IS_INCLUDED`. The comment at `src/p7_tophits.c:577-580` states the
consequence: a caller that prints a subset can see a different width than
the width over all registered hits.

Printing itself is the subset. Both tabular functions emit a row only when
`th->hit[h]->flags & p7_IS_REPORTED` (`src/p7_tophits.c:1643-1644`,
`1736-1737`). Domain rows also require `dcl[d].is_reported`
(`src/p7_tophits.c:1741`).

What gets registered, under `--cut_ga`, is the same set that is reported.

`p7_pipeline_Create` on `--cut_ga` turns E-value reporting off and selects
model bit cutoffs (`src/p7_pipeline.c:165-171`). In scan mode,
`p7_Pipeline` reads the rest of a profile only after the MSV filter
(`src/p7_pipeline.c:739-744`) and then calls `p7_pli_NewModelThresholds`,
which sets `pli->T = pli->incT = om->cutoff[p7_GA1]` and
`pli->domT = pli->incdomT = om->cutoff[p7_GA2]` (`src/p7_pipeline.c:540-545`).
A hit is created only if `p7_pli_TargetReportable` is true
(`src/p7_pipeline.c:832-840`). For a bit cutoff that predicate is
`score >= pli->T` (`src/p7_pipeline.c:414-416`). The same call then sets
`p7_IS_REPORTED` and, because `incT == T`, `p7_IS_INCLUDED`
(`src/p7_pipeline.c:913-919`). `p7_tophits_Threshold` does not re-threshold
when `use_bit_cutoffs` is set; it only counts
(`src/p7_tophits.c:933-960`).

So a model that passes F1/F2/F3 and fails GA1 is not registered. It is not
in the width. A model that passes GA1 is registered and reported. At the
sequence level, "all of `th`" and "reported only" are the same set under
`--cut_ga`. "Included only" is not a narrower set: inclusion uses the same
GA bit score.

This is the opposite of E-value mode. There the hit list can be longer
than the final reported set (`src/p7_pipeline.c:832-835`), and the width
loop would then read unreported hits. That path is not this test.

Query-name width does not read the model database. It cannot change
because a candidate model was dropped.

**How a width bug would show up.** Bytes differ. `split()` tokens do not,
because the formats pad with spaces (`%-*s`, `%9.2g`, `%6.1f`). Class:
whitespace-only. If the pilot's reading of the gate is wrong and an
unreported hit also changes a printed number, the class is value-only
instead, and that is a failure of the claim.

**How the pilot detects it.** Every comparison runs a byte check and a
token check. Stock-vs-stock on the pilot sample must be byte-identical;
a width that depends on thread interleaving or on an RNG would fail there
first. E1 and E2 must be byte-identical to stock. The unpinned control
must not be whitespace-only (its E-value tokens change). The 5% model
deletion must not be whitespace-only (those rows go missing).

### Remedies, not implemented

The width loop does not consult the reported flag. If a later HMMER, or
this pilot, registers a hit it does not print, one of these would be the
redesign. None is adopted before the pilot. Each has its own controls.

1. **Pad.** Add to the replay database the registered hits that set the
   width, even when they are not candidates, and still report only the
   candidate rows. Positive control: E1 on the original 300 stays
   byte-identical (the pad is empty when every width-setter is already a
   candidate). Negative control: a pad model that itself passes GA must
   not be used; that case has to fail as extra rows, or the pad is
   unsound. Detector: a fixture whose only unreported registered name is
   longer than every reported name is whitespace-only before the pad and
   byte-identical after it.
2. **Refuse.** If the hit that sets the name or accession width is not a
   candidate, do not replay. Positive control: E1 on the original 300
   still ships, because that width-setter is a candidate. Negative
   control: the long-name fixture must refuse, and must not be reported
   as exact.
3. **Tokens.** State the claim as byte-identical modulo column padding,
   and require `split()` tokens to be equal. Positive control: a
   padding-only pair is TOKEN-EQUAL and not EXACT. Negative control: the
   unpinned run is not token-equal (E-value tokens differ on every line).
   The 5% deletion is missing rows, not token-equal.

## (b) Other reads of non-candidate models

**domZ.** After the per-query scan, `hmmscan.c:490-491` sorts, then calls
`p7_tophits_Threshold`. If `domZ` was not set on the command line,
`pli->domZ = th->nreported` (`src/p7_tophits.c:962-963`). `nreported`
counts `p7_IS_REPORTED` hits (`src/p7_tophits.c:954-959`). The domain
conditional E-value is `exp(lnP) * pli->domZ` (`src/p7_tophits.c:1767`).
Sequence E-values use `pli->Z` (`src/p7_tophits.c:1675`, `1762`), and `-Z`
fixes `Z` before the scan (`src/p7_pipeline.c:194-198`), so
`p7_pli_NewModel` does not replace it with the running model count
(`src/p7_pipeline.c:498`).

Under `--cut_ga`, `nreported` is the number of GA1 hits. A model below
GA1 never increments it. A candidate that is omitted from the replay
database decrements it, and every remaining domain row's c-Evalue can
change.

**How it shows up.** Missing rows for the omitted model, and value-only
on surviving domtblout rows when `domZ` changes. The tblout E-value does
not move if `-Z` is still the full release count.

**Pilot.** The injected control deletes 5% of the oracle candidate models
and reruns the pinned replay. It must differ from stock, and the deleted
models' pairs must be classified missing. Value-only on the surviving
domain rows is recorded if present; it is not required. The unpinned
control (no `-Z`) must differ on every body line: `Z` becomes the
candidate-database size and every sequence E-value token changes
(value-only, not whitespace-only).

**incE / incdomE.** `--cut_ga` sets `inc_by_E` and `incdom_by_E` to false
(`src/p7_pipeline.c:169-170`) and then overwrites `incT` / `incdomT` with
GA1 / GA2 (`src/p7_pipeline.c:544-545`). The default inclusion E-values
are not read. `p7_pli_TargetIncludable` and `p7_pli_DomainIncludable`
compare bit scores (`src/p7_pipeline.c:450-462`). Inclusion equals
reporting. A non-candidate model has no threshold to contribute.

**How it would show up.** The tblout `inc` column, or a domain row present
on only one side. Class: value-only, or missing/extra. Pilot: token
comparison includes that column. Stock-vs-stock must match it. E1 must
match it. There is no separate inclusion arm; a mismatch here is a failed
E1, not a new test.

**Sort and ties.** `hit_sorter_by_sortkey` (`src/p7_tophits.c:310-328`)
orders by `sortkey` descending, then `strcmp` of the model name, then
strand, then alignment start. Under `--cut_ga`, `inc_by_E` is false, so
`sortkey` is the bit score (`src/p7_pipeline.c:862`), not a P-value and
not a file position. `hmmscan` sorts once per query before output
(`src/hmmscan.c:490`). `qsort` returns equal only when name, strand, and
start all match, so distinct Pfam names make the order a function of the
hit set and the scores.

**How it would show up.** Same row keys, different sequence: class order.
A score change that also reorders is value-only and order. File order of
the replay database is not an input to this comparator. Pilot: the
classifier reports order when the key sequence differs and the key
multiset does not. Stock-vs-stock must not report it. E1 must not report
it.

**Filters and the traceback.** F1/F2/F3 return before a hit is created
(`src/p7_pipeline.c:725-762`). They read that model and that sequence.
They do not read other models. Domain-definition sampling resets its RNG
to the stored seed when `do_reseeding` is set (`src/p7_domaindef.c:609-613`).
A seed that depended on the database would make two stock runs differ.

**Pilot.** Two stock `--cut_ga` scans of the pilot sample, same database,
no `-Z`. Bodies must be byte-identical before E1 or E2 runs. If they are
not, the pilot stops. That failure is indeterminism, not an exactness
result.

## (c) The "--" row and the description column

tblout and domtblout do not emit a body line whose payload is `--`.
A query with no reported hit contributes no body line
(`src/p7_tophits.c:1643-1644`). A null accession is printed as `-`
(`src/p7_tophits.c:1651`, `1757`). A null description is printed as `-`
(`src/p7_tophits.c:1689`, `1778`). The description is the last `%s`, not a
width-limited field, so a name-width change does not truncate it and does
not merge it into the previous column.

The token `--` in this file is the human-readable header underline for the
domain-count column (`src/p7_tophits.c:1169`). That write goes to the `-o`
stream, which the locked argv sends to `/dev/null`. It is not a compared
body line. Header lines in the two tables start with `#` and are excluded.

**How it would show up.** A missing description becomes the token `-`:
value-only on that row, not whitespace-only. A query that loses every hit
disappears as missing rows, with no sentinel left behind. An extra `-`
token from a null accession is value-only if the accession string itself
changed.

**Pilot.** The token check treats `-` as a value. Whitespace-only means
every token matches and some bytes do not. The known-good 300 and the
pilot E1/E2 runs must not change a `-` into a description or the reverse.
The injected deletion must be missing keys, not a rewrite of another
row's description.
