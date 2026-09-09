# Related Work Positioning Memo

**Project:** Separating Reward-Model Accuracy Decay from Overoptimization  
**Purpose:** Lock contribution claims before experiments (arXiv / PhD bar)

## Core claim

The shared symptom \(\hat R \uparrow, R^* \downarrow\) under a frozen imperfect proxy reward model conflates two mechanistically distinct failures:

1. **RM accuracy decay (misgeneralization / OOD):** policy occupancy leaves preference support; \(r_\theta\) becomes unreliable.
2. **Overoptimization (Goodhart / exploitation):** \(r_\theta\) remains confident but systematically wrong; the optimizer exploits a fixed flaw.

Prior work measures or mitigates “reward hacking / overoptimization” as a single phenomenon. We provide **causal identification**, a **multi-signal diagnostic evaluated as a classifier**, and **mode-conditional mitigations**.

---

## Prior art map

### Gao et al., 2023 — *Scaling Laws for Reward Model Overoptimization*

- **What they do:** Synthetic gold RM labels a proxy; track gold vs proxy vs KL under RL and best-of-\(n\).
- **Result:** Predictable overoptimization curves; larger RMs / more data help; RL is KL-inefficient vs BoN.
- **Gap we fill:** They characterize *severity* of proxy–gold divergence, not whether divergence is driven by **OOD RM failure** vs **in-support exploitation**. No diagnostic classifier, no mode-conditional fixes.

### Eisenstein et al., 2024 — *Helping or Herding?* (CoLM)

- **What they do:** RM ensembles at train/inference time for LLM alignment.
- **Result:** Ensembles mitigate hacking but **do not eliminate** it when members share systematic errors; underspecification + distribution shift.
- **Gap we fill / motivation:** Agreement ≠ safety. Undergraduate “disagreement ⇒ decay, agreement ⇒ overopt” is false under shared blind spots. We treat shared-blind-spot ensembles as a **required negative control** and use richer signals (support novelty, accuracy probes, policy geometry).

### Coste et al., 2023 / AdvPO (2024) / URM (2024) / InfoRM (NeurIPS 2024)

- **What they do:** Uncertainty penalties, adversarial robust policy opt, uncertainty-aware RMs, information-bottleneck RMs to *mitigate* overoptimization / misgeneralization.
- **Gap we fill:** Mitigation without **causal mode labels**. We evaluate whether mitigations help **conditionally** on the true mode (wrong fix fails).

### Lee et al. — PEBBLE (ICML 2021) / B-Pref (NeurIPS 2021 D&B)

- **What they do:** Preference-based RL with intermittent RM updates; ensemble disagreement sampling; Mistake/Oracle teachers; continuous-control benchmarks.
- **Gap we fill:** Frozen windows between updates are ideal for separating RM change from RL amplification—but standard logs do not. We instrument frozen windows, induce both modes, and evaluate diagnostics against ground truth.

### Goodhart taxonomy (Manheim & Garrabrant) / specification gaming vs goal misgeneralization

- **What they do:** Conceptual splits among failure mechanisms (regressional, extremal, causal, adversarial Goodhart; specification gaming vs misgeneralization).
- **Gap we fill:** Operationalize an analogous split for **frozen learned reward models in deep RL** with measurable tests and experimental induction protocols.

### Skalse et al. / reward hacking definitions; Casper et al. open problems in RLHF

- **Relevance:** Vocabulary and open-problem framing. Our contribution is empirical identification methodology, not a new definition paper.

---

## Contribution bullets (abstract-ready)

1. **Formalization** of Decay vs Overopt under intermittent and fully frozen proxy RMs.
2. **Identifying interventions** that assign ground-truth mode labels by construction.
3. **Multi-signal diagnostic** (ensemble disagreement, preference-support novelty, accuracy probes, policy entropy/KL) evaluated with AUROC against those labels.
4. **Mode-conditional mitigation** experiments showing asymmetric outcomes.
5. **Failure analysis** for shared-blind-spot ensembles (Helping/Herding link) and multi-seed, multi-env evidence.

## What we explicitly do *not* claim

- LLM alignment SOTA without a real LLM study (optional synthetic LLM toy is stretch-only).
- That ensemble disagreement alone identifies the mode.
- That we are the first to observe \(\hat R \uparrow, R^* \downarrow\).

## Citation anchors (bib keys)

- `gao2023scaling`
- `eisenstein2024helping`
- `lee2021pebble`, `lee2021bpref`
- `coste2023reward`, `advpo2024`, `urm2024`, `inform2024`
- `manheim2018categorizing`
- `langosco2022goal` (goal misgeneralization)
- `krakovna2020specification` (specification gaming)
