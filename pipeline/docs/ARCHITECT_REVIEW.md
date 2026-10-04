# Architect review — ACTS record memoization under the PC standard

**Written:** 2026-10-03, at `6b5bd23`. This is a review, not a protocol. It
changes no locked text and runs no tools.

Every number is labelled **MEASURED** (committed source given) or
**PROJECTED** (formula and assumptions given). The arithmetic for derived
shares comes from the fitted parameters in the cited file, with nothing
re-timed. Items marked **PROPOSED** have not been pre-registered. If one is
adopted, it needs its own protocol before it runs.

The standard applied here is the six-ability brief in
[`AGENTS.md`](../../AGENTS.md#review-standard-principal-architect--pc-chair).

---

## 1. Cost decomposition and the Amdahl target

The repo's model (`acts/predict.py:127`) covers one run over $N$ records
with miss fraction $m$:

$$T_\text{stock} = a + bN, \qquad T_\text{cached} = a + b\,mN + w, \qquad T_\text{first} = T_\text{cached}\big|_{m=1} + P$$

Here $w$ is the total wrapper overhead per run (parse, hash, lookup, splice,
reassemble), and $P$ is the one-time inference cost
$P = \sum_i (a + b\,n_i)$ over the probe calls.

| Tool / mode | $a$ (s) | $bN$ (s) | $w$ (s) | $P$ (s) | Dominant | Source |
|---|---|---|---|---|---|---|
| hmmscan `--cut_ga`, $N=4192$ | 31.96 (1.0%) | 3030.2 (99.0%) | 0.019 | 615.8 (batched, `probe_n=8`) = 0.20 stock runs | **$bN$** | MEASURED fits, `results/hmmer_predicted_speedup_with_probe.json` |
| hmmsearch, $N=4192$ | 132.56 (21.0%) | 498.4 (79.0%) | 0.018 | 2392.7 = **3.79 stock runs** | $bN$ per run; **$P$ over the first few runs** | same |
| SnpEff 5.4c, $N=52{,}638$ (Mac fit) | 8.91 (66.8%) | 4.44 (33.2%) | 0.044 (`cat` stand-in) | not timed | **$a$** | MEASURED fit, `results/snpeff_timing_fit.json` |
| SnpEff, CARC exclusive | $a_\text{now}$ = 15.98 | — | — | — | **$a$** | MEASURED, `results/snpeff_alternating_carc.json` |
| SQLite cache lookup+save | — | — | ≈3.6–4.0 µs/record | — | — | MEASURED (Mac, indicative), `results/cache_scale.json` |

**Readings.**

1. **The cache can only remove $b(1-m)N$.** Even with every record a hit,
   the speedup is capped at $(a+bN)/(a+w)$:
   - hmmscan: **95.8×** (PROJECTED).
   - hmmsearch: **4.76×** (PROJECTED).
   - SnpEff: **1.49×** from the Mac fit (PROJECTED). The repo's ≈1.3× uses
     the CARC $a_\text{now}$. The measured CARC result is **1.167×**.

   SnpEff is dominated by startup ($a$), so record memoization is the wrong
   lever there. That is a result, not a failure, and the paper should say so
   with the formula.
2. **For hmmsearch, $P$ is mostly startup cost.** The batched schedule makes
   18 calls, and $18a = 2386.0$ s, which is **99.7%** of
   $P = 2392.7$ s. Shrinking probe *records* is therefore banned work. The
   only levers are fewer calls or amortizing $a$ across calls. At
   `probe_n=8`, singleton probing (12 calls, 1595.4 s) beats batched probing
   (18 calls). `OPEN_REQUESTS.md` already records this.
3. **Optimizing $w$ is banned work at current scale.** Against hmmscan's
   $b = 0.72$ s/record, the wrapper's ≈4 µs/record lookup is about $5\times10^{-6}$
   of that cost. Leave SQLite, hashing and splicing alone unless a tool turns
   up with $b$ in the µs range.

**Amdahl target for the paper:** the $b\cdot n$ term on tools where
$bN \gg a$, with $P$ reported as an amortized one-time cost. The screen
rule should keep rejecting tools where $a$ dominates ($a/(a+bN) > 0.5$)
instead of trying to rescue them.

---

## 2. The core unowned abstraction

**Primitive: content-keyed record function with pass-through splice.**

A record stream is $X = (x_1,\dots,x_n)$, produced by a per-format parser
$\pi$ (split on delimiters). Each record's fields split three ways:

- **key fields** $K$: the output depends on them.
- **pass-through fields** $U$: the tool only copies them into the output.
- **produced fields** $O$: the tool computes them from $K$.

The tool is treated as a black box. The system learns $K$ and $U$ by
perturbation, caches $h(x|_K)$, and on a hit splices the *new* record's
$x|_U$ back around the cached $O$.

This is what the 2026 neighbors do not do:

- **INCR** (OSDI 2026) and **Caruca** (arXiv 2510.14279) reuse or split by
  *bytes* or by *annotated statelessness*. Neither infers which part of a
  record the output depends on (`docs/RELATED_WORK.md`, `6b5bd23`).
- **Riker, Rattle and ProcessCache** key on whole files.

**Why the key, not the record, is the unit (MEASURED,
`results/content_key_overlap.json`).** Byte-key recall divided by
inferred-key recall:

| Workload | Byte / inferred recall | Reading |
|---|---|---|
| VCF HG00096 ∪ HG00097 → HG00099 | **0.557** (0.438 / 0.787) | Byte keys lose 44% of reuse to per-sample ID/QUAL/INFO pass-through. |
| GenBank *E. coli* proteomes, $k=1..6$ | **0.00** at every $k$ | Identical sequences carry per-submission IDs, so byte reuse is zero. |
| RefSeq control, $k=9$ | 0.998 | Shared `WP_` accessions hide the effect, as pre-registered. |

The pre-registered kill rule (ratio ≥ 0.9 on both VCF and GenBank) **did
not fire**.

**Cross-domain applicability.** Tested and hypothesized domains are kept
apart:

| Domain | Format primitive | Status |
|---|---|---|
| Genomics: variant annotation (SnpEff, `bcftools +fill-tags`) | VCF line; $K$ = CHROM POS REF ALT (+SAMPLES after widening) | **TESTED**: MATCH on 52,638 records; fill-tags MATCH (`results/inference_checks.json`) |
| Proteomics: profile search (hmmscan, hmmsearch) | FASTA record → table rows; $K$ = sequence hash, description = pass-through | **TESTED**: hmmscan byte MATCH; hmmsearch whitespace MATCH only (`results/inference_fasta_reuse_bytes.json`) |
| Plain line transformers | newline record | **TESTED** wiring only (`line_memo` fixture). Not a paper result. |
| Cheminformatics (Mordred on SMILES lines, `--kind linetable`) | line → table row; $K$ = SMILES, name = pass-through | **HYPOTHESIZED**: run skipped on install size (227 MB > cap); CARC job written, not submitted |
| Speech (Whisper per-clip) | `--kind files` | **HYPOTHESIZED**: job BLOCKED |
| Log transformers / static-analysis linters | line or file record; timestamp/path = pass-through | **HYPOTHESIZED**. ruff was *rejected* in the tool screen: own per-file cache, 0.7 s job, $w$ omitted (`results/tool_screen.json`). |

**Borrowed mechanisms, credited and not claimed as novel:**

- **Group testing / adaptive batching** for subset-invariance: 1+2+4+8
  batches, cost independent of `probe_n` (`427fcbb`). This is Chen/Segura
  metamorphic-testing cost reduction.
- **Property testing** for determinism and shuffle invariance.
- **Dune** `cache-check-probability` for the hit audit.

The novelty claim is only the inferred content key plus splice.

---

## 3. Formal model and invariants

**Definitions.** Let $\mathcal{X}$ be the record space, and let
$\pi : \text{bytes} \to \mathcal{X}^*$ and
$\rho : \mathcal{Y}^* \to \text{bytes}$ be the format parser and printer.
Write $T$ for the tool, treated as a function of its argv-named inputs only.
Fix a field partition $(K, U)$ of $\mathcal{X}$ and a MATCH relation
$\equiv$, which is one of: byte, order, multiset, or record-body
(`docs/INFERENCE_PROTOCOL.md`).

**Invariants.** For all $X$ in the argv-named input domain:

- **I1 Determinism:** $T(X) \equiv T(X)$.
- **I2 Order independence:** for every permutation $\sigma$,
  $\pi(T(\sigma X)) = \sigma\,\pi(T(X))$, up to $\equiv$.
- **I3 Subset invariance:** for every sub-stream $S \subseteq X$,
  $\pi(T(S)) = \pi(T(X))\big|_S$.
- **I4 Key sufficiency:** there exist $g$ and a splice operator $\oplus$
  such that $\tau(x) = g(x|_K) \oplus x|_U$ for every record $x$.

**Proposition (soundness of reassembly).** If I1–I4 hold, the cache $C$
maps $h(x|_K) \mapsto g(x|_K)$ for keys produced by earlier runs, and
misses $M \subseteq X$ go through $T$ in one call. Then

$$\rho\Big(\big[\,C[h(x|_K)] \oplus x|_U \;\text{if hit, else}\; \pi(T(M))_x\,\big]_{x\in X}\Big) \;\equiv\; T(X).$$

*Proof sketch.* By I3 and I2, $T$ restricted to $M$ gives each miss record
the same output it has inside $T(X)$, in an order recoverable by position.
By I4, a hit's output depends only on $x|_K$, which $C$ holds through the
injective-in-practice hash $h$, and on $x|_U$, which comes from the new
input. By I1, the cached value equals what $T$ would produce now.
Concatenating in input order gives $T(X)$ up to $\equiv$. ∎

This assumes $h$ has no collisions and that $T$ reads no inputs outside
argv. That second assumption is fault class F6, which is outside the
guarantee.

**What the probes actually give.** I1–I4 cannot be decided from a black
box. They are tested on finite samples. Suppose a fault fires
independently on a fraction $p$ of records and $n$ probe records are drawn.
Then

$$\Pr[\text{probe misses fault}] = (1-p)^n.$$

For $p=0.01$ and $n=50$, this is **0.605** (PROJECTED, closed form). That
is consistent with the one in-scope miss in the first probe-eval round:
`vcf F4` at $p=0.01$, `probe_n=50` (MEASURED, `results/probe_eval.json`).
The deployed audit re-runs each hit with probability $q$. A fault that
touches $h$ hits escapes the audit with probability $(1-q)^h$. These are
the only probabilistic statements the paper should make. Do not claim a
theorem beyond them.

**Runtime bounds** (from §1). Speedup at run $k$ with hit fraction
$\alpha_k = 1 - m_k$:

$$S_k = \frac{a + bN}{a + b(1-\alpha_k)N + w}, \qquad S_k > 1 \iff b\,\alpha_k N > w.$$

The cumulative speedup over $K$ runs, with inference paid once, is

$$S_\text{cum}(K) = \frac{\sum_k (a + bN_k)}{P + \sum_k \big(a + b(1-\alpha_k)N_k + w\big)}.$$

The break-even number of runs against the probe cost is the smallest $K$
with $\sum_{k\le K} b\,\alpha_k N_k \ge P + Kw$.

**Probe cost for an $a$-heavy tool.** With $c$ calls,
$P = c\,a + b\sum_i n_i$, and $P \to c\,a$ when $b$ is small. For
hmmsearch, $c\,a/P = 0.997$ (MEASURED inputs, §1). So $c$ is the design
variable, and group-testing schedules should be judged by calls, not by
records.

---

## 4. Algorithm specification

This describes what is on disk (`acts/infer_vcf.py`, `acts/infer_fasta.py`,
`acts/cache.py`, `acts/audit.py`), restated in generic primitives.

```
INFER(T, X, probe_n):                                 # once per (tool, argv, format)
  S ← sample(X, probe_n)
  if T(S) ≢ T(S)                         → REFUSE_NONDETERMINISTIC     # I1 (F1, F7)
  if π(T(σS)) ≠ σ π(T(S))                → REFUSE_NEIGHBORS            # I2 (F2, F8)
  for B in batches(S, 1,2,4,8):                                         # I3, c = 15 calls
     if π(T(B)) ≠ π(T(S))|_B             → REFUSE_GLOBAL               # (F3)
  K ← all fields; U ← ∅
  for field f in record schema:                                         # I4, field roles
     S' ← S with f perturbed per record
     if π(T(S')) differs only in copies of f   → U ← U ∪ {f}           # pass-through
     elif produced fields change               → keep f ∈ K            # key (widen)
  late-key probe: first miss batch carrying fields unseen in S → repeat I4 on them (F5)
  if some produced field still varies with no attributable field → REFUSE_AMBIGUOUS
  return contract(K, U, produced-field order, MATCH relation)

RUN(T, X, contract, cache, q):
  for x in π(X): hit/miss on h(x|_K)
  if miss_frac ≥ 0.95                    → REFUSE_DUPS_RARE (a whole-command cache does as well)
  Y_M ← π(T(misses))                                                    # one tool call
  for x in X: y_x ← hit ? cache[h(x|_K)] ⊕ x|_U : Y_M[x]
  with prob q per hit: re-execute; on disagreement → REFUSE_AUDIT
  first run on this contract: require ρ(y) ≡ T(X)  else REFUSE_MATCH
  cache ← cache ∪ {h(x|_K) ↦ y_x|_O : x ∈ misses}
  return ρ(y)
```

**Inference vs. refusal.** This is the line that Gemini's probe-cost answer
blurred.

| Observation | Treated as | Action | Fault class |
|---|---|---|---|
| Output changes after perturbing $f$, but only where $f$ is copied | **inference** | $f \in U$; splice on hit | (normal; VCF `ID`, `QUAL`, `INFO/AF`…) |
| Produced fields change after perturbing $f$ | **inference** | widen $K$ to include $f$ | F4, F5; fill-tags widened to `SAMPLES` (`results/inference_checks.json`) |
| Same input, different output | **refusal** | `REFUSE_NONDETERMINISTIC` | F1, F7 |
| Output depends on neighbors or order | **refusal** | `REFUSE_NEIGHBORS` | F2, F8 |
| Output depends on stream size or global state | **refusal** | `REFUSE_GLOBAL` | F3 |
| Output depends on non-argv state (env, unnamed files) | **limitation** | outside guarantee; Linux file tracing partial | F6 |

---

## 5. PC red-team audit

### Attack 1: "INCR plus Caruca already does this. It is engineering."

*Threat:* both are OSDI/arXiv 2026 work from the same group. A reviewer
reads ACTS as INCR's chunk memo combined with Caruca's splittability.

*Defense on disk:* the content-key kill test, described in §2. Byte reuse
is 0.557 of inferred reuse on VCF and 0.00 on GenBank (MEASURED). Neither
paper infers $K$ vs $U$ (`RELATED_WORK.md`).

*Still required:*

- **PROPOSED: run INCR head-to-head.** Use hmmsearch on genome $k+1$ after
  genomes $1..k$, with INCR's stateless annotation supplied by hand
  (favoring INCR).
- **Prediction:** INCR's chunk hits are bounded by byte recall, which is 0
  on GenBank. So ACTS hits should be at least INCR's on every input, and
  strictly greater on GenBank.
- This is the "Running baselines" box in `STATUS.md`. Without it the
  delta is argued, not shown.

### Attack 2: "Speedups are small, startup-capped, and come from one tool."

*Threat:* the only timed, exclusive result is SnpEff at **1.167×**
(MEASURED, CARC job 12345442). hmmscan **2.96× / 3.12×** cumulative is
PROJECTED (`results/confirm_predictions.json`, locked before data). The
savings jobs 12394300/01/503/504 have not been collected.

*Defense:* the decomposition in §1 predicts which tools win. The CARC
check (predicted 1.203× vs measured 1.167× for SnpEff) shows the model is
calibrated before any cache is built.

*Still required:*

1. Collect the savings jobs and run the pre-registered confirmatory
   hmmscan. Report against the locked predictions even if they miss.
2. **PROPOSED zero-hit overhead experiment.** Report $T_\text{first}/T_\text{stock}$
   and $T_{\alpha=0}/T_\text{stock}$, so the cost of being wrong is on the
   page. The predicted worst case is $1 + (w + P)/(a+bN)$.
   - hmmscan: about 1.20 on run 1, from $P$, then ≈1.000.
   - hmmsearch: about 4.79 on run 1, from $P$, which is the honest headline
     cost.

### Attack 3: "Black-box probing is unsound. You will ship wrong output."

*Threat:* finite probes cannot prove I1–I4 hold.

*Defense on disk (MEASURED, `results/probe_eval_audit.json`):*

- In-scope unsafe-ship is **4/224**.
- False-refuse is **0/20**.
- The audit alone catches 12.
- F6 accounts for **64 cells** and is declared out of scope.

The closed form $(1-p)^n$ in §3 explains the residual. The paper should
plot measured miss rate against $(1-p)^n$, not claim zero.

*Still required:* Linux F6-file tracing (INCOMPLETE: no Docker, Discovery
SSH timeout). Until it runs, the paper states F6 as a limitation.

### Kill experiments and mandatory ship controls

A filter that reaches 0% unsafe-ship by refusing valid tools fails.

| Experiment | Faulty cases (must REFUSE or widen) | Ship controls (must SHIP) | Status |
|---|---|---|---|
| Probe eval | F1–F5, F7, F8 at $p \in \{0.01,0.05,0.2,1\}$, VCF + FASTA | SnpEff (MATCH 52,638; 41,447 hits / 11,191 misses); fill-tags (widened to SAMPLES; 23,072 hits); the 20 false-refuse controls | MEASURED (`probe_eval*.json`) |
| Content key | byte keys on GenBank must lose reuse | RefSeq control must keep ratio ≈1 (0.998) | MEASURED, kill did not fire |
| Confirmatory hmmscan | prediction miss outside locked band → report as failure | hmmscan byte MATCH on every run | pre-registered, jobs not submitted |
| **PROPOSED** INCR head-to-head | INCR with a single new sequence → full rerun expected | ACTS must still SHIP with byte MATCH on the same inputs | not registered |
| **PROPOSED** zero-hit overhead | — | stock-vs-ACTS MATCH at $\alpha=0$; overhead within $1 + (w+P)/(a+bN)$ | not registered |
| **PROPOSED** cross-domain (Mordred) | descriptor tool with a global normalization step must REFUSE_GLOBAL | per-molecule descriptors must SHIP with name = pass-through | CARC job written, awaiting Josh |

**Top risk if nothing else lands:** one timed tool, one projected tool,
and an argued baseline. The order that removes the most reviewer risk per
CARC hour:

1. Collect savings.
2. Run the confirmatory hmmscan.
3. Run INCR head-to-head.
4. Run Mordred.

---

## Correction 2026-10-03 (after `d5c88b0`)

Attack 2 above says the savings jobs 12394300/01/503/504 "have not been
collected." They had already ended: all four FAILED on 2026-09-28 after
A/hmmsearch hit its own cached-MATCH gate at genome 5 (multi-word FASTA
descriptions classified as produced), and a shared STOP file halted the
others. The fix (`f8e3685`) adds the inference-time round-trip guard, and
the fixed reruns are queued as 12629413–12629416. Record:
`results/savings_failed_20260928/` and the 2026-10-03 addendum in
`docs/SAVINGS_PROTOCOL.md`. The confirmatory jobs are still unsubmitted.

**Architecture novelty, component by component.** Only one stage is new:
field-role inference (K / U / O with key widening) plus splice reassembly.
The round-trip guard is a moderate addition (checking an inferred contract
by rebuilding perturbed output). Every other component is credited:
property/metamorphic testing (determinism, shuffle), Caruca (line-level
statelessness ≈ subset invariance), group testing (batched subsets),
Rattle/Riker/ProcessCache (input tracing), Dune (hit audit), Amdahl (cost
gate). The paper should present ACTS as infrastructure with one novel
stage, not as a novel architecture.

---

## Addendum 2026-10-03 (late) — the minimal sound key

The §2 novelty claim is narrowed after the prior-art pass
(`RELATED_WORK.md`, late addendum). This is the formal content it rests on.

**Setting.** A record has fields $F$. The per-record function is $\tau$.
For a field $f$, write $x[f\!\leftarrow\!v]$ for $x$ with $f$ set to $v$.

- **Irrelevant:** $\tau(x[f\!\leftarrow\!v]) = \tau(x)$ for all $x, v$.
- **Transport:** there is a fixed set of output positions $\mathrm{pos}_f$
  such that $\tau(x[f\!\leftarrow\!v]) = \tau(x)[\mathrm{pos}_f \leftarrow v]$
  for all $x, v$. The value is copied and nothing else changes.
- **Joint transport:** the transport identity holds when any subset of
  transport fields is substituted at once (no interaction).
- $D$ = fields that are not irrelevant (the prior-art dependency key).
- $U \subseteq D$ = transport fields.
- $K^\* = D \setminus U$.

A field set $S$ is a **sound splice key** if there is a $g$ with
$\tau(x) = g(x|_S)[\mathrm{pos}_f \leftarrow x_f]_{f \notin S}$ for all
$x$.

**Proposition.**

- (i) Under joint transport, $K^\*$ is a sound splice key.
- (ii) Every sound splice key $S$ satisfies $K^\* \subseteq S$.
- (iii) Hence, for any input history, the recall under $K^\*$ is at least
  the recall under $S$, including $S = D$.

*Proof.*

- (i) Fix $x$. Irrelevant fields do not affect $\tau$. Substituting all of
  $U$ at once changes $\tau(x)$ only at $\bigcup_{f\in U}\mathrm{pos}_f$,
  by joint transport. So $\tau(x)$ is determined by $x|_{K^\*}$ together
  with the values of $U$ written at their positions. Define
  $g(x|_{K^\*}) := \tau(x)$ with $U$ set to any fixed reference values.
- (ii) Suppose $f \in K^\*$ and $f \notin S$. Then, by the definition of a
  sound splice key, changing $f$ alters $\tau(x)$ only by writing $x_f$ at
  $\mathrm{pos}_f$. That makes $f$ a transport field (or an irrelevant one
  if $\mathrm{pos}_f = \varnothing$), which contradicts $f \in K^\*$.
- (iii) Recall is antitone in the key: $S \supseteq K^\*$ refines the
  partition of records, so every $S$-match is a $K^\*$-match. ∎

**What the system checks versus assumes.** Transport and joint transport
are tested on probe samples, not proved:

- The single-group perturbation tests transport for each field.
- The all-at-once perturbation of every non-key group tests joint
  transport (`acts/infer_vcf.py:526`).

A violation that the probes miss is a fault of class F4 or F5. It is
bounded by $(1-p)^n$ (§3) and caught at runtime by the audit with
probability $1-(1-q)^h$. The proposition makes no claim beyond what the
probes establish.

**Measured consequence** (`results/copy_aware_key.json`):

- $D/K^\* = 0.557$ (VCF/SnpEff).
- $D/K^\* = 0.00$ (GenBank/hmmscan).
- $D/K^\* = 1.000$ (RefSeq control).

This is the reuse that the strongest prior-art key construction leaves on
the table.
