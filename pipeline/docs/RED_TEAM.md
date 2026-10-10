# PC red-team — laboratory draft of “Reference-Side Contract Inference for Unmodified Scientific CLIs”

**Written:** 2026-10-09, against `pipeline/paper/main.tex` at `fdf5f83` (USENIX ATC formatting, post-hoc hmmscan column added). The review was drafted against `7361359` and retargeted after that commit landed on `origin/main`. Line numbers below are `fdf5f83`.
This file is a review. It edits no other file and runs no tool.

**Score scale.** 1 reject, 2 weak reject, 3 weak accept, 4 accept, 5 strong accept.
Confidence is 1–5. Every number below is **MEASURED** (committed file named) or **PROJECTED** (formula and the inputs named). Nothing in this file was timed in the session that wrote it.

**What was read, besides the draft.** `AGENTS.md`, `pipeline/SCOPE.md`, `pipeline/docs/ARCHITECT_REVIEW.md`, `pipeline/docs/REFERENCE_PRIOR_ART.md`, `pipeline/docs/REFERENCE_INCREMENTAL_PROTOCOL.md`, `pipeline/docs/SAVINGS_PROTOCOL.md`, `pipeline/docs/BASELINES_PROTOCOL.md`, and the result files cited under each attack. A web search on 2026-10-09 (Exa) returned iBLAST (Dash et al., PLoS ONE 2021, DOI `10.1371/journal.pone.0249410`), iSeqSearch (Yoo et al., PeerJ 2025, and the 2024 bioRxiv), and `EESI/Incremental-Protein-Search`. Those hits are the same hand-built Spouge/Karlin wrappers already scored **NARROW** in `REFERENCE_PRIOR_ART.md`. No hit in that search infers both decomposition and a column normalizer for an unmodified CLI. The search highlights are not a re-read of the PDFs; the prior-art file is the reading.

---

## 1. Three reviews

### Reviewer A — bioinformatics practitioner

**Summary.** The draft asks whether an unmodified profile or protein search can be re-run on a new reference by scanning only the changed entries and rescaling the statistics that depend on database size. On `hmmscan --cut_ga` the fitter ships entry count and per-key row count (`results/reference_fitter_t1.json`, T1 PASS). Without `--cut_ga` it refuses (`results/reference_fitter_t2.json`). That scope matches how HMMER actually thresholds: bit score under `--cut_ga`, E-value otherwise, and the negative control’s hit set is a strict superset (`results/reference_kill_r2n.json`: union 1,085, full run 1,082). I would use the refusal. I would not yet replace a Pfam re-annotation with the merge.

**Strengths.**

- The closed family does not name HMMER, and the tie-break on the historical R2p halves separates entry count (578/578) from total model length (17/578 and 19/578) on tblout columns 4 and 7 (`results/reference_fitter_t1.json`).
- c-Evalue is assigned to the merged per-sequence row count, which is the right data dependence for `--cut_ga` domtblout (`results/reference_kill_r3c.json`: 511/511).
- Pfam 38.1→38.2 really does have something to reuse: 26,082 of 30,134 models are unchanged under the strict hash (`results/reference_kill_r1.json`).
- The paper says ref-merge is printed precision, and it marks the release timing pending.

**Weaknesses.**

- A Pfam user compares E-values as printed numbers that downstream cutoffs consume. R2p’s pre-registered check 3 found 1,156/1,156 E-values consistent with the half-ULP predicate and only 724/1,156 byte-reproducible (`results/reference_kill_r2p.json`). The draft quotes the 1,156 and omits the 724. iBLAST’s own case study reports 100% E-value match and 100% hit match on its nt slices (PLoS ONE 2021, as read in `REFERENCE_PRIOR_ART.md`). Their bar is exact on the statistic they repair. This draft’s bar is weaker, and the release that would show the weaker bar on a real Pfam diff has no successful measurement (protocol addendum 2026-10-09: jobs 12760029 and 12864042 superseded; smoke 12865788 is `STOP_MATCH` and “not a measurement”).
- The abstract’s 2.740× and 6.847× are record-side hmmsearch, not a re-annotation. The diverse collection’s post-hoc correction is 1.856× before probe cost and 1.513× with it (`results/savings_sensitivity.json`). That is a modest saving on the workload a surveillance lab does not have (clonal O157 is the 4.404× case). hmmscan, which is what `pfam_scan.pl` runs, is now in the draft as POST-HOC (locked 3.568× and 19.468×, corrected 2.95× and 16.18×, Table `tab:hmmscan`). That table is “no probe cost.” The same sensitivity file’s with-\(P\) figures are 2.905× and 15.319× (`results/savings_sensitivity_hmmscan.json`: 2.9054086230922684 and 15.318572090685732). The abstract does not mention them.
- DIAMOND versus iSeqSearch is the comparison a practitioner will demand, because iSeqSearch already rescales m8 by database length. It is pending. The smoke file `results/reference_diamond_smoke/reference_diamond_d2.json` has `"decision": "SHIP"` and `"smoke": true`. The draft is right that smoke is not the comparison. A reader of the tree will still ask why a second tool already shipped in a smoke directory.

**Questions.**

1. On a 38.2 row produced from a changed-model scan, what is the numerical gap between the reprinted E-value and HMMER’s own print, at the factor \(30134/4052\)? (Counts are MEASURED in `reference_kill_r1.json`; the ratio is PROJECTED.)
2. Will the authors put 724/1,156 in the RQ3 section, next to 1,156/1,156?
3. Is the DIAMOND smoke SHIP going to be described as a non-result in the camera-ready, with the pre-registered D2/D3 still the only citation?

**Score.** 2 (weak reject). **Confidence.** 4.

The HMMER contract is the right scientific object. The draft does not yet show that a re-annotation a biologist would ship matches stock closely enough, or that it is faster.

### Reviewer B — incremental builds and command caches

I work in the line of Riker (ATC 2022), ProcessCache, INCR (OSDI 2026), Caruca, and KumQuat (PPoPP 2022). I read `REFERENCE_PRIOR_ART.md` against those papers as positioned there.

**Summary.** The surviving sentence — no prior system infers, for an unmodified CLI and with no per-tool plugin, both reference-entry decomposition and a normalizer from a small fixed family — is the right claim shape, and the kill rule’s KILL branch does not fire on the works I know. KumQuat’s combiner DSL has no reference scale factor. INCR’s default grain is the command; chunking needs a crowdsourced annotation INCR does not infer. Riker, Rattle, and ProcessCache miss when the reference file changes. GeStore, iBLAST, and iSeqSearch hand-build the repair. That literature placement is earned. The system result that would make the placement a paper is not in the draft.

**Strengths.**

- The authors refuse to call group testing, metamorphic tests, or the Dune-style audit novel. Table `tab:prior` credits GeStore, KumQuat, Caruca, and INCR in the right columns.
- T3’s length-versus-count fixtures are the right discriminator against a HMMER plugin. The outcome addendum records them passed. A plugin adjusted until T1 passes still fails fixture B if it hard-codes entry count.
- The content-key secondary result is a real delta over a dependency key: VCF ratio 0.5567, GenBank ratio 0 at every \(k\), RefSeq control 1 (`results/copy_aware_key.json`). Whole-file caches cannot see that split.
- Riker’s absence is reported as a host limit. `results/baseline_ptrace_abi.json` (job 12866431) measured `ptrace(0x420e)` → `rc=-1`, `errno=5` (EIO) on kernel 4.18.0-553. That is evidence about the host, and it is not evidence that Riker would have reused a record.

**Weaknesses.**

- “No per-tool branch” is demonstrated by T1 on one argv and by unit fixtures that the draft itself says have no results JSON (`main.tex` around the T3 table: “There is no separate results JSON for these fixtures”). ATC will not take a passing unit test as the second tool.
- The grain claim against Riker, ProcessCache, and INCR is the pre-registered expectation in `BASELINES_PROTOCOL.md` (a new FASTA path reruns; a replay skips). `results/baseline_smoke.json` does not exist. ProcessCache and INCR are queued (jobs 12866390, 12866391, 12866392) on a shared xeon-4116, not exclusive, and have not finished. Phase 2 wall-time (192–220 requested node-hours per wrapper in that protocol) is correctly not submitted. A specialist will not accept “expected behavior” as the comparison table.
- Docker does not answer Riker. The build report (`results/baseline_build.json`, job 12865942) records Docker absent (exit 127). A container on kernel 4.18 still issues `0x420e` to that kernel. The ABI probe already says a header shim would compile and fail at `ptrace` time.
- Caruca stops before aggregator synthesis and points at KumQuat. The draft’s answer to KumQuat is R2n (the union is a strict superset). That shows a byte-equality combiner would refuse. It does not show KumQuat’s search failing to find a rescale, because KumQuat was not run. The textual DSL argument is fair. It is an argument.

**Questions.**

1. Where is the diff that shows `acts/reference_fit.py` contains no symbol `hmmscan`, `diamond`, `blastp`, or `evalue` mapped to a member? T3-B is the test. I want the negative grep in the artifact appendix.
2. After jobs 12866390–92 finish, will genome-2 RERUN and replay SKIP be the entire baseline section, with Phase 2 explicitly declined?
3. What host, other than Discovery’s 4.18 kernel, will run current Riker, and is that host pre-registered?

**Score.** 2 (weak reject). **Confidence.** 4.

The related-work sentence can survive. The paper cannot, until a second unmodified CLI is fitted or refused under the pre-registered protocol and the whole-command tools have at least the two-genome smoke.

### Reviewer C — measurement

**Summary.** I ignored the mechanism and read the abstract, Table `tab:savings`, the pending macros, and the fit-error paragraphs. The draft is more honest than most systems submissions about imputation. Honesty does not make an imputed cumulative speedup a result. The primary contribution has no wall-clock number. The numbers that are printed belong to the secondary mechanism, and the locked column is the one the authors’ own flag says is inflated.

**Strengths.**

- Fit error is reported at all 12 sampled hmmsearch genomes, relative error 0.351 to 0.807, and the fit is not quietly replaced (`main.tex` RQ2; `results/savings_20261006/A_hmmsearch.json` and `B_hmmsearch.json`).
- Both the locked imputation and the post-hoc correction are in Table `tab:savings`. Probe cost \(P = 1595.447\,\mathrm{s}\) is in the table (`results/savings_summary.json`).
- The 38.1→38.2 speedup is a projection with a pre-registered ±25% gate (`REFERENCE_INCREMENTAL_PROTOCOL.md`, primary mean \(6.999\times\)), and the draft prints `\pending` rather than that projection as a result.
- SnpEff is not smuggled in as a 2×. The record-side ceiling arithmetic is in Table `tab:amdahl` and is labeled projected.

**Weaknesses.**

- The first speedups a reader sees are \(2.740\times\) and \(6.847\times\) (abstract). The correction that the next sentence applies is \(1.856\times\) and \(4.404\times\). With \(P\), corrected A is \(1.513\times\) (`results/savings_sensitivity.json`). Corrected A is below the pre-registered Part 2 prediction of \(2.111\times\) (`results/savings_summary.json`, `predicted_part2_cum_speedup`). The diverse collection, after the correction the flag requires, is under 2× even before the probe.
- The correction assumes the sampled stock/fit ratio represents the unsampled genomes. That assumption is stated. It is not a measurement. The fully measured series is specified and absent (`SAVINGS_PROTOCOL.md` addendum 2026-10-08; jobs 12862906 and 12862907 were pending at submit).
- The body now reports hmmscan as POST-HOC (lines 777–814): locked 3.568× and 19.468×, corrected 2.95× and 16.18×, no \(P\). The sensitivity file also has 2.905× and 15.319× with \(P\) (`results/savings_sensitivity_hmmscan.json`). The abstract still opens on the imputed hmmsearch pair and does not mention this column. `paper_uses` remains hmmsearch, which is what the protocol requires. The measurement problem is the abstract’s first number, not a hidden file.
- RQ4, RQ5, RQ6, and RQ7 are pending in the draft. RQ7’s pending line is stale: `results/reference_boundary_blast.json` already records `decision: REFUSE` for NCBI BLAST+ `blastp` 2.14.1 (git `2ea39e2`, host `a01-16`, finished 2026-10-09). The draft says the boundary experiment has not been run.

**Questions.**

1. Will the abstract’s only speedups be the corrected column, with the locked imputation moved to a sentence that begins “the pre-registered imputation, which over-predicted stock time”?
2. When the 58 hmmsearch stock JSONs exist, will Table `tab:savings` be replaced, or will a third column appear?
3. Why does RQ7 still say pending?

**Score.** 2 (weak reject). **Confidence.** 5.

I would accept a short paper whose abstract said: one fitter, hmmscan contract shipped, BLAST refused, record-side diverse speedup 1.86× imputed-corrected and awaiting full stock, release timing not yet measured. I will not accept the abstract as printed.

---

## 2. PC chair synthesis

**Recommendation.** Do not submit this draft. The related-work sentence is in good shape. The evaluation of the contribution the sentence names is not. Three reviewers land at 2. The disagreement is about which hole is fatal, not about whether the draft is ready.

The five attacks below are ranked by how likely each is to sink the paper if it is submitted with the evidence on `fdf5f83`. Attacks that were considered and ranked lower are listed after the five, so they are not dropped.

### Rank 1 — The printed speedups are the secondary path, and the locked column is the inflated one

**Why it sinks.** The title, the first contribution, and the prior-art sentence are reference-side inference. The abstract’s only measured speedups are record-side hmmsearch under the locked imputation \(a + b N_i\). That imputation over-predicted every sampled stock wall. The primary re-annotation speedup is `\pending{RQ4}`. A committee that came for a systems speedup finds either no number (the contribution) or a number the authors have already discounted (the secondary path, diverse collection 1.856× / 1.513× with \(P\)).

**Evidence that answers it.**

| Claim | Status |
|---|---|
| Locked hmmsearch cumulative wall, no \(P\) | MEASURED as an imputed total: A 2.740193934015858×, B 6.846592216443059× (`results/savings_summary.json`) |
| Same, with singleton-8 \(P\) | A 2.23308564806322×, B 4.900397318731101× (same file) |
| Post-hoc correction | A \(r = 0.627662232339967\), 1.8561541144638773× (1.5126488173514772× with \(P\)); B \(r = 0.6052815600933489\), 4.4038095881881× (3.1519938702250814× with \(P\)) (`results/savings_sensitivity.json`) |
| Sampled stock vs fit | Flag fired at 12/12 sampled genomes; A measured stock 384.227–526.950 s vs fitted 618.958–740.945 s (`results/savings_20261006/A_hmmsearch.json`, `B_hmmsearch.json`) |
| Reference-side speedup | **NOT ANSWERED.** `results/reference_reannot_churn.json` is model-file accounting, `timed` false in the protocol’s reading. Jobs 12760029 and 12864042 are superseded. Smoke 12865788 is not a measurement (`REFERENCE_INCREMENTAL_PROTOCOL.md`, addendum 2026-10-09) |
| Projected gate if the timing is later run | PROJECTED primary mean 6.99924607283027× from \(a, b\) in `results/headline_screen.json` and \(c = 4052/30134\) (`REFERENCE_INCREMENTAL_PROTOCOL.md`). Not a result |

**Cheapest response.** Two parts.

1. **Text, 0 CPU-hours, no exclusive node, no new pre-registration.** Lead the abstract with the corrected pair and with “reference-side wall time is unmeasured.” Keep the locked pair in RQ2 as the pre-registered imputation. This does not create a result. It stops the sink that comes from the first sentence a reviewer quotes.
2. **Experiment that replaces the imputation.** The pre-registered hmmsearch stock completion (`SAVINGS_PROTOCOL.md`, addendum 2026-10-08): 58 genomes, exclusive `epyc-7542`, build `01:00:00` plus each genome `00:45:00` (44.5 node-hours requested). Expected measurement in that addendum: about 6–9 node-hours plus one build, from the sampled walls 384–527 s. Jobs 12862906 and 12862907 were already submitted. Pre-registration exists. This answers only the secondary-path half of the attack.

The experiment that answers the primary-path half is Rank 3’s release run. Rank 1 still sinks if that run is missing, even after the stock completion lands.

**Depends on pending results.** Measured stock completion (hmmsearch) for the secondary number. Pfam 38.1→38.2 for the contribution’s number. DIAMOND timing is a different speedup and does not repair this abstract. ProcessCache/INCR, BLAST, and Riker do not.

### Rank 2 — “This is GeStore / iSeqSearch with inference” — the delta is real on paper and thin in the evaluation

**Why it sinks.** The NARROW verdict is correct: GeStore’s HMMER plugin does not rescale, iBLAST writes Spouge in BLAST-specific code, iSeqSearch copies that rescale onto any m8 producer (readings in `REFERENCE_PRIOR_ART.md`; confirmed again by the 2026-10-09 search highlights, which describe hand-written \(E_{\mathrm{total}} = E_{\mathrm{part}} \cdot n_{\mathrm{total}} / n_{\mathrm{part}}\)). A systems PC will grant the sentence and then ask for the demonstration: the same fitter, no plugin, on a tool whose formula was not the one used to choose the family, with a comparison against the hand-built rescale. T1 is the tool the family was chosen in view of (the protocol says so). T3 is a pure-Python fixture. The draft says there is no results JSON for T3.

**Evidence that answers it.**

| Piece | Status |
|---|---|
| T1 SHIP, no HMMER normalizer in the assignment | MEASURED `results/reference_fitter_t1.json`: tblout 4 and 7 and domtblout 6 and 12 are `entry_count`; domtblout 11 is `per_key_row_count` of tblout; other numeric columns `identity` |
| T2 REFUSE | MEASURED `results/reference_fitter_t2.json` |
| T3 A–E | Recorded as PASS in the 2026-10-06 outcome addendum of `REFERENCE_INCREMENTAL_PROTOCOL.md`. **No results JSON**, as the draft states. A unit-test log is weaker than a committed measurement file |
| GeStore-style baseline refuses synthetic law A | Same addendum (“The gestore baseline refuses law A”) |
| Second unmodified CLI, pre-registered, full reference | BLAST: MEASURED REFUSE, and the draft does not cite it (see Rank 4). DIAMOND D2/D3: **NOT ANSWERED** as a pre-registered result. Smoke `results/reference_diamond_smoke/reference_diamond_d2.json` is `SHIP` with `smoke: true` and expectation “evalue is total_entry_length”; `reference_diamond_d2n.json` is `REFUSE`. The protocol says the smoke does not satisfy D3. It is not the defeat of this attack |
| Head-to-head wall versus iSeqSearch | **NOT ANSWERED** |

**Cheapest response.**

1. **Text, 0 CPU-hours.** State in the introduction that T1+T3 are the discrimination against a HMMER plugin, and that a second search tool’s fit is unmeasured except for the BLAST REFUSE (once Rank 4’s text fix lands). Delete any reading of “for an unmodified CLI” as “shown on CLIs in general.”
2. **Experiment.** Pre-registered DIAMOND D0–D3 (`REFERENCE_SECOND_TOOL_PROTOCOL.md`): one exclusive `epyc-7542`, 32 CPUs, 64 GB, 24 h requested on the resubmission addendum. D2 is the fit (the novelty). D3 is the timing against stock and against iSeqSearch at commit `7e862bf`. Pre-registration exists. Do not cite the smoke SHIP as D2. A fit-only subset is not separately budgeted; the locked job is the 24 h request. Swiss-Prot-scale wall is not measured, so this review does not invent a shorter number.

**Depends on pending results.** DIAMOND versus iSeqSearch (D2 for the delta, D3 for the speed). BLAST boundary is already measured and should be cited; it is a refusal, so it shows the fitter can say no, and it does not show a second SHIP. Pfam timing does not answer GeStore. Riker does not.

### Rank 3 — Printed-precision ref-merge has not been shown on a release, and it is weaker than byte identity

**Why it sinks.** The contribution is a merge. The merge’s equality is ref-merge: hit sets and unnormalized columns byte-identical; normalized columns inside the half-ULP predicate of equation (consistent), with the triangle bound (bound) that grows with \(|\phi|\). R2p already took the pre-registered branch “consistent, not byte-reproducible”: 724/1,156 E-values are byte-reproducible (`results/reference_kill_r2p.json`). The draft never prints 724. The bound is the relation a user gets. On this release the two factors a merge would apply are PROJECTED from MEASURED counts in `reference_kill_r1.json`:

\[
\phi_{\mathrm{cached}} = 30134/27481 = 1.09654, \qquad \phi_{\mathrm{changed}} = 30134/4052 = 7.43682.
\]

The changed-entry rows, which are the ones scanned on the sub-reference and rescaled by \(N'/|\mathrm{changed}|\), carry the larger source-rounding term. No timed 38.1→38.2 arm has passed ref-merge. The checker that omitted the source-rounding term ran in jobs 12760029 and 12864042; both are superseded. Smoke 12865788 passed preflight and then `STOP_MATCH` on tblout column 4 of `('WP_000010777.1', 'AAA_lid_14', '')` because a reprint was stored and the next render compared it as if \(\phi = 1\). The protocol says that job is not a measurement. T1’s residuals are partition consistency on historical halves, not a release merge.

**Evidence that answers it.**

| Piece | Status |
|---|---|
| Hit-set equality and 0 unnormalized mismatches under `--cut_ga` | MEASURED R2p (578 hits) and R3c (511 domain lines) |
| Half-ULP consistency of E-values | MEASURED 1,156/1,156 (R2p); 511/511 on three domain E-value columns (R3c) |
| Byte-reproducible E-values | MEASURED 724/1,156 (R2p). **Not in the draft** |
| The bound (bound) | Stated in the draft and in the 2026-10-09 protocol addendum. Not evaluated on a 38.2 table |
| A release merge that passed ref-merge | **NOT ANSWERED** |

**Cheapest response.**

1. **Text, 0 CPU-hours.** Print 724/1,156 next to 1,156/1,156. State \(\phi_{\mathrm{changed}}\) from the counts above as the factor the bound must be read at. Say that T1 is not a release.
2. **Experiment.** The pre-registered five-proteome, three-repeat 38.1→38.2 run (`REFERENCE_INCREMENTAL_PROTOCOL.md`, addendum 2026-10-06): one exclusive `epyc-7542`, 32 CPUs, 128 GB, 48 h requested. PROJECTED occupancy in that addendum is about 30–40 h; that projection is not a result. The salvaged cache (2 contracts, 18,282 rows, 140,620,277 coverage rows, copy from job 12865202) is reusable under the corrected checker. Pre-registration exists. The gate is \(|\bar S - 6.99924607283027| / 6.99924607283027 \le 0.25\), and every timed incremental arm must ref-merge against that repeat’s stock. A `STOP_MATCH` is a result and sinks the correctness claim in the way the protocol already specifies. Report it either way.

**Depends on pending results.** Pfam 38.1→38.2, on the corrected checker. Measured stock completion does not. DIAMOND ref-merge is a second instance of the same predicate, useful after this one exists. BLAST does not produce a merge.

### Rank 4 — The closed family has shipped on one argv, and the second real CLI refused for reasons the family does not explain

**Why it sinks.** The protocol’s own red-team says the four members were chosen with R2p, R3c, and the Spouge formula in view. T3 is the pre-registered answer, and it is synthetic. The first unmodified CLI outside that argv pair is BLAST+ `blastp` 2.14.1, setting B1, 20 queries, Swiss-Prot 2026_03 (575,748 entries, total length 209,017,843). It REFUSEs. The recorded reason is `out: column 2 matches no normalizer` (`results/reference_boundary_blast.json`). Column 2 is `pident`: identity is consistent on 15,124/15,125 rows and fails one row by 11.458 (`21.875` vs `33.333` on `WP_000153074.1`). `evalue` (column 10) fits `total_entry_length` on 15,124/15,125 and misses one row by 155.376. `bitscore` identity fails one row by 0.7 (`24.3` vs `25.0`, same query). Key sets are unequal: aligned 15,125, only-union 13,812, only-whole 0. The protocol predicted REFUSE on row keys and allowed a column failure to surface first. That prediction holds. It also falsifies the B1-fit prediction that `pident` and the alignment-length columns would be identity on every aligned row, and that `evalue` would fit `total_entry_length` on all of them. One row is enough to refuse, which is what the rule says. A reviewer will say the family was not shown to be the law of a second tool; it was shown to refuse when a single aligned row leaves every member.

The draft’s RQ7 still says this experiment is pending (line 1056). That is a factual error relative to the tree at `fdf5f83`.

“Only one or two reference tools” is this attack. hmmscan is the only SHIP under a pre-registered full protocol. BLAST is a second tool and a refusal. DIAMOND’s pre-registered run does not exist. The smoke SHIP must not be promoted to fill the hole.

**Evidence that answers it.**

| Piece | Status |
|---|---|
| Family not named for a tool, tie-break separates count from length on HMMER | MEASURED T1 residuals |
| Synthetic length law ships, rank and pairs refuse | Protocol outcome addendum; no results JSON |
| BLAST REFUSE | MEASURED `results/reference_boundary_blast.json`. **The draft says pending** |
| DIAMOND on the pinned full releases | **NOT ANSWERED** (smoke is not D2) |

**Cheapest response.**

1. **Text, 0 CPU-hours, no new pre-registration.** Replace the RQ7 pending line with the JSON’s decision, reason, key-set counts, and the three near-miss columns. State that B1-fit did not hold on `pident` or on all of `evalue`. Do not add a fifth family member. The protocol forbids it.
2. **Experiment, only if the PC wants a second SHIP rather than a second decision.** DIAMOND D2 inside the 24 h exclusive job in Rank 2. Pre-registration exists. A refusal there is also a result and would narrow the claim to HMMER score-thresholded modes plus a BLAST refusal. That is a survivable paper if the abstract says so. It is not a survivable paper if the abstract says “unmodified scientific CLIs” and D2 is still missing.

**Depends on pending results.** DIAMOND D2 (and D2n, the negative control). BLAST is done. Pfam timing does not test the family on another tool.

### Rank 5 — The timed record-side jobs probed 8 records; rare faults and per-query width sit below that probe

**Why it sinks.** It sinks the safety claim attached to the only timed savings, not the reference-side fitter. The savings jobs infer with `probe_n = 8`, singleton schedule, 12 calls, \(P = 1595.447\,\mathrm{s}\) (`results/savings_summary.json`). The deployed safety table’s in-scope unsafe-ship is 4/224 at probe sizes 50, 200, 500, and 2000 (`results/probe_eval_audit.md`). There is no cell at 8. The four misses are vcf F3 at \(p = 0.01\), \(n = 50\); vcf F4 at \(p = 0.01\), \(n = 50\); fasta F4 at \(p = 0.001\), \(n \in \{50, 200\}\) (same writeup). At \(n \ge 500\) the same slice is 0/56. False-refuse is 0/20.

PROJECTED, from the draft’s own formula \((1-p)^n\): at \(p = 0.01\) and \(n = 8\), \((0.99)^8 = 0.9227\). At \(n = 50\) the draft already prints 0.6050. An 8-record probe misses a 1% per-record fault with probability about 0.92. The safety section never puts that probability next to the savings jobs.

The concrete miss already happened on the sibling mode. The hmmscan contract inferred at `probe_n = 8` pinned target-name width to `fixed_min` 20. Re-render of archived A stock tblout mismatched 22, 22, 20, 21, and 37 rows (`results/hmmscan_layout_preflight.json`). The cause, recorded in `SAVINGS_PROTOCOL.md` (addendum 2026-10-06), is per-query name width: HMMER sets the column to \(\max(20, \text{longest target name in that query})\), and the 8-record probe never saw a model name longer than 20. Re-inference left the layout unpinned; whitespace MATCH then had 0 mismatches on those five files. hmmsearch’s pinned contract had 0 mismatches on the three archived files checked in that same JSON. The paper’s primary mode survived this particular bug. The probe that certified it is the probe that missed the sibling’s per-query rule. Audit \(q = 0.02\) does not repair a layout rule the contract froze in.

**Evidence that answers it.**

| Piece | Status |
|---|---|
| 4/224, 0/20, 0/56 at \(n \ge 500\) | MEASURED `results/probe_eval_audit.md` |
| \((1-0.01)^{50} = 0.6050\) | PROJECTED, already in the draft |
| \((1-0.01)^{8} = 0.9227\) | PROJECTED here; **not in the draft** |
| hmmscan per-query width miss | MEASURED `results/hmmscan_layout_preflight.json` |
| hmmsearch byte layout on the archived files | MEASURED 0 mismatches in that same file |
| Savings jobs’ MATCH/audit | MEASURED: no MATCH, audit, or stop failures; A 30/30, B 40/40 (`results/savings_summary.json`) |
| A probe_eval cell at `probe_n = 8` | **NOT ANSWERED** |

**Cheapest response.**

1. **Text, 0 CPU-hours.** In RQ2, next to \(P\), print \((0.99)^8 = 0.9227\) and the layout file’s mismatch counts. Say the 4/224 table starts at \(n = 50\). Say hmmscan’s pinned floor was refuted and the paper’s hmmsearch contract was not, on the files in `hmmscan_layout_preflight.json`.
2. **Experiment, only if the committee wants a cell at the deployed size.** Extend `probe_eval` with `probe_n = 8` under a new dated addendum before the run. The existing suite is a Mac measurement of decisions, not a CARC wall (`probe_eval_audit.md`). No exclusive node. CPU-hours are not in a committed file, so this review does not invent them. Pre-registration is **needed**; the locked sizes are 50, 200, 500, 2000. Do not rerun collections A and B to answer this.

**Depends on pending results.** None of the five pending result streams answer the missing \(n = 8\) cell. The layout file already answers the hmmscan width incident. Linux F6-file tracing is a related limitation (32/32 unsafe on this Mac, `trace_status` unavailable) and is not one of the five pending items. It stays a limitation until `results/f6_trace_linux.json` exists.

### Attacks considered and ranked lower

**Baselines could not run (Riker blocked by ptrace).** Real, and Reviewer B will write it. It is sixth because the draft already marks the comparison pending, and the ABI failure is measured rather than hidden. It becomes a sink only if the camera-ready still says whole-command tools were compared. Evidence: Riker did not link; `0x420e` returns EIO (`results/baseline_ptrace_abi.json`). ProcessCache SHA-256 and both INCR columns are queued, not finished (`BASELINES_PROTOCOL.md` addendum 2026-10-09). **Cheapest experiment:** let 12866390–92 finish. They are shared xeon-4116, 8 CPUs, 48 GB, time limit `1-20:00:00`, not exclusive. Pre-registration exists (Phase 1). They decide RERUN versus SKIP. They are not a wall-time table. **Riker-in-Docker on CARC does not answer Riker:** Docker was absent (exit 127, job 12865942), and a container does not change kernel 4.18’s `ptrace` ABI. A two-genome Riker smoke needs a kernel that accepts `0x420e`. That host is not pre-registered. Phase 2 (192–220 requested node-hours per wrapper) stays declined until the smoke matches the expected rerun/skip pattern. Full-collection baseline walls are the wrong purchase.

**Only bioinformatics, so not general.** The mechanism is format parsers plus a closed numeric family, which is not inherently a bioinformatics idea. The evidence is HMMER, a BLAST refusal, SnpEff/fill-tags ship controls, and a synthetic fixture. Mordred and Whisper are hypothesized and not run (`ARCHITECT_REVIEW.md`). ruff was rejected at screen time. This attack sinks the title (“Scientific CLIs”) more than it sinks a scoped paper. **Cheapest response is text:** title and CCS should say reference-side inference for score-thresholded profile search, with BLAST as a refusal. A non-bio CLI is not the next CARC job. Pre-registration for Mordred exists as a skipped install (`ARCHITECT_REVIEW.md`); it is not required to answer Ranks 1–4.

**Copy-aware key is incremental over GREYONE / DUST / Param Miner.** The draft already calls the record side secondary and occupied up to the copy split. The measured ratios in `copy_aware_key.json` answer the “byte keys suffice” attack. It does not sink the paper if the abstract stays on the reference side.

---

## 3. Proposed experiments, ranked

Costs are the pre-registered requests or the protocol’s stated projections. Where no committed file gives a wall, the cell says so.

| Rank | Experiment | Attacks it answers | Cost | Exclusive? | Pre-registration |
|---|---|---|---|---|---|
| 1 | Text pass on `main.tex`: corrected speedups in the abstract; 724/1,156; \(\phi_{\mathrm{changed}}\); BLAST REFUSE cited; \((0.99)^8\); layout mismatches; smoke DIAMOND labeled non-result; title scoped | 1 (wording), 2 (wording), 3 (wording), 4 (the stale pending line), 5 (wording) | 0 CPU-h | No | Not an experiment |
| 2 | Pfam 38.1→38.2 re-annotation on the corrected checker, cache from job 12865202 reused | Rank 1 primary half; Rank 3 | 48 h requested; PROJECTED occupancy about 30–40 h (`REFERENCE_INCREMENTAL_PROTOCOL.md`) | Yes, one `epyc-7542`, 32 CPU, 128 GB | Exists (2026-10-06 addendum). Superseded jobs are not a result |
| 3 | DIAMOND D0–D3 versus stock and iSeqSearch | Rank 2; Rank 4 | 24 h requested, exclusive `epyc-7542`, 32 CPU, 64 GB (`REFERENCE_SECOND_TOOL_PROTOCOL.md` resubmission addendum) | Yes | Exists (2026-10-06). Smoke does not satisfy it |
| 4 | hmmsearch stock completion, 58 genomes, jobs 12862906 / 12862907 | Rank 1 secondary half | 44.5 node-h requested; expected about 6–9 node-h plus one build, from sampled walls 384–527 s (`SAVINGS_PROTOCOL.md` 2026-10-08) | Yes, `epyc-7542` | Exists. Already submitted; pending at that addendum’s submit record |
| 5 | Wait for ProcessCache and INCR smokes 12866390–92. Report RERUN/SKIP only | Baselines, ranked below the five | Already queued: shared xeon-4116, 8 CPU, 48 GB, `1-20:00:00`, not exclusive | No | Exists (Phase 1). Do not start Phase 2 (192–220 node-h per wrapper) off this review |
| 6 | `probe_n = 8` row in the probe-eval suite | Rank 5, only if text is not enough | Wall not in a committed file. Mac, decisions, not a speed | No | **Needed** before the run. Locked sizes are 50/200/500/2000 |
| 7 | hmmscan stock completion, jobs 12864755 / 12864756 | Replaces the imputation inside the POST-HOC column the draft already prints | 117 node-h requested; expected about 46 node-h plus one build (`SAVINGS_PROTOCOL.md` 2026-10-09) | Yes, `epyc-7542`, `nice=10000` | Exists, and the mode stays post-hoc. Do not run this ahead of ranks 2–4 |
| 8 | Riker on a kernel that accepts `ptrace` request `0x420e`, two genomes plus replay | Baselines | Not an exclusive `epyc-7542`. Docker on Discovery’s 4.18 kernel does not implement `0x420e` (`baseline_ptrace_abi.json`, `baseline_build.json`) | No | **Needed** if the host is not the locked Discovery node class |

**Pending-result map.**

| Pending result | Which attacks need it |
|---|---|
| Pfam 38.1→38.2 | Rank 1 (the contribution’s speedup), Rank 3 (release ref-merge). Not sufficient for Rank 2 |
| DIAMOND vs iSeqSearch | Rank 2, Rank 4. D2 is the fit; D3 is the wall |
| ProcessCache / INCR | The baseline attack below the five. Not Ranks 1–5 |
| BLAST boundary | Already MEASURED (`reference_boundary_blast.json`). Rank 4 needs a text citation, not a rerun. The diagnosis job named in `pipeline/jobs/reference_boundary_diagnosis.job` is post-hoc and is not a license to add a family member |
| Riker-in-Docker | Does not answer Riker on this kernel. A different kernel does, and it needs a new pre-registration |
| Measured stock completion | Rank 1’s secondary column (hmmsearch). hmmscan completion is optional and post-hoc |

---

## 4. Claims in the draft that are overstated or under-supported

Line numbers are `pipeline/paper/main.tex` at `fdf5f83`.

1. **Lines 45–50, abstract.** “Locked record-side cumulative wall speedups on hmmsearch are \(2.740\times\) and \(6.847\times\); a post-hoc correction … lowers them to \(1.856\times\) and \(4.404\times\).”
   The locked pair is the pre-registered imputation, and the fit over-predicted stock time at 12/12 sampled genomes. Corrected A with \(P\) is 1.513×, which the abstract omits.
   **Fix.** First sentence: corrected walls, with and without \(P\). Second sentence: the locked imputation, labeled as the total the fit inflates.

2. **Line 21, title.** “Unmodified Scientific CLIs.”
   The pre-registered SHIP is `hmmscan --cut_ga`. BLAST REFUSEs. DIAMOND’s pre-registered run is absent.
   **Fix.** Name score-thresholded HMMER, and say a second CLI was refused or is unmeasured.

3. **Lines 90–91, contribution 1.** “One generic fitter, with no per-tool code, infers for an unmodified CLI…”
   Supported as a specification and as T1. Read as an evaluated fact about CLIs, it is one argv plus fixtures.
   **Fix.** “Infers or refuses. Evaluated SHIP: `hmmscan --cut_ga`. Evaluated REFUSE: the same binary without that flag, the synthetic rank and pair fixtures, and BLAST+ `blastp` (cite the JSON).”

4. **Line 222, Figure 1 caption.** “Later output matches stock under ref-merge.”
   Later output on a Pfam release has not passed ref-merge. T1 matches a partition probe to a whole-reference probe.
   **Fix.** “The acceptance test is ref-merge. A timed release merge is unmeasured.”

5. **Line 950, RQ3.** “\(1{,}156/1{,}156\) E-values consistent with entry count.”
   True, and incomplete. `reference_kill_r2p.json` also has `evalue_byte_reproducible: 724`.
   **Fix.** Add “724/1,156 of those tokens are byte-identical after rescale.”

6. **Line 521.** “\(c_{\mathrm{R1}}\) lies below both thresholds, so on these assumptions one re-annotation’s projected savings cover the probe.”
   The arithmetic is labeled projected (Table `tab:breakeven`, \(S/P = 4.952\) primary). The sentence is easy to quote as a finding. The linear-\(b\) assumption is the assumption Rank 3’s run exists to test.
   **Fix.** Keep the table. End the paragraph with “This is not a measured saving.”

7. **Lines 777–814, POST-HOC hmmscan.** The mode is now reported, labeled secondary, with locked 3.568× / 19.468× and corrected 2.95× / 16.18×. The table header is “No \(P\).”
   `results/savings_sensitivity_hmmscan.json` also stores with-\(P\) speedups 2.9054086230922684× (A) and 15.318572090685732× (B). The abstract (lines 45–50) still does not mention the column.
   **Fix.** Add the with-\(P\) pair to Table `tab:hmmscan`. Keep the mode post-hoc. Do not move 19.468× into the abstract.

8. **Line 997.** “There is no separate results JSON for these fixtures; the record is that outcome addendum.”
   This is honest, and it is the weakest link in the “not a HMMER plugin” claim.
   **Fix.** Leave the sentence. Do not let the introduction treat T3 as a measured CLI.

9. **Line 1056, RQ7.** “A boundary on an unmodified CLI outside that argv pair … is `\pending{boundary refusal beyond T2 and the synthetic fixtures}`.”
   Stale. `results/reference_boundary_blast.json` records REFUSE, reason `out: column 2 matches no normalizer`, only-union 13,812, only-whole 0, `evalue` `total_entry_length` 15,124/15,125, `pident` identity 15,124/15,125.
   **Fix.** Replace the pending macro with those figures and the statement that B1-fit did not hold.

10. **Line 1039, RQ5.** Pending DIAMOND is correct. The tree contains `results/reference_diamond_smoke/reference_diamond_d2.json` with `decision: SHIP` and `smoke: true`.
    **Fix.** One sentence: a smoke SHIP and a smoke REFUSE exist, they are not D2/D3, and they are not a speedup.

11. **Line 1078, Table `tab:prior`, “This fitter”.** “probed partition, or refuse; closed family, or refuse; no per-tool branch.”
    The row describes the program. A reader reads it as the evaluation.
    **Fix.** Footnote the row: “SHIP measured for `hmmscan --cut_ga`. REFUSE measured for BLAST+ `blastp` B1 and for hmmscan without `--cut_ga`.”

12. **Lines 1145–1149.** “The defeat on disk is that pair of designs together with a fitter that has no per-tool branch. T1 passes … and the length fixture ships total entry length.”
    The designs are a fair reading of GeStore and iBLAST. The defeat-on-disk is one HMMER SHIP plus a fixture with no results JSON. iSeqSearch’s hand-built DIAMOND rescale has not been run against this fitter.
    **Fix.** “T1 and T3 discriminate a HMMER plugin from the fitter. They do not measure DIAMOND. That comparison is pending.”

13. **Lines 1185–1188, conclusion.** “One fitter, with no per-tool code, accepts or refuses a reference-side contract for an unmodified CLI … The release-level speedup, the second search tool, and the whole-command baselines remain to be measured.”
    The last sentence is the right scope. The first sentence still universalizes one SHIP. The second search tool has a measured refusal the conclusion does not mention, and the release attempts that failed their checker are not mentioned.
    **Fix.** “Accepts `hmmscan --cut_ga` and refuses BLAST+ `blastp` under B1 and hmmscan without `--cut_ga`. No release-scale ref-merge has passed. Record-side hmmsearch, after the post-hoc stock correction, is 1.856× and 4.404× before probe cost.”

---

## 5. Chair’s next step

The single next action is the pre-registered Pfam 38.1→38.2 re-annotation on the corrected ref-merge checker, reusing the salvaged cache, on one exclusive `epyc-7542`, under the existing ±25% gate. Report `STOP_MATCH` if it fires. Do not retune the family from the BLAST residuals while that job is in the queue.

The text pass in §3 rank 1 can land in the same week and does not need CARC. It is what keeps the current abstract from being the sentence the committee remembers. It is not a substitute for the release run.
