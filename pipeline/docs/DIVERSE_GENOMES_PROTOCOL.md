# Diverse genomes: HMMER exactness where stitching and width can break

Written before the pilot and before any `hmmscan` in this test. No number
below is a measured hmmscan result. The semantics review is
`pipeline/results/diverse_genomes/semantics.md`. The locked draw is
`pipeline/results/diverse_genomes/draw.json`. The generator is
`pipeline/scripts/draw_diverse_genomes.py`.

This text is committed before the pilot. The pilot cannot run until the
proteomes below are approved and the shared SSH master is up. That is a
deviation from "pilot, then lock." The pilot may change one rule, in a
dated addendum, and that spends the one redesign this question is
allowed. The measured run uses the text after that addendum. It does not
start in this commit.

## Question

On `hmmscan --cut_ga`, is a TARE update from Pfam 38.1 to Pfam 38.2
byte-identical to a stock run on the new release, on proteomes that are
not the two bacterial genomes already passed through the shipped tool?

The failure this draw is built to see is a body line whose bytes depend
on something outside that protein's own reported hits: a column width, a
query name, or a per-query count. The semantics note says where each one
is computed and how a break is classified.

## What the writers actually depend on

Under `--cut_ga`, registered hits and reported hits are the same set.
Target-name width is the longest reported target name on that query,
with a floor of 20. It is not a file-wide width. Query-name width is
`strlen` of that query's FASTA name, with the same floor. `domZ` is the
number of reported targets on that query. TARE stitches the original
lines back into input order. It does not re-pad.

Pfam 38.2, local file md5 `7ab3c4e215d0daaea3004e37c4e24f8a`, has 147
names longer than 20. The longest is `Bacteriocin_streptolysin_S_pre`
(30). A query that hits that name and a shorter name pads every row of
that query to 30. Dropping the long name shrinks the survivors:
whitespace-only, plus missing rows. Other queries do not move.

Query descriptions are not in tblout or domtblout. The target
description is, and it is the last field. Spaces in it do not move the
query-name column. Across the 16 KiB prefixes of the locked proteomes
and a 40-MAG prefix sample (seed `20261154`, first 256 KiB), the longest
FASTA name token was 14 characters. None exceeded the floor of 20. The
longest description in that sample was 211 characters, on
`GCA_060790075.1`, and that assembly is in the measured set for that
reason. File-wide maxima are measured from the headers after approval
and before any hmmscan. If every name is still at most 20, the
query-name width was at the floor. That is reported. It is not a failure
of exactness. The target-name width above is the width stress the
reference itself supplies.

`%3d` domain counts and `%5d` coordinates overflow at 1000 and 100000.
More than 20 domains does not overflow. Human (`GCF_000001405.40`) and
Drosophila (`GCF_000001215.4`) are in the draw because they contain long
multi-domain proteins. The stock domtblout is what shows whether any
query has more than 20 domain rows. If none does, that stress was not
exercised.

## Draw

Seeds, from this experiment's block, not reused:

- Pilot `20261151`. One archaeon, one eukaryote, one MAG. Removed from
  the measured pools before the measured seed is applied.
- Measured `20261152`. Each stratum has its own `random.Random(20261152)`.
- Injected drop `20261153`. Not used in the draw.
- Prefix sample `20261154`.

Accessions already used or pre-registered in
`pipeline/docs/EXACT_REPLAY_PROTOCOL.md` are out of every pool. The list
is `excluded_accessions` in the draw file. Phylum is column 8 of NCBI
`rankedlineage.dmp` (0-based index 7). `Proteobacteria` and
`Pseudomonadota` count as one phylum toward the cap. The stored phylum
string stays NCBI's.

Eligibility, in the order the script applies it:

- Archaea and bacteria, tier 1, which is the tier this draw used: RefSeq
  `GCF_`, latest, full, a reference or representative genome, complete
  genome, a non-empty phylum, at least one protein-coding gene, one row
  per species. Archaea: 15 genomes, at least 3 phyla, cap not applied.
  Bacteria: 30 genomes, at least 10 phyla, at most 6 from the
  proteobacterial phylum. Phylum order is shuffled with the measured
  seed, then round-robin. This draw did not need tier 2 or tier 3.
- Eukaryotes: the RefSeq reference rows for Homo sapiens, Drosophila
  melanogaster, and Saccharomyces cerevisiae, plus 2 genomes sampled
  from the other reference or representative complete or chromosome
  assemblies.
- MAGs: GenBank `GCA_`, latest, contig or scaffold, `excluded_from_refseq`
  contains `metagenome`, at least one protein-coding gene. Five are
  drawn by the same round-robin. The bacteria MAG table that was read is
  an extract, not the full GenBank bacteria catalog: 248,829 latest GCA
  rows whose exclusion field contains `metagenome`, md5
  `b6aecaf94f7d2fbd06d789399c64a93e`. The archaea MAG rows are the same
  flag inside `genbank_archaea.txt`. Two further MAGs were added from
  the prefix sample: the longest name token and the longest description.

The draw file is the lock. A later NCBI catalog is not a reason to
redraw. Summary md5s are in that file. The runner stops if it is pointed
at a summary whose md5 differs.

Counted from that file, not from a new sample:

| Stratum | Pilot | Measured | Phyla in the measured set |
|---|---:|---:|---|
| Archaea | 1 | 15 | 8 |
| Bacteria | 0 | 30 | 30, of which Pseudomonadota is 1 |
| Eukaryote | 1 | 5 | human, Drosophila, S. cerevisiae, plus two |
| MAG | 1 | 7 | five stratified, plus the two prefix additions |

Measured genomes: 57. With the pilot: 60 proteomes. Exact total size
88,232,300 bytes. Each size is the `Content-Length` from HTTP HEAD
(`pipeline/results/diverse_genomes/proteome_heads.json`). The same
integer was read from the `Content-Range` total of a 16 KiB range
request, which was used only to see the first FASTA headers. The two
agree on every file. Those ranges are not the proteomes. The proteomes
are not downloaded in this commit.

Pilot, disjoint from the measured set:

1. `GCF_052510705.1`, archaeon, *Natrialba aegyptia*
2. `GCF_000226115.1`, eukaryote, *Thermothielavioides terrestris*
3. `GCA_003676205.1`, MAG, a spirochete symbiont

## Command

Stock, the comparison target, no pin:

```
hmmscan --cut_ga --noali --cpu 8 --tblout T --domtblout D -o /dev/null <pfam> <proteins>
```

`--cpu 8` is this test's width. The headline timing runs used 4. `-o
/dev/null` is the shipped headline command. The human-readable report
uses `--textw` (default 120). The compared files do not.

TARE, from `pipeline/`:

```
python3 -m acts run --strategy reference \
  --pin '-Z {entry_count}' --verify audit \
  --prep 'hmmpress -f {reference}' \
  --input <proteins> --reference <pfam> --cache <cache> -o <out> -- \
  hmmscan --cut_ga --noali --cpu 8 \
  --tblout {output:tblout} --domtblout {output:domtblout} \
  -o /dev/null {reference} {input}
```

Fill on Pfam 38.1
(`/project2/biyik_1165/jjt_373/csci270-star/reference_reannot/data/pfam38.1/Pfam-A.hmm.gz`).
Update on Pfam 38.2
(`/project2/biyik_1165/jjt_373/csci270-star/pipeline/data/hmmer/Pfam-A.hmm.gz`).
One update. This test is correctness. Walls are recorded and are not a
speedup claim. If a press does not report 27,481 models for 38.1 or
30,134 for 38.2, stop. That arm is INCONCLUSIVE.

Body lines are lines that do not start with `#`. Both tables.

## Pilot, then the gate

On each of the three pilot proteomes, in the order above:

1. Stock 38.2, twice, no `-Z`. The two tblout bodies must be
   byte-identical, and the two domtblout bodies must be byte-identical.
   If any pair differs, stop. The tool is not deterministic at
   `--cpu 8`. No TARE run is scored. That stop is indeterminism.
2. Fill on 38.1. Update on 38.2 with the command above, check on.
   Byte-compare both tables to one of the stock runs.
3. Negative control. From the stock tblout, the candidate models are the
   sorted target names. Drop `max(1, round(0.05 * n))` of them with
   `random.Random(20261153)`. Rerun the pinned replay on the reduced
   set and run the shipped check (neighbor pad, and the three random
   pads when the residue cap does not bind). The body must differ from
   stock, and the check must refuse. A byte-identical drop is
   INCONCLUSIVE for that proteome's control. A check that accepts a
   differing body is UNSAFE. Do not start the measured run.

The positive control is the stock pair, and a pilot TARE decision of
`SHIP` whose bodies match stock. The negative control is the drop.

## Measured run

Same command on every measured proteome. Stock 38.2 once, as the
comparison target. The pilot's double stock run is the determinism
evidence. The drop is not repeated.

## Pass rule

A genome is one of these:

- **Pass.** Decision `SHIP`, and tblout and domtblout bodies are
  byte-identical to stock.
- **UNSAFE.** Decision `SHIP` and any body byte differs. Also the pilot
  control, if the dropped replay differs from stock and the check does
  not refuse. Any UNSAFE fails the claim.
- **Needless refusal.** Decision starts with `REFUSE`, and a replay body
  was written and is byte-identical to stock on both tables. Count it.
  List the accession and the decision string. It is not a pass and it
  is not UNSAFE.
- **Refusal.** Decision starts with `REFUSE`, and either no replay body
  was written or the body differs from stock. Count it separately from
  needless refusals. A differing body that was refused is the check
  doing what it is for.
- **INCONCLUSIVE.** Stock tblout body has fewer than 100 lines, or the
  run did not finish. Not a pass, not UNSAFE, not in N.

The claim fails only on UNSAFE. It does not require every genome to
ship. Needless refusals are a reported count, not a silent pass.

## Difference classes

Both tables, body lines only. Byte equality and `split()` token equality
are both recorded.

- whitespace-only: bytes differ, tokens equal
- value-only: a shared row's tokens differ
- missing / extra: the row-key multiset differs
- order: same keys, different sequence

tblout key: target name, query name. domtblout key: target name, query
name, hmm from, hmm to, ali from, ali to. Those fields are counted from
the left. The target description is the last field and may contain
spaces.

## Power

The compared lines are the stock body lines, tblout plus domtblout, of
measured genomes that passed. The floor is 50,000. Below the floor the
result is INCONCLUSIVE, not a failure. A byte match below the floor is
not a pass of the claim.

Two stresses are reported beside that, and neither one is the pass rule:

- If no stock domtblout query has more than 20 domain rows, the
  multi-domain stress was not exercised.
- If the file-wide maximum FASTA name length is at most 20, the
  query-name width was at the floor.

## Residue budget

The shipped check is not retuned. `residue_cap_binds` is true when
`2 * length > total` for any record in that layer (`acts/audit.py`).
When it binds, the audit is skipped and the three random pads are
skipped. The decision line is `skipped, input below record granularity`.
The neighbor pad still runs. The in-situ check at fill still runs.

A skip is reported per genome, with which layer skipped. It is not a
pass of the skipped layer and it is not UNSAFE. On a proteome the cap
usually does not bind. On a few-record FASTA, one long protein can be
half the residues, and both layers skip. A skipped audit has miss
probability 1 for a difference the neighbor pad does not cover. When
the record count is at most 20 and the cap does not bind, the floor of
20 takes every record.

This test does not cut a protein into windows.

## Pooled N

Table 2 of the paper totals N = 96,902 compared lines with none
differing. This test does not edit the paper. After the measured run,
if there is no UNSAFE genome:

```
N_new = 96902 + L
p_up = 1 - 0.05 ** (1 / N_new)
```

`L` is the sum of tblout and domtblout body lines over measured genomes
that passed. Pilot lines are not added. Lines of one run share a pin
and a reference. They are not independent. The bound is descriptive, as
in the paper. If any genome is UNSAFE, report the failures and do not
quote `p_up` as support for the claim.

## What is reported per genome

Group, NCBI protein count, FASTA record count, body lines on each
table, decision, which of the neighbor pad, random pads, audit, and
in-situ check ran or were skipped, and the difference classes. Then
totals by group.

## CARC, not submitted

Correctness only. Non-exclusive. `--cpus-per-task=8`. `--mem=48G` when
the NCBI protein count is above 8,000, otherwise `--mem=16G`. At most
20 array tasks at once (`%20`). Time 12 hours for the larger memory and
6 hours otherwise. Scratch is node-local `/tmp` when `df -Pk /tmp` shows
at least 40 GiB free, otherwise `/scratch1/$USER/`, the same floor as
`pipeline/jobs/headline_carc_pilot.job`. On any crash or signal, write
the JSON with the exception text and `outcome` FAIL, then exit, as
`pipeline/scripts/headline_carc_measured.py` does. Do not touch jobs
12864756 or 13208152. Do not submit until
`squeue -j 13208152` shows no PENDING task. Before the first CARC
command, `ssh -O check discovery` once. If there is no master, stop.
No CARC command is part of this commit.

## Provenance

One JSON per run under `pipeline/results/diverse_genomes/`, with git
head, the seed, HMMER and TARE versions, host, argv, md5 of each input,
and one record per genome as above. The draw file is not that run.

## Not claimed

No speedup. No new method. No statement that a query name longer than
20 characters was found. The prefix maxima above are not file-wide, and
they are not hmmscan output.

## Addendum 2026-10-18

This is the one rule change the pilot is allowed. The pass rule, the
commands, the seeds, and the draw are unchanged.

The first archaeon attempt (job `13224419_0`, 16G) put scratch on
node-local `/tmp`. That mount is tmpfs and is charged to the job
cgroup. Both pressed Pfam releases lived there. The fill was
OOM-killed (`oom_kill`, return code -9) after 5153 s. The record is
`pipeline/results/diverse_genomes/pilot_oom_16g_tmpfs.json`. The same
genome on `/scratch1` at 16G finished: the stock pair matched, the
update was `SHIP` and byte-identical, and the injected drop was
refused. Scratch for every task in this test is `/scratch1/$USER/`,
including when `/tmp` has 40 GiB free. The 40 GiB floor is checked on
that directory.

The MAG and the fungus had already passed on `/tmp` (16G and 48G).
They are scored. They are not rerun.

HMMER 3.4 `hmmpress` rejects a gzipped HMM. Each task gunzips the
locked file into scratch and presses the plain text. The recorded md5
is still the gzip. Pressed model counts remain 27,481 and 30,134.

No second change. At the archaeon rate, 1606 s for 4,332 records, one
stock scan of the human FASTA (136,807 records) is about 14 hours.
The 12 hour limit stays. If that genome does not finish, it is
INCONCLUSIVE.
