# Knob inference: find the normalizer pin and the reporting thresholds from outside (pre-registered 2026-10-12)

Written **before** any implementation of `acts/infer_knobs.py` and **before**
any K1 run. Locked text is never edited; later changes are dated addenda.
No number below is a result.

## Why this exists

Exact mode takes the normalizer pin as caller data
(`--pin '-Z {entry_count}'`, EXACT_REPLAY_PROTOCOL.md) and, after E3, the
slack flags the same way. A reviewer will call that a per-tool plugin.
GeStore's plugins are hand-written per tool (Pedersen, Willassen, and
Bongo, Euro-Par HiBB 2013). The claim needs the system to find the pin
and the reporting thresholds itself. No tool name and no flag literal
are compiled into `acts/`.

## What inference may read

Only these:

1. The tool's argv (the command that will be wrapped).
2. The fitted contract: which output columns the closed family assigned
   to `entry_count`, `total_entry_length`, or `per_key_row_count`
   (REFERENCE_INCREMENTAL_PROTOCOL.md, fitter addendum). Identity and
   byte columns are part of that contract.
3. The tool's own help text.
4. Runs of the tool on sub-references.

Nothing else. Not the tool's source, not a manual, not an environment
variable, not a table of known flags.

`per_key_row_count` is not a pin target. The tool recomputes it from
its own reported set (EXACT_REPLAY_PROTOCOL.md). Inference searches
only over size members that the contract actually assigned:
`entry_count` and `total_entry_length`.

## Help-text candidates

Run `<tool> -h`, capturing stdout and stderr. The exit code is ignored.
If that text yields no numeric-argument option, run `<tool> --help` the
same way and use that text instead.

One candidate per help line, in file order. A later line that repeats
an option token is ignored. The option token is the flag immediately
before a numeric placeholder, or the flag in `--opt=<placeholder>`:

- a bracketed placeholder whose name is one of `x`, `n`, `num`, `int`,
  `float`, `double`, `integer`, `number`, `real`, `size`, `count`,
  `value` (case-insensitive);
- a bare placeholder token `N`, `NUM`, `INT`, `FLOAT`, or `NUMBER`.

A line with no such placeholder is not a candidate, even if it prints a
default. File placeholders (`<f>`, `<file>`, `<path>`, `<dir>`,
`<string>`) are not numeric.

A printed default on that same line is recorded when it matches
`[10.0]` (a finite decimal or scientific literal in square brackets),
`(default: 10)` / `(default 10)` / `(default=10)`, or `default: 10` /
`default=10`. No default means the option can still be a normalizer
candidate and cannot be a threshold candidate.

Each candidate is `{option, default, help_line}`.

## Normalizer knob

Parameters fixed now. `M(W)` is `|W|` for `entry_count` and the sum of
per-format entry lengths for `total_entry_length`.

Build W and H as below. H is a subset of W, in W's file order.

Baseline, two runs, same records, no extra option:
`run(records, H)` and `run(records, W)`. On rows whose entry is in H
and whose key is in both outputs, at least one column fitted to M must
differ in its printed token. Otherwise this probe cannot see M. The
sizes are locked, so inference does not enlarge them. That member is
`no knob` with reason `probe cannot see M`.

Then, for each candidate option `o`, one run: `run(records, H, o=M(W))`.
The value is passed as the argv pair `o` then the integer decimal of
`M(W)`. Accept `o` for M only when, on shared rows (keys in both that
run and `run(records, W)`, entry in H), every column fitted to M is
byte-identical to the W run and every identity column and every byte
column is byte-identical. Any other outcome rejects `o` for this
member. A run that throws is a rejection `tool failed`, not an accept.

Exactly one accepted option: the pin template is `{option} {{{member}}}`
with the member name inside the braces. Zero accepted: this member is
`no knob`. Two or more: keep only those for which every shared row's
raw body line (the line that is not a `#` line) is byte-identical to
the W run, on every contract table. If that leaves exactly one, it is
the pin. Otherwise the member is `no knob` (reason `tie`).

The reported `pin` is the templates of the fitted size members, in the
order `entry_count` then `total_entry_length`, joined by one space.
If any fitted size member is `no knob`, the reported pin is `no knob`
and exact mode refuses. A contract with no fitted size member is
`no knob`.

## Threshold knobs

Slack factor `s = 4`, fixed. For each candidate that has a numeric
default `d`, one run: `run(records, W, o=d·s)`. The value is the
integer decimal when `d·s` is an integer, otherwise the shortest
round-trip. This run is not reused as the normalizer run: the argument
is different.

Compare that run to the baseline `run(records, W)`, per contract table,
row key as the fitter defines it (record, entry, optional row index):

- Accept only if every baseline key is still present, at least one
  table's key set is a strict superset, every shared row's raw body
  line is byte-identical, and at least one numeric column has every
  added row's parsed finite value inside `(d, s·d]`.
- That column is the one the threshold applies to. Report it as
  `{table}:{index}`. Several qualifying columns are joined with commas
  in table-name then index order.
- A row set that does not change is `row set unchanged`. A missing
  baseline key is `rows dropped`. A shared line that differs is
  `shared rows changed`. Added rows with no bounded column are
  `no bounded column`. Those are not thresholds. A filter or a scoring
  knob fails one of these. It is not a threshold.

## Cost

Each candidate is invoked at most once for the normalizer question and
at most once for the threshold question. No search over scales. Help
text is not a probe call. `tool_calls` counts `invoke` calls inside
inference. The cap is 96. Past the cap, remaining candidates are
`cap` and are not accepted. Identical invocations may be cached by the
driver; a cache hit is not another `tool_calls` increment.

The fitter calls that produce the contract are extra. They are recorded
as `fit_calls`. Probe cost for this test is `P = tool_calls + fit_calls`.

## Output

```
{"pin": "...", "thresholds": [{"option": "...", "default": 0, "column": "..."}],
 "rejected": [{"option": "...", "role": "...", "reason": "..."}],
 "tool_calls": 0}
```

`pin` is either the derived template or the string `no knob`. The K1
result file also lists every help candidate with its accept or reject
reason, the git hash, the host, and the tool version line.

## Test K1

Tool and argv, HMMER 3.4 on `PATH`, no `--cut_ga`:

```
hmmscan --noali --cpu 1 --tblout {output:tbl} --domtblout {output:dom}
  {reference} {input}
```

`--cpu 1` is load control so this probe does not sit on the E3 timing
run. It is not a scientific flag. The help line for that option is
still a candidate and must be rejected.

Queries: 50 proteins from
`pipeline/data/recurrence/A/GCF_002853805.1_protein.faa.gz`.
`random.Random(20261014).sample(range(n), 50)`, indices sorted, records
written in that file order.

Reference: Pfam 38.2, `pipeline/data/hmmer/Pfam-A.hmm.gz`. Let `N` be
the number of `//`-terminated model blocks. W is 400 of them:
`random.Random(20261014).sample(range(N), 400)`, indices sorted, models
written in that file order. H is the first part of
`partition_indices(400, 2, 20261014)` (the fitter's Fisher–Yates,
`acts/reference_fit.py`), 200 entries, in W's file order. The
complement is the other part. Do not press the full Pfam file. Each
sub-reference the driver writes is at most these 400 models, prepared
with `hmmpress -f` so the tool can read it. Pressed sidecars stay in
the work directory, not in git.

Contract: `probe_fit` on W with `primary_parts=[H, complement]`,
`sample=False`, same records. Column members on the returned tables are
the contract even when the decision is REFUSE because row-key sets
differ (the R2n shape). A tie is resolved by the fitter's own
disambiguating probe, not by a new rule. If that result assigns no
`entry_count` column, K1 is INCONCLUSIVE. Do not paste the `--cut_ga`
column map from T1 in its place.

Ground truth, written now:

| Check | Required |
|---|---|
| Pin | `-Z {entry_count}` |
| Not the pin | `--domZ` is not the pin |
| Thresholds include | `-E` and `--domE` |
| Allowed extra thresholds | `--incE` and `--incdomE`, and only if the recorded column is an inclusion count (`inc`) |
| Must be rejected | `--F1`, `--F2`, `--F3`, `--seed`, `--cpu` |

A missing help token is not an acceptance. A present token that is
accepted against the "must be rejected" row is a failure.

## Test K1n — negative controls (fixtures, no tool binary)

1. A fake tool whose normalized column has no setting option. Inference
   returns `no knob`.
2. A fake tool whose only numeric option changes a score arbitrarily.
   That option is rejected. It is not the pin and not a threshold.

## Kill rule

If the inferred pin is not `-Z {entry_count}`, or `-E` or `--domE` is
missing from the thresholds, or any decoy in the "must be rejected" row
or in K1n is accepted, knob inference is not shippable. Write the
measured outcome down and stop. Do not retune `s`, the placeholder
list, the accept rule, or the seeds.

Missing data, a missing binary, or fewer than 400 models is
INCONCLUSIVE, not a kill and not a pass.

## Optional K2

Only if a `diamond` binary is already on `PATH`. No download. Same
inference, same code path, on `diamond blastp`. Whatever it returns is
exploratory. There is no ground truth and no kill. Do not time it.

## Integration (not this milestone)

Do not edit `reference_run.py` until E3 has shipped. When a later patch
wires this in:

- If inference returns a pin other than `no knob`, `--pin` becomes
  optional. The wrapper substitutes `{entry_count}` and
  `{total_entry_length}` in that derived template the same way it
  substitutes a caller-supplied `--pin`.
- `--slack` becomes optional. The options in `thresholds` are the ones
  multiplied by the slack factor. Every other option stays at the tool
  default. An inclusion option is widened only when inference listed it.
- If inference returns `no knob`, exact mode refuses, the same outcome
  as `REFUSE_PIN` when a fitted size member is unset.
- A fitter REFUSE on decomposition still refuses reuse. Knob inference
  does not override that.

## Addendum 2026-10-12 — worker-count probe guard (before any K1 run)

No K1 output exists yet. The locked base argv is `--cpu 1`. On this
build the help default of that option is 0, and 0 means every core.
The normalizer probe would pass `M(W) = 400`. Neither value is
executed. The driver refuses an invocation that sets that option to
anything but 1, and inference records the refusal. A refused probe
cannot be accepted. The accept rule, `s`, the seeds, and the ground
truth are unchanged.

## Addendum 2026-10-12 — K1 outcome

Rules above are unchanged. Result file `results/knob_inference/k1.json`.
Git `48f3371`. Host `Joshuas-MacBook-Pro-3.local`, arm64, HMMER 3.4
(Aug 2023). The reference file has 30,134 model blocks, which matches
the stated Z. W is 400 models and H is 200. Diamond is not on `PATH`;
K2 was not run.

**K1 — INCONCLUSIVE.** Not a pass and not a kill. The whole reference
and both halves wrote header-only tblout and domtblout: 0 body lines
in every table (MEASURED, three scans, about 0.1 s each, `--cpu 1`).
`probe_fit` returned SHIP with an empty column list, because there
were no aligned rows and therefore no `entry_count` column. Knob
inference did not start. No pin, no thresholds, no decoy judgment.
`fit_calls` = 3. Inference `tool_calls` were not taken. Probe cost
P = 3.

A zero row set is a property of this seeded draw. E1 recorded 534
tblout body lines on 300 queries against all 30,134 models. Scaling
that rate to 50 queries and 400 models is about one expected hit.
The locked sample can miss. The seeds are not redrawn here.

## Red-team

**Attack 1. "The pin is a HMMER plugin."**
Defeat: `acts/infer_knobs.py` contains no tool name (the existing
`test_no_tool_names_in_acts` guard) and no flag literal. K1n's fixtures
are not that tool. The template is the option token the probe accepted,
plus the member name.

**Attack 2. "Any flag that changes the output is called the pin."**
Defeat: K1n's decoy must be rejected. K1 must reject `--F1`, `--F2`,
`--F3`, `--seed`, and `--cpu`.

**Attack 3. "The parser is a hand-written HMMER help grammar."**
Defeat: the unit tests feed canned lines in the four shapes above
(`-Z <x>`, `--domE <x>`, `--opt=N`, `--opt N`, defaults `[10.0]` and
`(default: 10)`). A line with no numeric placeholder produces no
candidate. Widening the placeholder list after K1 is a post-hoc
addendum.

## Addendum 2026-10-12 — K1r (pre-registered)

Written **before** any K1r run and before any edit to `acts/infer_knobs.py`
for this test. No number below is a result. K1 stays INCONCLUSIVE. Its
seeds are not redrawn. `results/knob_inference/k1.json` is not rewritten.

K1's 50-by-400 draw had about one expected hit and wrote empty tables, so
the accept rule never saw a row. K1r asks the same question on a sample
built so that hits exist. The accept rule, `s = 4`, the placeholder list,
the cap of 96, and the worker-count guard (a probe that sets the worker
option to anything but 1 is refused and cannot be accepted) are unchanged.

### Sample construction

This scan is not a K1r result. Record its wall and its tblout body-row
count as SAMPLE-CONSTRUCTION.

Queries come from
`pipeline/data/recurrence/A/GCF_002853805.1_protein.faa.gz`.
The E1 index list is `sorted(random.Random(20261012).sample(range(n), 300))`,
which is the order that sample file was written. One stock scan of those
300 records, in that order, against full Pfam 38.2
(`pipeline/data/hmmer/Pfam-A.hmm.gz`):

```
hmmscan --noali --tblout T --domtblout D <Pfam 38.2> <queries>
```

No `--cut_ga`, no worker flag, no `-Z`. `--tblout` and `--domtblout` are
how the row count is recorded. They are not pins and not thresholds.
The database argument is that Pfam file. A pressed copy already built
from that same file may be substituted so the scan can read it; pressing
the full file is not a probe call.

Q is the first 50 indices in that sorted list whose query name has at
least one tblout body row. If fewer than 50 of the 300 have a body row,
K1r is INCONCLUSIVE. Do not draw a new sample.

W has 400 models. Hit models are the Pfam entries, in 38.2 file order,
whose NAME or ACC key equals the target name or accession on a tblout
body row for a query in Q. A target that matches no entry is counted as
unmatched and is not a member of W. If there are more than 400 hit
models, W is the first 400 in file order and that fact is recorded; the
fill step does not run. Otherwise the fill is
`random.Random(20261015).sample` of the non-hit model indices, size
`400 - |hits|`, and W is hits plus fill, written in 38.2 file order.

H is 200 of W, stratified, in W's file order. Hit-in-W and fill-in-W are
the two strata. One `random.Random(20261015)`, independent of the fill
draw, samples `len(stratum) // 2` from the hit stratum and then from the
fill stratum. If those floors sum to less than 200, the remainder is
the unselected fill models in file order, then the unselected hit models
in file order, until `|H| = 200`. That remainder is not a new sample.
The complement is `W \ H`. If `|W| < 400`, K1r is INCONCLUSIVE.

### Power floor

Before any candidate probe, under the K1r-b argv (default E-value
reporting, `--cpu 1`, no `--cut_ga`): `run(Q, H)` and `run(Q, W)`. A
shared tblout row is a body line whose target name or accession is a key
of an H entry and whose `(query name, target name)` pair occurs in both
outputs. The two runs must share at least 30 such rows. If they do not,
K1r is INCONCLUSIVE. Stop. Do not redraw Q, W, or H, and do not probe
candidates on either arm.

The same count is recorded for the K1r-a argv. If K1r-b cleared the
floor and K1r-a shares fewer than 30 rows, K1r-a alone is INCONCLUSIVE
and its candidates are not probed. That is the empty-table failure, not
a kill and not a redraw.

### Arms

Both arms use the same Q, W, and H. Sub-references are at most these 400
models, prepared with `hmmpress -f` in the work directory, not in git.

K1r-a argv:

```
hmmscan --cut_ga --noali --cpu 1 --tblout {output:tbl} --domtblout {output:dom}
  {reference} {input}
```

K1r-b argv is that command without `--cut_ga`.

Ground truth, written now:

| Check | K1r-a | K1r-b |
|---|---|---|
| Pin | `-Z {entry_count}` | `-Z {entry_count}` |
| Not the pin | `--domZ` | `--domZ` |
| Thresholds | none accepted | must include `-E` and `--domE` |
| E-value flags | `-E`, `--domE`, `--incE`, `--incdomE` rejected | `--incE`, `--incdomE` may be accepted only with the column recorded |
| Bit-score flags | any acceptance is a kill | `-T`, `--domT`, `--incT`, `--incdomT` may be accepted or rejected; the reason is recorded |
| Must be rejected as pin and as threshold | `--F1`, `--F2`, `--F3`, `--seed`, `--cpu`, `--domZ` | same |

`--cut_ga` overrides E-value reporting, so an E-value option that does
not change the row set is a rejection. The shipped reason for that
outcome is `row set unchanged`. K1r-a treats every non-accept as the
required no-effect rejection. Accepting any threshold on K1r-a is a
kill. A help token that the parser does not emit is not an acceptance;
record it as absent.

### Fit path

K1r-a calls `probe_fit` on W with `primary_parts=[H, complement]`,
`sample=False`, `monotone=False`. Gathering cuts do not move with the
database size, so the row-key sets are the ones the base fitter already
accepts.

K1r-b calls the same fit with `monotone=True`. That is the
monotone-decomposition fit shipped in `fbe39d1`: `rows(full) ⊆ ∪ rows(parts)`
is allowed, and extra rows on the parts are allowed. `probe_fit` already
takes `monotone` without `--pin` and without `--slack`. The exact-mode
gate that sets `monotone` only when both are present is in
`reference_run.py` and is not on this path. No fit-only switch is added
to `infer_knobs.py`. Inference is not given `--pin` or `--slack`.

Column members on the returned tables are the contract. If a fit assigns
no `entry_count` column, that arm is INCONCLUSIVE. A REFUSE that still
assigned an `entry_count` column does not skip inference; the decision
and the reason are recorded. A tie is resolved by the fitter's own
disambiguating probe.

### Pin comparison (locked)

On shared rows the shipped `_normalizer_reason` already compares only
columns whose member is the one being pinned, plus columns whose member
is `identity` or `byte`. `per_key_row_count` columns are not compared.
domtblout conditional E-values depend on the number of reported targets,
which differs between H and W for a reason that is not the entry-count
pin. That exclusion is the rule for K1r. It is not a change to the
function. If an identity or byte column differs, the reason is
`identity columns differ` and the candidate is not the pin. The
tie-break, used only when two or more options pass that comparison,
stays the shipped full-body comparison.

### Kill rule

On either arm: the pin is not `-Z {entry_count}`, `-Z` is not the
accepted normalizer, or a decoy in the "must be rejected" row is
accepted as a pin or as a threshold. On K1r-b: `-E` or `--domE` is
missing from the thresholds. On K1r-a: any threshold is accepted.
Any one of these means knob inference is not shippable. Write the
measured outcome and stop. Do not retune `s`, the placeholder list, the
accept rule, or the seeds.

Missing data, a missing binary, fewer than 400 models, fewer than 50
queries with a hit, or a failed power floor is INCONCLUSIVE, not a kill
and not a pass.

### Cost

`tool_calls` is counted inside `infer_knobs`, per arm. That number is P
for this test. `fit_calls` are the `probe_fit` invocations and are
recorded beside P, not inside it. The construction scan and a power-floor
pair that is not re-entered through `infer_knobs` are recorded separately
and are not P. A driver-level cache hit still counts as a `tool_calls`
increment when `infer_knobs` invokes it; only `infer_knobs`'s own cache
suppresses the increment.

### Output

`results/knob_inference/k1r.json`: git hash, host, HMMER version line,
SAMPLE-CONSTRUCTION (wall, tblout body rows, `|Q|`, hit-model count,
unmatched targets, `|W|`, `|H|`, whether hits were truncated at 400),
the power-floor shared-row counts, and for each arm every help candidate
with accept or reject and the reason, the fit decision, and `tool_calls`.

## Addendum 2026-10-12 — K1r outcome

Rules above are unchanged. Result file `results/knob_inference/k1r.json`.
Git `7c64e27`. Host `Joshuas-MacBook-Pro-3.local`, arm64, HMMER 3.4
(Aug 2023). No retune. `--pin` and `--slack` stay required.

**SAMPLE-CONSTRUCTION** (not a K1r result). One `hmmscan --noali` of the
E1 300 against pressed Pfam 38.2: wall 60.01 s, 1,361 tblout body rows,
2,729 domtblout body rows. 288 of the 300 queries had a tblout row. Q is
the first 50 of those in sample order (289 tblout rows on Q). Hit models
277, none unmatched, not truncated. Fill 123. `|W| = 400`. H is 138 of
the hit stratum and 62 of the fill (floors 138 and 61, one remainder
from the fill in file order). The reference has 30,134 models.

**Power floor, passed.** K1r-b shared 143 tblout rows on H (H 143 rows,
W 290). K1r-a shared 53 (H 53, W 105). Both are at least 30.

**K1r-a — PASS.** Fit SHIP. Pin `-Z {entry_count}`. `--domZ` rejected
(`m-columns differ` as a normalizer, `no numeric default` as a
threshold). No threshold accepted. `-E`, `--domE`, `-T`, and `--domT`
were rejected because the binary refuses them together with `--cut_ga`
(`tool failed`). `--incE`, `--incdomE`, `--incT`, and `--incdomT` have
no printed default, so they were not threshold probes (`no numeric
default`); as normalizers they also failed the same incompatibility.
`--F1`, `--F2`, and `--F3` were `row set unchanged`. `--seed` was
`shared rows changed`. `--cpu` was the worker-count refusal. None of
those is an accept. P = `tool_calls` = 26. Fitter `probe_invocations`
= 3.

**K1r-b — KILL.** Fit REFUSE (`tbl: column 16 matches no normalizer`)
with three `entry_count` columns assigned, so inference ran. Pin
`-Z {entry_count}`. `--domZ` rejected as on K1r-a. Decoys rejected:
`--F1` and `--F3` `shared rows changed`, `--F2` `row set unchanged`,
`--seed` `shared rows changed`, `--cpu` worker-count refusal, `--domZ`
not a threshold. `-E` at 40 left both tables unchanged (290 tblout and
506 domtblout body lines; reason `row set unchanged`). `--domE` at 40
wrote 515 domtblout body lines against 506 and was `shared rows
changed`. Neither is an accepted threshold, so `-E` and `--domE` are
missing. P = 26. Fitter `probe_invocations` = 3.

Knob inference is not shippable. The accept rule, `s`, the placeholder
list, and the seeds were not changed.

## Addendum 2026-10-12 — K1s (pre-registered redesign after the K1r KILL)

Written **before** any K1s run and before the K1s edit to `acts/infer_knobs.py`.
No number below is a result. K1 stays INCONCLUSIVE. K1r-a stays PASS.
K1r-b stays KILL. Their seeds, `s = 4`, and their accept rule are not
retuned and are not the rule for this test. K1s is a redesign after that
known failure, labelled as such.

K1r-b relaxed each default `d` to `4d`. On a 400-model sub-reference the
P-value pre-filters already drop every row the E-value cutoff would have
added, so `-E` was `row set unchanged`. `--domE` did add domain rows, and
those rows renumbered the domain index, changed the domain-count columns,
and changed per-target domain counts. The K1r rule required shared rows
to be byte-identical, so `--domE` was `shared rows changed`. Neither
failure is evidence about a tighter cutoff. K1s tightens, and it does not
treat a renumbered index or a row-count column as a change of row identity.

The placeholder list, the cap of 96, and the worker-count guard (a probe
that sets the worker option to anything but 1 is refused and cannot be
accepted) are unchanged. Help text is still not a probe call.

### Samples

The held-out sample decides the verdict. The secondary sample is reported
and is not used for the verdict. It is the K1r sample, which informed
this redesign.

Held-out queries come from
`pipeline/data/recurrence/A/GCF_002090355.1_protein.faa.gz`.
Draw `sorted(random.Random(20261016).sample(range(n), 300))` and scan
those records, in that order, against full Pfam 38.2
(`pipeline/data/hmmer/Pfam-A.hmm.gz`) with the K1r construction command:
default reporting, no `--cut_ga`, no worker flag, no `-Z`. That scan is
SAMPLE-CONSTRUCTION, not a K1s result. Record its wall and its body-row
counts. A pressed copy of that same Pfam file may be substituted so the
scan can read it. Pressing is not a probe call.

Q is the first 50 indices in that sorted list whose query name has at
least one tblout body row. If fewer than 50 of the 300 have a body row,
the held-out sample is INCONCLUSIVE. Do not draw a new sample.

W has 400 models. Hit models are the Pfam entries, in 38.2 file order,
whose NAME or ACC key equals the target name or accession on a tblout
body row for a query in Q. The same unmatched-target and truncation rules
as K1r apply. The fill, when there are fewer than 400 hit models, is
`random.Random(20261016).sample` of the non-hit model indices, size
`400 - |hits|`. W is hits plus fill, written in 38.2 file order.
`|W| < 400` is INCONCLUSIVE.

H is the K1r stratified half of W, with a fresh `random.Random(20261016)`
that does not continue the fill draw: `len(stratum) // 2` from the hit
stratum, then from the fill stratum, then remainder in file order, fill
stratum first, until `|H| = 200`. The complement is `W \ H`.

The secondary sample is the K1r sample: the same genome, the same
`random.Random(20261012)` draw of 300, the same fill and stratified half
at `random.Random(20261015)`, and the same Q, W, and H rules. Rebuilding
it from those seeds is the same sample. Its construction scan is labelled
SECONDARY-SAMPLE and is not a held-out result.

### Power floor

On the held-out sample, before any candidate probe, under the K1s-b argv
(default reporting, `--cpu 1`, no `--cut_ga`): `run(Q, H)` and `run(Q, W)`.
A shared tblout row is defined as in K1r. The two runs must share at least
30 such rows. If they do not, the held-out sample is INCONCLUSIVE. Stop.
Do not redraw Q, W, or H, and do not probe candidates on either held-out
arm. The secondary sample is still run and still does not decide the
verdict.

Record the same count for the K1s-a argv. If K1s-b cleared the floor and
K1s-a shares fewer than 30 rows, K1s-a alone is INCONCLUSIVE and its
candidates are not probed. The secondary sample uses the same floor. A
secondary floor failure is reported and does not change the held-out
verdict.

### Arms

Both arms of a sample use that sample's Q, W, and H. Sub-references are
at most these 400 models, prepared with `hmmpress -f` in the work
directory, not in git.

K1s-a argv is the K1r-a argv (`--cut_ga`). K1s-b argv is the K1r-b argv
(that command without `--cut_ga`). The fit path is the K1r fit path:
K1s-a uses `monotone=False`, K1s-b uses `monotone=True`. A fit that
assigns no `entry_count` column makes that arm INCONCLUSIVE. A REFUSE
that still assigned `entry_count` does not skip inference. Inference is
not given `--pin` or `--slack`.

### Structural columns

Computed from the default run `run(Q, W)` only, before any comparison,
per output table. A column is an integer column when every body row has
a token of optional sign and digits only. A is the integer columns for
which one of the following holds for every body row:

1. Count. There is one table T, possibly this one, and one key, either
   `(record, entry)` or `(record)`, such that the cell equals the number
   of body rows in T that share that row's key.
2. Rank. In this table, in file order, the cell equals the row's 1-based
   position within its `(record, entry)` group.

A column that fails either test on any row is not in A. A table with no
body row has an empty A. Record A as column indices per table, with
which of the two tests matched.

`per_key_row_count` columns are the contract columns whose member is
`per_key_row_count`. Row identity is the body row with the A columns and
those columns removed. Identity comparison is by multiset.

### Pin

Pin detection is the K1r pin detection, unchanged, including which
columns `_normalizer_reason` compares. It has to pass on the held-out
sample on both arms. The secondary sample records its pin and does not
decide.

### Thresholds

Tighten only. Do not relax. For each help candidate with a numeric
default `d`, for `f` in `(10, 100, 1000)` in that order, one run
`run(Q, W)` with that option set to `d/f`. The value is the integer
decimal when `d/f` is an integer, otherwise the shortest round-trip.
`t = d/f` is that same number. A throw on a run is `tool failed` for
that `f`. It is not an acceptance. Later factors are still run.

Accept the option as a reporting threshold on table X at the first `f`
where all three hold:

1. The identity multiset of X under the tight run is a proper submultiset
   of the default run. Rows only disappear. At least 3 identities are
   gone.
2. X has a printed numeric column `c` such that every removed row has
   `c > t` and every kept row has `c ≤ t`, with no exception and no
   tolerance. Removed rows are the default rows in the multiset
   difference. Kept rows are the rows that remain. Record every such
   `c`, as `table:index` in index order.
3. Each kept row's identity equals its default identity. Columns in A
   and `per_key_row_count` columns may differ. No other column may.

The first accepting `f` for that table is the one recorded. Other tables
keep walking the ladder. One run of an `f` feeds every table.

If no `f` removes at least 3 identities on any table, and some `f`
leaves every identity multiset unchanged while a cell in A or in a
`per_key_row_count` column differs, the option is `non-reporting
threshold`. That class is never reporting. It is the expected class for
an inclusion flag whose only change is a count column.

If no `f` removes at least 3 identities and no `f` is that column-only
change, the option is INCONCLUSIVE. INCONCLUSIVE is not a rejection and
not an acceptance.

If some `f` removes at least 3 identities and no table accepts, the
option is rejected. A pure disappearance with no column that cuts at
exactly `t` is `no exact bound`. New identities, or a kept identity
whose non-A, non-`per_key_row_count` cells differ, are `shared rows
changed`. A throw with no later accept is `tool failed`. A candidate
with no numeric default is not probed; record `no numeric default`.

### Ground truth

Written now. The held-out sample decides. The secondary sample does not.

| Check | K1s-a (`--cut_ga`) | K1s-b (default reporting) |
|---|---|---|
| Pin | `-Z {entry_count}` | `-Z {entry_count}` |
| Not the pin | `--domZ` | `--domZ` |
| Reporting thresholds | none accepted | exactly `-E` on tblout and `--domE` on domtblout |
| Bounding column | — | record which column cut at `t`. The full-sequence E-value is the one `-E` must use. The domain E-value `--domE` uses is the one `--domE` must use |
| `--incE`, `--incdomE` | not reporting | `non-reporting threshold`, rejected, or `no numeric default`. Never reporting |
| `-T`, `--domT`, `--incT`, `--incdomT` | not reporting | not reporting. No numeric default is allowed; record why |
| Not reporting thresholds | `--F1`, `--F2`, `--F3`, `--seed`, `--cpu`, `--domZ`, `-Z` | same |

An extra reporting pair, a missing required pair, a wrong pin, or any
of those decoys accepted as a pin or as a reporting threshold, on the
held-out sample, is a ground-truth miss.

### Kill rule

Any ground-truth miss on the held-out sample kills that arm. Either arm
killing means knob inference is not shippable. Write the measured
outcome and stop. Do not retune the factors, the placeholder list, the
accept rule, the structural-column tests, or the seeds.

Missing data, a missing binary, fewer than 400 models, fewer than 50
queries with a hit, or a failed held-out power floor is INCONCLUSIVE,
not a kill and not a pass.

### Cost and output

`tool_calls` is counted inside `infer_knobs`, per arm, per sample. That
number is P for that arm. Each factor is its own call. A driver cache
hit still counts when `infer_knobs` invokes it. `fit_calls` sit beside
P. Construction scans are not P.

`results/knob_inference/k1s.json`: git hash, host, HMMER version line,
both samples' construction records, both power floors, A per table, and
for every candidate every `f` with accept, reject, or inconclusive and
the reason. Held-out and secondary are separate objects. The verdict
fields are the held-out arm verdicts only.
