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
