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
