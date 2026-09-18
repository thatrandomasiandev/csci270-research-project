# Formal Definitions and Identification

## Setup

Let \(r^*: \mathcal{S}\times\mathcal{A}\to\mathbb{R}\) be the ground-truth (gold) reward.  
Let \(\{r_{\theta_k}\}_{k=1}^{K}\) be an ensemble of proxy reward models trained from preference data \(\mathcal{D}\) collected under occupancy support \(\mathrm{supp}(\mathcal{D})\subseteq\mathcal{S}\times\mathcal{A}\).  
Write \(\bar r_\theta = \frac{1}{K}\sum_k r_{\theta_k}\) and disagreement
\[
u(s,a) = \mathrm{Var}_k\big(r_{\theta_k}(s,a)\big).
\]
Policy \(\pi\) induces occupancy \(d_\pi\). Episode returns:
\[
R^*(\tau)=\sum_t r^*(s_t,a_t),\qquad
\hat R(\tau)=\sum_t \bar r_\theta(s_t,a_t).
\]

A **frozen window** is an interval of environment steps during which \(\theta\) (hence \(\bar r_\theta\)) is held fixed while \(\pi\) continues to update (PEBBLE between RM updates, or fully frozen proxy SAC).

## Symptom filter

A frozen window is a **proxy–gold divergence symptom window** if, comparing early vs late halves of the window,
\[
\Delta \hat R > \delta_{\hat R}
\quad\text{and}\quad
\Delta R^* < -\delta_{R^*}
\]
for fixed thresholds \(\delta_{\hat R},\delta_{R^*}>0\) (defaults: absolute mean episode return change of 5% of the healthy-task scale, or absolute 5.0 in synthetic units).

Only symptom windows enter the diagnostic evaluation set.

---

## Mode A — RM accuracy decay (OOD / misgeneralization)

**Definition.** In a frozen window, failure is **Decay** if proxy error on on-policy mass grows primarily because \(d_\pi\) leaves preference support:
\[
\mathbb{E}_{d_\pi}\big[|\bar r_\theta - r^*|\big]
\quad\text{increases while}\quad
\mathbb{E}_{d_\pi}\big[\mathbf{1}\{(s,a)\notin\mathcal{N}(\mathrm{supp}(\mathcal{D}))\}\big]
\quad\text{increases,}
\]
and epistemic uncertainty rises:
\[
\mathbb{E}_{d_\pi}[u(s,a)] \uparrow,
\quad
\text{oracle preference accuracy on on-policy probes } \downarrow.
\]

**Operational ground-truth label (Decay protocol):**

1. Restrict \(\mathrm{supp}(\mathcal{D})\) (coverage mask and/or label noise) so \(\mathcal{S}\) is thin.  
2. Optimize \(\pi\) against frozen \(\bar r_\theta\) with weak trust-region / no KL.  
3. Label the run **Decay** iff at symptom time:
   - preference-support novelty \(N(d_\pi;\mathcal{D})\) exceeds threshold \(\tau_N\);
   - on-policy oracle preference accuracy \(< \tau_{\mathrm{acc}}\);
   - ensemble disagreement exceeds \(\tau_u\).

These checks are **pre-registered** for induction validation; the diagnostic classifier is forbidden from using the protocol ID, only measurable signals.

## Mode B — Overoptimization (Goodhart / in-support exploitation)

**Definition.** In a frozen window, failure is **Overopt** if \(\bar r_\theta\) remains calibrated to its *training objective* on the visited region, but that objective diverges from \(r^*\):
\[
\arg\max \bar r_\theta \;\neq\; \arg\max r^*
\quad\text{on a positive-measure set visited by }d_\pi,
\]
while support novelty and disagreement stay low:
\[
N(d_\pi;\mathcal{D})\le \tau_N,\qquad
\mathbb{E}_{d_\pi}[u(s,a)]\le \tau_u,\qquad
\text{held-out preference accuracy on }\mathrm{supp}(\mathcal{D})\text{ remains high.}
\]

**Operational ground-truth label (Overopt protocol):**

1. Construct misspecified teacher reward \(r_{\mathrm{wrong}}\) that equals \(r^*\) on a training manifold \(\mathcal{M}_{\mathrm{train}}\) but diverges on an exploit manifold \(\mathcal{M}_{\mathrm{hack}}\) (e.g., omit a cost; reward a spurious correlate).  
2. Train the proxy ensemble on preferences labeled by \(r_{\mathrm{wrong}}\) (or by \(r^*\) restricted so the spurious correlate is sufficient).  
3. Freeze \(\theta\); optimize SAC hard against \(\bar r_\theta\).  
4. Label **Overopt** iff at symptom time:
   - policy mass on \(\mathcal{M}_{\mathrm{hack}}\) exceeds \(\tau_{\mathrm{hack}}\);
   - \(R^*\downarrow\), \(\hat R\uparrow\);
   - novelty and disagreement remain below thresholds;
   - held-out accuracy on \(\mathcal{M}_{\mathrm{train}}\) stays \(\ge \tau_{\mathrm{acc}}^{\mathrm{hi}}\).

## Negative control — shared blind spots

Train all ensemble members on the **same** misspecification (identical \(r_{\mathrm{wrong}}\)). Overopt can occur with **low** disagreement. Any diagnostic that requires high \(u\) to call Overopt fails this control. This operationalizes Eisenstein et al. (Helping/Herding).

## Identification assumptions

1. **Gold access in simulation:** \(r^*\) is known for evaluation (standard synthetic/gold-RM setup à la Gao).  
2. **Frozen \(\theta\) in symptom windows:** RM parameters do not change during the measured divergence.  
3. **Protocol exclusivity:** Decay and Overopt induction runs are generated from distinct protocols; mixed failures are analyzed separately and excluded from primary AUROC unless labeled `mixed`.  
4. **Measurable support:** Novelty \(N\) is computed via \(k\)-NN distance in \((s,a)\) (or segment embedding) to the preference buffer.

## Diagnostic features (classifier inputs)

For each symptom window, compute feature vector \(\phi\):

| Feature | Notation |
|---------|----------|
| Mean ensemble disagreement | \(\mathbb{E}_{d_\pi}[u]\) |
| Preference-support novelty | \(N(d_\pi;\mathcal{D})\) |
| Held-out preference accuracy | \(A_{\mathrm{hold}}\) |
| On-policy oracle preference accuracy | \(A_{\mathrm{on}}\) |
| Fixed-reference preference accuracy | \(A_{\mathrm{ref}}\) |
| Mean action entropy | \(H[\pi]\) |
| KL to init policy | \(\mathrm{KL}(\pi\|\pi_{\mathrm{init}})\) |
| Hack-manifold mass (analysis only; **not** for primary classifier) | \(m_{\mathrm{hack}}\) |

Primary classifier uses only features available without knowing \(\mathcal{M}_{\mathrm{hack}}\) (exclude \(m_{\mathrm{hack}}\)). Report AUROC for Decay vs Overopt.

## Decision rule (baseline)

Logistic regression / linear score on standardized \(\phi\) trained on a subset of seeds; evaluate on held-out seeds and envs. Ablate each feature family.
