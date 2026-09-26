# Headline-tool survey — record memoization (2026-09-25)

Research and pre-registration only. No installs, no timing runs, no downloads
in this session. Written so a later CARC screen can pick a tool where
`b·N` dominates startup, records recur across runs, there is no user-result
cache (or ours clearly beats it), absolute time saved is minutes-scale, and
output is per-record (VCF / FASTA / TSV).

SnpEff 5.4c is live but capped (~1.17× exclusive CARC; ~1.3× even at 100%
hits). ruff was a formula-pass on a 0.7 s strawman (`--no-cache`). The
question is which *unmodified* CLI is a paper instance.

**Gap we own:** reuse of the *user’s* prior per-record results across runs.
A public precomputed lookup (UniParc, UniRef100, VEP transcript cache,
dbNSFP scores) is not that gap.

**Ceiling used below** (TOOL_SCREEN.md erratum):

```
ceiling(m) = (a + b·N) / (a + b·m·N + w)
```

`m` is the miss fraction on a later run. Advance in the screen only if
`ceiling(m) ≥ 3.0` *and* absolute time saved `≥ 60 s`. If `a → 0`, the
ratio cannot beat `1/m`, so **`m` must be `< 1/3`** (hit rate `> 2/3`).
Distant-strain pairwise identity around 50% cannot pass the 3× gate no
matter how large `b·N` is.

---

## Recurrence priors (cited)

| Setting | Number | What it is | Rating |
|---------|--------|------------|--------|
| 1000G CEU chr22 `-c1`, 96∪97 → 99 | **m = 0.213** (recall 0.787) | Carried ALTs only; `pipeline/results/vep_chr22_overlap.json` | measured here |
| *E. coli* B vs K-12 basic genomes | **> ½ of 3,793 proteins identical** | Studier *et al.*, *J. Mol. Biol.* 2009, PMID [19765592](https://pubmed.ncbi.nlm.nih.gov/19765592/) | **trust** — pairwise exact AA, two lab lineages |
| *E. coli* all-strain intersection | 247 proteins identical across *all* strains in that build | Sun *et al.*, *J. Proteome Res.* 2026 / bioRxiv [10.1101/2025.09.11.675345](https://doi.org/10.1101/2025.09.11.675345) | **provisional** — lower bound; not pairwise |
| *E. coli* 61-genome “core” | ~2,200 families at **50% AA / 50% length**, not 100% identity | Lukjancenko *et al.*, *Microb. Ecol.* 2010, [10.1007/s00248-010-9717-3](https://doi.org/10.1007/s00248-010-9717-3) | **trust** for homology; **do not use as exact-identity m** |
| Bakta vs public UniParc/UniRef100 | “up to 99% of CDS” hash-identified | Schwengers *et al.*, *Microb. Genom.* 2021, [PMC8743544](https://pmc.ncbi.nlm.nih.gov/articles/PMC8743544/) | **trust** — public lookup hit rate, *not* user–user recall |

Pangenome papers almost always cluster at 50–95% AA identity. Exact-sequence
`m` for two K-12 derivatives is **not** in those tables; Studier’s B vs K-12
“more than half identical” is the closest trusted pairwise number. Two K-12
proteomes (MG1655 / W3110 / BW25113) should sit well above 2/3 identical;
the screen **measures** MD5 identity rather than assuming it.

---

## Candidate table

Every cell has a citation or is marked **estimate**. “Built-in cache?” means
a lookup that returns *results* for a sequence/variant the tool has seen.
Reference databases (HMM libraries, DIAMOND `.dmnd`, VEP transcript cache)
are **not** user-result caches.

| Tool | Built-in cache? | a / b estimate | Recurrence | Per-record output? | Install / CARC | Verdict |
|------|-----------------|----------------|------------|--------------------|----------------|---------|
| **HMMER3 `hmmscan`/`hmmsearch` vs Pfam-A** | **No** user-result cache. Pfam is a model library, not a memo of prior queries ([HMMER User Guide](http://eddylab.org/software/hmmer/Userguide.pdf); Eddy, *PLoS Comput. Biol.* 2011, [10.1371/journal.pcbi.1002277](https://doi.org/10.1371/journal.pcbi.1002277)). | **a** = pressed-HMM load. Eddy (*cryptogenomicon*, 2011) [hmmscan vs hmmsearch](http://cryptogenomicon.org/hmmscan-vs-hmmsearch-speed-the-numerology.html): a ~30 aa ORF vs Pfam is ~7 ms CPU but naive `hmmscan` can reread ~1 GB from disk (~3 s) per query if the library is not resident. **b** ≈ 0.5–1 s/protein for ~11k models on one 2.4 GHz core (Finn *et al.*, *NAR* 2010, [PMC2808889](https://pmc.ncbi.nlm.nih.gov/articles/PMC2808889/) — dated model count). pyHMMER: **~2 h / 1e6 proteins / 32 threads** with Pfam in RAM ([pyhmmer performance tips](https://pyhmmer.readthedocs.io/en/stable/examples/performance_tips.html)); micropan docs: “usually several minutes per genome” ([hmmerScan](https://search.r-project.org/CRAN/refmans/micropan/html/hmmerScan.html)). **Estimate** for one *E. coli* proteome (~4k seq), `--cpu` = node width, `hmmsearch` best mode: **minutes, not sub-seconds**. `b·N ≫ a` if the HMM library is loaded once. | Exact AA identity. Studier B vs K-12: >½ identical (**m ≲ 0.5**, fails 3×). Two K-12: expect **m ≪ 1/3** (unmeasured; screen will hash). | **Yes.** `--tblout` / `--domtblout` is one TSV line (or several) per query–model hit; lines group by query name. Fits FASTA inference. | HMMER binary: small. [Pfam-A.hmm.gz](https://ftp.ebi.ac.uk/pub/databases/Pfam/current_release/) **399 MB** (listing 2026-01-22). `hmmpress` on node. CARC CPU exclusive: yes. | **RANK 1 — screen.** No user memo. Per-protein work is real. Install under 1 GB. |
| **VEP `--offline --everything --fork 1`** | Official `--cache` is a **reference-data** store (transcripts, known variants), not a memo of prior user VCFs ([VEP cache docs](https://www.ensembl.org/info/docs/tools/vep/script/vep_cache.html); locked in `WHAT_WE_ARE_BUILDING.md`). Adding sample 1,001 still annotates every site in that VCF. Plugin-local hashes are not a persistent user VCF cache. | McLaren *et al.*, *Genome Biol.* 2016, [10.1186/s13059-016-0974-4](https://doi.org/10.1186/s13059-016-0974-4): NA12878 **4,474,140** variants in **62 min 9 s** (1,200 v/s) on a quad-core; chr21 67,416 vars in **47 s**; “**negligible startup**”; typical exome (1–2×10⁵) “under 5 minutes.” Ensembl tuning page: ~**3×10⁶ vars / 30 min** if cache + fork + `--no_stats` ([vep_other](https://www.ensembl.org/info/docs/tools/vep/script/vep_other.html)). `--hgvs` (on under `--everything`) adds **~50–80%** runtime (same page). **Estimate:** WGS `--everything --fork 1` ≈ **1.5–2 h**; chr22-only (N=52,638) is SnpEff-class and may fail the 3× gate. | CEU `-c1` **m = 0.213** after two samples (measured). Same prior on more chromosomes (unmeasured; expect similar). | **Yes.** `--vcf` one body line per variant. Generic VCF path. | Software: small. GRCh38 cache **~14–20 GB** compressed ([Ensembl FTP](https://ftp.ensembl.org/pub/release-116/variation/indexed_vep_cache/); issue [1501](https://github.com/Ensembl/ensembl-vep/issues/1501) quotes the 110 tarball). `--everything` wants FASTA (**~1 GB** unpacked). Extra 1000G VCFs: chr1/chr2 = **1.0 G** each ([20190312 listing](https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000_genomes_project/release/20190312_biallelic_SNV_and_INDEL/)). CARC: yes, CPU. | **RANK 2 — screen, Josh-gated.** Intended scientific instance. Needs WGS-scale N. |
| **ESM-2 `esm-extract`** | **No** result cache in [facebookresearch/esm `extract.py`](https://github.com/facebookresearch/esm/blob/main/scripts/extract.py). `cache_folder` stores **weights**, not embeddings ([fair-esm README](https://github.com/facebookresearch/esm)). ESM Atlas is a separate precomputed set; the CLI does not query it. Third-party wrappers add resume; that is not the stock CLI. | Lin *et al.*, *Science* 2023, [10.1126/science.ade2574](https://doi.org/10.1126/science.ade2574): model family, not a CLI timing table. Community: 2,320 seqs in **97 s** on GPU at batch 16 ([esm#685](https://github.com/facebookresearch/esm/discussions/685)) → **~40 ms/seq estimate**. CPU “50–200× slower” (third-party [esm-embed](https://github.com/Aaryesh-AD/esm-embed); **weak**). **Estimate:** GPU proteome = minutes; CPU proteome = **hours**. `a` = weight load (tens of seconds). | Same exact-AA prior as HMMER. | **Yes, awkwardly.** One `.pt` per FASTA record. Mean-pool TSV is one line per query if we ask the screen to write it; stock CLI is directory-of-tensors. | `esm2_t33_650M_UR50D` weights **~2.5 GB**. Needs PyTorch. CARC **GPU partition** preferred; CPU exclusive will run but is slow. | **RANK 3 — screen, Josh-gated.** Clean “no user cache”; format and GPU are the risks. |
| InterProScan 5/6 | **Yes, public only.** MD5 → EBI Matches API / UniParc precomputed matches. Docs: “sequences already found in UniProtKB”; local MLS is a copy of that DB, **>1 TB**, not the user’s previous FASTA ([HowToRun](https://interproscan-docs.readthedocs.io/en/v5/HowToRun.html), [LocalLookup](https://interproscan-docs.readthedocs.io/en/v5/LocalLookupService.html), [v6 MLS](https://interproscan-docs.readthedocs.io/en/v6/HowToInstall.html)). GitHub [issue 131](https://github.com/ebi-pf-team/interproscan/issues/131): lookup helps iff sequences are in UniProt. User novel proteins are recomputed every run. | “Couple of minutes” per sequence locally ([HowToRun](https://interproscan-docs.readthedocs.io/en/v5/HowToRun.html)). FAQ: *E. coli* ~3,000 proteins **~1 h** on their farm. UniProt chunks: 8k seq / 16 CPU / **2 h** ([ImprovingPerformance](https://interproscan-docs.readthedocs.io/en/v5/ImprovingPerformance.html)). Jones *et al.*, *Bioinformatics* 2014, [10.1093/bioinformatics/btu031](https://doi.org/10.1093/bioinformatics/btu031): 3,990 *E. coli* proteins **32 min** (12 workers, cluster mode). Blum *et al.*, *NAR* 2021, [10.1093/nar/gkaa977](https://doi.org/10.1093/nar/gkaa977): Arabidopsis 31,819 seq **12 h** without lookup vs **0.7 h** with lookup (v5.45+). **Estimate with lookup ON (required baseline):** isolate proteomes collapse toward lookup latency (ms–s), SnpEff-class `a`. | Public hit rate high for *E. coli* (Bakta’s 99% is the same universe). User–user ∩ UniParc-miss is the only wedge — thin for isolates. | **Yes.** TSV one-or-more lines per protein ([OutputFormats](https://interproscan-docs.readthedocs.io/en/v5/OutputFormats.html)). | **6.6 GB** compressed (v5.78-109.0 [release](https://github.com/ebi-pf-team/interproscan/releases/tag/5.78-109.0)); Linux/Java 11; needs `ebi.ac.uk` or 1 TB MLS. CARC: yes, large disk + egress. | **Reject for isolate headline.** Lookup ON is the fair baseline; then *E. coli* is mostly free. Keep as a *novel-MAG* follow-up, not the screen. `--disable-precalc` is a ruff-style strawman. |
| eggNOG-mapper | **Yes, user-result cache.** `--md5` then `-m cache -c FILE` reuses prior annotations by sequence MD5 ([USAGE](https://github.com/eggnogdb/eggnog-mapper/blob/main/USAGE.md), wiki [v2.1.2–2.1.4](https://github.com/eggnogdb/eggnog-mapper/wiki/eggNOG-mapper-v2.1.2-to-v2.1.4)). `--resume` is interrupt-resume, not a second-genome memo. Prebuilt `eggnog.db.*.bin` caches are DB indexes, not query results. | Cantalapiedra *et al.*, *Mol. Biol. Evol.* 2021, [PMC8662613](https://pmc.ncbi.nlm.nih.gov/articles/PMC8662613/): minutes-scale proteome/genome plots (Fig. 2); Diamond iterate beats MMseqs at 10⁶–10⁷ queries. Issue [456](https://github.com/eggnogdb/eggnog-mapper/issues/456): 43 seq in **~1 h**, of which annotation was 35 s — **DB/Diamond setup dominates small N**. Wiki: 300–400 proteins/s for the annotation stage with `eggnog.db` in `/dev/shm`. | Same exact-AA story, but **their cache already does our job**. | **Yes.** `.emapper.annotations` TSV, one line per query. | Core data **~45 GB** ([USAGE](https://github.com/eggnogdb/eggnog-mapper/blob/main/USAGE.md)). CARC: yes, if disk is approved. | **Reject — occupied.** Screening against `-m cache` is a running-baseline later, not a headline hunt. |
| DIAMOND `blastp` | **No** persistent query-result cache. `--mp-recover` resumes an *interrupted* distributed run ([wiki](https://github.com/bbuchfink/diamond/wiki/6.-Distributed-computing)). DAA is an output format, not a memo. | Buchfink *et al.*, *Nat. Methods* 2021, [10.1038/s41592-021-01101-x](https://doi.org/10.1038/s41592-021-01101-x). Docs: designed for **>1e6** queries; small files do not amortize index build ([manual](https://github.com/bbuchfink/diamond_docs/blob/master/Documentation.MD)). Issues [185](https://github.com/bbuchfink/diamond/issues/185), [413](https://github.com/bbuchfink/diamond/issues/413): hours to load huge `.dmnd`; one-query searches lose to BLAST. Swiss-Prot-scale: seconds–minutes for one proteome (**estimate**). NR-scale: `a` is huge. | Exact-AA, same as HMMER. | **Yes.** BLAST tabular, one line per hit. | Binary small. Swiss-Prot `.dmnd` hundreds of MB. NR: **hundreds of GB**. | **Reject.** Swiss-Prot fails absolute-time; NR fails install. Small-N `a` is the documented failure mode. |
| Bakta (per-protein steps) | **Yes, public hash.** MD5+length → UPS/IPS in a SQLite of UniParc/UniRef100/RefSeq; remainder → Diamond vs UniRef90 ([paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC8743544/), [docs](https://bakta.readthedocs.io/)). Not the user’s previous genome. | *E. coli* **7:09** wall / 8 threads / 4.4 GB RAM (same paper, Table 1). Up to **99%** CDS skip alignment. **Estimate:** after hash, leftover `b·N` is tens–hundreds of proteins. | Public hit rate high; user–user leftover is small. | Genome GFF/JSON, not a single protein TSV. Gene calling (Pyrodigal) is **genome-coupled**. | DB **~53 GB** (paper). | **Reject.** Best mode *is* the public hash. Whole-genome, not per-record CLI. 7 min job. |
| Prokka | **No** user-result memo. `--proteins` is a trusted *reference* BLAST DB, reused if already `makeblastdb`’d ([PR 124](https://github.com/tseemann/prokka/pull/124), [README](https://github.com/tseemann/prokka)). Does not import last run’s CDS. | Seemann, *Bioinformatics* 2014, [10.1093/bioinformatics/btu153](https://doi.org/10.1093/bioinformatics/btu153). Bakta paper: Prokka **4:13** on the same *E. coli*. Hierarchical BLAST then HMMER; “~70% of the workload” on a small Swiss-Prot BLAST (README). | Exact-AA possible on the BLAST/HMM steps, but gene calling is not a function of one protein. | `.tsv` of features exists; the invocation is whole-genome. | Small (0.6 GB DB in Bakta’s comparison). | **Reject.** Fast, genome-coupled, not a clean FASTA-in TSV-out tool. |
| SnpSift `dbnsfp` | **No** user-VCF memo. Tabix into a public score table ([SnpSift dbNSFP](https://pcingola.github.io/SnpEff/snpsift/dbnsfp/)). `annotateMem` builds an in-memory DB from *reference* VCFs, not from last sample. | Throughput claim for `annotateMem`: “>1 million VCF lines/min” ([annotateMem](https://pcingola.github.io/SnpEff/snpsift/annotate_mem/)). `dbnsfp` itself is tabix-per-site; **estimate** chr22 = seconds–a minute + JVM `a`; WGS missense-only = minutes of I/O. | Same CEU **m = 0.213**. | **Yes.** VCF INFO fields. | dbNSFP academic download **~50 GB** ([dbnsfp.org/download](https://www.dbnsfp.org/download/)); v4.1a Zenodo listing **30.5 GB** ([10.5281/zenodo.4323592](https://zenodo.org/records/4323592)). Liu *et al.*, *Genome Med.* 2020, [PMC7709417](https://pmc.ncbi.nlm.nih.gov/articles/PMC7709417/). | **Reject.** Lookup of a lookup. 50 GB for an I/O-bound job that is SnpEff-class unless N is WGS-and-slow. |
| AutoDock Vina `--batch` (non-bio) | **No** result cache. `--batch` writes `<ligand>_out.pdbqt`; reruns overwrite. Resume is a *pipeline* (`jamresume`, [PMC12639438](https://pmc.ncbi.nlm.nih.gov/articles/PMC12639438/)), not Vina. | Trott & Olson, *J. Comput. Chem.* 2010, [PMC3041641](https://pmc.ncbi.nlm.nih.gov/articles/PMC3041641/): **1.16 min/complex** average, 8 threads, 190-complex set. 1,000 ligands ≈ **20 h estimate**. `a` (maps) is small vs `b`. | Growing screen libraries: same ligand vs same receptor recurs. No public ligand-identity table; **m** is whatever the library duplicate rate is (often low unless you re-screen). | Per-ligand PDBQT, not one TSV file. Score lines can be scraped. Fails the “generic vcf/fasta/tsv” path without a new format. | Binary small. CARC CPU: yes. | **Reject as headline.** Fits (1)(3)(4) if the library repeats ligands; fails (5) and has no measured (2). Keep as the existence proof that a non-bio CLI *can* fit the cost model. |

SnpEff heavier and ruff are already closed (`pipeline/results/tool_screen.md`).
Not re-opened.

---

## Ranked shortlist (screen these)

### 1. HMMER3 vs Pfam-A — headline protein

No user-result cache, TSV out, proteome wall time is minutes, install is
399 MB + a small binary, CARC exclusive CPU is enough. Recurrence is exact
AA identity on a growing K-12 set; we will *measure* `m` and only then
apply the 3× rule. Strongest objection: if two K-12 proteomes share fewer
than 2/3 identical sequences, the ratio gate dies even if `b·N` is huge
(Studier’s B vs K-12 is the warning). That is a measured kill, not a
guess.

### 2. VEP `--offline --everything --fork 1` — headline variant

This is the instance SCOPE already named. The official cache is the wrong
baseline to fear: it does not memo user VCFs. McLaren’s “negligible
startup” plus 62 min / 4.5e6 variants is why chr22 SnpEff was the wrong
N. `--everything` inflates `b` (HGVS +50–80%). Strongest objection: the
GRCh38 cache is tens of GB and chr22-only may still be Amdahl-capped;
the screen is therefore **multi-chromosome**, not a repeat of N=52,638.

### 3. ESM-2 `esm-extract` — headline model-inference

Stock CLI has no embedding memo. Per-sequence GPU work is tens of
milliseconds; CPU is hours per proteome. Same FASTA records as HMMER, so
one recurrence table serves both. Strongest objection: output is `.pt`,
CARC GPU may be a different allocation, and 2.5 GB weights need approval.
If GPU is absent and CPU `a` (weight load) dominates a short test, it
fails like SnpEff — that is why it is third, not first.

---

## Prior-art brief (this survey)

**Claim we are choosing an instance for:** automatic record-level reuse for
an unmodified CLI, persisted across runs, `cmp`/body-MATCH gated.

**Closest trusted work we are not reinventing**

- Whole-command: Rattle (OOPSLA 2020), Riker (ATC 2022), ProcessCache (2023).
- Hand-built per-record: Oculus (BMC 2012), SeAlM (ICDMW 2019), lab VEP wrappers.
- Public precomputed lookups: InterProScan MLS, Bakta AFSI, VEP `--cache`, dbNSFP.
- User-result cache inside one tool: eggNOG-mapper `-m cache`.

**Delta:** none of the public lookups memo *this user’s last FASTA/VCF*.
eggNOG already does, so it is not the instance. HMMER and VEP `--everything`
do not.

**Non-claims:** we are not inventing InterProScan’s lookup, Bakta’s hashes,
or VEP’s cache. We are not claiming 3× on SnpEff.

---

## Search trail (this pass)

Scholar + web, 2026-09-25. Queries included: InterProScan precalculated
match lookup; eggNOG-mapper `-m cache`; Bakta AFSI/UPS; DIAMOND result
cache; VEP `--everything` runtime; SnpSift dbNSFP; Pfam `hmmscan` timing;
pangenome exact protein identity; ESM-2 extract cache; AutoDock Vina batch
cache; sentence-transformers CLI cache (occupied by `llm embed-multi`).
Shortlist ≥5 trusted/provisional papers per non-empty area; field is
*not* thin.
