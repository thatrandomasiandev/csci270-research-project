# TARE orchestrator report — 2026-10-19

Consolidated report from the remaining-experiment fan-out. The system is **TARE**. The package remains `acts`. This session did **not** edit `pipeline/paper/tare/main.tex`. The hub owns paper integration.

Orchestrator branch: `exp/orchestrator-report`. Worktrees were created from `origin/main` at launch (`1c65571`); by the time this report was written, `origin/main` had advanced (orchestrator worktree HEAD at creation: see git). Per-workstream tips below are the authoritative result branches.

CARC jobs still live at report time (left alone; never touched `12864756`):

| Job | Name | State |
|---|---|---|
| 13241855 | tare-w8-pilot | RUNNING |
| 13241901 | tare-w6-hmmer (Drosophila) | RUNNING |
| 13241865 | tare-w5x-pilot | PENDING (Priority) |
| 13241867 | tare-w12a-pilot | PENDING (Priority) |
| 13243768 | tare-w6-blast (measured after NOT_SHIP pilot) | PENDING (Priority) |

---

## Scoreboard

| WS | Branch | Tip | Status | One-line result |
|---|---|---|---|---|
| W6 | `exp/w6-row-keys` | `080636d` | **DONE** (partial HMMER) | Row-key/text fixes; **BLAST NOT_SHIP**; 5/6 needless HMMER SHIP; Drosophila still RUNNING |
| W7 | `exp/w7-breakeven` | `0ea9c8c` | **DONE** | Break-even fallback at default 0.80; Pfam subset `f_delta=0.975` → FALLBACK, equal stock |
| W8 | `exp/w8-release-chain` | `53d6e58` | **INCONCLUSIVE** | Pilot `13241855` still RUNNING (3/5 steps SHIP); no measured.json |
| W9 | `exp/w9-server-figures` | `bc04472` | **DONE** | Server fit **a=0.973, c=0.098**; figures updated |
| W10 | `exp/w10-bounded-audit` | `fb0e8f7` | **DONE** | Cold-cache audit; hidden misses 489/800 (shipped) / 272/800 (bounded s=299) |
| W12a | `exp/w12a-expert-script` | `b9ed4b8` | **INCONCLUSIVE** | Pilot `13241867` still PENDING; no server.json |
| W12b | `exp/w12b-iseqsearch` | `5b949cf` | **INCONCLUSIVE** | Declared `--dbsize` pin staged; exclusive job not submitted; no speed number |
| W5x | `exp/w5x-baselines-x86` | `5965454` | **INCONCLUSIVE** | Pilot `13241865` still PENDING; no Table 4 ρ |
| WA | `exp/a-unrelated-ship` | `258b20d` | **INCONCLUSIVE** | pfscanV3: 8/10 SHIP byte-identical, 2 power-floor misses; not a SHIP claim |

---

## W6 — row keys, text columns, BLAST+

**Status: DONE** (HMMER follow-up partial). Branch `exp/w6-row-keys`, tip `080636d98371aaae6746af8088f302a869baf35f`. Code freeze `1c62ab90044de3d16cedf578f6a2851600ad954f`.

**Headline:** `BLAST_SHIP: NOT_SHIP`. After occurrence-index keys and mostly-text pass-through, BLAST+ still refuses with `out: column 2 matches no normalizer`. Five of six prior needless HMMER refusals re-ran as SHIP and byte-identical (including headline `GCF_015290725.1`). Drosophila `GCF_000001215.4` job `13241901` still RUNNING.

**Controls:** BLAST stock-vs-stock identical (297810 lines); unpinned differs; drop body differs; shipped drop check not reached (gated on SHIP). HMMER follow-ups: fill+update SHIP and byte-identical on five finished genomes.

**Deviations:** Partial Drosophila; measured BLAST job `13243768` submitted after NOT_SHIP pilot (disclosed); optional exclusive timing skipped.

### Proposed paper sentences (verbatim from W6)

1. After disambiguating repeated row keys by occurrence order and treating a mostly-text or trailing free-text column as pass-through, five of the six previously needless HMMER refusals re-ran as shipped updates with bodies byte-identical to stock (follow-up; not part of the locked headline or diverse draw). One genome (`GCF_000001215.4`) was still running at report time.
   `% source: pipeline/results/w6_followup/hmmer_GCF_002078355.1.json outcome=SHIP`
   `% source: pipeline/results/w6_followup/hmmer_GCF_000284335.1.json outcome=SHIP`
   `% source: pipeline/results/w6_followup/hmmer_GCF_001017655.1.json outcome=SHIP`
   `% source: pipeline/results/w6_followup/hmmer_GCA_001817145.1.json outcome=SHIP`
   `% source: pipeline/results/w6_followup/hmmer_GCF_015290725.1.json outcome=SHIP`
   `% source: pipeline/results/w6_followup/hmmer_GCF_015290725.1.json compare.byte_equal=true`
   `% source: (pending) CARC job 13241901 GCF_000001215.4 RUNNING`

2. BLAST+ 2.14.1 with `--pin '-dbsize {total_entry_length}'` on Swiss-Prot 2026_01→2026_03 (pilot, 300 queries, seed 20261201) did **not** ship: both releases refused with `out: column 2 matches no normalizer`, while the fallback full-scan tables were ordered-equal to stock (297,810 lines on 2026_03; stock-versus-stock MD5 `30fb3f478b88414cae107e54765304e8`).
   `% source: pipeline/results/w6_followup/blast_pilot.json outcome=NOT_SHIP`
   `% source: pipeline/results/w6_followup/blast_pilot.json cli.2026_03.why="out: column 2 matches no normalizer"`
   `% source: pipeline/results/w6_followup/blast_pilot.json cli.2026_03.vs_stock.ordered_body_equal=true`
   `% source: pipeline/results/w6_followup/blast_pilot.json stock_vs_stock.n_lines=297810`
   `% source: pipeline/results/w6_followup/blast_pilot.json stock_vs_stock.md5_a=30fb3f478b88414cae107e54765304e8`
   `% source: pipeline/results/w6_followup/blast_pilot.json frozen_code_commit=1c62ab90044de3d16cedf578f6a2851600ad954f`

3. Therefore BLAST+ is **not** claimed here as the first shipping program from an unrelated codebase; the remaining blocker after the row-key and text-column fixes is the closed normalizer family on a percent-identity column, not duplicate keys.
   `% source: pipeline/results/w6_followup/blast_pilot.json outcome=NOT_SHIP`
   `% source: pipeline/results/w6_followup/blast_pilot.json cli.2026_01.why="out: column 2 matches no normalizer"`

Full writeup: `pipeline/docs/prompts/2026-10-19_w6_report.md` on that branch.

---

## W7 — break-even fallback

**Status: DONE.** Branch `exp/w7-breakeven`, tip `0ea9c8c23bdcf43c7c1a4a8b259f1fbeb30df770`. Freeze `b59307fecb781b768f846bc11068526879df8c5d`.

**Headline:** Default threshold 0.80; on a 40-model Pfam 37.4→38.0 subset, `f_delta=0.975`, decision `FALLBACK`, both tables match stock (8 rows). Pilot low arm `f_delta≈0.083` SHIPed. Laptop times are not a speed claim. Full pair timing remains W8.

**Controls:** Known-bad comparator; pilot high FALLBACK / low SHIP; stock-vs-stock; cold fill stays SHIP; flag and history overrides in unit tests. Pytest 386 passed, 1 skipped.

### Proposed paper sentences (verbatim from W7)

TARE runs the stock command when the changed fraction is above the break-even `(1-c)/a`, and uses 0.80 when the cache has no usable fill or update history.

`% source: pipeline/results/breakeven/measured.json threshold_default = 0.8`

`% source: pipeline/results/breakeven/measured.json run.update.f_threshold_source = default`

On a 40-model draw from Pfam 37.4 to Pfam 38.0, 39 of 40 entries were new to the cache (`f_delta = 0.975`). TARE fell back, and both tables matched stock on 8 rows.

`% source: pipeline/results/breakeven/measured.json pair.n_fresh = 39`

`% source: pipeline/results/breakeven/measured.json pair.n_new = 40`

`% source: pipeline/results/breakeven/measured.json pair.f_delta = 0.975`

`% source: pipeline/results/breakeven/measured.json run.update.decision = FALLBACK`

`% source: pipeline/results/breakeven/measured.json run.tare_vs_stock.tblout.n_stock = 8`

`% source: pipeline/results/breakeven/measured.json run.tare_vs_stock.domtblout.n_stock = 8`

`% source: pipeline/results/breakeven/measured.json run.tare_vs_stock.equal = true`

Below the threshold the replay path is unchanged: a 24-model draw with changed fraction 0.0833 shipped an exact replay and matched stock.

`% source: pipeline/results/breakeven/pilot.json low.f_delta = 0.08333333333333333`

`% source: pipeline/results/breakeven/pilot.json low.run.update.decision = SHIP`

`% source: pipeline/results/breakeven/pilot.json low.run.update.why = exact replay under pinned normalizer`

`% source: pipeline/results/breakeven/pilot.json low.run.tare_vs_stock.equal = true`

Full writeup: `pipeline/docs/prompts/2026-10-19_w7_report.md` on that branch.

---

## W8 — release chain timing

**Status: INCONCLUSIVE.** Branch `exp/w8-release-chain`, tip `53d6e58eba31b75dd14186a52f53e9c582353088`. Frozen CARC code `bebabc5b7f4b81c72e322f3a68f363a4429f855a`.

**Headline:** Pilot job `13241855` still RUNNING on `b22-21`. Partial: proteome `GCF_003018555.1`, seed `20261221`; fill 37.3 and updates 37.3→37.4 (`f_delta=0.02013`) and 37.4→38.0 (`f_delta=0.93118`, replay forced) SHIP; 5% drop refused; drift not run; measured not submitted. No \(S_g\).

**Controls:** Negative control refused (good). Drift not executed.

### Proposed paper sentences (verbatim from W8)

None yet. The pilot is incomplete (no drift result, no finished `outcome`). The measured chain has not run. Any sentence with an \(S_g\) or payback index would be unsupported.

Full writeup: `pipeline/docs/prompts/2026-10-19_w8_report.md` on that branch.

---

## W9 — server cost figures

**Status: DONE.** Branch `exp/w9-server-figures`, tip `bc044725d2a567f18e831ec9baecb0ef516e4f67`.

**Headline:** Server fit over nine EXACT genomes: **a = 0.973**, **c = 0.098**, ceiling **10.2×**; in-sample prediction **4.37×** vs measured median **4.24×**. Figure 5 solid curve uses server fit; laptop dashed. `server_cost_fit.json` written.

**Controls:** Laptop recomputation rounds to published 1.06 / 0.152; drop-lowest sensitivity stored unused.

### Proposed paper sentences (verbatim from W9)

**Cost model** (replace the `c = 0.152` / `6.6×` claims; the two laptop discovery errors can stay as the laptop check):

On the nine exact server genomes the same definitions give \(a = 0.973\) and \(c = 0.098\). A release that changed nothing would be at most \(10.2\times\) faster with this overhead. At \(f_\Delta = 0.134\) the fitted curve predicts \(4.37\times\); the measured median on those genomes is \(4.24\times\). The coefficients are fit on the same nine genomes, so that comparison describes the sample. The dashed curve is the laptop fit, \(a = 1.06\), \(c = 0.152\).

% source: MEASURED pipeline/results/exact_replay/server_cost_fit.json a=0.9725467626703342 c=0.09799254461859343 one_over_c=10.20485797049357 f=0.13446605163602576 speedup_at_headline_f=4.371258544780619 n_genomes=9 laptop_reference.published_a=1.06 laptop_reference.published_c=0.152 laptop_reference.recomputed_a=1.0603329419944263 laptop_reference.recomputed_c=0.15235585532542203; MEASURED pipeline/results/exact_replay/headline_carc.json headline_median=4.243202948728078 n_speedups=9; DERIVED a_round=round(a,3); DERIVED c_round=round(c,3); DERIVED ceil_round=round(one_over_c,1); DERIVED s_fit=round(speedup_at_headline_f,2); DERIVED s_med=round(headline_median,2); NOMINAL nine=9

**Other releases** (replace the laptop speedups 3.5–5.8×, 1.8×, and 0.88×):

Strict hashes of all seven consecutive Pfam pairs put the changed fraction between 2.0% and 93.1%. With the server coefficients the model predicts \(4.6\)–\(8.5\times\) for the four pairs that changed at most 12.2%, \(2.1\times\) for 37.0\(\rightarrow\)37.1 (39.3%), and \(0.996\times\) for 37.4\(\rightarrow\)38.0 (93.1%). The timed pair, 38.1\(\rightarrow\)38.2 (13.4%), predicts \(4.37\times\). Only that pair has been timed. At 0.996× a full run is still slightly cheaper, and TARE does not yet decide this on its own.

% source: MEASURED pipeline/results/release_chain/pairs.json pairs.0.f_delta=0.3926620156341935 pairs.1.f_delta=0.041368998172453895 pairs.2.f_delta=0.03181297084834589 pairs.3.f_delta=0.020132600258732213 pairs.4.f_delta=0.9311802701115678 pairs.5.f_delta=0.1221935155198137 pairs.6.f_delta=0.13446605163602576; MEASURED pipeline/results/exact_replay/server_cost_fit.json a=0.9725467626703342 c=0.09799254461859343 predictions.0.speedup=2.0838772394144036 predictions.1.speedup=7.234537864366587 predictions.2.speedup=7.756017624028534 predictions.3.speedup=8.505394644305186 predictions.4.speedup=0.9964040755600193 predictions.5.speedup=4.611877051086615 predictions.6.speedup=4.371258544780619; DERIVED p_lo=100*pairs_3_f_delta; DERIVED p_hi=100*pairs_4_f_delta; DERIVED p_371=100*pairs_0_f_delta; DERIVED p_mid=100*pairs_5_f_delta; DERIVED p_timed=100*pairs_6_f_delta; DERIVED s_lo=1/(a*pairs_5_f_delta+c); DERIVED s_hi=1/(a*pairs_3_f_delta+c); DERIVED s_371=1/(a*pairs_0_f_delta+c); DERIVED s_380=1/(a*pairs_4_f_delta+c); DERIVED s_timed=1/(a*pairs_6_f_delta+c); NOMINAL four=4; NOMINAL seven=7; HAS 37.0; HAS 37.1; HAS 37.4; HAS 38.0; HAS 38.1; HAS 38.2

**Figure 4 caption** (the top panel is the old laptop content; the bottom panel is new):

Where the time goes. Top, laptop: the first version, the median of three runs, and the two shipped runs. Bottom, server: the headline genomes with the lowest, median, and highest speedup, each bar the median of three update runs. The black tick is a stock run. Dotted ticks: discovery predicted as \(f_\Delta T_{\text{stock}}\).

% source: MEASURED pipeline/results/exact_replay/headline_carc.json genomes.7.S_g=4.133848860006259 genomes.7.stock_median_s=2329.090906601865 genomes.7.tare_median_s=563.4194634291343 genomes.8.S_g=4.243202948728078 genomes.8.stock_median_s=2203.676445968915 genomes.8.tare_median_s=519.3426929130219 genomes.6.S_g=5.065259864107012 genomes.6.stock_median_s=2554.41851097811 genomes.6.tare_median_s=504.3015717868693; MEASURED pipeline/results/exact_replay/headline_measured/headline_measured_13227819_2.json repeats.3.wall_s=563.4194634291343 repeats.3.phases.discovery_s=326.66202274989337; MEASURED pipeline/results/exact_replay/headline_measured/headline_measured_13227819_4.json repeats.3.wall_s=519.3426929130219 repeats.3.phases.discovery_s=301.54377289582044 repeats.3.phases.replay_s=25.706460212823004 repeats.3.phases.ic2_neighbor_s=43.577584363054484 repeats.3.phases.ic2_random_20261031_s=8.02239132206887 repeats.3.phases.ic2_random_20261032_s=7.958026549313217 repeats.3.phases.ic2_random_20261033_s=8.028765022289008 repeats.3.phases.verify_s=47.65006781509146; MEASURED pipeline/results/exact_replay/headline_measured/headline_measured_13208152_9.json repeats.3.wall_s=504.3015717868693 repeats.3.phases.discovery_s=278.78749465197325; MEASURED pipeline/results/exact_replay/server_cost_fit.json f=0.13446605163602576 phase_bars.genomes.0.role=lowest_S_g phase_bars.genomes.1.role=median_S_g phase_bars.genomes.2.role=highest_S_g; NOMINAL three=3

The check on the median server bar is the sum of the five phase keys cited for `headline_measured_13227819_4.json`. Those five sum to the fit file's `phase_bars.genomes.1.stages_s.check` = 115.23683507181704.

**Figure 5 caption, panel (a)** (panel (b) can stay):

(a) HMMER. The solid curve is the server fit, \(a = 0.973\), \(c = 0.098\), from the nine exact genomes. The dashed curve is the laptop fit, \(a = 1.06\), \(c = 0.152\). Gray circles are the two laptop updates. The open diamond is the server median of nine with its 95% CI. Ticks are the server model at the measured \(f_\Delta\) of all seven Pfam pairs. The light dashed curve is \(1/f_\Delta\). The dotted line is the server ceiling \(1/c = 10.2\times\).

% source: MEASURED pipeline/results/exact_replay/server_cost_fit.json a=0.9725467626703342 c=0.09799254461859343 one_over_c=10.20485797049357 n_genomes=9 laptop_reference.published_a=1.06 laptop_reference.published_c=0.152; MEASURED pipeline/results/exact_replay/headline_carc.json headline_median=4.243202948728078 bootstrap_ci95.low=4.172363531540619 bootstrap_ci95.high=4.683831507831228 n_speedups=9; LEN predictions=7; NOMINAL ci=95; NOMINAL nine=9; NOMINAL seven=7

Full writeup: `pipeline/docs/prompts/2026-10-19_w9_report.md` on that branch.

---

## W10 — bounded audit / adversarial

**Status: DONE.** Branch `exp/w10-bounded-audit`, tip `fb0e8f7636dfeca86baac6c796342d054d6432c5`. Code freeze `bcca3b47697051857cf0fb61f8e33d504d709fd9` (pre-registration pushed before measured results).

**Headline:** Audit runs on cold cache. Hidden/distant couplings: shipped sample misses **489/800**; bounded **s=299** misses **272/800**; in the bound region (`k`∈{22,100}) bounded misses **3/400**. C0 needless refusals **0**. Table 3 controls still refuse/pass. Bounded cost ≈ **6.4%** of stock (scaled verify).

**Controls:** DIAMOND known-bad refuse; DIAMOND 22-line refuse; 5% drop refuse; HMMER correct pass. Real hmmscan confirmations C0–C4 behaved.

### Proposed paper sentences (verbatim from W10)

The cold-cache gate is why the published check missed 741 of 800 hidden couplings. With the audit on every exact replay, the same grid misses 489 of 800 under the shipped sample and 272 of 800 under a sample of 299 records.

% source: DERIVED shipped_hidden_misses_v1=measured.json cells C2/k1.UNSAFE=49 + C2/k5.UNSAFE=48 + C2/k22.UNSAFE=43 + C2/k100.UNSAFE=38 + C3/d2/k1.UNSAFE=48 + C3/d2/k5.UNSAFE=49 + C3/d2/k22.UNSAFE=48 + C3/d2/k100.UNSAFE=44 + C3/d5/k1.UNSAFE=50 + C3/d5/k5.UNSAFE=49 + C3/d5/k22.UNSAFE=46 + C3/d5/k100.UNSAFE=41 + C3/d20/k1.UNSAFE=49 + C3/d20/k5.UNSAFE=49 + C3/d20/k22.UNSAFE=48 + C3/d20/k100.UNSAFE=42
% source: DERIVED shipped_hidden_misses_v2=measured_v2.json shipped.cells C2/k1.UNSAFE=50 + C2/k5.UNSAFE=41 + C2/k22.UNSAFE=31 + C2/k100.UNSAFE=2 + C3/d2/k1.UNSAFE=49 + C3/d2/k5.UNSAFE=45 + C3/d2/k22.UNSAFE=28 + C3/d2/k100.UNSAFE=2 + C3/d5/k1.UNSAFE=49 + C3/d5/k5.UNSAFE=38 + C3/d5/k22.UNSAFE=31 + C3/d5/k100.UNSAFE=5 + C3/d20/k1.UNSAFE=49 + C3/d20/k5.UNSAFE=41 + C3/d20/k22.UNSAFE=24 + C3/d20/k100.UNSAFE=4
% source: DERIVED bounded_hidden_misses=measured_v2.json bounded.cells C2/k1.UNSAFE=44 + C2/k5.UNSAFE=20 + C2/k22.UNSAFE=0 + C2/k100.UNSAFE=0 + C3/d2/k1.UNSAFE=42 + C3/d2/k5.UNSAFE=26 + C3/d2/k22.UNSAFE=1 + C3/d2/k100.UNSAFE=0 + C3/d5/k1.UNSAFE=46 + C3/d5/k5.UNSAFE=26 + C3/d5/k22.UNSAFE=1 + C3/d5/k100.UNSAFE=0 + C3/d20/k1.UNSAFE=46 + C3/d20/k5.UNSAFE=19 + C3/d20/k22.UNSAFE=1 + C3/d20/k100.UNSAFE=0
% source: MEASURED pipeline/results/adversarial/measured_v2.json shipped.check.audit_plan.s=50
% source: MEASURED pipeline/results/adversarial/measured_v2.json bounded.check.audit_plan.s=299
% source: MEASURED pipeline/results/adversarial/measured_v2.json seed=20261232

The sample size is the classical with-replacement choice `s = ceil(ln(0.05) / ln(1 - 0.01)) = 299`. At `k = 22` the audit-only detection is 0.963; the measured bounded rates are 1.00 (C2) and 0.98 (C3 at distances 2, 5, and 20). At `k = 100` every bounded cell is 1.00. A correct replay is still shipped: C0 is 50 of 50 at each `k`, and needless refusals are 0.

% source: MEASURED pipeline/results/adversarial/measured_v2.json bounded.cells["C2/k22"].audit_bound.detection_with_replacement=0.9633822894376469
% source: MEASURED pipeline/results/adversarial/measured_v2.json bounded.cells["C2/k22"].detection_rate=1.0
% source: MEASURED pipeline/results/adversarial/measured_v2.json bounded.cells["C3/d2/k22"].detection_rate=0.98
% source: MEASURED pipeline/results/adversarial/measured_v2.json bounded.cells["C3/d5/k22"].detection_rate=0.98
% source: MEASURED pipeline/results/adversarial/measured_v2.json bounded.cells["C3/d20/k22"].detection_rate=0.98
% source: MEASURED pipeline/results/adversarial/measured_v2.json bounded.cells["C2/k100"].detection_rate=1.0
% source: MEASURED pipeline/results/adversarial/measured_v2.json bounded.cells["C3/d2/k100"].detection_rate=1.0
% source: MEASURED pipeline/results/adversarial/measured_v2.json bounded.cells["C3/d5/k100"].detection_rate=1.0
% source: MEASURED pipeline/results/adversarial/measured_v2.json bounded.cells["C3/d20/k100"].detection_rate=1.0
% source: MEASURED pipeline/results/adversarial/measured_v2.json bounded.cells["C0/k1"].correct_ship=50
% source: MEASURED pipeline/results/adversarial/measured_v2.json bounded.cells["C0/k1"].needless_refusal=0
% source: MEASURED pipeline/results/adversarial/measured_v2.json shipped.cells["C0/k1"].correct_ship=50
% source: MEASURED pipeline/results/adversarial/measured_v2.json shipped.cells["C0/k1"].needless_refusal=0

On the nine headline genomes the shipped audit is 2.14% of the stock median and the bounded sample is 6.43%, scaled from the existing verify phase.

% source: MEASURED pipeline/results/adversarial/measured_v2.json server_audit_cost.shipped_fraction_of_stock_median=0.021358068062426384
% source: MEASURED pipeline/results/adversarial/measured_v2.json server_audit_cost.bounded_fraction_of_stock_median=0.06429750013644711
% source: MEASURED pipeline/results/adversarial/measured_v2.json server_audit_cost.n_genomes=9
% source: MEASURED pipeline/results/adversarial/measured_v2.json server_audit_cost.not_a_new_timing_job=true

The Table 3 controls still behave under this code: the DIAMOND known-bad replay and the 22-line replay refuse, the injected 5% drop refuses, and the correct HMMER proteome stays byte-identical with the pads passing.

% source: MEASURED pipeline/results/adversarial/controls_v2.json dx2.refused=true
% source: MEASURED pipeline/results/adversarial/controls_v2.json dx2.fail_mode=pad_hit
% source: MEASURED pipeline/results/adversarial/controls_v2_dx3.json refused=true
% source: MEASURED pipeline/results/adversarial/controls_v2_dx3.json stock_rows=227223
% source: MEASURED pipeline/results/adversarial/controls_v2_dx3.json replay_rows=227205
% source: MEASURED pipeline/results/adversarial/controls_v2_hmmer.json drop_refused=true
% source: MEASURED pipeline/results/adversarial/controls_v2_hmmer.json dropped_models=186
% source: MEASURED pipeline/results/adversarial/controls_v2_hmmer.json correct_passed=true
% source: MEASURED pipeline/results/adversarial/controls_v2_hmmer.json oracle_byte_identical=true
% source: MEASURED pipeline/results/adversarial/confirm_v2.json trials[0].decision=SHIP
% source: MEASURED pipeline/results/adversarial/confirm_v2.json trials[0].reused_rows=0
% source: MEASURED pipeline/results/adversarial/confirm_v2.json trials[0].audit_checked=20

Full writeup: `pipeline/docs/prompts/2026-10-19_w10_report.md` on that branch.

---

## W12a — expert script timing

**Status: INCONCLUSIVE.** Branch `exp/w12a-expert-script`, tip `b9ed4b851a23e80d19fad22cfa5234aef15ff73d`. Staged driver `893b067f1975da20b41076e530e6135eb93a9a0c`.

**Headline:** HMMER tarball path fixed (checksum matched). Pilot `13241867` still PENDING (Priority). No speedup, ratio, or byte-identity. Measured not submitted.

**Controls:** Not executed (job never started).

### Proposed paper sentences (verbatim from W12a)

The CARC timing that was meant to replace the laptop 4.6× expert-script estimate did not run: pilot job 13241867 was still pending, so this paper does not report a TARE speedup, an expert-script speedup, their ratio, or a byte-identity count from W12a.

% source: pipeline/results/baselines_exact/server_pilot_queued.json status = queued
% source: pipeline/results/baselines_exact/server_pilot_queued.json label = INCONCLUSIVE
% source: pipeline/results/baselines_exact/server_pilot_queued.json slurm_job_id = 13241867
% source: pipeline/results/baselines_exact/server_pilot_queued.json walls_are_evidence = false
% source: pipeline/results/baselines_exact/server_pilot_queued.json server_json_written = false

Full writeup: `pipeline/docs/prompts/2026-10-19_w12a_report.md` on that branch.

---

## W12b — iSeqSearch timing

**Status: INCONCLUSIVE.** Branch `exp/w12b-iseqsearch`, tip `5b949cf8ed5c399407b1e4572858df2ee3b97daf`. Declared-pin code `9d57c817ba39840db6aab236c8814d02f303c508`.

**Headline:** Saved classification still **407 / 31377**. Bare-pin pilot returned `REFUSE_PIN` (`total_entry_length: no knob`) — separate arm, not a speed claim. Declared `--dbsize {total_entry_length}` driver staged; confirmation and exclusive measured **not submitted** (node cap). No speed number.

**Controls:** Saved integers match dx_i; classifier known-good/bad; pilot stock-vs-stock; iSeqSearch not byte-identical. Declared-pin refusal control not run.

### Proposed paper sentences (verbatim from W12b)

No timing number is proposed. The exclusive run did not happen, and it did not use the declared `--dbsize` pin.

The saved classification still supports the existing figure sentence (407 of 31,377). Source: `pipeline/results/iseqsearch_timing/reverify_saved.json` `classification.shared_byte_identical=407` `classification.shared_rows=31377`.

Bare-pin pilot, not a speed sentence and not the declared command: TARE returned `REFUSE_PIN` (`total_entry_length: no knob`) and wrote no body. Source: `pipeline/results/iseqsearch_timing/pilot.json` `tare_cold.decision=REFUSE_PIN` `tare_cold.why=total_entry_length: no knob` `controls.tare_returned_stock[0]=false`. The pilot host is an EPYC 7513, 4 threads, one pass, 50 queries.

Full writeup: `pipeline/docs/prompts/2026-10-19_w12b_report.md` on that branch.

---

## W5x — Table 4 on x86

**Status: INCONCLUSIVE.** Branch `exp/w5x-baselines-x86`, tip `59654547606cce30ee01764dddb012e0f2775714`. Harness `e8309972225551ff1d1a4f953e3b34a9c19505ec`.

**Headline:** Protocol and harness staged. Pilot `13241865` still PENDING (Priority). No ρ. Measured not submitted. Do not copy arm64/overhead numbers into Table 4.

**Controls:** Not executed.

### Proposed paper sentences (verbatim from W5x)

None for Table 4 numbers. The current draft’s “not built (x86 only)” for ProcessCache and the arm64 Riker/INCR ratios must not be replaced until `pipeline/results/baselines_x86/measured.json` exists with `systems.<name>.status` = `MEASURED` (or `BLOCKED` with an exact kernel error).

Current honest citation for this session:

```
% source: INCONCLUSIVE pipeline/results/baselines_x86/queued.json label=INCONCLUSIVE pilot_job_id=13241865 pilot_state=PENDING systems.riker.status=NOT_RUN systems.incr.status=NOT_RUN systems.processcache.status=NOT_RUN systems.tare.status=NOT_RUN
```

Full writeup: `pipeline/docs/prompts/2026-10-19_w5x_report.md` on that branch.

---

## WA — unrelated program (pfscanV3)

**Status: INCONCLUSIVE** (`UNRELATED_SHIP: INCONCLUSIVE`). Branch `exp/a-unrelated-ship`, tip `258b20d91a9b38eb82a00ad4964073ab433c2108`. Freeze `01d5745970112232e041ac2b8be0a8421f0e20e8`.

**Headline:** Triggered after W6 BLAST NOT_SHIP. Measured job `13225577` already finished: **8/10 SHIP** with **0** differing lines; **2** genomes INCONCLUSIVE (stock lines 1857 and 1853 &lt; power floor 1906). Pilot PASS cited. Seeds on branch were 20261101–20261103 (locked before WA seed block); disclosed. Not a SHIP claim for the paper’s unrelated-program sentence without a fresh draw.

**Controls:** Pilot known-bad drop refused; identity normalizer; no pin.

### Proposed paper sentences (verbatim from WA)

1. On a locked pfscanV3 command (`--matrix-only --nthreads 1 --output-method 7`), TARE's exact path authorized an update from PROSITE 2026_02 to 2026_03 on eight of ten measured bacterial proteomes with byte-identical bodies and zero differing lines; two genomes were INCONCLUSIVE for missing power (stock body lines 1857 and 1853 below the pilot floor of 1906).
   `% source: pipeline/results/unrelated_ship/measured.json checks.n_ship = 8`
   `% source: pipeline/results/unrelated_ship/measured.json checks.n_differing = 0`
   `% source: pipeline/results/unrelated_ship/measured.json checks.power_floor = 1906`
   `% source: pipeline/results/unrelated_ship/measured.json genomes[0].lines.stock = 1857`
   `% source: pipeline/results/unrelated_ship/measured.json genomes[8].lines.stock = 1853`
   `% source: pipeline/results/unrelated_ship/measured.json outcome = INCONCLUSIVE`

2. The unrelated tool is SIB pftools pfscanV3 (archive tag v3.2.13; binary prints Version 3.2.12), not the HMMER/Infernal tree; the pilot locked an identity normalizer with no pin and a known-bad drop control that refused.
   `% source: pipeline/results/unrelated_ship/pilot.json outcome = PASS`
   `% source: pipeline/results/unrelated_ship/pilot.json version_string = Version 3.2.12 built on Oct 18 2026 at 02:26:00.`
   `% source: pipeline/results/unrelated_ship/pilot.json checks.known_bad_refused = true`
   `% source: pipeline/results/unrelated_ship/measured.json locked_command = pfscanV3 --matrix-only --nthreads 1 --output-method 7 --fasta {reference} {input}`

3. On every genome that cleared the power floor, the 2026_02→2026_03 matrix release reused 1,434 stable entries and scanned 7 fresh ones, matching the full matrix delta between those releases.
   `% source: pipeline/results/unrelated_ship/measured.json genomes[1].release_diff.n_stable = 1434`
   `% source: pipeline/results/unrelated_ship/measured.json genomes[1].release_diff.n_fresh = 7`
   `% source: pipeline/results/unrelated_ship/pilot.json references.2026_02.n_matrix = 1434`
   `% source: pipeline/results/unrelated_ship/pilot.json references.2026_03.n_matrix = 1441`

Full writeup: `pipeline/docs/prompts/2026-10-19_wa_report.md` on that branch.

---

## Hub priorities (suggested)

1. **Merge-ready now (results + copy):** W7, W9, W10; W6 code + follow-up (except Drosophila pending); WA as INCONCLUSIVE / 8-of-10 with power caveat.
2. **Waiting on CARC:** W8 pilot → measured; W12a pilot → measured; W5x pilot → measured; W12b confirm + exclusive measured (declared `--dbsize`); W6 Drosophila JSON; cancel or ignore `13243768` BLAST measured after NOT_SHIP.
3. **Paper:** hub integrates proposed sentences with `% source:` keys; do not invent timing numbers for INCONCLUSIVE workstreams.

## Not for agents (reminder)

- DIAMOND upstream bug report: Josh sends it.
- Only hub edits `pipeline/paper/tare/main.tex`.
