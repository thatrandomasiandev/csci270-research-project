# BLAST+ pin exactness pilot

Written before the pilot runs. The diagnosis that motivates it is
`results/blast_diagnosis/rootcause.md` (job `13223561`, git
`10c3c81acf67eca1d427ea9afc04cec9d170b646`): `-dbsize` set to the whole
reference's residue count makes both halves of Swiss-Prot 2026_03
reproduce the unpinned `blastp` table on the locked 20-query probe.
This file tests that pin through the shipped tool, on a sample that
probe did not use. Locked text below is not edited after the run
starts. Later notes are dated addenda.

The gate is not changed. `reference_run.py` applies an explicit pin
only after the unpinned fit returns SHIP. If the unpinned fit refuses,
the tool's decision is that refusal, and this pilot records it.

## Claim under test

A declared pin `--pin '-dbsize {total_entry_length}'` makes TARE's
reference strategy emit a body identical to unpinned `blastp` 2.14.1
when the reference moves from Swiss-Prot 2026_01 to Swiss-Prot 2026_03.

## Data

- Queries: 20 records from
  `GCF_001513615.1_protein.faa.gz`, drawn by
  `sample_record_indices(n, 20, 20261141)`. This genome is not
  `GCF_002853805.1`, and `20261141` is not the B1 seed `20261006`.
- References, read only:
  `uniprot_sprot_2026_01.fasta.gz`, then
  `uniprot_sprot_2026_03.fasta.gz`.
- Binary: the CARC module `blast-plus/2.14.1`. No new install.
- Threads: 2. B1 used 4. The shared-machine rule for this session is
  2, and the pilot is a new sample, so it does not repeat B1's thread
  count. Stock versus stock is under these 2 threads.
- `OLD_FSC` unset. No `-comp_based_stats` in the argv. The pin is the
  only added option, and the tool inserts it.

The tool's own probe still uses its compiled seed `20261006` and
`PROBE_N`. On a 20-record query file that probe is the whole file, so
the seed does not draw a further subset. Disjointness comes from the
query file, not from a second draw inside the tool.

## Command

From `pipeline/`, the shipped tool, twice, same cache, same pin.
First reference 2026_01, then 2026_03.

```
python3 -m acts run
  --strategy reference
  --pin '-dbsize {total_entry_length}'
  --verify full
  --prep 'makeblastdb -in {reference} -dbtype prot -out {reference}'
  --input {queries}
  --reference {release}
  -- blastp -query {input} -db {reference} -out {output}
       -outfmt "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore"
       -max_target_seqs 100000 -evalue 1000 -num_threads 2
```

## Controls

1. Stock versus stock, before the tool. Two unpinned `blastp` runs of
   the pilot queries against 2026_03. Byte-identical files, or the
   pilot stops. A mismatch is a determinism failure, not a pin result.
2. Power. The stock table must contain at least 1,000 data rows. Fewer
   is INCONCLUSIVE. The tool and the drop are not run.
3. Positive, through the tool. On each release the decision is read
   from `decision.txt`. SHIP is a pass only if `--verify full` did not
   return `REFUSE_MATCH`. The rendered table's line multiset is also
   compared with the unpinned stock table of that release.
4. Positive, the comparison the pin check makes, run beside the tool
   because the gate may refuse before it. Subjects that appear in the
   2026_03 stock table, searched with `-dbsize` equal to
   `pin_values` of the full 2026_03 reference. The line multiset must
   equal the stock table: zero missing, zero extra.
5. Negative. Drop 5 percent of those subject ids,
   `k = max(1, round(0.05 * n))`, drawn by `random.Random(20261142)`.
   Search the remainder with the same `-dbsize`. The body must differ
   from stock, and the difference class must include missing rows.
   A byte-identical negative is a failed control.

The drop is outside the CLI. The shipped tool has no drop switch. The
same shape is the injected control in the HMMER exactness pilot.

## Difference classes

`compare_row_sets` in `scripts/blast_hsp_diagnosis.py`: missing, extra,
`different_hsp`, `same_interval_different_score`, `value_only`. Order
is not identity for that comparison. The tool's own body check is
order-sensitive; a SHIP from the tool already passed that check.

## Stop

The script does not edit `acts/`. It does not resubmit if stock versus
stock fails or the row floor is missed. One pilot. No redesign inside
this file.

## Addendum 2026-10-18, after job 13223656

The run is `results/blast_diagnosis/pin_pilot.json`, git
`f2f1f189e937655a4eb419c6c1af4a06e9d8e497`, host `a03-19`. The 20 query
ids are disjoint from the B1 twenty. Swiss-Prot 2026_03 has the same
MD5 as the diagnosis file (`bc9d398533e6df582b563c6c03093bd0`),
575,748 entries, 209,017,843 residues.

Stock versus stock is byte-identical: 15,498 lines, MD5
`543e49c6748995b5bf04d47546829d29`. The row floor is met.

The shipped tool returns REFUSE on 2026_01 and on 2026_03, both with
`duplicate rows have no row-index column` (`reference_fit.py`,
`index_candidates`). The pin is not applied. The gate was not changed.

Beside the tool, the pin does what the half probe did. Searching the
14,955 subjects that appear in the stock table, with `-dbsize
209017843`, returns the same 15,498 lines: zero missing, zero extra.
Dropping 748 of those subjects (seed 20261142, 5 percent) returns
14,718 lines. The 780 absent lines are missing, and there are no extra
lines. 14,718 + 780 = 15,498.

Outcome recorded by the script: `PIN_EXACT_GATE_DID_NOT_SHIP`.
