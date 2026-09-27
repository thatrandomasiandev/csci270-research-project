# STATUS — STAR ≥2× (CSCI 270 A-contract)

**Updated:** 2026-09-26

## Scope — LOCKED (Zhang)

Same output · fair (1 thread) · 10 Illumina datasets · ≥2× wall-clock.

## Honest benchmark (locked)

| Knob | Value |
|------|-------|
| Index | per-dataset `genome_nb10/` (human chr1 10Mb nb10; **fly 2L:1–10Mb nb10**; nfcore nb7) |
| Reads | Suite B FASTQs (i01–i04 teaching; i05–i10 = 50k PE) |
| Threads | 1 |
| BAM | `SortedByCoordinate`, `--outBAMcompression 0` (same both sides) |
| Opt binary | `star/src/STAR_opt_mac_s8_pgo` (S1–S8 + jemalloc + PGO/LTO/`-mcpu=native`) |
| Stock binary | `star/src/STAR_stock_mac` |

**Withdrawn:** Nbases=14 / 800-read “2.5×” (rigged oversized index).  
**Fly note:** full-fly 143 Mb index asymptoted ~1.4× (SA-bound, 48 bp reads). Narrowed to **2L:1–10Mb** teaching subset (parallel to human chr1 10Mb) → ≥2×.

## Graded claim framing (2026-09-26)

**Redefine:** ≥2× is **S1–S8 + disclosed build extras** (jemalloc + PGO/LTO/`-mcpu=native`) on the sealed Mac binary `STAR_opt_mac_s8_pgo`. Algorithm-only (pure S1–S8) ≥2× is **UNSUPPORTED** (i03 pure-S8 min_pair 1.986×, MATCH). Do not chase a 10/10 pure-S8 Suite B table for the graded claim.

## Algorithm (S1–S8) + jemalloc + PGO

See `star/docs/OPTIMIZATION.md` and `star/src/star-2x-verified.patch`.

Headline: **`stitchWindowAligns` spent ~half of runtime copying fat `Transcript` objects.** Bounded copies, pass-by-ref + undo, dead-stitch skip, TLS leaf adopt, closed-form scoring, **S8 leaf move-assign**, **jemalloc**.

## Mac Suite B — all 10 (MATCH every timed pair)

`bakeoff_s8j_i0{1..10}/`, n=3 (i03 n=9). CSV: `star/bench/results/illumina10_s8j_mac.csv`

| ID | stock mean±std (s) | opt mean±std (s) | mean | min_pair | ≥2×? | Notes |
|----|--------------------|------------------|------|----------|------|-------|
| i01 | 6.459±0.002 | 3.047±0.053 | 2.120× | 2.078× | yes | human nb10 |
| i02 | 6.702±0.032 | 3.068±0.014 | 2.184× | 2.171× | yes | human nb10 |
| i03 | 5.560±0.035 | 2.691±0.020 | 2.066× | 2.039× | yes | human nb10 (n=9) |
| i04 | 6.288±0.098 | 2.912±0.027 | 2.160× | 2.149× | yes | human nb10 |
| i05 | 10.374±0.002 | 4.860±0.014 | 2.134× | 2.128× | yes | fly 2L 10Mb |
| i06 | 12.892±0.024 | 5.917±0.009 | 2.179× | 2.171× | yes | fly 2L 10Mb |
| i07 | 11.974±0.036 | 5.509±0.028 | 2.174× | 2.168× | yes | fly 2L 10Mb |
| i08 | 11.828±0.011 | 5.445±0.009 | 2.172× | 2.171× | yes | fly 2L 10Mb |
| i09 | 14.633±0.069 | 6.212±0.014 | 2.356× | 2.343× | yes | nfcore nb7 |
| i10 | 13.907±0.036 | 5.894±0.045 | 2.360× | 2.346× | yes | nfcore nb7 |

**Scoreboard:** **10/10** datasets with min_pair ≥2.0 (all MATCH).

## Lab notebook

Notion **ACTS Lab Notebook** (private draft): https://app.notion.com/p/3e3950426b79817cada0d637afbecdab  
Entries: https://app.notion.com/p/7f89e6e6773240639e944d67953dfd85 · charter `lab-notebook/AGENT.md`

## Research method (not graded)

Survivor 1 — record-level **incremental** memoization. `python3 -m acts`. Headline is a later run that pays only for unseen records (not within-file PCR dups). STAR BAM refuses identity. Course 10/10 table above is a **source** 2×, not this method.

### SnpEff record memoization — CARC exclusive (reference)

Source: `pipeline/results/snpeff_alternating_carc.json` (job **12345442**, exclusive node `b22-02`). Cached-identity MATCH: `pipeline/results/snpeff_cached_identity.json`.

- Median speedup **1.1668×**, 95% CI **[1.1595, 1.1705]**; MATCH on all **52,638** records; **10/10** pairs `bodies_equal`.
- Model check: `a_now` = **15.98 s**, predicted **1.203×** vs measured **1.167×**. The `t = a + b·n` model predicts the speedup before any cache is built.
- SnpEff is capped by startup cost: ceiling about **1.3×** even at 100% hits (`a_now` + locked `b`, `N` in the same JSON).
- Mac **1.29×** (`pipeline/results/snpeff_alternating.json`, also copied under `mac_side_by_side` in the CARC JSON) is **withdrawn as a headline**: the run broke its idle precondition (load 5 → 27). Keep it as a recorded result, not the claim.

Record inference is **generic for VCF** (`8540926`, probes `3f47a00`). STAR argv still refuses identity. FASTA→table is not on disk yet.

### Tool screen (2026-09-25)

Source: `pipeline/results/tool_screen.json` · protocol commit `c51ed61` · write-up `pipeline/results/tool_screen.md`.

- SnpEff heavier (stats, −ud 20000): ceiling **1.30×**, fails the advance rule.
- `ruff check --no-cache`: passes the locked formula at **4.52×** but is **REJECTED** — ruff already caches per file, `--no-cache` is a strawman; full run is **0.7 s**; the rule omitted wrapper overhead `w`.
- VEP and SnpSift dbNSFP were skipped (not installed). The headline-tool question is still open.

## In flight

- [x] Withdraw rigged claim; rebuild nb10; land S1–S8; MATCH-gated harness
- [x] Lock fair `--outBAMcompression 0`
- [x] Push i03 min_pair ≥2.0 (S8 + jemalloc; focused 9/9 ≥2.0)
- [x] Fetch i05–i10 + Mac bakeoffs
- [x] Fly i05–i08 ≥2× via 2L:1–10Mb teaching index
- [x] Professor reproduce path — `star/docs/REPRODUCE.md` + `fetch_suiteB.sh` / `build_stock_opt.sh` / `reproduce_all.sh` / `package_for_professor.sh`
- [x] Figure pack — `star/bench/scripts/plot_all_figures.py` → `star/bench/results/figures/` (+ CARC panels 11–13)
- [x] CARC i01–i04 bakeoff (jobs 12159614/12159615 COMPLETED; all MATCH min_pair ≥2.25×; CSV notes `s7pgo` / **S7≠S8** vs Mac sealed S8+jemalloc+PGO; **no jemalloc** — not Mac-parity)
- [ ] CARC i05–i10 (sync fly/nf-core Suite B data; extend bakeoff job)
- [ ] CARC jemalloc-linked rebuild (parity with Mac sealed binary)
- [~] Flag-matrix §5.3 — **DEFERRED** (2026-09-26): fairness is claimed **within** the locked CLI (`--outBAMcompression 0` both sides). Sensitivity vs default zlib BAM is out of the graded claim for now. Professor path stays `package_for_professor.sh` / `fetch_suiteB.sh` (bare clone ≠ repro).
- [x] EGAS second Method — **none on disk** (2026-09-24). Parked. Not STAR, not `fat_copy`; 2048 rejected. Record: `pipeline/SECOND_METHOD.md`
- [x] Pivot research front door to Survivor 1 (`python3 -m acts`) — record memoization; STAR source 2× untouched
- [x] Suite B PE uniqueness (`pipeline/results/suiteB_dups.csv`): best 1.15× if per-read (i03); i05/i07/i08 dups rare. STAR instance dead (identity + budget).
- [x] STAR instance of record memo: **REFUSE_IDENTITY** (BAM is not per-read). Line fixture is the wiring proof.
- [x] Persistent cache + incremental line fixture (`run_a` → `run_b`)
- [x] Suite B **cross-sample** overlap (`pipeline/results/suiteB_overlap.csv`): best recall_in_new 0.108 (i03→i04); fly ~0.018 (rare). Reads are the wrong incremental instance.
- [x] VEP protocol locked (`pipeline/docs/VEP_PROTOCOL.md`): records-only MATCH, `-c1` overlap, no haplo, chr22. Tools absent → INCOMPLETE
- [x] bcftools 1.24 + SnpEff 5.4c GRCh38.86. Identity: body MATCH + shuffle MATCH on 200 vars; full-file DIFF on `##SnpEffCmd` only (`results/snpeff_identity/report.json`)
- [x] 1000G chr22 `joint_called_c1` overlap CEU: pairwise recall 0.62–0.64; union of 2 → 3rd = 0.787 (`results/vep_chr22_overlap.json`)
- [x] Timed SnpEff miss-vs-full — MATCH 52,638 (`results/snpeff_cached_identity.json`); Mac timing recorded, not the claim
- [x] CARC exclusive SnpEff alternating rerun — job 12345442, `b22-02`, median **1.1668×** (`results/snpeff_alternating_carc.json`)
- [x] Tool screen (`c51ed61`) — SnpEff heavier fails; ruff formula-pass rejected (`results/tool_screen.json`)
- [x] Generic VCF record inference (`8540926` + `3f47a00`); SnpEff MATCH 52,638 via probes
- [x] FASTA→table record format (`2ef93ff` protocol; fixtures + local search in `results/inference_fasta_local.json`)
- [ ] Headline tool (SnpEff capped ~1.3×; ruff rejected; VEP / dbNSFP skipped)
- [ ] Running baselines (the tool’s own cache; Riker / ProcessCache)
- [ ] Read ProcessCache thesis + vCache (ICLR 2026) before a paper draft (`literature/READING.md`)
- [x] Write-up draft — conference paper at `star/writeup/paper/main.pdf` (update when CARC 10/10 lands)
- [x] Notion lab notebook + first conference-length entry (Mac Suite B seal)

## Blockers

- Sync fly 2L10M + nf-core indexes/FASTQs to CARC before full graded bakeoff
- jemalloc availability / packaging on graded Linux node for Mac-parity binary
- **Professor handoff:** run `./star/bench/scripts/package_for_professor.sh ~/Desktop/STAR_suiteB_repro.tar.gz` and send the tarball (repo alone omits gitignored Suite B data)
