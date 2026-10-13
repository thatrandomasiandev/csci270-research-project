# Second tool: DIAMOND blastp (pre-registered 2026-10-06)

Written **before** any DIAMOND invocation and **before** any Swiss-Prot
download. Locked text below is never edited. Later changes are dated
addenda. This file does not authorize a download over 1 GB.

The fitter under test is the one shipped in `8fc852e`
(`acts/reference_fit.py`, `acts/reference_run.py`,
`acts/reference_formats.py`). No member is added to the closed family.
No per-tool branch is added for this argv. A refusal is a result and
counts against the claim.

## MMseqs2 is excluded

MMseqs2 is not the second tool. Its prefilter keeps a per-query global
top-k (`--max-seqs`, default 300). That couples the reported hit set to
the rest of the database the same way DIAMOND's default `-k 25` does,
so a partition probe cannot decompose. The exclusion is fixed here,
before any run. MMseqs2 is not a fallback if DIAMOND refuses.

## Pinned program

| Item | Value |
|---|---|
| Tool | DIAMOND |
| Tag | `v2.2.5` |
| Commit | `6dc57174369ba131d35a21db9735a48ac01e6610` |
| Source read | GitHub tag archive, 15,169,124 bytes |
| Binary the job must use | release asset `diamond-linux64.tar.gz` for tag `v2.2.5` |
| Check | `diamond version` on the compute node must report 2.2.5. Any other string stops the job. Do not build a different commit. |

Source facts, this commit, default sensitivity (no `--fast` /
`--sensitive` / `--mid-sensitive` and no other sensitivity switch):

- `ScoreMatrix::evalue` (`src/stats/score_matrix.cpp:218-224`) returns
  `evaluer.evalue(raw_score / scale_, qlen, slen) * db_letters / slen`,
  except when `config.symmetrize_evalue` is set and `qlen < slen`, in
  which case the divisor is `qlen`. `scale_` defaults to 1
  (`score_matrix.h`). S1 does not pass `--symmetrize-evalue`. The
  default branch is linear in `db_letters`.
- `db_letters` is `SequenceFile::letters()`, the sum of stored
  sequence lengths (`src/run/double_indexed.cpp` sets it from
  `cfg.db->letters()`; `src/data/fasta/fasta_file.cpp` accumulates
  `seq_length_`). It is the pre-registered `total_entry_length` member
  only if that sum equals the FASTA residue count from
  `acts/reference_formats.py` (non-whitespace characters in the
  sequence body). D0 checks this on the real database. A mismatch does
  not add a family member.
- `report_cutoff` (`score_matrix.cpp:238-243`): if `min_bit_score != 0`,
  the hit is kept when `bitscore(score) >= min_bit_score`; otherwise
  the E-value cutoff applies (`max_evalue` default 0.001,
  `config.cpp:262`). `bitscore` (`score_matrix.cpp:254-258`) does not
  read `db_letters`. `--min-score` is the score-thresholded mode, the
  analogue of `hmmscan --cut_ga`.
- `-k` / `--max-target-seqs` default is 25
  (`DEFAULT_MAX_TARGET_SEQS` in `config.h:55`). `-k 0` sets the cap to
  `INT64_MAX` (`output_format.cpp:243-244`).
- `--max-hsps` default is 1 (`config.cpp:298`), so one row per
  query–subject pair.
- `--motif-masking` default for this sensitivity is on
  (`search/setup.cpp:120`, `soft_masking_algo` at line 538). S1 turns
  it off. The motif list is a fixed set, not a count of this database.
- `--freq-masking` is a boolean, false unless the flag is passed
  (`config.cpp:425`). Frequent seeds are built only inside
  `if (config.freq_masking …)` (`search/stage0.cpp:168`). The sensitivity
  trait `freq_sd = 50` (`setup.cpp:121`) is unused while the flag is
  off. `--freq-sd` without `--freq-masking` aborts
  (`run/config.cpp:158-159`).
- `--block-size` / `-b` default for this sensitivity is 2.0, in
  billions of letters (`setup.cpp:130`). `block_size()` is
  `chunk_size * 1e9` (`config.h`).
- `--comp-based-stats` default is Hauser, mode 1
  (`DEFAULT_CBS = CBS::HAUSER` in `stats/cbs.h:209`). That adjustment
  is a function of the query and subject compositions, not of the
  other entries. S1 pins the default explicitly.
- `--index-chunks` trait for this sensitivity is 4 (`setup.cpp:126`).
  S1 does not pass `-c`. It is named so it is not tuned later.
- `--masking` default is tantan (`config.cpp:252`), per sequence.
  S1 does not pass it.

## Queries

Collection A genome 1 proteins, already on disk:

`pipeline/data/recurrence/A/GCF_002853805.1_protein.faa.gz`

5117 records (counted from that file on the Mac, 2026-10-06). The
probe uses the shipped sampler: `n_p = 300`, seed `20261006`, the
second `random.Random` in `acts/reference_fit.py`. D3 uses every
record.

## References

Two consecutive UniProtKB/Swiss-Prot releases. FASTA only.

| Role | Release | Date | URL | Bytes | MD5 |
|---|---|---|---|---|---|
| Newer | 2026_03 | 02-Sep-2026 (`reldate.txt`) | `https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/uniprot_sprot.fasta.gz` | 93,801,562 | `bc9d398533e6df582b563c6c03093bd0` (current `RELEASE.metalink`) |
| Older | 2026_01 | 28-Jan-2026 (relstat) | see the hold below | 1,722,763,542 | `6042adf20dad1ab62112c9053bdebd20` |

Release 2026_01 statistics, from
`UniProtKB_SwissProt-relstat.html` on that release (not a search
result): 574,627 sequences, 208,482,574 amino acids.

### Hold: the older release is over 1 GB

The previous-release directories on `ftp.uniprot.org` (checked
2024_01, 2025_04, 2026_01, and the loose-FASTA paths for 2019_11
through 2026_01) do not publish `uniprot_sprot.fasta.gz`. The only
Swiss-Prot archive for 2026_01 is

`https://ftp.uniprot.org/pub/databases/uniprot/previous_releases/release-2026_01/knowledgebase/uniprot_sprot-only2026_01.tar.gz`

at 1,722,763,542 bytes (metalink). The 2024_01 and 2025_04 Swiss-Prot
archives are the same kind of bundle (directory index 1.5G and 1.6G).
The current loose FASTA is under 1 GB. The older one is not.

**D1–D3 do not start until an addendum records approval to download
that archive.** The job must not fetch it before that addendum. After
approval, the inner FASTA is the older reference; its bytes and MD5
are recorded in the result JSON. The tar's MD5 must match the metalink
before extraction.

`-b 2.0` is one block for 208,482,574 letters (`2e9` is larger). Gate,
before the probe: if `diamond dbinfo` letters on either database
exceed 2,000,000,000, stop. Do not raise `-b` after seeing hits.

## S1 — the argv

Fixed now. Score cutoff first.

`--min-score 40`. The bit score is `(λ · round(raw / scale) − ln K) / ln 2`.
Forty bits is `2^40`, four groups of ten bits, about `10^12` on the
alignment's own odds scale, before any database-size factor. Zero is
the sentinel that leaves the E-value cutoff in force
(`min_bit_score != 0` in `report_cutoff`), so the cutoff has to be a
positive bit score. Forty is that round point. It is not estimated
from these queries or these releases.

Full S1 command, after `{reference}` has been indexed by prep. Thread
count is 32, matching one exclusive EPYC 7542 (`--cpus-per-task=32`).

```
diamond blastp
  --db {reference}
  --query {input}
  --out {output}
  --min-score 40
  -k 0
  --motif-masking 0
  -b 2.0
  --comp-based-stats 1
  --threads 32
  --outfmt 6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore
```

Not passed, and not to be added after a run: `--symmetrize-evalue`,
`--freq-masking`, `--freq-sd`, `--sensitive` and the other sensitivity
switches, `-c`, `--masking`, `--evalue`, `--top`, `--max-hsps`.

Prep, caller data, not compiled into `acts/`:

```
diamond makedb --in {reference} --db {reference} --threads 32
```

`diamond blastp --db {reference}` reads `{reference}.dmnd`.

## S2 — fallback, named now

Used only if S1's decomposition probe refuses.

On this commit, frequent-seed handling is already off unless
`--freq-masking` is present, and `--freq-sd` cannot be passed alone.
There is no `--freq-masking 0`. Turning the flag on, even with a huge
`--freq-sd`, replaces the complexity seed mask (`mask_seeds`) with the
frequency filter. That is not neutralization.

**S2 is S1 with `--freq-masking` and `--freq-sd` still absent.** It is
not a different command. If S1 refuses, S2 does not rescue it, and the
refusal stands. No third setting is declared.

## D0 — letters, before the fit is interpreted

On each release, after `makedb`:

- `diamond dbinfo` field `Letters`
- sum of per-entry lengths from `parse_reference` on that FASTA

Record both. Equal means the E-value factor is the pre-registered
`total_entry_length` member. Unequal: still run D2, do not add a
member, and a refusal is the expected consequence.

## D1 — churn

Entries parsed by the shipped FASTA parser. Identity is
`entry_content_hash` with the FASTA volatile-tag list, which is empty,
so the hash is the whole record. A header edit is a changed entry.
That is the locked rule in the fitter pre-registration. It is the `c`
in the formula, because it is the fraction the incremental run
reuses.

Report, for the newer release: entries in each release, added,
removed, unchanged. `c = 1 − (unchanged / n_new)`.

Also report, as a description and not as `c`, the fraction of newer
entries whose residue string (whitespace ignored) is unchanged and
whose id token is unchanged. Do not put that fraction into the
formula after seeing it.

No 50% kill rule. R1's threshold is not copied here.

## D2 — decomposition and fit

The shipped fitter's probe on the **newer** release, S1 argv, seed
`20261006`, `k = 2`, `n_p = 300`. No tool-specific code. The
disambiguating partition is part of that probe. It is not a new
member.

Expected assignment, after the tie-break if the primary split ties:

| Column | Member |
|---|---|
| `evalue` | `total_entry_length` |
| every other numeric column | `identity` |

Decision: ship. A primary tie between `entry_count` and
`total_entry_length` is allowed; the length-descending partition is
what has to leave `total_entry_length`. Shipping `entry_count`, or
refusing, counts against the claim. Record the assignment that
actually came out. Do not edit the table above.

## D2n — negative control

Same probe, same release, same seed, with `-k 25` instead of `-k 0`
(the global per-query top-k). Every other S1 flag stays.

**Must REFUSE**, because the row-key sets differ. If it ships, the
probe cannot tell a global top-k from an uncoupled hit rule, and D2's
ship carries no weight.

## D3 — re-annotation timing

One exclusive `epyc-7542` node, account `biyik_1165`, partition
`main`, `--cpus-per-task=32`, `--mem=64G`. Nothing on a login node.
Own tree:

`/project2/biyik_1165/jjt_373/csci270-star/pipeline-ref-second/`

Own hash file:
`results/reference_diamond/GIT_HASH` inside that tree. Do not read or
write `results/savings/` or the savings jobs.

Untimed, before the clock, in this order:

1. D0 and the S1 probe (D2) on the newer release.
2. One full S1 search of all 5117 queries against the **older**
   release, loaded into the reference cache. This is the warm state.
3. One discarded S1 search of all 5117 queries against the newer
   release, so the first timed stock run is not the only one that
   pays cold start.
4. The six stock runs that identify `a` and `b` (three at 300, three
   at 5117), described under Prediction. Their walls are the fit.
   They are not the alternating means.

Clocked: three repeats, this order, one arm at a time, same node:

| Repeat | Order |
|---|---|
| 1 | stock, ACTS, iSeqSearch |
| 2 | ACTS, iSeqSearch, stock |
| 3 | iSeqSearch, stock, ACTS |

Arms, all S1 flags and 32 threads:

- **Stock.** `diamond blastp` on the newer release, full FASTA.
- **ACTS.** `python3 -m acts run --strategy reference` on the newer
  release, cache warm from the older release, prep as above. The
  probe is not inside this interval. Wall time is the incremental
  re-annotation only.
- **iSeqSearch.** Public code
  `EESI/Incremental-Protein-Search` at
  `7e862bf3afa52b65b3cca4255de66ab4cb764fe3` (2025-02-18). It does not
  run DIAMOND. It merges two m8 files.
  `run_merge.sh --default OLD DELTA OUT L_old L_delta` calls
  `source/main.py`, which rescales column `[-2]` by
  `(L_old + L_delta) / L_part` and dedupes on `(query, subject)`,
  keeping the lower E-value (`source/merger.py`). The usage string in
  that script does not match the argument count; the call follows the
  code, not the usage string. `OLD` is the warm older-release m8.
  `DELTA` is S1 against the FASTA of newer entries whose fitter hash
  is not in the older release (added or edited records). `L_old` and
  `L_delta` are those two databases' `diamond dbinfo` letter counts.
  Their sum is what the code uses. Do not replace it with the true
  newer-release letter count. Removed entries' hits stay if the code
  keeps them.

  If that commit does not run (import error, the PeerJ-noted
  `IndexError` on a short line, or any non-zero exit), the arm is
  absent. Say why, in the result file, and compare against the
  published methodology only: Spouge rescale by database length,
  Pearson correlation of E-values, and hit counts. Do not reimplement
  their merger inside `acts/`.

**Prediction.** Three repeats at one `n` estimate one mean. They do
not identify both `a` and `b`. The fit therefore uses six stock S1
runs on the newer release, all before the alternating block and after
the discarded cold-start run:

- three at `n = 300`, the probe sample (seed `20261006`);
- three at `n = 5117`, every query.

Ordinary least squares, no intercept constraint:

\[
T = a + b n.
\]

`b` has to be positive. If it is not, the prediction is undefined and
D3 is not confirmed. Unchanged fraction `c` is D1's fitter-hash
fraction. For the full query set:

\[
\mathrm{speedup}(c) = \frac{a + b \cdot 5117}{a + c\, b \cdot 5117}.
\]

Assumptions, fixed now: `a` does not shrink on the smaller reference;
per-record cost scales with `c`, not with the residue-only fraction;
merge and rescale stay inside the measured ACTS wall and are not
subtracted; the probe and the six fit runs are not inside that wall.
If `c = 0` or the denominator is not positive, the prediction is
undefined and D3 is not confirmed.

**CONFIRMED** when the prediction is defined and the mean of the three
alternating stock walls divided by the mean of the three alternating
ACTS walls is within ±25% of `speedup(c)`:

\[
\left| \frac{\bar T_{\text{stock}}}{\bar T_{\text{ACTS}}} - \mathrm{speedup}(c) \right|
\le 0.25 \cdot \mathrm{speedup}(c).
\]

The six fit runs are not those alternating means. iSeqSearch's
alternating mean is reported against the same `speedup(c)` and is not
part of the CONFIRMED predicate. The predicate is the ACTS arm.

## MATCH

ACTS is accepted only under **ref-merge** against the stock newer-release
output: same row keys, non-numeric columns byte-identical, `identity`
columns byte-identical, `evalue` consistent with
`total_entry_length` under the shipped half-ULP predicate. Not
byte-identical.

iSeqSearch, if it produces a file, is scored two ways, both reported:

1. ref-merge against the same stock output. Their merger prints
   `str(float)`, so E-values will miss a byte compare; the half-ULP
   predicate still applies to `evalue`, and every other numeric column
   must be byte-identical. Extra or missing keys fail ref-merge.
2. Their published bar, which is weaker: Pearson correlation of
   E-values on the intersection of `(qseqid, sseqid)` pairs, plus hit
   counts (stock, merged, intersection, only-stock, only-merged).
   They report extra hits. That does not satisfy ref-merge.

## Results

One JSON per decision, each with `acts.provenance` plus DIAMOND
version, the argv, both release URLs, both checksums, and D0's two
letter counts:

- `pipeline/results/reference_diamond_d0.json`
- `pipeline/results/reference_diamond_d1.json`
- `pipeline/results/reference_diamond_d2.json`
- `pipeline/results/reference_diamond_d2n.json`
- `pipeline/results/reference_diamond_d3.json`

## Not allowed after the runs

A fifth normalizer. A DIAMOND-named branch in `acts/`. A column map
from `evalue` to `total_entry_length`. Editing this locked text. Using
the residue-only fraction as `c`. Treating S2 as a license to pass
`--freq-masking`.

## Addendum 2026-10-06 — download approved

Written after the hold above and before any download or DIAMOND run.
The locked text is unchanged.

The older archive may be fetched. Conditions, fixed by the approval:

- Download on the CARC data-transfer node into `/project2`, not on the
  Mac and not on a login node.
- The tar MD5 must be `6042adf20dad1ab62112c9053bdebd20` before
  extraction. A mismatch stops the run.
- Extract only the Swiss-Prot FASTA member. Record that file's own
  size and checksum in the result JSON.
- Delete the tarball after a successful extract. Do not commit the
  FASTA, the database, or the tar to git.
- The release pair is **2026_01 → 2026_03**. Two releases. `c` is the
  churn of that pair under D1.

The newer FASTA (93,801,562 bytes, MD5
`bc9d398533e6df582b563c6c03093bd0`) is fetched the same way. It is
under 1 GB. The DIAMOND v2.2.5 Linux binary is fetched the same way.

## Addendum 2026-10-09 — input resolution

Job 12759635 failed on input resolution before any measurement; fix; resubmission.

The locked D0–D3 definitions do not change. Smoke output is not a measurement.

Job 12759635 (`acts_ref_diamond`, commit `d5d5a66`) started 2026-10-08 03:25 on b22-22, working directory `/home1/jjt_373`, and exited 1 after 11 seconds. `data/swissprot/OLD_PATH` held the relative path `data/swissprot/uniprot_sprot_2026_01.fasta.gz`. No D0–D3 file was written.

Before any DIAMOND invocation, every input path is resolved against a declared absolute root and checked for existence, size, and MD5. A miss stops with `STOP_INPUTS`. The job `cd`s to that root and passes only absolute paths. Runtime Python dependencies are pinned in `pipeline/requirements-diamond.txt` (`biopython==1.85`, `numpy==2.4.6`, `tqdm==4.67.1`) and installed once into `${ACTS_CODE_ROOT}/venv`. The job does not pip-install into `~/.local`. The checkout's own `requirements.txt` still says `biopython==1.79` and `tqdm==4.64.0` and does not name numpy; those older pins are not what this job loads.

Measured identities, `md5sum` on compute node a01-04, job 12863550, 2026-10-09. The raw lines are `pipeline/results/reference_diamond_input_checksums.txt`. The 2026_01 tar MD5 in the locked table is unchanged. This row is the extracted FASTA the driver opens.

| Input | Bytes | MD5 |
|---|---|---|
| 2026_01 Swiss-Prot FASTA | 93457057 | `5245b19456d9a063b13c46602269bc5f` |
| 2026_03 Swiss-Prot FASTA | 93801562 | `bc9d398533e6df582b563c6c03093bd0` |
| DIAMOND v2.2.5 linux64 binary | 28553136 | `7de14b7f9f4c440ddfb5142ad96b1d8b` |
| Collection A queries `GCF_002853805.1_protein.faa.gz` | 1074926 | `b170d133266427c46d87d99284e1fda3` |
| iSeqSearch `source/main.py` at `7e862bf3afa52b65b3cca4255de66ab4cb764fe3` | 2477 | `2c0762059f0229add06bf351edb2f979` |

`--smoke` keeps the first 2,000 entries of each release and the first 50 query proteins, runs D0–D3 with one fit wall at n=10, one at n=50, and one alternating repeat (stock, ACTS, iSeqSearch) on 4 threads. It writes only under `results/reference_diamond_smoke/`. It does not satisfy D3.

Resubmission uses a new code tree, these same files by absolute path, and the original resources: exclusive `epyc-7542`, 32 CPUs, 64 GB, 24 h.

## Addendum 2026-10-09 — ref-merge checker omitted source rounding

ref-merge checker omitted source rounding; found in smoke before any measured outcome; locked definition unchanged; implementation corrected; error bound stated; 12760029 and 12864042 superseded.

D3's MATCH for the ACTS arm is ref-merge, the relation in `REFERENCE_INCREMENTAL_PROTOCOL.md`. The smoke at `results/reference_diamond_smoke/reference_diamond_d3.json` (job 12863759, code `45a0b6e`) reported `ref_merge_acts` failed on `('WP_000010284.1', 'sp|Q84P26|4CLL8_ARATH', '')`. That failure was the checker, which compared the reprinted E-value to stock at \(\phi = 1\) and dropped the source-rounding term. It was not a failure of the locked predicate. The smoke is not a measured outcome.

The corrected checker tests each rescaled cell with the locked predicate against its source printed value, and it requires the emitted cell to equal the deterministic reprint of that source times \(\phi\). Identity and byte columns stay byte-exact. Row-key sets stay equal.

User-facing error bound, for a cell that passes:

\[
|\mathrm{emitted} - \mathrm{stock}| \le \mathrm{half\text{-}ULP}(\mathrm{stock}) + \mathrm{half\text{-}ULP}(\mathrm{emitted}) + |\phi|\cdot\mathrm{half\text{-}ULP}(\mathrm{source}).
\]

iSeqSearch still has no source token. Its ref-merge stays the locked printed comparison: half-ULP at \(\phi = 1\) on `evalue`, every other column byte-identical. That path is not the ACTS checker.

Job 12864042 ran the checker that omitted source rounding. It is superseded, as is 12760029. No measured outcome from either is a result.

The Pfam cache note is in the incremental addendum of the same date. DIAMOND does not use that cache. The smoke of this checker, job 12865057, code `e85f24d`, is recorded under `results/reference_diamond_smoke/`. `ref_merge_acts` passed. That smoke is not a measurement.

## Addendum 2026-10-10 — D0–D2n measured; D3 killed; resume

Job 12866389, code `9cbd81bbdb73876ab788ed75c0e0aa532447cb76`, exclusive `epyc-7542` node `b22-24`. Started 2026-10-10T09:53:06-07:00. Slurm state `OUT_OF_MEMORY`, exit `0:125`, ended 2026-10-10T12:34:04-07:00, elapsed 02:40:58. ReqMem 64G. Batch MaxRSS 47,504,664 KB. The log, the four stage files, and `job_12866389.json` are in `pipeline/results/reference_diamond/`. The locked D0–D3 definitions, S1, and the D3 prediction rule are unchanged.

### D0–D2n against the locked predictions

These four JSON files are the measurement from that code. They were not recomputed. The driver that wrote them records git, host, and package versions. It does not record a memory field. Memory for the job is the sacct MaxRSS in `job_12866389.json`.

D0. `old_equal` and `new_equal` are true. `diamond dbinfo` Letters equals the FASTA length sum on both releases: old 208,482,574 letters and 574,627 entries; new 209,017,843 letters and 575,748 entries. The E-value factor is the pre-registered `total_entry_length` member. MEASURED `reference_diamond_d0.json`, written 2026-10-10T09:53:46-07:00.

D1. `c = 0.01778382208883056 = 1 − 565509/575748`. Added or changed 10,239. Removed 9,118. The residue-and-id fraction 0.9921962386321793 is the descriptive fraction and is not `c`. MEASURED `reference_diamond_d1.json`, written 2026-10-10T09:54:39-07:00.

D2. SHIP. No tie-break. Column 10, `evalue`, is `total_entry_length`. Columns 2–9 and 11 are `identity`. `expectation.matches` is true. MEASURED `reference_diamond_d2.json`, written 2026-10-10T09:54:49-07:00. The three probe invocations are the 10 seconds between the D1 file and this file.

D2n. REFUSE, which is the required negative-control result. The reason is that the row-key sets differ: whole 3,686, union 6,121, only-union 2,435, only-whole 0. MEASURED `reference_diamond_d2n.json`, written 2026-10-10T09:54:57-07:00.

### Why the step was killed

The job set scratch to `${SLURM_TMPDIR:-/tmp}`. The log's `df` on `b22-24` shows `/` is tmpfs, size 126G. CARC documents compute-node `/tmp` as RAM, charged to the job's memory request, and capped at half the node (https://www.carc.usc.edu/user-support/frequently-asked-questions). `sinfo` lists `epyc-7542` nodes at 256000 MB. 126G is half of that.

Stdout was last written at 2026-10-10T09:54:57-07:00. Its last line is `D3 timing`. The shell then reports that the Python driver was killed, and Slurm reports one oom-kill in the batch step. The next statement after that print is one S1 `diamond blastp` of all 5,117 queries with `-k 0`, writing `cold.m8` into the scratch directory. That search ran until 12:34:04, 2h39m07s, and produced no further stdout.

D2 finished in about 10 seconds, including the whole-database `-k 0` probe on 300 queries, so those probe files were not a 45 GiB resident set. MaxRSS 47,504,664 KB is 45.3 GiB of anonymous resident memory. The cgroup limit was 64G. Tmpfs pages are charged to that same cgroup and are not included in MaxRSS. The diamond process and the files on the RAM disk were in one 64G limit.

After that search the driver kept every stock, ACTS, and iSeqSearch m8 via `Path.read_text`. That code had not run yet. The resume indexes one file at a time and deletes the cold-start file and each fit file after the wall is recorded, so those copies are not retained.

Job 12917861 is an ordinary-node probe of the same S1 flags at 16 threads, with output on `/scratch1`, for the seeded 300 queries, the first 300, and the first 1,500. It measures output bytes and maximum resident set. Its numbers are not part of this addendum until that job's log is in the tree. They are not assumed.

### Resume

`--resume-d3` reads the four committed files and does not rewrite them. It rebuilds the databases, checks `dbinfo` letters and the D1 counts against those files, and stops on a mismatch. It stores the committed D2 fit as the cache contract, then runs the untimed warm load, the discarded cold start, the six fit runs, and the alternating block. `c` in the prediction is the committed D1 value. S1 is unchanged. The probe is not repeated: it is outside the alternating means, and its assignment is the committed D2 fit.

Scratch for the rerun is `/scratch1/$USER` (Lustre). On 2026-10-10 that directory had a 10 TB quota and was using 33 KB. The driver refuses to start a measurement when scratch is tmpfs, unless `--allow-tmpfs-scratch` is set. The job also exits before DIAMOND when `findmnt` does not report a non-tmpfs filesystem.

The rerun asks for `--mem=0` on the exclusive node, which is the node's memory. The locked paragraph above still says `--mem=64G`. That is the request the cgroup enforced. This addendum changes the request. It does not change the prediction rule.

## Addendum 2026-10-12 — Test D-X (pre-registered)

Written before any D-X search and before any measured D-X wall. The locked
D0–D3 text, S1, and the D3 resume rule are unchanged. No number below is
a result. This test does not read or write the CARC D3 resume files.

### Why

The prior-art verdict says the narrow exact claim survives on a second
tool only with no compiled per-tool formula, the pin found by inference,
and a body compare. The hand-built approximate competitor on this tool
is iSeqSearch's iDiamond at `7e862bf3afa52b65b3cca4255de66ab4cb764fe3`.
Search here is heuristic, and some internals read the database. The
BLAST boundary run found one `different_hsp` row. Pinned replay may not
be exact. A clean KILL is a result.

### Host and inputs

One Mac run. Walls are indicative. Scratch is a normal disk directory
under `pipeline/data/` (APFS, not tmpfs, not a RAM disk). The driver
refuses to start when that directory's mount is tmpfs.

S1 argv and prep are the locked commands, including `--threads 32`,
`-k 0`, `--min-score 40`, `-b 2.0`, and the locked outfmt. Sensitivity
mode and columns are not changed. This host has fewer than 32 cores;
the thread count stays 32.

The binary is the v2.2.5 macOS release asset, because this host is
Darwin arm64. `diamond version` must contain `2.2.5`. Any other version
string stops the run. The linux64 MD5 in the input table is the CARC
binary. The Mac binary's own MD5 is recorded in the result and is not
required to equal that row. Source commit of the tag remains
`6dc57174369ba131d35a21db9735a48ac01e6610`; this run does not build a
different commit.

Inputs are the two Swiss-Prot FASTA rows in the 2026-10-09 checksum
table. A size or MD5 mismatch is `STOP_INPUTS`. The 2026_01 tar, if
fetched, must match `6042adf20dad1ab62112c9053bdebd20` before
extraction. The extracted FASTA must match
`5245b19456d9a063b13c46602269bc5f`. Data stays outside git.

The D2 contract is the committed fit
(`results/reference_diamond/reference_diamond_d2.json`). It is not
refit. Column 10 is `total_entry_length`. No column is `entry_count`.

### Queries

DX-E1, DX-E2, and DX-I use the same 300 queries: record indices
`sorted(random.Random(20261017).sample(range(n), 300))` from
`GCF_002853805.1_protein.faa.gz`, written in that file order.

DX-K queries are held out, from `GCF_002090355.1_protein.faa.gz`,
K1r-style, seed `20261018`. Three independent `random.Random(20261018)`
instances, so the query draw does not consume the fill stream:

1. Draw `sorted(sample(range(n), 300))`. One S1 scan of those records
   against full 2026_03 is SAMPLE-CONSTRUCTION, not a DX-K result.
2. Q is the first 50 indices in that sorted draw with at least one
   body row. Fewer than 50 is INCONCLUSIVE, not a kill and not a pass.
3. Hit entries are 2026_03 entries, in file order, whose key equals a
   subject id on a Q row. Unmatched subject ids are counted and are
   not members of W. More than 400 hit entries: W is the first 400 in
   file order and the fill does not run. Otherwise the fill is
   `sample` of the non-hit indices, size `400 - |hits|`. W is hits
   plus fill, in file order. `|W| < 400` is INCONCLUSIVE.
4. H is the K1r stratified half. The third `Random(20261018)` samples
   `len(stratum) // 2` from the hit stratum, then from the fill
   stratum. If those floors sum to less than 200, the remainder is
   unselected fill entries in file order, then unselected hit entries,
   until `|H| = 200`. H is written in W's file order.

### DX-K

`acts/infer_knobs.py` accept, reject, placeholder, and threshold rules
are unchanged. The contract is the committed D2 tables. The help probe
is generic and does not name a program:

- Let `k` be the index of the first option token in the argv.
- For `j = 1 .. k` inclusive, try `argv[:j] + ['--help']`, then
  `argv[:j] + ['-h']`.
- Use the first text that yields a numeric-argument option under the
  locked parser.
- If none do, try the bare prefixes `argv[:j]` in the same order and
  use the first that yields a numeric-argument option. This covers a
  program that prints usage when required arguments are missing and
  rejects a help flag.
- If none do, inference receives the last bare prefix's text.

Help text is not a probe call. A line with no locked numeric
placeholder is not a candidate, including a line that only prints
`default=`.

Ground truth, written now: the pin is `--dbsize {total_entry_length}`.
Decoys must not be accepted as the pin or as a reporting threshold:
`--threads`, `-p`, `--block-size`, `-b`, `--index-chunks`, `-c`, and
any option whose token or help line contains `seed` or `shape`.

Driver safety, the worker-count analogue, fixed now. A refused probe
is `tool failed` and cannot be accepted. It is not executed:

- `--threads` set to anything but `32`;
- `-b` or `--block-size` set to anything but `2.0` (the unit is
  billions of letters, and the probe value is a letter count);
- `-c` or `--index-chunks` set to an integer above 64.

Every inference invocation also has a 10-minute wall and an 8 GiB
resident cap. A kill is `tool failed`. Stock searches are not under
that cap; they have a 60-minute wall and a 18 GiB resident cap so a
runaway stops without using the RAM disk.

KILL: the pin is not `--dbsize {total_entry_length}`, there is no pin,
or a decoy is accepted. Do not retune the placeholder list, `s`, or
the accept rule.

### DX-E1

Only if DX-K passes. Stock S is S1 on 2026_03 for the 300 queries.
Replay R is S1 on the queries with at least one S row, against the
union of S's subject entries in 2026_03 file order, with the inferred
pin set to `{total_entry_length}` of the full 2026_03 release.
Rn is R without the pin. Body lines are every line that does not start
with `#`. R must be byte-identical to S. Rn must differ. Any body
difference kills exact mode for this tool. Classify every differing
row: `same_hsp_different_value` (same query, subject, and
`qstart qend sstart send`, some other cell differs), `different_hsp`,
`row_missing` (in S only), `row_extra` (in R only). Report counts.

### DX-E2

Only if DX-E1 passes. Cache is stock S1 on 2026_01 for the same 300
queries. Changed or new entries are 2026_03 entries whose strict hash
(sequence plus header, as the FASTA parser defines it) is absent from
2026_01. Discovery is S1 on that sub-reference, unpinned, with the
declared slack. Candidates are cached rows whose subject entry is
unchanged, plus discovery rows. Replay is S1 on the queries that have
a candidate, against the union of those entries in 2026_03 file order,
with the inferred pin and without the slack flags. Compare body bytes
to stock S1 on 2026_03.

Declared slack, caller data, not inferred: `s = 2` on the e-value
cutoff. The help default of that cutoff is 0.001, so discovery and
only discovery adds the e-value option set to `0.002`. S1's
`--min-score 40` stays on every invocation. Replay does not add the
e-value option. Thresholds are not inferred. This is the K1s rule that
thresholds stay caller data.

Any body difference: exact mode is not claimed for this tool. Record
the difference classes. No per-tool branch is added.

### DX-I

Runs even if DX-K, DX-E1, or DX-E2 is a kill. Same 300 queries and the
same 2026_01 → 2026_03 update. OLD is stock S1 on 2026_01. DELTA is
stock S1, not the slack command, on the FASTA of 2026_03 entries whose
strict hash is not in 2026_01. `L_old` and `L_delta` are `diamond
dbinfo` letter counts. Their sum is what the merger uses. The call is
`source/main.py --default OLD DELTA OUT L_old L_delta` at the pinned
commit. Do not reimplement the merger.

Against stock S1 on 2026_03, for iDiamond and, if DX-E2 produced a
body, for ACTS: rows only-stock, only-other, shared; fraction of
shared rows whose body line is byte-identical; Pearson and Kendall τ
of the e-value column on shared rows. DX-I has no kill.

### Output

`pipeline/results/reference_diamond/dx.json`: git hash, host, version
strings, MD5s, and every count. MEASURED numbers come from that file.
Walls are single-run and indicative.

## Addendum 2026-10-12 — Test D-X outcome

Rules above are unchanged. Result file
`results/reference_diamond/dx.json`. Git `fd9f43b`. The provenance
`git_dirty` bit is true because unrelated paths were already modified;
this run did not edit them. Host `Joshuas-MacBook-Pro-3.local`, arm64,
14 cores, DIAMOND `diamond version 2.2.5`, macOS universal binary MD5
`711d4c7b29e24c3fd6ec6a288ec1d326`. Scratch was APFS
`/System/Volumes/Data`, not tmpfs. Input MD5s matched the committed
table. `dbinfo` letters matched D0: 2026_01 is 208,482,574 and 2026_03
is 209,017,843. Changed or new entries: 10,239, equal to D1.

**DX-K — KILL.** Not a pass. Help candidates: 0. The subcommand usage
text was retrieved, and the locked placeholder grammar extracted no
numeric-argument option, so `--dbsize` was not a candidate and neither
were the decoys. Pin `no knob`, reason `total_entry_length: no knob`.
The member was visible: the reason is not `probe cannot see M`.
`tool_calls` = 2 (the half and whole baselines only). Decoys accepted:
none. SAMPLE-CONSTRUCTION, not a DX-K result: 300-query scan 4.50 s,
40,337 body rows, 288 queries with a hit, Q = 50, hit entries 8,713
(W truncated to 400), unmatched subjects 0.

**DX-E1 — NOT_RUN. DX-E2 — NOT_RUN.** Stopped at the DX-K kill. No
difference classes. Exact mode is not claimed for this tool. Nothing
was added to `acts/` that names the tool. An inferred pin of `no knob`
is already `REFUSE_PIN`. Step 4 (CLI smoke, regression test) was not
run.

**DX-I — comparison, no kill.** Merger exit 0. `L_old` = 208,482,574,
`L_delta` = 4,056,372, sum 212,538,946, which is what the merger used.
Stock 2026_03 has 31,377 rows. iDiamond has 31,510. Shared 31,377.
Only-stock 0. Only-iDiamond 133, and all 133 subject ids are absent
from 2026_03 (removed entries kept). Shared-row byte-identical
fraction 407/31,377 = 0.012971. Of the other shared rows, 30,968
differ only in the e-value cell (the merger's `str(float)` rescale)
and 2 differ in subject coordinates as well (`sstart`/`send` shifted,
query interval and bit score unchanged): `WP_001110573.1` /
`sp|Q9VL32|SUR_DROME` and `WP_001285559.1` / `sp|Q9VL32|SUR_DROME`.
E-value Pearson 0.9999991687961751. Kendall τ 0.9999939628622326.
n = 31,377. ACTS has no rows: E2 did not run.

Walls, one Mac run, indicative: stock 2026_01 4.06 s, stock 2026_03
3.61 s, delta search 0.42 s. The whole driver was 37 s. Not a speedup
claim.

## Addendum 2026-10-12 — DX2 (pre-registered after pilot)

Written after the pilot commit `97683b6` and before any measured DX2
search. The locked D-X text, the DX-K kill, and `acts/infer_knobs.py`
are unchanged. Pin inference stays closed. No number below this
paragraph is a measured DX2 result. The pilot file is
`results/reference_diamond/dx2_pilot.json`. It is a pilot, not a result.
The semantics note is `results/reference_diamond/dx2_semantics.md`.

### Pilot findings

Host `Joshuas-MacBook-Pro-3.local`, DIAMOND 2.2.5, macOS binary MD5
`711d4c7b29e24c3fd6ec6a288ec1d326`. Inputs matched the committed FASTA
table. `dbinfo` letters matched D0. Queries: 50 with a hit, drawn from
`GCF_002090355.1` by `random.Random(20261019)` (pool of 80, 78 had a
hit). Threads 8 on every search. These queries are not the measured set.

- **B0.** Stock twice, bodies identical, 6,451 rows. `--threads 1` and
  `--threads 8` bodies identical. Both logs: `Algorithm: Double-indexed`,
  `Block size = 2000000000`.
- **B1.** Oracle replay with `--dbsize 209017843` is not the stock body.
  6,448 shared rows are byte-identical, including the E-value cell.
  `row_missing` 3, `row_extra` 0, `different_hsp` 0,
  `same_hsp_different_value` 0. All three missing rows are one query,
  `WP_000273290.1`, against `sp|O67359|GPH_AQUAE` (bitscore 49.3),
  `sp|Q48A85|GPH_COLP3` (47.4), and `sp|B7GL49|PPAX_ANOFW` (40.0). The
  unpinned control differs: 6,335 `same_hsp_different_value`, the same
  3 missing rows, 113 shared lines byte-identical. The pin is
  load-bearing for the printed E-value. It does not cause the three
  misses.
- **B2.** HMMER positive control passes. E1 argv, Pfam 38.2, `--cut_ga`,
  `--cpu 4`, `-Z 30134`, first 50 indices of the E1 draw
  (`random.Random(20261012).sample` of 300 from `GCF_002853805.1`).
  47 queries with a hit, 102 candidate models, pad 200. tblout 104/104
  and domtblout 114/114, ordered bodies equal, no pad hit. DIAMOND on
  the true B1 candidates: the stated certificate passes (6,448 R rows
  all present in R+, 0 pad hits) while R+ has one extra row on a
  candidate subject (`PPAX_ANOFW`, one of the three stock rows R
  missed). Negative control: drop 645 of 6,451 hit subjects (10%,
  `random.Random(20261022)`). The certificate fails, 9 pad-hit rows.
  Nine of the dropped subjects fell in the pad. It can see that
  incomplete set.
- **B3.** No declared extra. Stock and replay both double-indexed, both
  one block of 2e9 letters. `--no-ranking` on the replay only still
  misses the same 3 rows. `--algo` and `-b` were not retuned.
- **B4.** On entries unchanged between 2026_01 and 2026_03 (565,509),
  the 50 queries have 6,256 hit pairs in each release and 0 pairs hit
  in one release only.
- **B5.** Indicative walls: stock 2.82 s, R 0.161 s, R+ 0.190 s.
  R+/R = 1.18. R+/stock = 0.067.

The stated certificate does not fail when R+ adds a row whose subject
is already in U. That is how it passed over a replay that missed three
stock rows. The measured arms keep that predicate. A pass on a replay
that differs from stock is UNSAFE, which is the kill this test exists
to allow.

### Locked argv

S1 with `--threads 8` on every invocation, including `makedb`. Eight is
the cap while another job may share this machine. B0 showed 1 and 8
threads print the same body, so the count is not a second scientific
knob. No B3 extra. Declared pin, replay only:
`--dbsize {total_entry_length}` with the full 2026_03 letter count
209,017,843.

E2 slack carrier, required because `slack_rewrite` only scales a flag
the argv already sets and rejects `--evalue 0.002` on bare S1. The E2
tool argv is S1 plus `--evalue 0.001`. `--slack '--evalue 0.002'` then
has factor 2. Cache fill and discovery use 0.002. Replay uses 0.001
plus the pin. `--min-score 40` stays on every invocation. Stock, the
comparison target, is S1 without `--evalue`. Under `--min-score`,
`report_cutoff` uses the bit score and does not read the E-value
cutoff (`score_matrix.cpp:238-243` at the pinned tag). This flag is
the slack carrier, not a size-dependent knob.

### Queries, references, pad

DX2-E1 and DX2-E2 use the same 300 queries:
`sorted(random.Random(20261017).sample(range(n), 300))` from
`GCF_002853805.1_protein.faa.gz`, written in file order. Releases
2026_01 → 2026_03. Pad seed `20261020`. Pad is a sample of
non-candidate entries, size `max(200, |U|)`, merged with U in release
order. The same pin is used on R and on R+.

The certificate passes if and only if every R body line occurs in R+
with the same multiplicity, and R+ has no row on a Pad entry for a
replayed query. An extra R+ row on a candidate subject does not fail
it. That limitation is the one the pilot exhibited.

### Arms

Judged independently. Neither gates the other.

- **DX2-E1.** Stock S is S1 on 2026_03. U is S's subject entries in
  file order. R is S1 plus the declared pin on the queries with a hit,
  against U. Rn, the unpinned control, is recorded and is not an
  outcome. IC is R versus R+ on U ∪ Pad.
- **DX2-E2.** Shipped CLI, `python3 -m acts run --strategy reference`,
  `--pin '--dbsize {total_entry_length}'`, `--slack '--evalue 0.002'`,
  tool argv as above, `--prep` the locked `makedb` line with 8 threads.
  Cache filled by that command on 2026_01, then the same command on
  2026_03. The emitted replay body is compared to stock S1 on 2026_03
  without `--evalue`. IC uses the candidate union that replay searched.

### Outcome

Per arm:

- **EXACT.** Replay body equals the stock body, and IC passed.
- **SAFE-REFUSE.** IC failed. Record whether the replay body differed
  from stock (true refusal) or matched (needless refusal).
- **UNSAFE.** Replay body differs from stock, and IC passed. Report
  the difference classes. This is the kill.

Also record candidate pairs, rescanned entries, replay subjects, IC
overhead, and walls. Walls are one Mac run and are indicative. If E2
is EXACT, add the ACTS row beside iDiamond in the D-X comparison:
shared-row exact fraction, Kendall τ, Pearson, extra and missing rows
versus stock.

