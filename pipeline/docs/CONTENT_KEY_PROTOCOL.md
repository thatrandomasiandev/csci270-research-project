# Content-key kill test (pre-registered 2026-10-03)

Written **before** any byte-key or GenBank number is computed. Locked text
below is never edited; later changes are dated addenda.

## Question

Caruca (Lamprou et al., arXiv 2510.14279) mines splittability for opaque
commands, and INCR (OSDI 2026) reuses chunks. Combined, they give
byte-level record reuse for unmodified commands. ACTS's candidate
differentiator is the **inferred content key**: the part of a record the
tool's output depends on, with copied fields spliced back in from the new
input. That only matters if real records recur with **different bytes**.

## Metric

For a later input X and the set S of records seen in earlier inputs:
`recall_in_new = |{distinct keys of X that occur in S}| / |{distinct keys of X}|`,
computed under two keys:

- **byte key**: the whole record (VCF body line; FASTA header line plus
  sequence).
- **inferred key**: the key the committed contracts use (VCF
  `variant_key` = CHROM POS REF ALT, from `results/inference_checks.json`
  SnpEff contract; FASTA = MD5 of the uppercase sequence, `*` stripped,
  `acts.fasta.seq_key`).

Ratio reported: byte-key recall ÷ inferred-key recall.

## Workloads (locked)

1. **VCF**: HG00096 ∪ HG00097 → HG00099, the existing 1000G chr22
   `bcftools view -s S -c1` extracts (`data/vep_chr22/*.c1.vcf.gz`).
2. **Proteins, GenBank**: the GenBank (GCA_) assemblies paired with the
   first 10 genomes of collection A in its first ordering (seed 20260926,
   `results/recurrence_curves.json`), via `gbrs_paired_asm` in
   `data/recurrence/assembly_summary_ecoli.txt`. GenBank protein IDs are
   assigned per submission, so identical sequences usually carry different
   headers. Genomes without a paired GCA, or without a GenBank
   protein.faa, are skipped in order and listed. Recall for genome k+1
   against genomes 1..k, k = 1..9.
3. **Proteins, RefSeq (control)**: the same 10 RefSeq (GCF_) proteomes
   already on disk. RefSeq shares `WP_` accessions for identical
   sequences, so it is the case expected to hide the effect; descriptions
   still change between annotation releases (`results/savings_failed_20260928/`).

## Kill rule (locked)

If byte-key recall ≥ 90% of inferred-key recall on **both** the VCF
workload and the GenBank protein workload (at k = 9), the content-key
differentiator fails, and the paper does not claim it.

## Ship-controls

The generic path's committed results must still hold: SnpEff MATCH on
52,638 records with 41,447 hits / 11,191 misses and fill-tags 23,072 hits
(`results/inference_checks.json`). This test computes hashes only; it does
not rerun tools.

## Not in scope

No tool timing, no CARC. Downloads: GenBank protein FASTAs only (a few MB
each); stop above 1 GB.
