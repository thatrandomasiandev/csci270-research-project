# Comparison protocol (pre-registered) — 2026-09-27

Written **before** any comparison build, MATCH run, or timing run of
the arms below. Do not edit the locked sections after seeing
`results/compare_match.json` or any later timing JSON.

This is a **comparison map**, not a method. It places Survivor 1
(record cache) next to stock, compiler/runtime tuning, and a
budget-capped LLM code-optimization agent, on the same MATCH gate.
It does **not** claim novelty for PGO, LTO, `-march=native`, JVM
AppCDS / CDS, or JIT startup flags. Those are established levers
(AutoFDO ~10% geomean, Chen et al., CGO 2016; BOLT +2–8% on
already-FDO binaries, Panchenko et al., CGO 2019; AppCDS is a JDK
feature). OpenTuner / CompilerGym occupy flag search. PIE (Shypula
et al., ICLR 2024) occupies LLM edits on contest C++, not on these
CLIs.

No CARC. No publish. No download over 1 GB. Do not fetch Pfam.
Do not rerun STAR. Do not run the LLM agent in the commit that
adds this file, or in the MATCH-only follow-up.

Predecessor numbers (committed, not remeasured here):

| Source | Path |
|--------|------|
| STAR Mac Suite B 10/10 | `star/bench/results/illumina10_s8j_mac.csv`, `STATUS.md` |
| SnpEff `a`, `b`, measured cache | `results/snpeff_alternating_carc.json` |
| HMMER `a`, `b`, `w` | `results/headline_screen.json` |
| HMMER cache predictions | `results/hmmer_predicted_speedup.json` |
| HMMER MATCH types | `docs/SAVINGS_PROTOCOL.md` (locked MATCH table) |
| SnpEff MATCH type | VCF record-body (`acts.vcf.bodies_equal`) |

---

## What this is not (locked)

- Not a new method, paper claim, or Survivor-2.
- Not PGO / AppCDS novelty. Cite AutoFDO, BOLT, the JDK.
- Not permission to rerun STAR Suite B or to invent a second timer.
- Not permission to run the LLM agent. Design + budget only.
- Not a timing claim. The MATCH follow-up records MATCH only.
- Not a rewrite of `docs/SAVINGS_PROTOCOL.md`.
- Not CARC, not Pfam, not a >1 GB download.

---

## Arms (locked)

Same MATCH gate for every arm that produces tool output.

| ID | Arm | What it is |
|----|-----|------------|
| S | stock | Unmodified tool, default build / default JVM. |
| T | build/runtime tuning | **HMMER:** `-O3 -march=native`, LTO, PGO trained on a **different** proteome than the test FASTAs. **SnpEff:** JVM AppCDS / CDS archive plus JIT flags that target **startup** (`-Xshare:on`, `-XX:SharedArchiveFile`, `-XX:TieredStopAtLevel=1`). Not a source edit. |
| L | LLM code-optimization agent | Source edits, FunSearch-shaped: propose → MATCH → keep or refuse. **Design only in this protocol.** Do not run. |
| C | record cache | Survivor 1 (`python3 -m acts`). Unmodified binary. |
| TC | tuned build + cache | Arm T binary/JVM, then arm C. |

STAR reuses the **sealed EGAS 2×** as arm L (and the disclosed
PGO/LTO/native/jemalloc extras are already inside that sealed
binary). Cite; do not rerun. STAR has no separate T that is not
already in the sealed opt binary.

---

## Workloads (locked)

| Workload | Tool / mode | Input for later timing (not this MATCH) | `-Z` |
|----------|-------------|------------------------------------------|------|
| STAR | `STAR_stock_mac` vs `STAR_opt_mac_s8_pgo` | Suite B i01–i10, 1 thread, `--outBAMcompression 0` | n/a |
| SnpEff | 5.4c GRCh38.86 `-noStats -noLog` | HG00099 *N* = 52,638 (CARC JSON) | n/a |
| HMMER hmmscan | `--cut_ga --noali --tblout` | Savings collections A (30) and B (40) | n_models (HMMER default) |
| HMMER hmmsearch | `--noali --tblout` | Same collections | **`-Z 1e6 --domZ 1e6`** (fixed) |

HMMER CPU width for later timing stays the screen lock (`--cpu 32`
on the exclusive node that produced `headline_screen.json`). MATCH
below is local and small; it does not set that width as a timing
claim.

---

## MATCH (locked; same types as the savings protocol)

| Workload | MATCH | Notes |
|----------|--------|-------|
| hmmscan `--cut_ga` | **order** + whitespace-normalized (`split()`) | `SAVINGS_PROTOCOL.md`; `inference_fasta_reuse.json` → `scan_cut_ga` |
| hmmsearch `-Z 1e6 --domZ 1e6` | **multiset** + whitespace-normalized | same file → `search_fixed_Z` |
| SnpEff | **record-body** (`bodies_equal`) | non-header VCF lines as a multiset; dated headers ignored |
| STAR | already MATCH on every timed Suite B pair | cite the CSV; do not rerun |

Do not require byte-identical HMMER tblout. Do not silently switch
MATCH after a mismatch. Fail → STOP that arm; do not time it.

Small-input MATCH (this protocol’s follow-up, **no timing**):

- HMMER: tiny FASTA under `pipeline/data_compare/` (gitignored).
  PGO train proteome ≠ test proteome. HMM database is **hmmbuild**
  from the train sequences plus explicit GA cutoffs so `--cut_ga`
  is legal. **Do not download Pfam.**
- SnpEff: a small VCF (tens of records), record-body MATCH, jar at
  the read-only `pipeline/tools/snpEff/` symlink. Write nothing
  there. CDS archive goes under `pipeline/builds/` (gitignored).

---

## Cost model (locked)

Stock wall on *N* records:

```
t_S = a + b·N
```

Cache at miss fraction *m* (records still sent to the tool), with
measured wrapper *w*:

```
t_C = a + b·m·N + w
speedup_C(m) = t_S / t_C
```

Cumulative over a collection of *K* genomes, same formula per
genome with that genome’s *m(k)* (median curves in
`hmmer_predicted_speedup.json`).

Metrics for later timing (not claimed here):

1. **Per-run speedup** at the measured *m* of that run.
2. **Cumulative speedup** over the savings collections (HMMER A/B)
   or over Suite B (STAR, already sealed).

### Literature priors for arm T (not measurements)

Marked **prediction**. Used only to rank arms *before* any
comparison measurement.

| Prior | Value | Source | Applied to |
|-------|--------|--------|------------|
| ρ_PGO | **1.10** | AutoFDO ~10% geomean (Chen et al., CGO 2016). BOLT is +2–8% *on top of* FDO; we do not stack it in the prior. | HMMER: scales *a* and *b*. SnpEff: CDS is not PGO; ρ_PGO = 1 for the per-record term. |
| α_CDS | **a → 0.70 a** | AppCDS typical startup cut is tens of percent, not 2×. Genome-DB load may not move; 30% of *a* is the optimistic-but-not-fantasy prior. | SnpEff *a* only. |
| ρ_LLM | **unspecified** | PIE 6× is contest C++ (ICLR 2024). FormulaCode: agents stall on repo-scale scientific bottlenecks. No number. | Arm L is budget-capped, not cost-modelled. |

```
t_T     = (a / α) + (b / ρ)·N
t_TC    = (a / α) + (b / ρ)·m·N + w
```

α = 1, ρ = ρ_PGO for HMMER. α = 1/0.70, ρ = 1 for SnpEff.

---

## Committed *a*, *b*, *N*, *m* (locked citations)

### STAR — no record-level *a*, *b*

BAM is not a per-read identity. Record cache is
**REFUSE_IDENTITY** (`STATUS.md`). The graded 2× is extras-inclusive
source optimization, not cache.

Sealed Mac Suite B (`illumina10_s8j_mac.csv`; n=3, i03 n=9):

| ID | stock mean (s) | opt mean (s) | mean | min_pair | MATCH |
|----|----------------|--------------|------|----------|-------|
| i01 | 6.459 | 3.047 | 2.120× | 2.078× | yes |
| i02 | 6.702 | 3.068 | 2.184× | 2.171× | yes |
| i03 | 5.560 | 2.691 | 2.066× | 2.039× | yes |
| i04 | 6.288 | 2.912 | 2.160× | 2.149× | yes |
| i05 | 10.374 | 4.860 | 2.134× | 2.128× | yes |
| i06 | 12.892 | 5.917 | 2.179× | 2.171× | yes |
| i07 | 11.974 | 5.509 | 2.174× | 2.168× | yes |
| i08 | 11.828 | 5.445 | 2.172× | 2.171× | yes |
| i09 | 14.633 | 6.212 | 2.356× | 2.343× | yes |
| i10 | 13.907 | 5.894 | 2.360× | 2.346× | yes |

**10/10** min_pair ≥ 2.0, MATCH every timed pair. Algorithm-only
S1–S8 (no jemalloc) is **UNSUPPORTED** (i03 min_pair 1.986×). Do
not rebrand PGO or jemalloc as the stitch algorithm.

### SnpEff — `results/snpeff_alternating_carc.json`

Job **12345442**, exclusive `b22-02`.

| Symbol | Value |
|--------|--------|
| *a* (`a_now` mean) | **15.980524412821978** s |
| *b* | **8.425687600843582e-05** s/record |
| *N* | **52638** |
| *w* | **0.04422654166531478** s |
| miss_n | **11191** |
| *m* | 11191 / 52638 = **0.212603** |
| *b·N* | **4.435** s |
| *t_S* = *a*+*b·N* | **20.415** s |

Cache (already measured, cited, not a new claim):

- Predicted `r_from_a_now` = **1.2032×**
- Measured median *r* = **1.1668×**, 95% CI **[1.1595, 1.1705]**
- MATCH 52,638 records; 10/10 pairs `bodies_equal`
- Ceiling at *m* = 0: (*a*+*b·N*)/*a* = **1.277×** (~1.3× in `STATUS.md`)

Mac 1.29× in the same JSON (`mac_side_by_side`) is **withdrawn** as
a headline (idle precondition broken).

### HMMER — `results/headline_screen.json` (job 12377262, `b22-16`)

*N* = **4192** (BW25113). *m*_K-12 = **0.001908**.

| Mode | *a* (s) | *b* (s/rec) | *w* (s) | *t_S* (s) | *b·N* / *t_S* |
|------|---------|-------------|---------|-----------|----------------|
| hmmscan | 31.959641573764316 | 0.7228553909794854 | 0.019063675698513787 | 3062.17 | **0.990** |
| hmmsearch | 132.55764028895294 | 0.11889530446294444 | 0.018338670022785664 | 630.97 | **0.790** |

K-12 cache ceiling `headline_screen.json`: hmmscan **81.09×**,
hmmsearch **4.725×**.

### HMMER cache predictions — `results/hmmer_predicted_speedup.json`

Median *m(k)* curves, *N* locked to 4,192. **Predictions**, not
savings measurements.

| Workload | Mode | Point | *m*_median | speedup_median | kind |
|----------|------|-------|------------|----------------|------|
| A (diverse, k=10) | hmmscan | per-run | 0.3313 | **2.956×** | prediction |
| A (k=30) | hmmscan | per-run | 0.2361 | **4.097×** | prediction |
| A (k=10) | hmmsearch | per-run | 0.3313 | **2.120×** | prediction |
| A (k=30) | hmmsearch | per-run | 0.2361 | **2.521×** | prediction |
| B (O157, k=10) | hmmscan | per-run | 0.0170 | **36.66×** | prediction |
| B (k=39) | hmmscan | per-run | 0.00937 | **50.72×** | prediction |
| B (k=10) | hmmsearch | per-run | 0.0170 | **4.473×** | prediction |
| B (k=39) | hmmsearch | per-run | 0.00937 | **4.597×** | prediction |
| A (30 genomes) | hmmscan | **cumulative** | — | **2.936×** | prediction (`savings_budget`) |
| A (30) | hmmsearch | cumulative | — | **2.111×** | prediction |
| B (40) | hmmscan | cumulative | — | **18.35×** | prediction |
| B (40) | hmmsearch | cumulative | — | **4.077×** | prediction |

---

## Predicted winner, from *a* and *b*, **before** any comparison measurement

Every sentence in this section is a **prediction**. Arm L has no
*a*,*b* forecast (budget + MATCH only).

### STAR — predicted winner: **L** (sealed EGAS 2×)

Cache cannot enter (REFUSE_IDENTITY). Arm T is already inside the
sealed opt binary and is **not** a 2× by itself (AutoFDO/BOLT
priors; extras-off i03 min_pair 1.986×). The cost model of this
protocol does not apply; the sealed table is the code-opt arm.
Do not rerun.

### SnpEff — predicted winner: **TC**

*a* = 15.98 s dominates *b·N* = 4.43 s. Consequences:

| Arm | Predicted *t* (s) | Predicted vs stock | How |
|-----|-------------------|--------------------|-----|
| S | 20.415 | 1× | *a*+*b·N* |
| T | 15.621 | **1.307×** | *a* → 0.70*a*; *b* unchanged (CDS/JIT startup, not PGO) |
| C at measured *m* | 16.968 | **1.203×** | committed `r_from_a_now`; measured 1.167× already on disk |
| C at *m* = 0 | 15.981 | **1.277×** | ceiling; cache cannot beat *a* |
| TC at measured *m* | 12.173 | **1.677×** | CDS cuts *a*, cache cuts *b·m·N* |

Arm C is capped at ~1.28× even at 100% hits. Arm T (startup) is
the right *tuning* lever and is still ~1.3×. They attack different
terms, so **TC** is the predicted winner. Arm L is not predicted to
beat TC: SnpEff wall is JVM + genome-DB load, not a PIE kernel.

### HMMER hmmscan — predicted winner: **TC**, with the win coming from **C**

*b·N* is 99% of *t_S*. PGO prior ρ = 1.10 ⇒ arm T ≈ **1.10×**,
Amdahl-capped well below 2×. Cache at collection *m* is already
predicted 3–4× (A) and 37–51× (B) per later genome, cumulative
**2.94×** (A) / **18.4×** (B). TC adds the 10% rider on the miss
path only (at A k=10, ~3.25× vs cache 2.96×). **C beats T by a
wide margin; TC is the predicted winner** because T and C compose.
Arm L is not predicted to beat C on the savings collections:
HMMER3 is already a SIMD search kernel; PIE-scale edits are the
wrong prior.

### HMMER hmmsearch — predicted winner: **TC**, again C over T

*a* is 21% of *t_S* (startup-capped vs scan). Arm T ≈ **1.10×**.
Even *a* → 0 yields only *t_S*/(*b·N*) = **1.27×**. Cache K-12
ceiling is **4.73×**; collection A cumulative **2.11×**, B
**4.08×**; per-run A ~2.1–2.5×, B ~4.5×. **C beats T; TC wins**
as the composition. A 3× hmmsearch claim on collection A is
**not** licensed by this model (already stated in
`SAVINGS_PROTOCOL.md`).

### Ranking summary (prediction)

| Workload | Predicted winner | Why (from *a*, *b*) |
|----------|------------------|----------------------|
| STAR | **L** (sealed 2×) | no record identity; T is extras, not 2× |
| SnpEff | **TC** | *a* ≫ *b·N*; C capped ~1.28×; T cuts *a*; they stack |
| hmmscan | **TC** (C ≫ T) | *b·N* / *t_S* = 0.99; PGO ~10%; cache tracks 1/*m* |
| hmmsearch | **TC** (C ≫ T) | T ≤ 1.27× even at *a* = 0; cache 2–5× on the curves |

---

## LLM agent (design only; locked budget)

Do **not** run this arm in the MATCH follow-up or in any commit
that only builds T and checks MATCH.

| Knob | Lock |
|------|------|
| Shape | Propose a patch to stock source → rebuild → MATCH → keep iff MATCH and wall improves. FunSearch loop, not free-form rewrite of the repo. |
| STAR | Already run (EGAS). Sealed. Hours+tokens already spent. **Do not rerun.** |
| Hours | **8** wall-clock hours per remaining workload (SnpEff, hmmscan, hmmsearch). Stop at the cap even if MATCH is still green. |
| Tokens | **2,000,000** prompt+completion tokens per remaining workload. Combined cap; no rollover across workloads. |
| MATCH | Identical to the table above. MATCH fail → discard the patch, do not time it. |
| Fairness | Same threads / `--cpu` / JVM heap / `-Z` as stock. No workload narrowing unless SCOPE is updated with Josh (STAR already narrowed; do not narrow again). |
| Refuse | If the 8 h / 2 M token budget produces no MATCH-clean patch with predicted ≥1.10× from a profile (not from hope), the arm is **incomplete**, not a silent 1×. |

Closest trusted priors we are **not** claiming: FunSearch (Nature
2023) for the loop shape; PIE (ICLR 2024) for LLM edits + tests;
EGAS as the STAR driver (course object, not a new method).

---

## Local MATCH follow-up (after this file is committed)

1. Gitignore `pipeline/builds/` and `pipeline/data_compare/`.
2. Download **only** the HMMER 3.4 source tarball from eddylab
   (`http://eddylab.org/software/hmmer/hmmer-3.4.tar.gz`, tens of
   MB). Do not download Pfam.
3. Build stock (default `configure`) and tuned (`-O3 -march=native`,
   LTO, PGO) into `pipeline/builds/`. PGO train on
   `data_compare/pgo_train.faa`, **not** on the test FASTA and
   **not** on savings collections A/B.
4. Dump a SnpEff AppCDS archive into `pipeline/builds/snpeff/`.
   Jar stays at the read-only `tools/snpEff/` symlink.
5. MATCH on the small inputs above. Write
   `results/compare_match.json`. **No timing numbers.**
6. Homebrew `/opt/homebrew/bin/hmm*` may exist; do not use it as
   the tuned binary. Tuned variants are built in this repo.

`bash run_tests.sh` must pass before every commit. Commit this
protocol first, alone. Then scripts + MATCH JSON. Do not commit
`builds/` binaries.

---

## Requests for other agents

- **Savings (CARC) agent:** do not wait on this comparison. Collect
  the queued savings jobs when they finish. This protocol’s HMMER
  rankings are predictions against *your* cumulative metric.
- **ACTS / cache agent:** do not change MATCH types. Comparison
  MATCH is a copy of the savings-protocol table.
- **STAR / EGAS agent:** do not rerun Suite B for this comparison.
  The 10/10 CSV is the code-opt arm.
- **Anyone tempted to call PGO or AppCDS a method:** don’t.
