# Protein recurrence curves (pre-registered) — 2026-09-26

Written **before** any assembly is selected or any `protein.faa.gz` is
downloaded. Do not edit the locked sections after seeing
`results/recurrence_curves.json`.

K-12 MG1655 ∪ W3110 → BW25113 gave `m = 0.0019`
(`results/kprot_overlap.json`). Those three are lab derivatives of one
strain. This protocol measures the same miss fraction on collections people
actually annotate.

Local MD5 hashing only. No CARC. No HMMER / tool runs. No speedup claims.

```
python3 scripts/run_recurrence_curves.py
```

---

## Claim (what this measures)

On a realistic collection of bacterial proteomes, how many genomes of
exact-sequence memory does a later proteome need before the miss fraction
`m` falls below the HMMER ceiling gate (`m < 1/3`)?

This is **not** a pangenome paper and **not** a speedup claim. It is the
recurrence input the headline screen already said it needed
(`docs/HEADLINE_SCREEN.md`).

---

## Key (locked)

Same object as `scripts/run_kprot_overlap.py`, plus the stop-codon strip
the task required:

1. Read RefSeq `*_protein.faa.gz`. Headers are ignored.
2. Concatenate sequence lines. Strip all whitespace.
3. Uppercase.
4. Remove every `*` (terminal or internal stop).
5. Drop empty sequences.
6. Key = MD5 hex digest of the resulting ASCII bytes.

A proteome is the **set** of distinct keys (duplicates inside one FASTA
do not count twice). `m` is computed on sets, not on record multiplicity.

`run_kprot_overlap.py` did not strip `*`. Expected difference is
negligible; do not rewrite `kprot_overlap.json`.

---

## Established knowledge (do not reinvent)

Pangenome papers already say *E. coli* is open and *S. aureus* is still
far from a single proteome. Those numbers are **homology clusters**, not
exact MD5 keys. Exact identity is stricter, so `m` here will be **at least
as large** as a homology miss, usually larger.

| Work | Rating | What it already established |
|------|--------|-----------------------------|
| Tettelin *et al.* 2005 *PNAS* 102:13950. [doi:10.1073/pnas.0506758102](https://doi.org/10.1073/pnas.0506758102) | trust | Open pan-genome: new genomes keep adding genes. Core ≈ 80% of one GBS genome **by 50% identity / 50% length**, not MD5. |
| Touchon *et al.* 2009 *PLoS Genet* 5:e1000344. [doi:10.1371/journal.pgen.1000344](https://doi.org/10.1371/journal.pgen.1000344) | trust | 20 *E. coli* genomes: core 1,976 / average 4,721 (~42% of a genome is ubiquitous). |
| Lukjancenko, Wassenaar, Ussery 2010 *Microb Ecol* 60:708. [doi:10.1007/s00248-010-9717-3](https://doi.org/10.1007/s00248-010-9717-3) | trust | 61 *E. coli*+*Shigella*: core 993 families (~20% of a typical genome). |
| Studier *et al.* 2009 *J Mol Biol* 394:653. [doi:10.1016/j.jmb.2009.09.008](https://doi.org/10.1016/j.jmb.2009.09.008) | trust | **Exact** AA identity, but only B / K-12 lab pair: >½ of 3,793 basic-genome proteins identical. This is the cherry-pick `kprot_overlap` already used. |
| Eppinger *et al.* 2011 *PNAS* 108:20142. [doi:10.1073/pnas.1107176108](https://doi.org/10.1073/pnas.1107176108) | trust | 25-genome O157:H7 outbreak panel; lineage described as genetically homogenous, comparable to *Y. pestis*. |
| Bosi *et al.* 2016 *PNAS* 113:E3801. [doi:10.1073/pnas.1523199113](https://doi.org/10.1073/pnas.1523199113) | trust | 64 *S. aureus*: core 1,441 / pan 7,457 (homology). |

**Delta of this measurement:** exact MD5 miss curves `m(k)` on RefSeq
complete proteomes, read against the HMMER `ceiling ≥ 3 ⇒ m < 1/3` gate.
We do not invent a new pangenome estimator.

**Non-claims:** no 3×, no HMMER timing, no “ACTS is novel versus Bakta /
InterProScan public lookups,” no claim that O157:H7 is an ST in the MLST
sense (it is a named lineage / serotype).

---

## NCBI summary (locked source)

Download once, cache under `data/recurrence/` (gitignored):

```
https://ftp.ncbi.nlm.nih.gov/genomes/refseq/bacteria/Escherichia_coli/assembly_summary.txt
https://ftp.ncbi.nlm.nih.gov/genomes/refseq/bacteria/Staphylococcus_aureus/assembly_summary.txt
```

Column indices are 1-based as in NCBI’s
[assembly_summary README](https://ftp.ncbi.nlm.nih.gov/genomes/README_assembly_summary.txt):

| Col | Field |
|-----|--------|
| 1 | `assembly_accession` |
| 8 | `organism_name` |
| 9 | `infraspecific_name` (`strain=…`) |
| 10 | `isolate` |
| 11 | `version_status` |
| 12 | `assembly_level` |
| 14 | `genome_rep` |
| 16 | `asm_name` |
| 20 | `ftp_path` |

**Eligible row** (used by A, C, and B resolution):

- `assembly_accession` starts with `GCF_`
- `version_status` = `latest`
- `assembly_level` = `Complete Genome`
- `genome_rep` = `Full`
- `ftp_path` is not `na` / empty

**Strain name** of a row, in order: `infraspecific_name` with a leading
`strain=` stripped; else `isolate`; else empty. Normalize by uppercasing
and collapsing whitespace. An empty strain does **not** collapse with
other empties — those rows stay unique under their accession.

**Protein URL** from `ftp_path`:

```
{ftp_path}/{basename(ftp_path)}_protein.faa.gz
```

Rewrite `ftp://` → `https://`. Download that file only.

**Size cap.** Before downloading proteomes, sum HTTP `Content-Length` (or
treat unknown as 2 MiB). If the planned total exceeds 1 GiB, **stop and
ask Josh**. Do not download past the cap.

---

## Collection A — diverse *E. coli* (locked)

Target `K = 100`.

1. Eligible *E. coli* rows from the *E. coli* summary.
2. Drop a row if `organism_name`, strain, or isolate matches
   `(?i)(k-?12|mg1655|w3110|bw25113)` — the K-12 lab cluster, nothing else.
3. One per non-empty strain name: among rows that share a normalized
   strain, keep the one with the lexicographically smallest
   `assembly_accession`. Empty-strain rows are all kept.
4. Sort the unique-strain list by `assembly_accession`.
5. If `n < 100`, take all and record `K = n`. Else draw 100 **without
   replacement** with `random.Random(20260926).sample(list, 100)`, then
   re-sort the sample by accession for a stable on-disk order.

That is the only *E. coli* diversity draw. Do not prefer pathogens, do
not drop O157 after the fact, do not add K-12 back.

---

## Collection B — clonal outbreak / surveillance (locked)

**Paper.** Eppinger M, Mammel MK, Leclerc JE, Ravel J, Cebula TA.
Genomic anatomy of *Escherichia coli* O157:H7 outbreaks.
*Proc Natl Acad Sci USA* 108:20142–20147 (2011).
[doi:10.1073/pnas.1107176108](https://doi.org/10.1073/pnas.1107176108).
PMC [PMC3250189](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3250189/).

**Why this paper.** Single named lineage (O157:H7), not a species-wide
draw. 25 genomes in one comparative panel from three 2006 US food-borne
outbreaks (spinach SP, Taco Bell TB, Taco John TJ) plus lineage
references. Eppinger et al. call the lineage genetically homogenous.
That is the surveillance / outbreak object. It is **not** a hospital
single-ST set; O157:H7 is the published unit.

**Locked strain list** — Figure 1 circles 7–30 plus the EC4115
reference (25 names, this order):

```
EC4115
EC4045
EC4042
EC4113
EC4076
EC4084
EC4127
EC4191
EC4205
TW14359
EC4206
EC4196
EC4401
EC4486
EC4192
EC4009
EC508
EC869
FRIK2000
FRIK966
EC536
EDL933
Sakai
TW14588
EC4501
```

**Resolve each name** against eligible *E. coli* rows. A row matches if
the normalized strain, isolate, or `organism_name` contains the locked
name as a whole token (alphanumeric match after stripping
non-alphanumerics; `EDL933` must not eat `EDL933a` only if the remainder
is empty). If several rows match, keep smallest `assembly_accession`.
One assembly per locked name.

If a name has no Complete Genome hit, retry once at `assembly_level` =
`Chromosome` (same other filters). Still nothing → drop the name and
record it.

**Fallback B1 (only if fewer than 20 names resolve).** Still the
Eppinger lineage, not a new paper: every eligible *E. coli* row whose
`organism_name` contains `O157:H7`, one per strain as in A, sort by
accession. If more than 40, `random.Random(20260926).sample(list, 40)`
and re-sort. Record `fallback = "B1_O157H7_complete"`. If that set is
still `< 20`, stop; do not invent a third collection.

---

## Collection C — different species (locked)

*Staphylococcus aureus*, not *Klebsiella pneumoniae*. Same machinery as
A. Reason written down now: Bosi et al. 2016 already treat *S. aureus* as
the standard non-*E. coli* hospital-pathogen pangenome; we need exact
MD5 `m(k)` on that species, not another *E. coli* clone.

Target `K = 50`.

1. Eligible rows from the *S. aureus* summary.
2. No K-12 filter (does not apply).
3. One per strain name, same collapse as A.
4. Sort by accession. If `n < 50`, take all. Else
   `random.Random(20260926).sample(list, 50)`, re-sort.

---

## Metric (locked)

For each collection of size `K`:

- 20 random orderings. Ordering `i` (0-based) is
  `random.Random(20260926 + i).sample(genomes, K)` — a full permutation.
- For `k = 1 … K-1`:
  - `U(k)` = union of distinct keys in genomes `1 … k` of that ordering.
  - `P` = distinct keys of genome `k+1`.
  - `m(k) = 1 − |P ∩ U(k)| / |P|`  (`m = 1` if `P` is empty; flag it).
- At each `k`, report the **median**, **10th percentile**, and **90th
  percentile** of the 20 `m(k)` values (`numpy.percentile` with the
  default linear method, or the Python 3 equivalent).

This is the incremental miss the HMMER wrapper would still send to
`hmmsearch`. It is **not** Tettelin’s new-gene count (that counts
families new to the union, not the miss rate on the next genome).

---

## Pre-registered reading (locked)

HMMER gate from `docs/HEADLINE_SCREEN.md`:

```
ceiling(m) = (a + b·N) / (a + b·m·N + w)
```

`ceiling ≥ 3` is impossible when `m ≥ 1/3`, even at `a = w = 0`.

For each collection, the **crossing `k`** is the smallest `k` such that
the median `m(k) < 1/3`. If no such `k` exists:

- **A:** diverse-species headline **fails**. Only clonal / surveillance
  workloads (B, and C if it crosses) remain eligible to talk about.
- **B:** outbreak / surveillance workloads do not clear the gate on this
  lineage either.
- **C:** *S. aureus* generality fails.

Also report median `m` at `k ∈ {1, 5, 10, 50, K-1}` (omit any `k ≥ K`).

No interpolation of a crossing between integers. No loosening to
homology. No “almost 1/3.”

---

## Outputs (locked)

| Path | Contents |
|------|----------|
| `results/recurrence_accessions.json` | Per collection: summary URL + date, seed, selection rule id, each accession, strain, organism, ftp protein URL, downloaded bytes, MD5 of the `.faa.gz`, `n_unique` keys. Dropped B names. Whether B1 fired. |
| `results/recurrence_curves.json` | Per collection: `K`, `m_median[k]`, `m_p10[k]`, `m_p90[k]`, crossing `k` or `null`, snapshot values, one-sentence reading. |
| `results/figures/12_recurrence_A_ecoli.png` | Median `m(k)` + 10–90% band; dashed `y = 1/3`. |
| `results/figures/13_recurrence_B_o157.png` | Same. |
| `results/figures/14_recurrence_C_saureus.png` | Same. |

FASTAs stay under `data/recurrence/` (gitignored).

---

## Addendum 2026-09-26 — `stays_below_k`

Written after seeing collection C: median `m` first dips below 1/3 at
`k = 5` and rises back to 0.38 at `k = 10`. The locked **crossing `k`**
is still the first dip. The **reading** now uses `stays_below_k` =
smallest `k` after which every later median `m` stays `< 1/3` (or `null`
if the last point is still ≥ 1/3). Report both fields. Do not quote the
first dip as the gate.
