# Adversarial check of TARE (pre-registered)

Written after the pilot below and before the measured grid. The pilot is
not a result. Locked text in "Measured grid" is not edited after the run
starts; later notes are dated addenda.

System name in this document: TARE. The command is still `python3 -m acts`.

## Semantics review (before any run)

The tool under the check is `pipeline/scripts/coupling_shim.py`, wrapped
with the same argv shape TARE uses for hmmscan:

```
coupling_shim.py --cut_ga --noali --cpu 2 \
  --tblout {output:tblout} --domtblout {output:domtblout} \
  -o /dev/null <hmm> <fasta>
```

Exact mode adds `-Z {entry_count}` after the program name. The coupling
is not an argv flag. It is `TARE_COUPLING`, `TARE_K`, `TARE_SEED`,
`TARE_N`, `TARE_M`, `TARE_D`.

Option (ii), the synthetic scorer, is the measurement engine. It reads
HMMER3 profile text and FASTA, prints both tables, and does not call
hmmscan on the grid. A real hmmscan confirmation is a separate arm, one
trial per form, and is not part of the 50-trial rates.

Behaviors that could make a check fail for a reason other than the
injected coupling, and how the pilot detects them:

1. **E-value scaling.** E = `1e-3 * Z`. `Z` is `-Z` when present, else
   the number of models in the file. A missing pin changes every E-value
   and would look like a coupling. The unit test `test_pin_is_load_bearing`
   requires the pinned subset to match the full-file E-values and the
   unpinned subset to differ. The declared pin is `-Z {entry_count}`.
2. **`--cut_ga` vs E-value reporting.** Under `--cut_ga` a hit is kept
   when its bit score is at least the model's GA (20). The score is a
   hash of the record name and the model name, in `[21, 40]`, and does
   not read the rest of the file. Without `--cut_ga` the threshold is
   `E <= 10`. The grid always passes `--cut_ga`. `passes_report` is
   unit-tested both ways.
3. **Normalizer tie.** Model lengths are unequal (every 50th model has
   length 100000). The E-value column must fit `entry_count` and not
   `total_entry_length`. The clean-contract test asserts `SHIP` and that
   membership. If the measured run's clean contract is not `SHIP`, the
   grid is stopped.
4. **Probe leakage.** Affected records are drawn from the complement of
   TARE's probe sample (`PROBE_N = 300`, `PROBE_SEED = 20261006`, the
   same draw as `acts.reference_fit.sample_record_indices`). The unit
   test asserts the copies match and that the draw is disjoint from the
   probe. A coupling that is visible on the probe is fitted or refused
   by the contract: forcing the residue coupling onto every record makes
   the bias column `total_entry_length`. That is why affected records
   stay off the probe. Contract inference is not the detector under test.
5. **Residue cap.** Every query has the same length, so no record is
   half the residues. Random pads and the audit are not skipped. A
   skipped layer would be reported in the trial's `random_pads` or
   `audit` field and would be a deviation.
6. **One shared hit model.** Every record hits the same seed-chosen
   model, so the candidate union has size 1. File-order neighbors of
   that model are not themselves candidates. A dependency at distance
   `d > 1` is therefore not in the neighbor pad. A large candidate
   union would put some other record's neighbor on top of a distant
   dependency and confound the form. This is intentional.
7. **Stock-vs-stock.** Two calls with the same inputs return the same
   tables (`test_stock_matches_stock`). The replay TARE stitches is
   compared with an oracle that searches only the hit model under
   `-Z` equal to the full model count. `replay_oracle_mismatch` must
   stay 0. The pilot had 0 mismatches.
8. **Difference class.** Stock versus replay is labeled identical,
   value-only, missing, extra, missing_and_extra, or order. A refusal
   whose class is identical is a needless refusal.

The in-situ check (R3) uses the same probe sample. Couplings outside
that sample cannot fire R3. A measured R3 count of 0 is the predicted
consequence, not a silent skip.

## What each form changes

All forms are off for records outside the affected set. The affected
set has size `k`.

| Form | Env | What changes on an affected record | Single responsible entry |
|---|---|---|---|
| C0 none | `none` | nothing | no |
| C1 residues | `residues` | bias becomes the sum of lengths in the searched file | no |
| C2 presence | `presence` | the hit is omitted unless one other model, not a file-order neighbor, is in the file | yes |
| C3 order | `order` | the note names the model `d` positions earlier in the full reference, or `via-missing` if that model is absent. `d` in {2, 5, 20} on the grid; the pilot also uses `d = 1` | yes |
| C4 global | `global` | the note is a hash of the raw text of every model in the searched file | no |

C1 and C4 change whenever the searched set changes, so the neighbor pad
is predicted to catch them whenever it adds a model. Eq. 4 does not
apply: it is a formula for one left-out entry. C2 and C3 are that case.
Eq. 4 is evaluated with `q` equal to the measured fraction of the three
locked random pads that contain the responsible model, averaged over
trials. `n` and `s` are the paper's (record count, 50), not a refit.

Eq. 4 ignores the neighbor pad and the audit, and it treats each pad as
one detection event. Where the measured detection rate sits above
`1 - P_miss`, Eq. 4 over-predicts misses. Where it sits below, Eq. 4
under-predicts misses. The random-pad-only rate is reported separately
because an earlier layer short-circuits the later ones.

## Classifier

| Replay vs stock | Decision | Outcome |
|---|---|---|
| identical | SHIP | correct_ship |
| differs | SHIP | UNSAFE |
| differs | REFUSE from neighbor, random, audit, R3, or R4 | true_refusal |
| identical | REFUSE from those layers | needless_refusal |
| differs | contract or R2, before the check | contract_refuse |

UNSAFE is a finding. It is not rerun under a new rule.

A cell is INCONCLUSIVE when any trial has fewer stock tblout rows than
records (the shim is supposed to report one hit per record) or the
outcome is `INCONCLUSIVE`. That is missing power, not a kill of the check.

## Pilot, seed 20261111 (not a result)

Host: this laptop. `n = 400` records, `500` models, so the probe complement
is 100 records. Code content is the shim and driver in this commit; the
process recorded `git_head` `507c45fcd2eb3c3e7850791cb2daf5e84400ffab`
because the files were still untracked (`git_dirty_tracked` false under
`--porcelain -uno`). File: `pipeline/results/adversarial/pilot.json`.

Clean contract: `SHIP`, reason `decomposition and normalizers fitted`.
Oracle mismatches: 0. Stock rows: 400 on every trial. Status `OK`.

| Cell | Trials | Outcome | Layer | Difference class |
|---|---:|---|---|---|
| C0 k=5 | 3 | correct_ship | none | identical |
| C3 d=1 k=5 | 3 | true_refusal | neighbor_pad | value-only |
| C1 k=5 | 1 | true_refusal | neighbor_pad | value-only |
| C2 k=5 | 2 | 1 true_refusal, 1 UNSAFE | random_pad on the refusal | missing |
| C3 d=5 k=5 | 1 | UNSAFE | none | value-only |
| C4 k=5 | 1 | true_refusal | neighbor_pad | value-only |

Known-good control: C0 shipped and the replay matched stock.
Known-bad control: d=1 was a true refusal, the neighbor pad fired, and
`neighbor_has_responsible` was true on all three trials.
The UNSAFE rows were labeled UNSAFE rather than rewritten. On the C2
UNSAFE trial the responsible model was not a neighbor, and two of the
three random pads contained it (`q_trial = 2/3`); the affected records
were not in the size-50 sample, which is the `h` term of Eq. 4.

No redesign. The measured grid uses this shim and this classifier.

## Measured grid (locked)

Seed base `20261112`. Trial seed is the integer

```
{base}{cell_index:02d}{k:03d}{distance:02d}{trial:02d}
```

`cell_index` is the position in the list below. These integers are
derived from the block seed. They are not reused from the repository
or from another agent's block. The pilot used the same packing with
base `20261111` and its own shorter cell list; those seeds are the
`seed` fields in `pilot.json`.

Records: 2000. Models: 2500. Trials: 50 per cell. `k` in {1, 5, 22, 100}.

Cell order:

1. C0 `none`, distance 0, each k
2. C1 `residues`, distance 0, each k
3. C2 `presence`, distance 0, each k
4. C3 `order`, distance 2, each k
5. C3 `order`, distance 5, each k
6. C3 `order`, distance 20, each k
7. C4 `global`, distance 0, each k

Output: `pipeline/results/adversarial/measured.json`, with `git_head`,
the seed, Python and HMMER version strings, the argv, per-trial
decision, layer, outcome, difference class, `q_trial`, and per-cell
Wilson 95% intervals. Laptop wall times may be stored as
`indicative_wall_s`. They are not evidence.

Detection rate is true refusals divided by trials whose replay differed
from stock. Wilson intervals use that denominator. Eq. 4's predicted
detection is `1 - P_miss` with the cell's mean `q`, `n = 2000`, `s = 50`,
three pads, and only for C2 and C3. C0 is reported as the correct-ship
rate and the needless-refusal rate.

Positive control: C0, every k, must be able to ship. A needless refusal
is reported, not dropped.
Negative control: the pilot's d=1 neighbor catch. It is not repeated
inside the 50-trial grid. If the measured C3 cells show the neighbor
pad firing, that is recorded; it is not required.

Stop conditions, which are not a third redesign: clean contract not
`SHIP`; oracle mismatch; a trial throws. UNSAFE counts are kept.

## Not claimed

The grid does not estimate a Pfam-scale `q`. `q` is measured on this
2500-model reference, whose random pad has width `min(max(200, |U|),
non-candidates)` and `|U| = 1`. It does not say the neighbor pad proves
entry-locality. It does not retune `s`, the pad count, or the audit.

## Addendum 2026-10-18 — pilot file and measured run

Written after the measured grid. The locked "Measured grid" section is unchanged.

The pilot table above is not what `pipeline/results/adversarial/pilot.json` contains. That file is the in-process pilot: seed 20261111, 360 records, 200 models, three trials each of C0 at k=1 and k=5 and of C3 at distance 1 for the same k. Every C0 trial is `correct_ship` with identical tables. Every distance-1 trial is `true_refusal`, layer `neighbor_pad`. `known_good.ok` and `known_bad.ok` are true. The C1, C2, C3 distance-5, and C4 rows in the table above are not in the file and are not results. Needless refusal and UNSAFE are labeled by `test_classifier_labels_the_four_outcomes`. The measured grid is where the shipped check produced UNSAFE.

The measured command was `python3 pipeline/scripts/run_adversarial.py measured`. It started after commit `200cc7cd4df8e77c56c12ec60ab30548941e10cf` and recorded that head with `git_dirty_tracked` false. 1,400 trials, 28 cells, every cell `status` OK. Clean contract `SHIP`. Oracle mismatches 0. Stock tblout rows 2,000 on every trial.

The audit comparison runs only when the cache reused rows. Each trial used a fresh cache, so `trials[].audit` is null and no layer is `audit`. The layers that ran are the neighbor pad and the three random pads, which is what Eq. 4 describes.

Eq. 4 applies to C2 and C3. Its detection sits inside the cell's Wilson 95% interval in 15 of 16 cells. The exception is `cells["C3/d2/k1"]`: Eq. 4 detection 0.008 is below the interval [0.011, 0.135], so the formula slightly over-predicts misses there. The largest point gap is `cells["C2/k22"]`, 0.140 versus 0.080, and that formula value is still inside the interval. No cell has Eq. 4 above its interval. C1 and C4 are outside the formula: the neighbor pad refused all 200 trials of each.

UNSAFE is 741 trials, all in C2 and the three C3 distances. C0 is 200 correct ships and 0 needless refusals.

The hmmscan arm is `pipeline/results/adversarial/confirm.json`, one trial per form, seeds 20261113–20261117, the first 24 profiles of the read-only Pfam-A file, sequences emitted from `2CompART`. It is not part of the rates. C0 shipped identical to stock. C1 and C4 refused on the neighbor pad. C2 and C3 at distance 2 refused on a random pad.

## Addendum 2026-10-18 — the audit runs on the next release

The null `audit` fields are the cold cache, not the residue cap. On the 941 trials that finished the pad check, `random_pads` is `3 on 50 records, residue fraction 0.025000`. It is null on the 459 trials that a pad refused before that note was stored. The residue cap did not skip the pads.

`pipeline/results/adversarial/audit_gate.json` is a two-pass diagnostic on one cache. It is not part of the detection rates. Seed `20261118`, presence coupling, `k = 40`, 400 records, 500 models, pin `-Z {entry_count}`, git head `16e69a8dbf16ecb70f2862664a852874de5068ec`.

The cold pass has `reused_rows` 0, `audit` null, and decision `SHIP`. Its replay is class `missing` against stock. The warm pass has `reused_rows` 800. The neighbor pad and the three random pads still pass (`ic2` is `pass`). The audit then checks 20 records, residue fraction 0.05, and the decision is `REFUSE_AUDIT` with reason `tblout: audited records differ from a full run`.

The 741 UNSAFE trials are shipped output from a first exact run. A later run that reuses rows catches this coupling with the audit, after the pads have missed it. The 50-trial grid does not measure that second run.

## Addendum 2026-10-19 — cold audit, bounded sample, measured grid v2

Written after the pilot in `pipeline/results/adversarial/pilot_v2.json` and before the measured grid. The locked "Measured grid" section above is unchanged. This addendum locks the v2 run.

### What changed in the check

The exact-mode audit in `acts/reference_run.py` (`_run_exact`) used to run only when `reused_rows > 0`. A cold cache therefore shipped without an audit. The audit now runs on every exact replay that reaches it, including a cold cache. The residue cap is unchanged: one record longer than half the residues still skips the sample. The non-exact incremental path is unchanged; it is not a candidate-subset replay.

Two modes sit on that gate. Neither is a new detection theory.

1. **Shipped sample.** Bernoulli inclusion 0.02, then a floor of 20, seed `20260927`. This is the Dune cache-check probability at record granularity, already the shipped default.
2. **Bounded sample.** Choose `s` so that if at least a fraction `k_min/n` of records are affected, the with-replacement miss probability is at most `epsilon`:

   `s = ceil(ln(epsilon) / ln(1 - k_min/n))`

   Defaults `epsilon = 0.05` and `k_min/n = 0.01` give `s = 299` (capped at `n`). This is the classical binomial audit-sample size for a sample in which no misstatement is expected. A without-replacement draw of that size has hypergeometric miss probability at most the binomial value, so the formula is the conservative one. The draw itself is without replacement. `--audit-size` overrides `s`. The grid does not override it.

First-use verification is a third mode, off in this grid. When enabled, the first `K` updates of a `(program binary digest, argv namespace)` run a full stock comparison and only then switch to the sample. The default `K` when the flag is passed is 2. The constructor default is off (`K = 0`). Each grid trial uses a fresh cache, so leaving the mode on would turn every trial into a full comparison and would not measure the sample. That is a disclosed choice, not a retune of `s`.

### Semantics (no new tool behavior beyond the gate)

The shim, the pin, the probe complement, the residue cap, the classifier, and the difference classes are the ones in the locked section. The audit compares the pinned replay, restricted to the sampled records, with one unpinned call on those records and the full reference. That is the comparison the warm-cache diagnostic already used. A cold cache now reaches it.

A SHIP whose `audit` field is null is a return of the gate bug. It is recorded as a deviation. It is not repaired by changing `s` after the rates are in.

### Pilot, seed 20261231 (not a result)

Host: this laptop. `n = 400` records, `500` models. Code was the uncommitted tree on `1c65571538afcc139af560156147e4276905f9b4` (`git_dirty_tracked` true). The measured run uses the commit that contains that code and this addendum, with a clean tracked tree. File: `pipeline/results/adversarial/pilot_v2.json`.

Clean contract: `SHIP`. Oracle mismatches: 0. Stock tblout rows: 400 on every trial. Every trial has `reused_rows` 0.

| Arm | Cell | Trials | Outcome | Layer | Audit |
|---|---|---:|---|---|---|
| shipped | C0 k=5 | 3 | correct_ship | none | `checked 20`, cold |
| shipped | C3 d=1 k=5 | 3 | true_refusal | neighbor_pad | not reached |
| shipped | C2 k=80 | 3 | true_refusal | random_pad, random_pad, audit | the audit trial is `REFUSE_AUDIT` on a cold cache |
| bounded | C0 k=5 | 2 | correct_ship | none | `checked 299`, cold |
| bounded | C2 k=80 | 2 | true_refusal | audit | `REFUSE_AUDIT`, cold |

Known-good: C0 shipped, replay identical to stock, audit ran with `reused_rows` 0.
Known-bad neighbor: distance 1 refused on the neighbor pad.
Known-bad hidden: one shipped trial and both bounded trials refused on the audit after the pads had not refused that trial. The unit test `test_cold_cache_audit_refuses_a_far_model_the_pads_do_not_see` is the same observation on a record that is outside the probe and outside the size-50 pad sample.

No redesign. The measured grid uses this check and the locked classifier.

### Measured grid v2 (locked)

Seed base `20261232`. Trial seeds use the same packing as the locked grid. Records 2000. Models 2500. Trials 50 per cell. `k` in {1, 5, 22, 100}. Cell order is the locked list (C0, C1, C2, C3 at distances 2, 5, and 20, C4).

Two arms, same cells, same seeds:

1. **shipped** — Bernoulli 0.02, floor 20, cold audit on, first-use off.
2. **bounded** — `epsilon = 0.05`, `k_min/n = 0.01`, `s = 299`.

Output: `pipeline/results/adversarial/measured_v2.json`. It records `git_head`, `code_commit`, the seed, per-trial decision, layer, outcome, difference class, `reused_rows`, `audit`, `audit_checked`, per-cell Wilson 95% intervals, and the audit-only prediction. Laptop wall times are `indicative_wall_s` and are not evidence.

Detection is true refusals divided by trials whose replay differed from stock. Wilson intervals use that denominator. C0 is the correct-ship count and the needless-refusal count.

The audit-only prediction at a cell's `k` is reported three ways, and it is not a pass/fail rule:

- with-replacement: `1 - (1 - k/n)^s`
- hypergeometric: `1 - C(n-k, s) / C(n, s)`
- shim: the affected set is drawn from the non-probe complement, so the miss probability is `C(E - a, k) / C(E, k)` where `E` is the complement and `a` is how many audited records lie in it

The sizing guarantee is `P(miss) <= 0.05` when `k/n >= 0.01`. For `n = 2000` that starts at `k = 20`. Cells with `k` in {1, 5} are below the guarantee. The prediction is audit-only: a pad refusal raises detection and is not a failure of the bound.

Positive control: C0, every k, on both arms. A needless refusal is reported.
Negative control: the pilot's distance-1 neighbor refusal, and the pilot's cold `REFUSE_AUDIT`. They are not repeated inside the 50-trial grid.

Stop conditions, which are not a third redesign: clean contract not `SHIP`; oracle mismatch; a trial throws. UNSAFE counts are kept. A cell with fewer than 2000 stock tblout rows is INCONCLUSIVE.

The server cost of the sample is taken from the committed headline phase files under `pipeline/results/exact_replay/headline_measured/`. `verify_s` on arm B is the shipped audit. The bounded fraction is that measurement times `s_bounded / s_shipped`. No new exclusive timing job is launched for this fraction. Laptop times are not that fraction.

### hmmscan confirmation

One real `hmmscan` per form, not part of the rates. Sequences are emitted from the same 24-profile Pfam prefix, with emit seed `20261238`. Trial seeds are `20261233` (C0), `20261234` (C1), `20261235` (C2), `20261236` (C3, distance 2), `20261237` (C4). Output is recorded beside the grid and cited from the v2 result. `--cpu 1`. If the process does not fit in 3 GB it is not forced; a non-exclusive CARC job is the fallback, and a missing run is reported as missing.

### Not claimed

The bound does not promise to catch a single affected record out of 2000. It does not estimate a Pfam-scale `q`. It does not retune `epsilon` or `k_min` after the grid. First-use is implemented and tested; this grid does not measure it.
