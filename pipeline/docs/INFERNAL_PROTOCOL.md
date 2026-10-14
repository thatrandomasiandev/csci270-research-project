# Infernal cmscan re-annotation (pre-registered after the pilot)

Written after `results/infernal/pilot.json` and before any measured
cmscan. The genome list was fixed in `results/infernal/semantics.md`
before the pilot. This file does not change it.

Pilot genome `GCF_049949635.1` (seed `20261041`) is not reused.
`-Z` is `2 * sequence residues / 1e6`, sequence lines only. A string
that does not satisfy `int(float(s) * 1e6) == 2 * residues` is not used.
The first pilot scan counted FASTA-header letters and was discarded
(`pilot.json` `discarded_header_z`); it was not compared.

## What the pilot decided

Infernal 1.1.5, Rfam 15.1, `--cpu 4`, 440 tblout body lines, 146 models.
Body lines are the claim. The `#` footer that records the date and the
`--tblout` path differs across runs and is metadata.

| Check | No clan | Clan (`--fmt 2 --clanin`) |
|---|---|---|
| Stock vs stock bodies | byte-identical | byte-identical |
| Oracle on the hit set, file order | byte-identical, 41.2 s vs stock 275.2 s | byte-identical, 40.9 s vs stock 272.3 s |
| Drop 5% of hit models, seed `20261043` (7 models) | differs, class `missing` | differs, classes `missing` and `value-only` |
| Omit `-Z` | class `value-only` | not repeated; `-Z` is on both argvs |
| Safety pads | pass | pass |
| `python3 -m acts run --strategy reference --pin` | `REFUSE_PIN`, `no fitted size member`, 1799.5 s | `REFUSE`, subset probe cannot open the full clan file, 551.9 s |

The clan oracle filters `Rfam.clanin` to models present in the replay
CM. `cmscan.c:2816` (`read_clan_info_file`) rejects a clan-file name
that is absent from the pressed index, so the unfiltered file cannot
be passed to a subset. A one-member clan line is kept so the survivor
still receives its clan name. The filtered replay matched. Coupling
is contained by the hit set.

The no-clan CLI refusal matches the semantics note: no size member is
fitted, so exact mode refuses. The oracle body matched, so the refusal
is needless. It is not EXACT, and it is not a reason to invent a pin.

The clan CLI does not reach that refusal. The fit's whole scan runs,
then a reference subset is invoked with the original `--clanin`, and
cmscan exits on the missing name. That is a probe failure, not a
finding that families fail to replay.

DX2 regression: `tests/test_exact_certificate.py` (6 tests) passed
during the pilot. A live DIAMOND rescan was not repeated.

## Measured run

Script: `scripts/infernal_measured.py`. Output:
`results/infernal/test_i.json`. Same argv, same `-Z` rule, same
filtered clan file on subset scans. Rfam 15.1 only. This pilot did
not scan 15.0; the question under test is a re-run against the new
release, and the new release is the database.

Genomes, seed `20261042`, already sorted in the semantics note:

1. `GCF_003956185.1` — timing genome and the one CLI confirmation
2. `GCF_013168095.1`
3. `GCF_022846215.1`
4. `GCF_028743355.1`
5. `GCF_030515405.1`
6. `GCF_030708175.1`
7. `GCF_037287675.1`
8. `GCF_054510725.1`
9. `GCF_055382035.1`
10. `GCF_059615465.1`

The script recomputes this draw from `inputs.tsv` and stops if it
differs. No genome is added after a scan.

Per variant, per genome: one stock scan and one oracle replay. Bodies
compared with the pilot's row key. On `GCF_003956185.1` the stock and
the oracle are each repeated three times. If those stock bodies
differ, that variant stops. The median of the three stock/oracle wall
ratios is the mechanism timing. It is not an end-to-end CLI speedup:
the CLI does not ship.

CLI confirmation, once, on `GCF_003956185.1` only, both variants.
Expected: no-clan `REFUSE_PIN` / `no fitted size member`; clan `REFUSE`
on the clan-file name check. A different decision is recorded and not
repaired.

Row floor: 2,000 stock body lines summed across the ten files, per
variant. A body match below the floor is INCONCLUSIVE. A body mismatch
is not EXACT. EXACT here means the oracle bodies match on all ten and
the floor is met. The CLI outcome is reported beside that, not folded
into it.

Mac walls are indicative. Scratch is `~/tmp/infernal_work/measured`.

## Outcome addendum (2026-10-14)

`results/infernal/test_i.json`, git `c464622`. Both variants,
oracle bodies byte-identical on all ten genomes. 4,217 stock body
lines each, above the floor of 2,000. Outcome EXACT for the oracle.
The CLI outcome is separate and is not EXACT.

Timing genome `GCF_003956185.1`, three paired walls. Median
stock/oracle ratio 6.67× on both variants (no-clan 6.666, clan
6.667). That is the replay against the hit set (158 models), not a
shipped CLI speedup.

CLI on that genome, once: no-clan `REFUSE_PIN`, `no fitted size
member`, 2058.5 s (probe tool time 616.8 s, then the full-reference
tool time 1408.3 s). Clan `REFUSE`, the subset probe cannot find
`alpha_tmRNA` in the full clan file, 628.2 s. Same decisions as the
pilot. Nothing was retuned.

## Addendum 2026-10-14 — identity exact mode and subset side files

Written before the end-to-end run. The two CLI refusals above are
separate gates. Each is a caller-declared rule. Neither name is
compiled into `acts/`.

### No pin when every value column is identity

Exact mode is requested with `--pin` and no template. If the fit's
numeric columns include a reference-size member (`entry_count` or
`total_entry_length`), inference runs as before, and a missing knob is
still `REFUSE_PIN`. If every value column is the identity normalizer,
there is no pin to infer: replay runs with the caller's argv unchanged.
The in-situ check is the probe-sample replay against the whole probe
sample, with no added option, and it must be byte-identical. The safety
check is unchanged. A size member with no pin still refuses.

Fixture tests: identity ships; a six-decimal `entry_count` column with
no knob is `REFUSE_PIN`; the pinned size-scaled release still ships;
the same shape with the pin omitted refuses.

### Subset side files are declared, not inferred

A subset invocation was passing an argv file that names entries absent
from the subset, and the tool exited. Inferring which file to rewrite
is the wrong default: a token that happens to equal an entry name is
not evidence that the file is an entry list, and a silent rewrite can
change a full run's answer. The caller declares the file, as with
`--pin` and `--prep`:

```
--subset-aux '{arg-after:--flag}:tokens'
```

On a subset invocation only, tokens in that file that name an entry
outside the subset are dropped. A token that is not an entry name is a
label and stays, so a one-member group still carries its label. A line
with fewer than two tokens left is dropped. A call on the full
reference uses the original file. HMMER-shaped replay with no such
rule is unchanged.

The rewritten file is not a new normalizer. It only makes the subset
invocation a legal call.
