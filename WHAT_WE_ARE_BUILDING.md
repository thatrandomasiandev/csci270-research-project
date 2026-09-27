# What we are building

**Updated:** 2026-09-26

Plain-language companion: [`WHAT_THIS_IS.md`](WHAT_THIS_IS.md).

Two objects share this repo. They are not the same claim.

1. **Graded course artifact (Zhang A-contract):** a scoped STAR ≥2× on Suite B, same output, one thread. Sealed on Mac 10/10. Do not delete it.
2. **ACTS strategies (`pipeline/acts`):** speed up an **unmodified** tool. First strategy: **record-level incremental memoization**. Headline is a later run that pays only for unseen records. More strategies later — do not invent them.

EGAS (`python3 -m egas`) stays as the source-edit driver that produced (1). It is not this method.

## 1. The research method — record-level incremental computation

**One sentence:** If a black-box tool’s output for each record depends only on that record, cache those results across runs and reassemble; keep the result only if it is byte-identical to a full run.

**Falsifier:** records are not independent, overlap across runs is rare, or `cmp` fails.

```
first run:  memoize distinct records in this file (refuse if unique_frac ≥ 0.95)
later run:  pay only for cache misses          (refuse if miss_frac ≥ 0.95)
            reassemble → cmp → optional Dune-style hit audit → SHIP
```

```bash
python3 -m acts run --cache cache.jsonl --kind lines --input run_a.txt -- cat
python3 -m acts run --cache cache.jsonl --kind lines --input run_b.txt -- cat
python3 -m acts overlap --suiteb
```

**Why this is the gap (checked, not vibes):**

| Reuse level | Who | What they lack |
|-------------|-----|----------------|
| Whole command | Rattle (OOPSLA 2020), Riker (ATC 2022), ProcessCache (Shiptoski 2023 thesis), ccache | One new record in a big file → full rerun |
| Whole function | IncPy (ISSTA 2011), Mandala (SciPy 2024) | Python only |
| Per record, one tool | Oculus, SeAlM, lab VEP wrappers | Hand-built |
| Per record, split only | KumQuat | No reuse |
| Command-level hit audit | Dune `cache-check-probability` | Not record-level; not a CLI wrapper |

Ensembl VEP’s official `--cache` is a **reference-data** store (transcripts, known variants). It is not a memo of prior user VCFs. Adding sample 1,001 still annotates every variant in that VCF. That example stands; the citation must not confuse the two caches.

**Named delta:** automatic record-level reuse inside one invocation, persisted across runs, `cmp`-gated. Reviewers will cite ProcessCache, Rattle/Riker, KumQuat, Oculus.

**What is not the paper**

- **Tracing for hidden inputs** (Rattle/Riker/ProcessCache already do this at process granularity). We do not have it yet. Do not claim “first automatic cache keys.”
- **Statistical guarantee as novelty.** Dune already re-executes cached rules. `--audit-p` is that idea at record grain — engineering, not a theorem.
- **Parallelism.** KumQuat. Free later.
- **Near-duplicate hint-and-verify.** Stretch; weakens “unmodified.” Out of v1.

**STAR / RNA-seq reads are a dead instance, measured twice.** Identity fails (QNAME, sort, headers). Within-file uniqueness tops out at 1.15× on i03. Cross-sample `recall_in_new` (`pipeline/results/suiteB_overlap.csv`): human airway 0.067–0.108, nfcore 0.087, fly 0.017–0.020.

**SnpEff / chr22 variants are a live instance, timed, capped.** SnpEff 5.4c on 200 HG00096 `-c1` variants: body MATCH stock-vs-stock and after shuffle; full-file `cmp` fails on `##SnpEffCmd` only. 1000G CEU `-c1` overlap: pairwise recall 0.620–0.637; after two samples the third is 0.787 already seen (`pipeline/results/vep_chr22_overlap.json`).

Reference timing is the CARC exclusive alternating run (`pipeline/results/snpeff_alternating_carc.json`, job 12345442, node `b22-02`): median **1.1668×**, 95% CI **[1.1595, 1.1705]**; MATCH on all 52,638 records; 10/10 pairs `bodies_equal`. `a_now` = 15.98 s predicts **1.203×** vs measured **1.167×**. Startup caps the tool at about **1.3×** even at 100% hits. The Mac **1.29×** (`pipeline/results/snpeff_alternating.json`) is a recorded result, not the claim — idle precondition failed (load 5 → 27). Cached-identity MATCH is `pipeline/results/snpeff_cached_identity.json`.

**Record inference is generic for VCF** (since `8540926`; subset-invariance and late keys in `3f47a00`). `pipeline/acts/infer_vcf.py` classifies field roles by probe. `snpeff_ann.py` is a test oracle, not the runtime path. The SnpEff 1.17× is that method. STAR argv still refuses identity. The open format gap is FASTA-in / table-out (HMMER tblout), not VCF.

The **line_memo** pair (`run_a.txt` → `run_b.txt`, 50% recall) is the wiring proof of the headline. SHIP there is not a paper result.

## 2. The course object — STAR ≥2×

**One sentence:** On a locked 10-dataset Illumina bake-off, the patched STAR is at least twice as fast as stock, and every timed pair MATCHES.

Mac 10/10. [`STATUS.md`](STATUS.md). [`star/docs/REPRODUCE.md`](star/docs/REPRODUCE.md). Mechanism: copy-elision in `stitchWindowAligns`. Zhang grades this.

## 3. What is on disk today

| Object | Status | Where |
|--------|--------|--------|
| STAR source 2× | Mac 10/10 | `star/` |
| Persistent record cache | Lines: first-run + incremental SHIP | `pipeline/acts/cache.py` |
| Cross-run overlap probe | Suite B + arbitrary pairs | `python3 -m acts overlap` |
| Hit audit | Dune-style, optional `--audit-p` | `pipeline/acts/audit.py` |
| STAR identity refuse | Locked | `pipeline/results/star_identity_refuse.txt` |
| EGAS | Kept | `pipeline/egas/` |
| VEP protocol | Locked; SnpEff identity + `-c1` overlap landed | `pipeline/docs/VEP_PROTOCOL.md` |
| SnpEff cached identity | Body MATCH, 52,638 records | `pipeline/results/snpeff_cached_identity.json` |
| SnpEff CARC exclusive | Median 1.1668×; Mac 1.29× withdrawn as headline | `pipeline/results/snpeff_alternating_carc.json` |
| Tool screen | SnpEff heavier fails; ruff formula-pass rejected | `pipeline/results/tool_screen.json` |
| Record inference | VCF generic (probe roles). FASTA→table not yet. | `pipeline/acts/infer_vcf.py` |
| Reading list | ProcessCache + vCache unread | personal store `literature/READING.md` |

## 4. What we are building next

1. **FASTA→table record format.** VCF inference is done. Do not wrap a second tool by hard-coding its table columns.
2. **A headline tool.** SnpEff is capped (~1.3× at 100% hits). The 2026-09-25 screen (`pipeline/results/tool_screen.json`) rejected heavier SnpEff and rejected ruff (strawman `--no-cache`, 0.7 s job, omitted `w`). VEP and dbNSFP were skipped (not installed). The question is still open.
3. **Running baselines** — the tool’s own cache, then Riker / ProcessCache — and read ProcessCache + vCache before a paper draft.
4. Suite B overlap, VEP protocol lock, timed SnpEff miss-vs-full, CARC exclusive rerun, and the tool screen are **done**. Do not call 0.79 recall a speedup. Do not add tracing or an LLM grammar. Do not run STAR on deduplicated FASTQs. VEP still absent (full cache not pulled).

## 5. What we are not building

- SSE / unified-memory LLM serving.
- “2× any program.”
- A second STAR timer.
- EGAS-as-a-new-method.
- A paper whose novelty is “we have a confidence interval” (Dune) or “we parallelize” (KumQuat).

## 6. Which novelty type this is

| Type | Are we doing it? |
|------|------------------|
| Filling a literature gap | **Yes, one gap:** record-level reuse for unmodified binaries. Whole-command is occupied. Hand-built per-tool is occupied. |
| New method or tool | Same bet. The method is the wrapper + independence probe + persistent record cache + `cmp`. |
| Combining ideas | No. Do not sell “Rattle tracing × KumQuat split × Dune audit × LLM.” |
| New context / contradict | No. |

**Strongest objection:** if every scientific binary that is per-record has low cross-run overlap (reads) or fails `cmp` (STAR BAM, maybe VEP headers), the useful instance set is empty and we have a `cat` demo. Then kill the instance, or the method.

**Paper pitch we will actually stand behind** (X is unmeasured):

> Automatic record-level incremental computation for unmodified CLI tools. Whole-command caches (Rattle, Riker, ProcessCache, ccache) rerun when any input byte changes. Hand-built caches (Oculus, SeAlM, lab VEP wrappers) do not generalize. We infer records, memoize across runs, and accept only on byte-identical reassembly.

## 7. How to talk about it

- **To Zhang:** STAR ≥2×, Suite B, MATCH, one thread.
- **To ourselves:** incremental record cache; STAR source 2× is the course object.
- **Avoid:** “we 2× STAR without touching code,” “first statistical cache,” “VEP’s cache is our competitor.”

## Pointers

| Doc | Role |
|-----|------|
| [`STATUS.md`](STATUS.md) | STAR scoreboard + this method |
| [`pipeline/SCOPE.md`](pipeline/SCOPE.md) | Claim lock |
| [`pipeline/docs/VEP_PROTOCOL.md`](pipeline/docs/VEP_PROTOCOL.md) | VEP/SnpEff pre-registrations |
| [`pipeline/README.md`](pipeline/README.md) | Commands |
| [`AGENTS.md`](AGENTS.md) | Session protocol |
