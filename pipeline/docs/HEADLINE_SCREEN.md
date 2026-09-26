# Headline screen (pre-registered) — 2026-09-25

Written **before** any headline-screen timing run. Do not edit the locked
sections after seeing `results/headline_screen.json`.

This is the CARC screen for the top three from `docs/HEADLINE_CANDIDATES.md`.
It measures stock `t = a + b·n` in the tool’s **best** mode, then applies
the corrected ceiling. No ACTS cache is built. No speedup is claimed.
A tool that fails does not get a wrapper.

Survey: `docs/HEADLINE_CANDIDATES.md`. Predecessor: `docs/TOOL_SCREEN.md`
(commit `c51ed61`) and its 2026-09-25 erratum.

---

## Advance rule (locked — erratum)

For miss fraction `m` (records still sent to the tool on the later run):

```
ceiling(m) = (a + b·N) / (a + b·m·N + w)
saved(m)   = (a + b·N) − (a + b·m·N + w)
```

- `a`, `b` from OLS on the per-size **mean** wall times (same estimator as
  `snpeff_timing_fit.json`).
- `w` is wrapper overhead, **measured**, not omitted (ruff failure mode).
- `m` is the **measured** exact-record miss fraction on the locked later
  input, not a hoped-for 0.2.

**A tool advances only if all of these hold:**

1. `a > 0` and `b > 0` (linear model did not fail).
2. `ceiling(m) ≥ 3.0`.
3. `saved(m) ≥ 60` seconds.

Wall time is the rule. User+sys CPU is logged, not the rule.

If `m ≥ 1/3`, `ceiling(m)` cannot reach 3 even at `a = w = 0`. Report that
as `REFUSE_M` and stop; do not loosen the gate.

Baseline is the tool’s **best** documented mode (built-in lookup/cache
**on** if it has one). Do not pass `--disable-precalc`, `--no-cache`, or
an equivalent strawman.

---

## Design (all tools that run)

- **Machine:** one exclusive CARC `main` node, same account/partition style
  as SnpEff job 12345442 / STAR 12159614. Record `hostname`, `lscpu` model,
  `nproc`, `uptime` before every timed run.
- **Random subsets, not prefixes.** One subset per `n`, reused for the 3
  runs at that size. Seed **20260926**.
- 3 runs each. Outputs under `/tmp/acts_headline_screen/` (not the repo,
  not Drive).
- `resource.getrusage(RUSAGE_CHILDREN)` user+sys CPU per run, alongside
  `perf_counter` wall.
- One thread / `--fork 1` / `--cpu 1` **unless** the tool’s own best mode
  documents a higher default on a dedicated node. If so, lock `--cpu` to
  `nproc` and write that number into the JSON. Do not mix widths across
  sizes.
- **`w`:** same input at full `N`, tool binary replaced by a no-op that
  writes an empty-but-valid output of the same format (`true` + empty TSV
  header, or `cat` of a pre-built empty VCF header). 3 runs. `w` = mean
  wall. This is wrapper + I/O, not the tool.

Sizes, omitting any `n > N`:

| Tool | Sizes |
|------|-------|
| HMMER, ESM-2 | `{1, 50, 200, 800, N}` |
| VEP | `{1, 1000, 5000, 20000, N}` |

---

## Recurrence inputs (locked)

### Proteins (HMMER + ESM-2)

RefSeq `*_protein.faa.gz` (already-translated; no Prodigal):

| Role | Accession | Assembly |
|------|-----------|----------|
| prev A | [GCF_000005845.2](https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000005845.2/) | *E. coli* K-12 MG1655 ASM584v2 |
| prev B | [GCF_000010245.1](https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000010245.1/) | *E. coli* K-12 W3110 ASM1024v1 |
| later  | [GCF_000750555.1](https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000750555.1/) | *E. coli* K-12 BW25113 ASM75055v1 |

FTP pattern (NCBI datasets / RefSeq):

```
https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/005/845/GCF_000005845.2_ASM584v2/GCF_000005845.2_ASM584v2_protein.faa.gz
https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/010/245/GCF_000010245.1_ASM1024v1/GCF_000010245.1_ASM1024v1_protein.faa.gz
https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/750/555/GCF_000750555.1_ASM75055v1/GCF_000750555.1_ASM75055v1_protein.faa.gz
```

Each file is a few MB. **No Josh approval** (under 1 GB).

Record key = MD5 of the amino-acid sequence (uppercase, no whitespace),
same rule InterProScan/Bakta use. `m` = fraction of later (BW25113)
sequences whose MD5 is **not** in A ∪ B.

Optional diagnostic (not the gate): MG1655 vs
[GCF_000008865.2](https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000008865.2/)
O157:H7 Sakai. Studier B vs K-12 says this class sits near `m ≈ 0.5`
and **cannot** pass 3×.

### Variants (VEP)

Same 1000G release already used for SnpEff:

```
https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000_genomes_project/release/20190312_biallelic_SNV_and_INDEL/
ALL.chr{CHR}.shapeit2_integrated_snvindels_v2a_27022019.GRCh38.phased.vcf.gz
```

Samples HG00096, HG00097, HG00099. `bcftools view -s SAMPLE -c1` per
chromosome, then concatenate bodies in chromosome order. Key =
`CHROM POS REF ALT` (full ALT), as in `VEP_PROTOCOL.md`.
`m` = HG00099 sites not in 96 ∪ 97.

| Bundle | Chromosomes | Compressed size (FTP listing 2019-03-12) | Approval |
|--------|-------------|------------------------------------------|----------|
| Already on disk | 22 | 177 M | none |
| Screen (needed for `b·N`) | **16–22** | 177+179+293+294+361+351+398 M ≈ **2.05 G** | **Josh — total > 1 GB** |
| Optional WGS-scale | +1, +2 | 1.0 G each | **Josh — per file ≥ 1 GB** |

Do **not** run the advance rule on chr22 alone and call that the
headline. Chr22-only may be logged as a diagnostic; N is the
16–22 concat.

---

## Candidates

### 1. HMMER3 vs Pfam-A — run after small fetch

**Best mode (locked):**

```
hmmsearch --cpu "$NPROC" --noali --tblout OUT.tbl Pfam-A.hmm INPUT.faa
```

`hmmsearch` (HMMs as queries, sequences as the target) is the documented
faster orientation when Pfam is memory-resident
([Eddy 2011 numerology](http://cryptogenomicon.org/hmmscan-vs-hmmsearch-speed-the-numerology.html);
[pyhmmer tips](https://pyhmmer.readthedocs.io/en/stable/examples/performance_tips.html)).
Do not use `hmmscan` as the timed baseline.

N = number of BW25113 protein records after gzip decompress.

**Install (no >1 GB file):**

```
# CARC example — adjust module names when the job is written
module load gcc hmmer   # or conda: conda create -n acts-hmmer hmmer=3.4
cd $SCRATCH/acts_headline
curl -L -o Pfam-A.hmm.gz https://ftp.ebi.ac.uk/pub/databases/Pfam/current_release/Pfam-A.hmm.gz
# 399 MB — under 1 GB; no approval
gunzip -k Pfam-A.hmm.gz
hmmpress Pfam-A.hmm     # required by hmmscan; harmless for hmmsearch
# fetch the three .faa.gz listed above
```

Record Pfam version from `Pfam.version.gz` / the HMM header.

**Expected (not a claim):** minutes per full proteome; `b·N ≫ a` if the
HMM library is loaded once; `m` from the K-12 triple, hoped `< 1/3`.

### 2. VEP `--offline --everything --fork 1` — Josh-gated

**Best mode (locked):**

```
vep --offline --cache --everything --vcf --no_stats --fork 1 \
    --force_overwrite --fasta "$FASTA" -i INPUT.vcf -o OUT.vcf
```

`--everything` is the heavy per-variant switch named in the survey
(includes `--hgvs`). `--cache` **on** is the fair baseline (reference
data, not our memo). `--fork 1` matches VEP_PROTOCOL. No plugins
until independence SHIPs (same forbidden list: haplo, `--check_svs`).

**Install — all of these need Josh (each > 1 GB or the VCF bundle is):**

```
# VEP + cache (INSTALL.pl). GRCh38 cache tarball ~14–20 GB.
# https://ftp.ensembl.org/pub/current_variation/indexed_vep_cache/
#   homo_sapiens_vep_*_GRCh38.tar.gz
#
# FASTA for --hgvs / --everything
# https://ftp.ensembl.org/pub/current_fasta/homo_sapiens/dna/
#   Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz   (~1 GB compressed)
#
# VCFs chr16–chr22 from the 20190312 URL above (~2.05 GB). Optional chr1/chr2.
```

Do not fetch these from this protocol without approval.

**Expected (not a claim):** McLaren 1,200 v/s without `--everything`;
`--hgvs` +50–80% ([vep_other](https://www.ensembl.org/info/docs/tools/vep/script/vep_other.html)).
At N ≈ 4–6× chr22, wall should be **minutes**, not 13 s. `m` reused from
CEU 0.213 if the multi-chrom `-c1` table is not ready; **prefer
re-measuring** `m` on the concat (same script as
`scripts/run_c1_overlap.py`).

### 3. ESM-2 `esm-extract` — Josh-gated

**Best mode (locked):**

```
# GPU if the exclusive node has CUDA; else --nogpu (record which).
esm-extract esm2_t33_650M_UR50D INPUT.faa OUTDIR \
    --repr_layers 33 --include mean
```

Same FASTA subsets as HMMER. After the timed run, write a two-column TSV
(`id`, `md5`) plus the `.pt` files so the later generic FASTA path has a
line-oriented artifact. Timing is the stock CLI, not the TSV rewrite.

**Install — Josh (weights ~2.5 GB):**

```
# pip/conda pytorch + fair-esm
# first esm-extract downloads esm2_t33_650M_UR50D  (~2.5 GB)
# CARC GPU partition if available; otherwise exclusive CPU (slow, still valid)
```

**Expected (not a claim):** GPU minutes / CPU hours for N ≈ 4k; `a` =
weight load. Same `m` as HMMER.

---

## Approval checklist (do not fetch until Josh says so)

| Item | Size | Needed for | Ask Josh? |
|------|------|------------|-----------|
| Pfam-A.hmm.gz | 399 MB | HMMER | no |
| Three RefSeq `protein.faa.gz` | few MB each | HMMER, ESM-2 | no |
| HMMER / Python / bcftools | small | all | no |
| 1000G chr16–chr22 VCFs | **~2.05 GB** | VEP N | **yes** |
| 1000G chr1, chr2 | **1.0 GB each** | optional VEP WGS | **yes** |
| VEP GRCh38 cache tarball | **~14–20 GB** | VEP | **yes** |
| GRCh38 primary FASTA | **~1 GB** | VEP `--everything` | **yes** |
| ESM-2 650M weights | **~2.5 GB** | ESM-2 | **yes** |
| InterProScan / eggNOG / Bakta / dbNSFP / NR | 6–50+ GB | rejected tools | do not ask |

HMMER can run the moment the 399 MB Pfam file and the three FASTAs are
pulled. VEP and ESM-2 wait on approval.

---

## What this is not

- Not a cached-path MATCH and not a speedup claim.
- Not permission to download anything in the approval table.
- Not a rewrite of `results/snpeff_timing_fit.json` or `results/tool_screen.json`.
- Not STAR. Not ruff. Not InterProScan `--disable-precalc`.
- Not a second tool wrapper (`snpeff_ann.py` stays out of this screen).

```
# later session, after approval / small fetches
python3 scripts/run_headline_screen.py   # does not exist yet; do not write it here
```

Report: `results/headline_screen.json`.

---

## Erratum 2026-09-26 — HMMER E-values are not per-record

Written **before** any headline-screen timing run. Do not edit the 2026-09-25
locked text above. This addendum replaces the single locked `hmmsearch`
command; VEP and ESM-2 are unchanged (still Josh-gated).

`hmmsearch` output is **not** a function of one sequence. Sequence E-values
scale with `-Z` (number of targets in the file); domain E-values scale with
`--domZ`. A cache filled on MG1655∪W3110 and replayed on BW25113 would fail
MATCH whenever the proteome sizes differ, even if every amino-acid MD5
hits. The 2026-09-25 “do not use `hmmscan`” line is therefore wrong for a
record-memo headline.

Screen **both** modes below. Both must pass the 2026-09-26 subset-invariance
probe (INFERENCE_PROTOCOL.md addendum (b2)) **before any cache is built**.
The paper uses the first mode that both (1) passes (b2) and (2) advances
the ceiling rule; if both do, the paper uses (ii), which is the documented
faster orientation once Z is held fixed.

**(i) `hmmscan` — Z is the number of models (fixed for a given Pfam-A):**

```
hmmscan --cpu "$NPROC" --cut_ga --noali --tblout OUT.tbl Pfam-A.hmm INPUT.faa
```

**(ii) `hmmsearch` with `-Z` and `--domZ` fixed (best-mode baseline):**

```
hmmsearch --cpu "$NPROC" --noali -Z 1000000 --domZ 1000000 \
    --tblout OUT.tbl Pfam-A.hmm INPUT.faa
```

`Z_FIXED = 1000000` and `DOMZ_FIXED = 1000000` are the declared constants.
They do not change across subset sizes or proteomes. Implicit `-Z` (file
size) is not a legal baseline.

Sizes, seed, exclusive node, user+sys CPU, measured `w`, and the
`ceiling(m)` / `saved(m) ≥ 60 s` gate are unchanged. `m` is the K-12
value in `results/kprot_overlap.json` (MG1655 ∪ W3110 → BW25113).

No ACTS cache is built in this screen. A mode that fails (b2) is reported
and does not advance, even if the timing ceiling would have passed.
