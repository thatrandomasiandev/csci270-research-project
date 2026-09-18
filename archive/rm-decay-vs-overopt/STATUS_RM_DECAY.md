# Status: Target vs Current

**Project:** Separating Reward-Model Accuracy Decay from Overoptimization  
**Standard of work:** arXiv / PhD-application quality (not a course-grade optimization)  
**Status date:** 2026-09-08 ~21:07 PDT  
**Repo (local):** `/Users/joshuaterranova/Desktop/CSCI270/Research Project`  
**Repo (CARC):** `/project2/biyik_1165/jjt_373/rm-decay-vs-overopt`

This document is the working scoreboard: what “done” means for a publishable paper, versus what exists right now. It is intentionally detailed so you can resume cold without re-deriving context.

---

## 1. One-sentence scoreboard

| Dimension | Target | Current |
|-----------|--------|---------|
| Intellectual claim | Causal separation of **RM accuracy decay** vs **SAC overoptimization** under frozen imperfect proxies, with diagnostics + mode-conditional fixes | Claim is written and operationalized in code/docs; **not yet proven at scale with finished CARC stats** |
| Code | Reproducible training + diagnostics + CARC + analysis | **Largely built** (synthetic point-mass stack) |
| Experiments | Multi-seed × multi-env × protocols × mitigations on CARC | **Submitted; 90/90 still pending**; smoke succeeded |
| Analysis | AUROC, ablations, figures, mitigation tables | Scripts exist; **no final `results/summary.json` / figures from full CARC pull** |
| Paper | Conference-quality LaTeX + appendix, numbers filled | **Draft skeleton** with TBD result tables |
| Public artifact | arXiv + code release | **Not submitted**; git exists locally |

**Overall phase:** *Instrumentation + induction designed; cluster compute queued; analysis/paper blocked on results.*

---

## 2. Research target (what you want)

### 2.1 Core scientific claim

When a frozen proxy reward rises while true performance falls (\(\hat R \uparrow, R^* \downarrow\)), two distinct mechanisms can produce the **same symptom**:

1. **RM accuracy decay (OOD / misgeneralization)**  
   The policy leaves preference support; \(r_\theta\) becomes unreliable (high epistemic uncertainty / disagreement, preference-accuracy collapse on shifted states).

2. **Overoptimization (Goodhart / in-support exploitation)**  
   The RM remains confident but systematically wrong; SAC exploits a fixed flaw (especially under shared ensemble blind spots).

**Publishable bar is not** “we saw proxy↑ true↓.” That is already known (Gao et al., industry RLHF lore).  
**Publishable bar is:**

- Formal definitions with identification assumptions  
- Causal induction of each mode **by construction**  
- A multi-signal diagnostic evaluated as a **classifier (AUROC)**, not vibes  
- Explicit failure case: **shared blind spots** (Helping or Herding)  
- **Mode-conditional mitigations** (wrong fix fails; right fix helps)  
- Multi-seed, multi-env statistics suitable for conference review  

### 2.2 Contribution checklist (abstract-ready targets)

| # | Contribution | Done? |
|---|--------------|-------|
| 1 | Formalization of Decay vs Overopt under frozen proxies | **Docs yes** / paper draft partial |
| 2 | Identifying interventions with ground-truth labels | **Code yes** / large-scale validation pending |
| 3 | Multi-signal diagnostic + AUROC evaluation | **Code yes** / numbers pending |
| 4 | Mode-conditional mitigation experiments | **Jobs submitted** / results pending |
| 5 | Shared-blind-spot negative control + multi-env evidence | **In sweep design** / results pending |

### 2.3 Explicit non-goals (still in force)

- Not optimizing for CSCI 270 grading  
- Not rebranding LIRALab Walker PEBBLE sweeps as this paper’s contribution  
- Not claiming LLM alignment SOTA without a real LLM study  
- Not shipping “disagreement alone ⇒ decay” as the story (that is undergraduate / refuted by Helping or Herding)

### 2.4 Stretch (after core works; not started)

- Small LLM / synthetic-gold-RM toy repeating the same diagnostic (Gao-style) to show domain transfer  

---

## 3. Target experimental design vs what is running

### 3.1 Target design (from plan)

| Factor | Target | Implemented in jobs? |
|--------|--------|----------------------|
| Domains | ≥3 continuous-control tasks | **3 synthetic variants** (`point_mass`, `point_mass_tight`, `point_mass_wide`) — **not** yet Walker/Quadruped/DM Control |
| Seeds | ≥5 per primary cell | **Yes (0–4)** |
| Protocols | Oracle, Decay, Overopt, Shared-blindspot | **Yes** |
| Mitigations | Uncertainty penalty, KL, more prefs (mode-conditional) | **Yes** (on `point_mass` only) |
| Horizon | Paper-scale training | **25k frozen-proxy steps** after preference fit (synthetic; short by design) |
| Ensemble | Size 3–5; independent vs shared init | **K=3**; shared init for blindspot protocol |
| Compute | CARC SLURM arrays | **Submitted** |

### 3.2 Exact CARC job matrix (what 90 means)

**Smoke** `11829979` — **COMPLETED** (00:01:11)

**Baseline** `11829980` — array `0–59` = **60 tasks**

\[
3\ \text{envs} \times 4\ \text{protocols} \times 5\ \text{seeds} = 60
\]

**Mitigations** `11829981` — array `0–29` = **30 tasks**

\[
2\ \text{protocols (decay, overopt)} \times 3\ \text{mitigations} \times 5\ \text{seeds} = 30
\]

**Live queue (as of status date):** **90 PD (Priority), 0 running.** Start estimates `N/A`.  
Priority score ~3129 (top pending on cluster often ~8k–10k). Lab account already has substantial GPU usage.  
**ETA:** compute per task ~3–6 min once scheduled; **wall-clock dominated by queue** — realistic finish **overnight / by morning**, not tonight for sure.

### 3.3 Gap vs PhD-plan “≥3 envs”

| Wanted | Current |
|--------|---------|
| DM Control / Meta-World style domains (walker, quadruped, …) for external validity | Synthetic 2D point-mass suite only |
| PEBBLE-style intermittent RM freezes on deep control | Fully frozen proxy after one preference phase on toy env |
| Optional LLM toy | Not started |

**Interpretation:** The current stack is the right **identification sandbox** (clean causal labels). It is **not yet** the full external-validity half of a top-venue paper. Plan order was correct: prove induction + diagnostic on controllable env first; then port.

---

## 4. Target artifacts vs files on disk

### 4.1 Documentation

| Artifact | Target | Current path / status |
|----------|--------|------------------------|
| Related-work lock-in | Contribution table vs Gao, Helping/Herding, InfoRM, AdvPO, URM, PEBBLE/B-Pref, Goodhart, misgen vs gaming | [`docs/RELATED_WORK.md`](docs/RELATED_WORK.md) — **done** |
| Formal definitions + identification | Modes, symptom filter, GT checks, classifier features | [`docs/FORMALIZATION.md`](docs/FORMALIZATION.md) — **done** |
| This status board | Living target vs current | [`STATUS.md`](STATUS.md) — **this file** |
| README | Reproduce + context | [`README.md`](README.md) — present; will need results section after pull |

### 4.2 Source code

| Module | Target role | Current |
|--------|-------------|---------|
| `src/envs/point_mass.py` | Gold \(r^\star\), misspecified \(r_{\mathrm{wrong}}\), support mask, hack manifold, 3 env variants | **Done** |
| `src/sac.py` | SAC + entropy/KL-to-init + uncertainty penalty + KL coef | **Done** |
| `src/reward_model.py` | Ensemble preference RM, held-out / fixed-ref buffers, disagreement | **Done** |
| `src/protocols.py` | Oracle / Decay / Overopt / Shared-blindspot configs | **Done** |
| `src/diagnostics.py` | Novelty, symptom helpers, feature dataclass | **Done** |
| `src/train.py` | Full loop, frozen proxy, logging `summary.json` / `window.csv` / `features.jsonl` | **Done** |
| `src/run_sweep.py` | Local parallel sweeps | **Done** (superseded by CARC for main runs) |
| `analysis/evaluate_diagnostic.py` | Leave-one-seed-out AUROC + ablations + mitigation aggregates | **Done** (needs CARC results) |
| `analysis/plot_results.py` | Boxplots, diagnostic plane, AUROC bars | **Done** (needs CARC results) |

### 4.3 CARC / ops

| Artifact | Target | Current |
|----------|--------|---------|
| `carc/env.sh` | Account, paths, conda | **Done** (`rm-decay-vs-overopt`, falls back to `bpref`) |
| Sync script | Push code to project storage | **Done** (uses `discovery`; transfer node needs Duo) |
| Smoke / baseline / mitigation jobs | Reproducible arrays | **Done + submitted** |
| Dashboard | Live queue UI | **Done** at **http://127.0.0.1:8767** (`carc/dashboard/`) |

### 4.4 Paper

| Artifact | Target | Current |
|----------|--------|---------|
| `paper/main.tex` | ~9–10pp main + appendix, filled tables/figures | **Draft** — structure + claims; **TBD numbers**; figures referenced but not yet generated from full sweep |
| `paper/refs.bib` | Core citations | **Seed bib present** (some entries still “Anonymous” placeholders to clean) |
| `paper/main.pdf` | Compilable PDF | **Exists** from an earlier compile; **not final** |
| arXiv submission | Public preprint + code | **Not started** |

### 4.5 Results

| Artifact | Target | Current |
|----------|--------|---------|
| `results/raw/**/summary.json` | One per cell (90+ smoke) | **Local partial pilots** from earlier aborted local sweep (~32 dirs); **CARC raw almost empty** until jobs run |
| `results/summary.json` | Aggregated AUROC report | **Missing** |
| `results/figures/*.png` | Protocol boxplots, diagnostic plane, AUROC, ablations | **Missing / empty** |
| Versioned checksums of CARC pull | Reproducibility | **Missing** |

---

## 5. Plan todo list — target completion vs reality

| Todo ID | Target | Status now |
|---------|--------|------------|
| `lit-positioning` | Lock contribution vs prior art | **Complete** (`docs/RELATED_WORK.md`) |
| `formalize-modes` | Formal defs + GT labels | **Complete** (`docs/FORMALIZATION.md`) |
| `scaffold-repo` | Repo layout + CARC smoke path | **Complete** |
| `instrument-diagnostics` | Disagreement, novelty, entropy, KL, accuracy probes, frozen-window logs | **Complete in code** |
| `induce-both-modes` | Decay + Overopt protocols with verifiable checks | **Complete in code**; pilot evidence mixed but separable features observed; **awaiting multi-seed confirmation** |
| `pilot-conditions` | Pilots until both modes reliably appear | **Partial** — local pilots run; Decay strong (high OOD, low held-out); Overopt via analytical \(r_{\mathrm{wrong}}\) shows hack mass; symptom heuristic not always firing; needs CARC seeds |
| `carc-full-sweep` | Multi-seed × ≥3 envs factorial on CARC | **Submitted, not finished** (90 PD) |
| `mode-conditional-fixes` | Wrong vs right mitigations | **Jobs submitted, not finished** |
| `analyze-stats` | AUROC, CIs, ablations, failure cases | **Blocked on results** |
| `write-arxiv` | Final paper + code release | **Draft only; blocked on results** |

---

## 6. Scientific readiness detail (what “good pilots” already showed)

Local/pilot runs (not the final CARC stats) already suggested the induction is *directionally* working:

| Protocol | Desired signature | Pilot observation (illustrative, seed 0) |
|----------|-------------------|------------------------------------------|
| Oracle | Proxy ≈ true; healthy held-out acc | Proxy/true coupled (~−54); held-out high |
| Decay | High novelty / OOD; held-out collapse; true collapses | OOD mass ~0.8; held-out ~0.42; true ~−128 |
| Overopt | High hack mass; held-out stays high; lower OOD than decay | Hack mass ~0.44; held-out ~0.92; OOD ~0.19 |
| Shared blindspot | Same exploit, **disagreement ≈ 0** | Disagreement **0.0** with hack mass elevated |

**Remaining scientific risks (must resolve after CARC):**

1. Soft “symptom window” filter is brittle on this reward scale — primary evaluation should use **protocol labels** (as designed), with symptom as secondary.  
2. Overopt uses analytical \(r_{\mathrm{wrong}}\) as the SAC proxy (`proxy_source=wrong`) for airtight Goodhart; paper must be crystal clear that the **ensemble is for diagnostics**, not always the optimized scalar.  
3. Need AUROC ≫ 0.5 with leave-one-seed-out; if novelty alone dominates, ablations must say so honestly.  
4. Mitigation asymmetries must show up in true return; if not, either protocols or mitigation strengths need retuning **before** claiming actionability.  
5. External validity: synthetic ≠ Walker. Plan still requires a later deep-control port for a stronger PhD narrative.

---

## 7. Infrastructure status

| Item | Target | Current |
|------|--------|---------|
| SSH `discovery` | BatchMode from Mac | **Works** |
| Sync | Code on `/project2/.../rm-decay-vs-overopt` | **Synced** |
| Conda | Runnable train with torch+cuda on GPU nodes | Uses **`bpref`** (torch 2.7.1+cu118); dedicated `rmdiag` env not required yet |
| Dashboard | Local UI | **Running** on port **8767** |
| Local sweeps | Optional | **Stopped on purpose** when moving to CARC (do not restart locally for the main 90) |

---

## 8. What “finished” looks like (acceptance criteria)

You can call the **core paper package** ready for arXiv when **all** of the following are true:

1. **CARC baseline complete:** ≥5 seeds × 3 envs × 4 protocols with `summary.json` pulled and checksummed.  
2. **CARC mitigations complete:** decay/overopt × 3 mitigations × 5 seeds pulled.  
3. **Analysis:** `results/summary.json` reports full-model AUROC and feature ablations; figures written under `results/figures/`.  
4. **Induction validation:** pre-registered GT checks pass at rates you are willing to defend in the paper (report failures).  
5. **Mitigation story:** at least one clear asymmetry (e.g., more prefs helps decay more than overopt; KL/uncertainty pattern consistent with theory / Helping-Herding).  
6. **Paper:** numbers filled, Related Work accurate, limitations honest, bib cleaned, PDF polished.  
7. **Reproducibility:** README one-liner for sync → sbatch → pull → analyze.  
8. **(PhD stretch, optional for v1 arXiv):** second domain class (DM Control or LLM toy) or a clear “future work” that doesn’t overclaim.

Until (1)–(3) land, the project is **engineering-complete / science-incomplete**.

---

## 9. Immediate next actions (ordered)

1. **Wait for CARC** arrays `11829980` / `11829981` (monitor dashboard).  
2. **Pull results** from Discovery → local `results/raw/`.  
3. Run:
   ```bash
   python3 analysis/evaluate_diagnostic.py --root results/raw --out results/summary.json
   python3 analysis/plot_results.py --root results/raw --summary results/summary.json
   ```
4. **Interpret:** if AUROC weak or mitigations flat, retune protocols / mitigation coeffs and resubmit a **delta** array (do not silently rewrite history).  
5. **Fill paper tables/figures** from `summary.json`.  
6. Only then: arXiv packaging + public code cleanup.

---

## 10. Honest summary for you

**What you wanted:** a PhD-grade, arXiv-bound separation of RM decay vs overoptimization — formal, causal, multi-seed, multi-env, diagnostically evaluated, with mode-conditional fixes and a shared-blind-spot failure analysis.

**Where you are:** the **intellectual and software scaffold is in place**; pilots look promising; **the decisive evidence is sitting in a 90-task CARC queue that has not started running yet**. Paper and analysis are deliberately hollow until those jobs finish.

**Closest accurate label:** *Phase: queued for confirmatory compute.* Not blocked on ideas; blocked on GPUs.
