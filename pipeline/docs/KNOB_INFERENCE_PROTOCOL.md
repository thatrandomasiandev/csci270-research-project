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
