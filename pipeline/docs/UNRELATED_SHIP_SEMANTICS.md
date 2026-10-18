# Unrelated ship: semantics review (no runs)

Written before any pfscan, hhsearch, MMseqs2, Foldseek, bedtools, or YARA
process. Code under review is pftools 3.2.13 (`e35e503`, tag `v3.2.13`).
Starting commit of this worktree: `507c45fcd2eb3c3e7850791cb2daf5e84400ffab`.
No seed from block `20261101`–`20261109` has been used. No number below is
a measurement of a search.

The question is which program, from a codebase other than HMMER/Infernal,
TARE can replay exactly across two consecutive reference releases. HMMER
and Infernal share the Eddy lab codebase. A ship from somewhere else is
what turns the claim from a HMMER trick into a method.

## Choice

**pfscanV3, matrix profiles only, no pin.** PROSITE is an InterProScan
member database (analysis `PROSITEPROFILES` / `PROSITEPATTERNS`;
InterProScan 6 "Under the hood"). The program is SIB pftools, not the
HMMER/Infernal tree.

Say this plainly: the printed score does not depend on how many profiles
are in the file. Normalization coefficients live in the profile. TARE's
identity path is the one that should authorize, the same shape as
Infernal under Rfam's recommended command. A pin is not required, and
none is declared.

The pilot and the measured run are blocked on Josh approving the source
archive and two PROSITE releases. Sizes are in the approval request.
This file does not pre-register those runs.

## What an entry is

A generalized-profile entry (Bucher and Bairoch, ISMB 1994) runs from
an `ID` line to a `//` line. `ID NAME; MATRIX.` is a scoring profile.
`ID NAME; PATTERN.` is a regular expression. PROSITE `prosite.dat`
mixes both, plus a leading banner that ends at the first `//`.

pfscanV3's usage line is `pfscanV3 [options] profiles sequences`
(`src/C/prg/pfscan.c`). One entry is one profile. Records are the FASTA
sequences. That is the release direction: a new PROSITE edition changes
profiles, and the same proteome is scanned again.

InterProScan's profile step calls pfsearchV3 through `ps_scan.pl` (one
profile against a sequence collection). pfscanV3 is the library scan of
the same code and the same format, which is the shape TARE already
wraps (`{reference}` = entry file, `{input}` = records). A one-profile
file prints a stderr warning and does not exit (`pfscan.c`,
`ProfileCount == 1`).

## Why the score is entry-local

`src/C/utils/Normalization.c` converts a raw alignment score with
coefficients stored on that profile:

| Function | Printed normalized score |
|---|---|
| `LINEAR` (`R2N_1`) | `R1 + R2 * raw` |
| `GLE_ZSCORE` (`R2N_2`) | raw and the sequence length |
| `GLE_ZSCAVE` (`R2N_3`) | raw, sequence length, and a composition term |

None of the three reads the number of profiles, the residue total of
the profile file, or a rank among profiles. PROSITE's reporting mode is
mode 1. pfscanV3's `--mode` defaults to 1. Cut-off level `--level`
defaults to 0, which is the profile's own level-0 threshold
(`N_SCORE` on the `/CUT_OFF` block), not an E-value times database size.

The multi-profile alignment loop calls the printer with the composition
term set to `0` (`src/C/prg/threads_array.h`, `thread_xaliPT`, the
`PrintFunction` call). The cut-off for `GLE_ZSCAVE` still uses the
composition term. Both quantities are functions of that profile and
that sequence.

The heuristic is also per pair. `thread_heuristic` loops sequences and
then profiles and compares the heuristic score with
`prf->HeuristicCutOff`, or with a cut-off derived from that profile
when `--filter-normalized-cutoff` is set. The pass/fail bit is stored
at `Array[i * Nprf + k]`. Another profile does not enter the score.
Schuepbach et al. (Bioinformatics 2013) report that the heuristic
misses some true positives (lowest recovery they measured 92.6%). That
miss is a property of one profile. The same profile on the same
sequence misses or hits the same way in a subset file. Byte identity
with stock can hold while the tool itself is not a complete search of
the dynamic-programming matrix. The locked command does not pass
`--no-heuristic`.

`DISJOINT` is defined for two alignments of the same profile on the
same sequence (`doc/profile.pdf`, Appendix A: `UNIQUE`, or `PROTECT`
with `N1`, `N2`). It does not suppress a different profile.

## Output that the comparison will use

Locked argv, not yet run:

```
pfscanV3 --matrix-only --nthreads 1 --output-method 7 --fasta \
  {reference} {input}
```

`--matrix-only` leaves patterns out. Pattern search has its own cap,
`--max-regex-match`, default 16 (`threads_array.h`). That cap can drop
matches of one pattern and is a different InterProScan analysis
(`PROSITEPATTERNS`). It is not part of this ship.

`--output-method 7` is `PrintTSV` (`src/C/utils/output.c`). One tab
separated line per match:

| Column | Content | Depends on other profiles? |
|---|---|---|
| 0 | `AC\|ID` | no |
| 1–2 | profile start, profile end | no |
| 3 | FASTA header, first token, `>` stripped | no |
| 4–5 | sequence start, sequence end | no |
| 6 | raw score, integer | no |
| 7 | normalized score, `printf %f` (six digits) | no |
| 8 | strand | no |
| 9 | aligned string | no |

TARE splits lines on whitespace (`parse_table_text`). The header is
already cut at the first space, and the aligned string in this printer
is the residue string. A space inside column 9 would split the row.
The pilot has to show that a real line has ten fields.

There is no header line and no `#` line in method 7. Method 9
(`PrintClassification`) prints a best profile across the library. That
is competition. It is not the locked method.

With `--nthreads 1`, the compacted hit list is walked by one thread in
sequence-major, profile-file order. With more threads the same list is
split and printed under a mutex as threads finish, so line order can
move. The laptop cap is 2 threads. The locked command uses 1 so that
stock-versus-stock has a chance to be byte-identical. The pilot checks
that. Two threads are not the claim.

## Behaviors that can fail a comparison for a reason other than the claim

| Behavior | How it would show up | What the pilot checks |
|---|---|---|
| Default thread count is every core. Print order follows thread completion. | Stock versus stock differs, class `order`, at `-t` greater than 1. | Two stock runs at `-t 1` on the pilot proteome. Identical bodies are required before any TARE run. A second pair at `-t 2` is recorded and is not the locked argv. |
| `printf %f` on the normalized score. | A value-only diff if two builds format differently. Same binary must match itself. | Stock versus stock, class `value-only` if it happens. |
| Heuristic cut-off is inside the profile and is approximate. | Rows missing relative to a `--no-heuristic` run. Not a cross-profile effect. | Not a kill. One profile, with and without `--no-heuristic`, on a few sequences, recorded as a tool property. |
| Filter accepts a pair and `xalip` then returns no alignment. stderr gets `Internal error xalip`. The exit of that thread is commented out (`threads_array.h`). GitHub issue 29 is this at level `-1`. | stderr noise; stdout may omit that pair. Same pair should omit it in a subset. | Locked level is the default, 0. Pilot records whether stderr contains `xalip`. A non-zero exit is a tool failure, not a KILL of replay. |
| One-profile warning on stderr, no exit. | A replay whose candidate set has one profile still has to print that profile's rows on stdout. | If the pilot's candidate set is a singleton, compare stdout, not stderr. |
| `--database-index` can disagree with the FASTA. | Missing or extra rows against a fresh scan. | Not used. |
| `--output-length` / description truncation. | Truncated text fields. | Not used. Method 7 does not print the DE line. |
| Duplicate FASTA headers. | Two records share a key. TARE cannot tell their rows apart. | Pilot checks header tokens are unique. NCBI protein ids in the existing proteomes are. |
| `NALI` buffer passed to `xalip`. | Matches of one profile on one sequence beyond the buffer are dropped in both the full run and the subset. | Same binary, so byte identity can hold. If a row count looks capped, record it. Do not retune. |
| Pattern entries left in the reference while `--matrix-only` is set. | A changed pattern is a changed entry with no row. Waste, not a wrong row. | The reference file is the matrix entries only, written by the generalized-profile parser. |
| Cross-references (`DR`), dates (`DT`), and match counts (`NR`) change when the matrix does not. | Every entry looks new if the hash includes them. | Parser drops `DT DE CC DR NR 3D PR DO`. A matrix-score edit changes the hash. Unit test, not a search. |
| Apple Silicon versus SSE. pfscanV3's heuristic and alignment call SSE2/SSE4.1 (`_mm_malloc`, `GetHeuristicVersion`). This laptop is arm64. | The build fails, or a binary built for x86_64 does not run. | No run is attempted until the source is approved. If the build fails, that is the stop. It is not a reason to switch tools inside this review. |

## Releases

`ps_reldt.txt` on the Expasy FTP, fetched as text during this review,
says `Prosite Release 2026_03 of 02-Sep-2026`. The consecutive archived
pair is `prosite2026_02.tar.bz2` then `prosite2026_03.tar.bz2` under
`old_releases/`. Current `prosite.dat` was last modified 02 Sep 2026
and is 25,527,044 bytes. The experiment uses the two archives so both
sides are frozen releases, not a moving `prosite.dat`.

The old `ps_scan_macosx.tar.gz` (5 Jun 2020, 8,296,093 bytes) is the
Fortran-era pfsearch manual, not pfscanV3. It is not the binary.

## Contract expectation

Numeric columns should fit the identity normalizer. No column should
fit `entry_count` or `total_entry_length`, because those quantities are
not in the formula. If the fit reports a size member, the gate is
`REFUSE_PIN` unless a real knob is declared. There is no such knob in
the usage text (`--mode` selects a normalization mode inside the
profile; it does not set a database size). Do not invent one.

The known-bad control is an injected drop of candidate profiles, not an
unpinned replay. Unpinned and pinned are the same command when every
column is identity. Dropping candidates must change the body (class
`missing`) or the safety check must refuse. A drop that still matches
stock is a failed control.

## Candidates that are not the ship

### HH-suite hhsearch / hhblits

| Question | Answer |
|---|---|
| Entry | One HMM in an HHsuite database (a3m/hhm ffindex). |
| Whole-reference column | E-value. In the HH-suite 2 hit list, `Eval = exp(logPval + log(N_searched))`, and the header prints `Searched_HMMs` (`hhhitlist.C`, `PrintHitList`). HHblits' composite E-value adds `log(par.dbsize)`. Probability and the summary rank (`No`) also move when the searched set changes. |
| Pin | The man page `-Z` is "maximum number of lines in summary hit list" (default 500), not `N_searched`. No option in that man page sets the searched-HMM count to the full database while the file is a subset. |
| Determinism | OpenMP builds exist. Rank and E-value formatting (`%g` / `%e` cutovers in `PrintHitList`) are a second comparison hazard. |
| Consecutive releases | UniRef30 / pdb70 style dated databases exist. UniRef30 is on the order of 100 GB and BFD is larger than 1 TB (HH-suite database guide). Not a laptop scan under the 3 GB cap. |
| Practice | Remote homology search. Real. Different lab from HMMER (Söding). Still an HMM-HMM E-value. |
| Decision | Refuse for this experiment. Size-dependent E-value, no size pin, plus a rank cap that a pin would not freeze. |

### MMseqs2 search

| Question | Answer |
|---|---|
| Entry | One target sequence in the MMseqs database. |
| Whole-reference column | E-value uses the database size (developers, issue [soedinglab/MMseqs2#505](https://github.com/soedinglab/MMseqs2/issues/505), opened 2021-11-15, still open at its last update 2023-08-28: "Currently we don't have an option like that"). Prefilter survivor set depends on the whole database: `--max-seqs` is "Maximum results per query sequence allowed to pass the prefilter" and `maxResListLen = 300` (`src/commons/Parameters.cpp` on master, this review). |
| Pin | No `--db-size` in that parameter list. `--max-seqs` is a top-k, not a pin. Raising it does not make a subset's prefilter equal the full database's prefilter. |
| Determinism | Threaded. Result order is by score. Tie order can move. |
| Consecutive releases | Sequence databases (UniRef, NR) have releases. They are far past the laptop cap. |
| Practice | Real homology search. |
| Decision | Refuse. Two independent couplings: E-value scale with no pin, and prefilter top-k. A pin would not fix the second. This is the DIAMOND failure mode. No run, and no second design. |

### Foldseek search

| Question | Answer |
|---|---|
| Entry | One structure (3Di sequence plus backbone) in a Foldseek database. |
| Whole-reference column | Same prefilter as MMseqs2. The 2023 comment on MMseqs2 issue 505 asks for `--db-size` in Foldseek as well, which is evidence it was absent there too. |
| Pin | Not in the MMseqs2 parameter table Foldseek inherits. Not re-checked against a Foldseek binary, because the top-k refusal does not need one. |
| Determinism | Threaded, score order. |
| Consecutive releases | PDB and AlphaFold databases are large and updated often. |
| Practice | Real structure search. |
| Decision | Refuse for the same prefilter top-k. Not a second design of the MMseqs2 question. |

### bedtools intersect (fallback only)

| Question | Answer |
|---|---|
| Entry | One feature in `-b`. |
| Whole-reference column | Default output is one line per overlap. No database-size column. `-c` counts overlaps; the count depends on the overlapping features, which is the hit set, so a replay of those features can reproduce it. |
| Pin | None needed for the default. |
| Determinism | Single-threaded, file order, if the inputs are not being sorted concurrently. |
| Consecutive releases | Feature tracks (GENCODE, RepeatMasker) have releases. |
| Practice | Real, but interval overlap, not sequence annotation against a scoring library. |
| Decision | Fallback. Not chosen. pfscanV3 is a scoring annotation tool and is still available as a design. |

### YARA (fallback only)

| Question | Answer |
|---|---|
| Entry | One rule. |
| Whole-reference column | A condition can count strings and can name other rules. That is cross-entry coupling. Rules with no cross-rule reference are identity. |
| Pin | None for the independent case. None that freezes a cross-rule count. |
| Determinism | Rule order can be fixed. Threads exist. |
| Consecutive releases | Rule packs are published, but they are not a reference database in the PROSITE sense. |
| Practice | Real file scanning. Not protein annotation. |
| Decision | Fallback. A ship restricted to rules that do not mention other rules would be the trivial identity case. Not chosen. |

## Parser

TARE had no reader for this format. `acts/reference_formats.py` now
parses it as `generalized_profile`. The module does not name pfscan or
PROSITE. Tests: `pipeline/tests/test_generalized_profile.py`.

Volatile line codes: `DT`, `DE`, `CC`, `DR`, `NR`, `3D`, `PR`, `DO`.
`NR` is the per-release match-count block (the pftools SH3 example
carries `NR /RELEASE=...` and `NR /TOTAL=...`). The first draft of this
list omitted it. A release that only refreshes those counts must not
look like a new matrix. Primary key: `AC|ID`. Length: count of `/M:`,
or the PA text length for a pattern. A file that opens with `CC` lines,
as `prosite.dat` does, is the same format.

## What is not done

No pilot, no protocol, no measured JSON. Those wait on the three files
in the approval request. CARC was not contacted. Laptop wall times are
not in this file.
