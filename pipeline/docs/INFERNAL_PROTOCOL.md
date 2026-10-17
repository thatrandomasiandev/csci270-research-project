# Infernal cmscan re-annotation (pre-registered after the pilot)

Written after `results/infernal/pilot.json` and before any measured
cmscan. The genome list was fixed in `results/infernal/semantics.md`
before the pilot. This file does not change it.

Pilot genome `GCF_049949635.1` (seed `20261041`) is not reused.
`-Z` is `2 * sequence residues / 1e6`, sequence lines only. A string
that does not satisfy `int(float(s) * 1e6) == 2 * residues` is not used.
The first pilot scan counted FASTA-header letters and was discarded
(`pilot.json` `discarded_header_z`); it was not compared.

## What the pilot decided

Infernal 1.1.5, Rfam 15.1, `--cpu 4`, 440 tblout body lines, 146 models.
Body lines are the claim. The `#` footer that records the date and the
`--tblout` path differs across runs and is metadata.

| Check | No clan | Clan (`--fmt 2 --clanin`) |
|---|---|---|
| Stock vs stock bodies | byte-identical | byte-identical |
| Oracle on the hit set, file order | byte-identical, 41.2 s vs stock 275.2 s | byte-identical, 40.9 s vs stock 272.3 s |
| Drop 5% of hit models, seed `20261043` (7 models) | differs, class `missing` | differs, classes `missing` and `value-only` |
| Omit `-Z` | class `value-only` | not repeated; `-Z` is on both argvs |
| Safety pads | pass | pass |
| `python3 -m acts run --strategy reference --pin` | `REFUSE_PIN`, `no fitted size member`, 1799.5 s | `REFUSE`, subset probe cannot open the full clan file, 551.9 s |

The clan oracle filters `Rfam.clanin` to models present in the replay
CM. `cmscan.c:2816` (`read_clan_info_file`) rejects a clan-file name
that is absent from the pressed index, so the unfiltered file cannot
be passed to a subset. A one-member clan line is kept so the survivor
still receives its clan name. The filtered replay matched. Coupling
is contained by the hit set.

The no-clan CLI refusal matches the semantics note: no size member is
fitted, so exact mode refuses. The oracle body matched, so the refusal
is needless. It is not EXACT, and it is not a reason to invent a pin.

The clan CLI does not reach that refusal. The fit's whole scan runs,
then a reference subset is invoked with the original `--clanin`, and
cmscan exits on the missing name. That is a probe failure, not a
finding that families fail to replay.

DX2 regression: `tests/test_exact_certificate.py` (6 tests) passed
during the pilot. A live DIAMOND rescan was not repeated.

## Measured run

Script: `scripts/infernal_measured.py`. Output:
`results/infernal/test_i.json`. Same argv, same `-Z` rule, same
filtered clan file on subset scans. Rfam 15.1 only. This pilot did
not scan 15.0; the question under test is a re-run against the new
release, and the new release is the database.

Genomes, seed `20261042`, already sorted in the semantics note:

1. `GCF_003956185.1` — timing genome and the one CLI confirmation
2. `GCF_013168095.1`
3. `GCF_022846215.1`
4. `GCF_028743355.1`
5. `GCF_030515405.1`
6. `GCF_030708175.1`
7. `GCF_037287675.1`
8. `GCF_054510725.1`
9. `GCF_055382035.1`
10. `GCF_059615465.1`

The script recomputes this draw from `inputs.tsv` and stops if it
differs. No genome is added after a scan.

Per variant, per genome: one stock scan and one oracle replay. Bodies
compared with the pilot's row key. On `GCF_003956185.1` the stock and
the oracle are each repeated three times. If those stock bodies
differ, that variant stops. The median of the three stock/oracle wall
ratios is the mechanism timing. It is not an end-to-end CLI speedup:
the CLI does not ship.

CLI confirmation, once, on `GCF_003956185.1` only, both variants.
Expected: no-clan `REFUSE_PIN` / `no fitted size member`; clan `REFUSE`
on the clan-file name check. A different decision is recorded and not
repaired.

Row floor: 2,000 stock body lines summed across the ten files, per
variant. A body match below the floor is INCONCLUSIVE. A body mismatch
is not EXACT. EXACT here means the oracle bodies match on all ten and
the floor is met. The CLI outcome is reported beside that, not folded
into it.

Mac walls are indicative. Scratch is `~/tmp/infernal_work/measured`.

## Outcome addendum (2026-10-14)

`results/infernal/test_i.json`, git `c464622`. Both variants,
oracle bodies byte-identical on all ten genomes. 4,217 stock body
lines each, above the floor of 2,000. Outcome EXACT for the oracle.
The CLI outcome is separate and is not EXACT.

Timing genome `GCF_003956185.1`, three paired walls. Median
stock/oracle ratio 6.67× on both variants (no-clan 6.666, clan
6.667). That is the replay against the hit set (158 models), not a
shipped CLI speedup.

CLI on that genome, once: no-clan `REFUSE_PIN`, `no fitted size
member`, 2058.5 s (probe tool time 616.8 s, then the full-reference
tool time 1408.3 s). Clan `REFUSE`, the subset probe cannot find
`alpha_tmRNA` in the full clan file, 628.2 s. Same decisions as the
pilot. Nothing was retuned.

## Addendum 2026-10-14 — identity exact mode and subset side files

Written before the end-to-end run. The two CLI refusals above are
separate gates. Each is a caller-declared rule. Neither name is
compiled into `acts/`.

### No pin when every value column is identity

Exact mode is requested with `--pin` and no template. If the fit's
numeric columns include a reference-size member (`entry_count` or
`total_entry_length`), inference runs as before, and a missing knob is
still `REFUSE_PIN`. If every value column is the identity normalizer,
there is no pin to infer: replay runs with the caller's argv unchanged.
The in-situ check is the probe-sample replay against the whole probe
sample, with no added option, and it must be byte-identical. The safety
check is unchanged. A size member with no pin still refuses.

Fixture tests: identity ships; a six-decimal `entry_count` column with
no knob is `REFUSE_PIN`; the pinned size-scaled release still ships;
the same shape with the pin omitted refuses.

### Subset side files are declared, not inferred

A subset invocation was passing an argv file that names entries absent
from the subset, and the tool exited. Inferring which file to rewrite
is the wrong default: a token that happens to equal an entry name is
not evidence that the file is an entry list, and a silent rewrite can
change a full run's answer. The caller declares the file, as with
`--pin` and `--prep`:

```
--subset-aux '{arg-after:--flag}:tokens'
```

On a subset invocation only, tokens in that file that name an entry
outside the subset are dropped. A token that is not an entry name is a
label and stays, so a one-member group still carries its label. A line
with fewer than two tokens left is dropped. A call on the full
reference uses the original file. HMMER-shaped replay with no such
rule is unchanged.

The rewritten file is not a new normalizer. It only makes the subset
invocation a legal call.

## Addendum 2026-10-14 — when a cached replay can miss a hit

From Infernal 1.1.5. The documented argv does not pass `--oskip` or
`--oclan`.

Same-model duplicates are removed. `cmscan.c:672-673` sorts for removal
and calls `cm_tophits_RemoveOrMarkOverlaps` with clans ignored. Removal
clears `CM_HIT_IS_REPORTED` (`cm_tophits.c:1141-1143`). The group is the
same model, the same sequence, and the same strand
(`cm_tophits.c:1239-1243`). Removal combined with clan-only matching is
an error (`cm_tophits.c:1230-1232`). That hit is not in tblout. It is
the same family as the hit that removed it.

Cross-family competition is markup. `cmscan.c:676-677` sorts for markup
and calls the same function with `--oclan`. Markup sets
`CM_HIT_IS_MARKED_OVERLAP` and does not clear `CM_HIT_IS_REPORTED`
(`cm_tophits.c:1146-1148`). With `--oclan` false the group is any models
on one sequence and strand. With `--oclan` true it is also the same
`clan_idx`, and a family in no clan is not marked
(`cm_tophits.c:1246-1250`).

A marked hit is left out of format-2 tblout only when `--oskip` is set
and `win_oidx != -1` (`cm_tophits.c:2489-2491`, from `cmscan.c:721`).
`--oskip` requires `--fmt 2` (`cmscan.c:2154-2156`). The documented
command does not pass it, so a marked overlap is still a row.

A cached replay misses a hit after an update only when that hit was
absent from the cached table. Under the documented argv the absent hit
is a same-model duplicate, so removing a different family cannot unmask
it. Under `--oskip`, a lower-scoring overlap of another family is
absent. If that other family changes or disappears, a full run can
report the lower hit and a replay of the cached rows does not.

Measured on the ten Test I genomes, both variants, Rfam 15.1
(`results/infernal/exposure.json`). Hit keys are equal on every genome:
4,217 body rows each. Suppressed rows, defined as a no-clan row that
overlaps a different same-clan family and is absent from the clan
output: 0. Same-clan overlaps that remain in the clan output: 516, in
11 families. Of those families, `GlmZ_SraJ` changed from 15.0 to 15.1
and none were removed. Suppressors changed or vanished: 0, because no
row was suppressed.

A two-model check on `GCF_013168095.1` (`GlmY_tke1`, `GlmZ_SraJ`,
CL00011): format 2 without `--oskip` printed 3 body rows; with
`--oskip` it printed 2. The omitted row was `GlmY_tke1` on
`NZ_CP038408.1`, 5406578–5406430, minus strand. That switch is not in
the documented command. The constructed removal uses `GlmZ_SraJ`
because it is the overlap partner that changed, and because `--oskip`
omits a `GlmY_tke1` hit when both models are searched.

The shipped CLI on that removal, before the index fix below, refused at
the fit: `tblout: column 9 matches no normalizer`. Format 2's first
integer column is a per-file rank. It uniques the rows of one file and
aligns 36 of 460 hits with a half-file scan. The sequence-start column
aligns all 460, and the keys then match. With that key, the columns
that still differ are the rank and the overlap marks (columns 0 and
19–25 on this file). Those are not normalizers. Exact mode now replays
when every refusal is one of those column failures and the row keys
match. The probe-sample body check still has to pass. A key mismatch
still refuses, except the case below: a part reported rows the full
set omitted, and the full set lost none.

## Pre-registration 2026-10-14 — entry groups invalidated together

Registered before the implementation. The witness is the removal of one
overlapping family. The rule below is what shipped.

The caller declares a group file the same way as a pin:

```
--invalidate-group '{arg-after:--flag}'
```

Each line is a group id and then entry names. At cache fill, every covered
content hash stores the group ids it belonged to. On a later run a group is
invalid when any member is new, changed, or removed, or a member's set of
groups changed. Every still-present member of an invalid group is scanned
again; its cached rows are not reused. A removed entry is absent from the new
reference, so its group ids are the ones stored under its old hash. A removed
hash with no stored groups invalidates every group in the current file.

The path of that file is not part of the argv namespace, for the same reason
the reference path is not: a new release is the same command with new files.
A run that does not pass the rule keeps the old namespace. Overlap between
different groups is outside this rule. The documented command marks overlaps
across models whether or not they share a group.

One addition was required after registration, or the witness could not be
cached. Under `--oskip` a part that does not contain the suppressor reports
the hit the full set omitted. That is a key mismatch: rows only in the
parts, none lost from the full set. Exact mode replays that refusal. The
probe-sample body check is still the gate. A row present only in the full
set, a key that appears in two parts, and a fitted size member with no pin
still refuse. A run that does not pass `--invalidate-group` does not rescan
the group.

## Measured 2026-10-14 — removing GlmZ_SraJ

Genome `GCF_013168095.1`. Cache on Rfam 15.1, then 15.1 with
`GlmZ_SraJ` removed. Shipped CLI, `--pin` with no template, audit.

Documented command, no `--oskip`. Fill 1711.6 s, `SHIP`, identity
exact, 4,227 models. Update 666.0 s, `SHIP`, 459 reused rows, 4,226
models. Stock 328.4 s, 459 rows. Bodies identical. Outcome EXACT.
Removing one overlapping family does not unmask a row, which matches
the source: the documented command does not pass `--oskip`.

With `--oskip`. Fill 1345.4 s. `REFUSE_PIN`: the identity replay body
differs from the whole run. Both sides have 423 rows and the same hit
keys. Fourteen rows differ in the overlap mark only (column 19, `^` on
the full scan, `*` on the candidate replay). Each of those rows
overlaps a hit `--oskip` omitted, from a family with no remaining row:
`LSU_rRNA_archaea`, `LSU_rRNA_eukarya`, `SSU_rRNA_archaea`,
`SSU_rRNA_eukarya`, `SSU_rRNA_microsporidia`. The replay searches the
families that have a row. It does not search a family whose every hit
was omitted, and the mark on the survivor changes. The update reused
that failed check in 3.3 s and refused the same way. Stock on the
reduced CM, 333.1 s, 423 rows. Outcome SAFE-REFUSE. The group rule is
not reached, because the first run does not ship a cache. The unit
test is the case the rule covers: the sibling has no row while the
removed member is present, and with the rule the sibling is scanned
again.

## Pilot 2026-10-14 — seed 20261044

Not a result. One genome, `GCF_058683675.1`, drawn from the pool that
excludes the Test I pilot and the locked ten. Rfam 15.0 cache, then
15.1. Shipped CLI, audit. The clan variant passes `--subset-aux` and
`--invalidate-group`. Five records, so the audit checks all of them.

No clan: EXACT, 461 rows. Fill 1655.4 s, `SHIP`. Update 629.0 s,
`SHIP`, 457 fresh, 3,770 stable, 459 reused rows. Stock 310.7 s.
Update phases: discovery scan 17.1 s, replay scan 46.5 s, neighbor pad
67.5 s, three random pads 60.0 s, 53.1 s, 70.2 s, audit scan 309.9 s.
The 457 fresh models are the families that changed or are new.

Clan: EXACT, 461 rows. Fill 1651.1 s, `SHIP`. Update 693.4 s, `SHIP`,
892 fresh, 291 reused rows. Stock 309.0 s. Discovery scan 77.2 s,
replay scan 47.5 s, audit scan 311.2 s. The 892 is every family in a
15.1 clan (480) plus every changed or new family outside a clan (412).
A removed family that belonged to no clan had no group row, and the
fail-closed clause rescanned every clan.

The pilot changes the stored group before the measured run. A fill
writes an empty group id for an entry that is in no group, so removing
that entry invalidates no group. A content hash with no group row at
all still invalidates every current group. That is a cache filled
before groups were stored.

## Measured run — locked 2026-10-14

Seed `20261045`, ten genomes, sorted after the draw. The pool is the
genome accessions in `results/infernal/inputs.tsv`, minus
`GCF_049949635.1`, the Test I ten, and the pilot
`GCF_058683675.1`.

`GCF_001515725.1`, `GCF_003722195.1`, `GCF_005389605.2`,
`GCF_017654165.1`, `GCF_023657995.1`, `GCF_032384295.1`,
`GCF_041235215.1`, `GCF_048568975.1`, `GCF_059131955.1`,
`GCF_059719525.1`.

Both variants. Clan passes `--subset-aux` and `--invalidate-group`.
Cache fill on Rfam 15.0 once. Three updates to 15.1, each from a copy
of that cache. Three stock scans of 15.1. Floor 2,000 body lines per
variant, summed across the ten. Per genome, speedup is the median of
the three update walls over the median of the three stock walls. The
reported figure is the median of those ten ratios. The first update
keeps the phase breakdown. Discovery from 15.0 to 15.1, by
content hash with `DATE`, `BM`, `SM`, and `COM` dropped: 397 changed,
60 new, 11 removed, 457/4227 of 15.1.

## Addendum 2026-10-14 — measured run (seed 20261045) stopped, not a result

Josh stopped the locked measured run at about 23:00 PDT on 2026-10-14,
after 2 of the 10 genomes, because it was draining the laptop's battery
during the day. This is a resource stop, not an outcome-driven one: no
pass/fail rule had been applied when it was stopped.

Completed before the stop (`results/infernal/measured45_interrupted_summary.json`,
copied from the work directory): `GCF_001515725.1` and `GCF_003722195.1`,
both variants EXACT, 862 body lines per variant (below the 2,000 floor,
so INCONCLUSIVE on power). Median update/stock ratios 0.472 (no clan)
and 0.466 (clan). These are **not reported as the measured result**.

The run will be redone in full on a weekend, from the beginning. Because
both genomes' outcomes have now been seen, the redo will either (a) rerun
the same locked ten unchanged, disclosed as a restart, or (b) use a new
seed under a new pre-registration if the shipped code changes before
then (for example, sizing the check by residues). Whichever applies is
recorded before the redo starts.

## Semantics 2026-10-17 — do not window a sequence

Reviewed before the residue-budget pilot. Infernal 1.1.5, file and line as in `docs/EXACT_REPLAY_PROTOCOL.md` (addendum 2026-10-17). A sub-window scanned as its own sequence is not the full run's rows in that region: truncation passes treat the window ends as termini (`cm_pipeline.c:1375-1378`), `maxW` depends on the model (`cm_pipeline.c:1055`), overlap removal is global (`cmscan.c:671-677`), and `-Z` is the full-sequence database size (`cmscan.c:918-921`). The check does not window. The audit and the random-pad record sample skip when one record is longer than half the residues. The neighbor pad and the in-situ check still run. The miss probabilities are in that addendum.
