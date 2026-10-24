# Baselines the review asked for: rescaling and the expert script

Written **before** any measured run below. Locked text is not edited;
later changes are dated addenda. Starting commit
`507c45fcd2eb3c3e7850791cb2daf5e84400ffab` on `exp/d-baselines`.
Laptop walls are provenance, not speed evidence.

## Semantics review (no experimental runs)

HMMER 3.4 `src/p7_tophits.c` (tag `hmmer-3.4`), `p7_tophits_TabularTargets`
and `p7_tophits_TabularDomains`:

| Table | Column | Formula | Format |
|---|---|---|---|
| tblout | full-sequence E-value | `exp(lnP) * Z` | `%9.2g` |
| tblout | best-1-domain E-value | `exp(domain lnP) * Z` | `%9.2g` |
| domtblout | full-sequence E-value | `exp(lnP) * Z` | `%9.2g` |
| domtblout | c-Evalue | `exp(domain lnP) * domZ` | `%9.2g` |
| domtblout | i-Evalue | `exp(domain lnP) * Z` | `%9.2g` |

Scores, bias, coordinates, domain counts, and the description do not
scale with Z. Default `domZ` is `th->nreported`, the number of reported
targets for that query (`p7_tophits_Threshold`, when
`domZ_setby == p7_ZSETBY_NTARGETS`). It is not the database size.

`p7_tophits_GetMaxNameLength` takes the maximum over every registered
hit, including hits that are not reported. Column widths can therefore
exceed the longest *printed* name. Widths are per query. Hits are
ordered by `sortkey = -lnP` (ascending E-value). `qsort` tie order is
not specified.

`--cut_ga` reports on the gathering bit score. Z does not move a hit
across that line. A sub-database scan with `-Z 30134` prints the
full-database Z-scaled E-values and i-Evalues, and a c-Evalue scaled by
the sub-database's own `domZ`.

Printed E-values use two significant digits. Multiplying a printed
value by `30134/27481` and printing it again with `%9.2g` is not the
same double HMMER rounded internally. That is the failure the rescaler
is there to measure.

A format check, not a result: on the existing e1scale stock file
`S382.tbl` and `S382.dom` for `GCF_013315695.1`, libc `snprintf` of
`strtod` of every numeric field with HMMER's conversion specifiers
matched all 134,154 fields. Full-file md5 of two stock runs differs
because the `#` footer contains the date. Identity is body lines
(lines that do not start with `#`).

Behaviors that can fail a check for a reason other than the claim:

1. `#` footer date and paths. Compare body lines only.
2. Column padding from unreported hits. Count padding-only lines
   separately from value columns.
3. `domZ` changes when removed families drop out or discovery adds
   hits. c-Evalue must use the merged reported-target count, not Z.
4. Discovery lines already carry `-Z 30134`. Scaling them by
   `30134/27481` again would be a double correction.
5. HMMER `CKSUM` covers the model probabilities, not `GA`, `DESC`, or
   `ACC`. The expert script's name+checksum diff can disagree with
   TARE's strict entry hash (`DATE`, `BM`, `SM`, `COM` dropped). That
   disagreement is part of the expert-script result, not a bug to
   patch away.
6. DIAMOND hit sets depend on `--dbsize`, `-k`, `--min-score`, and
   block size. The analog uses the locked S1 argv from
   `run_reference_diamond.py` (`--min-score 40 -k 0 --motif-masking 0
   -b 2.0 --comp-based-stats 1`) plus `--dbsize` of the new database.
   Laptop threads are 2. If resident set exceeds 3 GB the run stops
   and is reported; it is not silently rerun at a different block size.
7. Stock `hmmscan` at `--cpu 2` versus the saved e1scale runs at
   `--cpu 4`. Body identity is required anyway. A cpu-dependent
   difference stops the arm as `INCONCLUSIVE`, not as a rescaler failure.

## D1 — strongest honest rescaler

Script: `pipeline/scripts/baseline_rescale.py`.
Result: `pipeline/results/baselines_exact/rescale.json`.
Pilot result: `pipeline/results/baselines_exact/rescale_pilot.json`
(`"pilot": true`, not a measured number).

Stable / changed / removed families use TARE's strict entry hash.
Cached Pfam 38.1 body lines are kept for stable families. Lines of
removed families are dropped. Changed and new families are not
rescaled from the cache; they are replaced by a pinned discovery scan,
the same discovery TARE runs:

```
hmmscan --cut_ga --noali --cpu 2 -Z 30134 --tblout T --domtblout D -o /dev/null <changed.hmm> <queries>
```

Z-scaled columns are multiplied by `30134/27481`. c-Evalue is multiplied
by `domZ_merged / domZ_source`, where `domZ_source` is the 38.1
reported-target count for a cached line and the discovery scan's
reported-target count for a discovery line, and `domZ_merged` is the
reported-target count of the merged lines for that query. Discovery
Z-scaled columns are left as HMMER printed them. Every numeric field is
printed with the conversion above via the same libc `snprintf` HMMER
links. Per-query target-name and accession widths are the widths
already printed on the source lines (so unreported-hit padding is kept
when we still have the line), widened if a merged name or accession is
longer. Query-name and query-accession widths are `max(20, len)` and
`max(10, len)`, which do not depend on the hit list. Hits in a query
are ordered by ascending rescaled full-sequence E-value, ties by target
name. Domain lines follow that order, then domain index.

### Pilot

Seed `20261133`. Pool: sorted `recurrence/A/*.faa.gz` excluding

```
GCF_002853805.1 GCF_002090355.1 GCF_013315695.1 GCF_049201905.1
GCF_059719525.1 GCF_016806025.1 GCF_017165095.1 GCF_001515725.1
GCF_001513615.1
```

(stems; files are `<stem>_protein.faa.gz`). Draw:

```
rng = random.Random(20261133)
proteome = rng.choice(pool)          # locked: GCF_024585005.1_protein.faa.gz
indices = sorted(rng.sample(range(n_records), 100))
```

Records are written in file order. This proteome is not in D1's measured
set and not in the CARC draw below. If `proteome` is not the locked
name, stop.

Pilot minimum: 30 tblout body lines in the stock 38.2 scan. Below that
the pilot is `INCONCLUSIVE` and the measured arm does not start. One
revision of the pilot size is allowed and must be an addendum; a second
failure stops D1.

### Measured set

The task names the comparison set. It is not a fresh draw.

- e1scale, seed 20261014, already measured: `GCF_013315695.1`,
  `GCF_049201905.1`, `GCF_059719525.1`. Reuse `~/tmp/e1scale_work`
  stock bodies. Do not modify that directory. Genome 1 has two stock
  38.2 runs (`S382_a`, `S382_b`); their bodies must match before any
  genome is scored. Genomes 2 and 3 have one stock run each. There is
  no previously stored output md5; record body sha256. Full-file md5
  is not the identity check.
- costpass, seed 20261015: `GCF_016806025.1`, `GCF_017165095.1`. No
  stock files remain under `~/tmp/costpass_work`. Rerun stock 38.1 and
  stock 38.2 at `--cpu 2`. Genome 1 is scanned twice on 38.2 before
  genome 2 is scored.

Power floor: 5,000 tblout body lines pooled across the five genomes.
Below that the measured label is `INCONCLUSIVE`.

### Controls

- Positive: reprint stock 38.2 with Z factor 1 and domZ factor 1, no
  lines added or dropped. Body lines must be byte-identical. Checked
  on the pilot stock and on every measured 38.2 stock before that
  genome is scored.
- Negative: the same builder with the Z factor forced to 1 (c-Evalue
  still uses domZ; discovery still pinned). Body lines must differ from
  stock 38.2. If they do not, Z is not load-bearing and D1 is `FAIL`.
- Stock-vs-stock first, as above. A mismatch stops the arm
  (`INCONCLUSIVE`), and no rescaler number is reported for that arm.

### Reported keys

Per table (`tbl`, `dom`), pooled and per proteome:

- `stock_lines`, `rescaler_lines`
- `byte_identical`, `byte_identical_over_stock` with Wilson 95% CI
- `token_identical`, `padding_only`
- `value_only_by_column` (token mismatches by column name)
- `missing`, `extra`, `order_only`
- `difference_classes` among `value-only`, `padding-only`, `missing`,
  `extra`, `order`, `different-row`
- cutoff crossings at 1e-3, 1e-5, 1e-10 on the full-sequence E-value,
  using `E <= cutoff`: `flip` (shared key, pass/fail differs),
  `lost` (stock passes, line missing), `gained` (rescaler passes, line
  extra)

Primary byte-identical fraction uses stock lines as the denominator.
A stock line with no byte-identical partner counts as a failure.
Wilson score interval, z = 1.959963984540054.

## D2 — expert script

Script: `pipeline/scripts/expert_update_hmmscan.sh`.
Plain `sh`, `awk`, `hmmfetch`, `hmmpress`, `hmmscan`. No check and no
audit. Diff is NAME plus CKSUM. Discovery is `hmmscan -Z <new count>`
on changed families. Candidates are cached hits of stable families plus
discovery hits. Proteins are batched with the same cost model TARE
uses (`startup_pairs = 2000`, `press_pairs = 84`, rarest-candidate
order, power-of-two grid then a neighborhood step, ties keep the
smaller chunk). Each batch is scanned against its candidate union in
new-file order, with `-Z` and `--cut_ga`. Bodies are merged in protein
order. `--cpu` comes from the environment (laptop: 2). `EXPERT_OMIT_Z=1`
drops the pin and exists only so the negative control can run; the
default path pins Z.

### Laptop correctness (D2a)

On the two costpass genomes, compare the script's tblout and domtblout
bodies to stock 38.2. Those stocks are the D1 reruns, frozen at the
same commit. Label `EXACT` only if both genomes and both tables are
byte-identical. Otherwise report difference classes and do not relabel
the script.

Controls, on the D1 pilot sample (seed 20261133, disjoint from
costpass), before the costpass runs:

- Positive: script versus stock 38.2. The pilot must finish and produce
  rows. Byte identity on the pilot is a bug hunt, not the measured
  claim. One fix of a script bug (wrong column, dropped name, missing
  pin, bad merge) is allowed and recorded as an addendum. A second
  failure is the result.
- Negative: `EXPERT_OMIT_Z=1` on the pilot must not be byte-identical
  to stock 38.2.

DIAMOND analog: `pipeline/scripts/expert_update_diamond.sh`. Same
shape on the dx3 case: Swiss-Prot 2026_01 to 2026_03, queries the
locked dx3 draw (seed 20261029, 2,000 proteins from
`GCF_001515725.1`, file order). That seed is the published case, not a
draw from this block. Diff by header id plus MD5 of the sequence.
Discovery and the candidate replay use `--dbsize` equal to the new
database letter count (dx3 recorded 209017843; recompute with
`diamond dbinfo` and stop if it differs). Pinned candidate replay is
compared to a stock 2026_03 blast. The script exits 0 either way.
Report missing, extra, value-only, and different-row lines, with
examples. Stock is run twice first; a mismatch is `INCONCLUSIVE`.
Threads 2. This case is known-bad for candidate replay; reproducing
silent differences is the success condition of the analog, not a
script bug to repair.

Result files:

- `pipeline/results/baselines_exact/expert_laptop.json`
- `pipeline/results/baselines_exact/expert_diamond.json`

### CARC timing (D2b) — not started until the gate

Do not submit a job until `ssh -O check discovery` succeeds and
`ssh discovery 'squeue -j 13208152 -h -o "%i %T"'` shows no `PENDING`.
Never touch jobs 12864756 or 13208152. No login-node compute. No
`carc-transfer`, no raw hostname, no `ssh -O exit`.

Job: `pipeline/jobs/baselines_exact_carc.job`, hardening copied from
`jobs/headline_carc_pilot.job` (exclusive EPYC 7542, `--mem=0`,
node-local scratch if `/tmp` has 40 GB free else `/scratch1/$USER`,
HMMER 3.4 built from the pinned tarball sha256
`ca70d94fd0cf271bd7063423aabb116d42de533117343a9b27a65c17ff06fbf3`).

Pool: the D1 pilot pool minus `GCF_024585005.1_protein.faa.gz`.

- Pilot seed `20261131`, one genome, locked name
  `GCF_041235215.1_protein.faa.gz`. One alternating triple
  (stock, TARE, expert). Purpose: the job runs and writes a row.
  Not a speed claim.
- Measured seed `20261132`, five genomes, locked sorted names
  `GCF_002302335.1`, `GCF_016904475.1`, `GCF_025259645.1`,
  `GCF_030347155.1`, `GCF_977065495.1`. If the draw differs, stop.

`r = 3`. For genome index `g` and replicate `i`, the arm order is a
rotation of `(stock, tare, expert)` by `(g + i) mod 3`. All three arms
see the same `--cpu` (the exclusive node's `SLURM_CPUS_PER_TASK`).
TARE is

```
python3 -m acts run --strategy reference --pin '-Z {entry_count}' \
  --verify audit --prep 'hmmpress -f {reference}' \
  --input Q --reference NEW --cache CACHE -o OUT -- \
  hmmscan --cut_ga --noali --cpu $CPU \
  --tblout '{output:tblout}' --domtblout '{output:domtblout}' \
  -o /dev/null {reference} {input}
```

with the cache filled on Pfam 38.1. `hmmpress` of the full databases
is outside every timed command. `S_g` is the median stock wall divided
by the median arm wall (`r = 3`). Across genomes, report the median of
`S_g` with a 95% percentile bootstrap (10,000 resamples, seed
`20261139`), the geometric mean, and the range, for TARE and for the
expert script. Primary ratio `R_g = S_g,TARE / S_g,expert`, summarized
the same way. The paper's derived laptop estimate is check+audit =
7.6% of a stock run, script about 4.6× where TARE reached 3.4×, so
`3.4/4.6`. That estimate is not a CARC measurement. Laptop walls are
not used to compute `S_g`.

Driver: `pipeline/scripts/baseline_carc.py`. It refuses to run unless
`ACTS_CARC=1`.

## Provenance

Every JSON under `pipeline/results/baselines_exact/` carries git HEAD,
seed, HMMER or DIAMOND version, host, argv, and wall times, and
`"walls_are_evidence": false` on laptop files.

## Addenda

### 2026-10-18 — unchanged target lists keep file order

The D1 order sentence says every query is sorted by ascending rescaled
full-sequence E-value. A reprint of stock 38.2
`GCF_013315695.1` (`S382.tbl`, 9094 lines; `S382.dom`, 8812 lines) with
Z factor 1 and domZ factor 1 is byte-identical only when a query whose
target list did not change keeps HMMER's file order. Printed E-values
tie more coarsely than HMMER's full-precision bit-score sort key, so
re-sorting that list fails the positive control. Queries that gain or
lose a target are still sorted by ascending rescaled full-sequence
E-value, then target name, then domain index. This is the one revision
of that sentence. The positive control itself is unchanged.

### 2026-10-18 — CKSUM misses 111 strict-hash changes

Family partition of the two Pfam gzips (md5s in the D1 script) gives
stable 26082, changed 4052, removed 165. Of the name-matched models
with equal CKSUM, 111 have a different strict entry hash
(`cksum_stable_strict_differs`). Tag diffs outside DATE/BM/SM/COM:
DESC 76, ACC 39, TC 39, GA 38, NC 38. The expert script stays on
NAME+CKSUM, which is the diff a competent user writes. Those 38 GA
changes can move a `--cut_ga` line without a CKSUM change. That is
recorded before any expert scan. It is not a script-bug fix. If the
costpass bodies are not byte-identical, the difference classes are the
result.

### 2026-10-18 — no 3 GB address cap on this Mac

`setrlimit` of `RLIMIT_AS`, `RLIMIT_DATA`, and `RLIMIT_RSS` to 3 GB
raises `ValueError: current limit exceeds maximum limit`. `ulimit -v`
returns `invalid argument`. The pressed 38.2 indexes are about 2.4 GB,
so a 3 GB address space could not map the database. Laptop scans stay
at `--cpu 2` and `nice -n 10`. Laptop walls remain not evidence.

### 2026-10-18 — one expert-script bug fix

The D1 pilot of `expert_update_hmmscan.sh` exited 1 before any body
comparison. `hmmscan` could not open `batches/b0.faa`. The FASTA
writer used a tab field separator, so `$1` on a header was the whole
line and no query id matched the plan. The same writer in the DIAMOND
script is fixed the same way. This is the one allowed script-bug fix
(dropped query file). The rerun then exited because `hmmfetch --index`
refuses to overwrite `Pfam-A.hmm.h3m.ssi`, while the guard only looked
for a `.ssi` suffix. An existing `.ssi` or `.h3m.ssi` is now left in
place. The NAME+CKSUM diff is unchanged.

### 2026-10-24 — queued W12a job moved to biyik_1173 (queue priority only)

Queued CARC job `13347581` (W12a expert-script measured) was moved from Slurm account
`biyik_1165` to `biyik_1173` on 2026-10-24. Queue priority / fairshare only: identical hardware
constraints and limits (`--exclusive`, `--mem=0`, `--constraint=epyc-7542`, same wall and exclusive
node caps). No cancel, resubmit, or redesign; job ID unchanged.
