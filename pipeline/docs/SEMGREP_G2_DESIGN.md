# Semgrep as TARE's non-biology domain: integration design and G2 pilot (2026-10-23)

G1 passed (pipeline/results/nonbio/g1_laptop.json): T(f) = 4.3 + 171.3·f s, 97.6% of cost
proportional to rules, projected 6.4× at 13.4% changed. This document fixes what TARE must learn
before the pilot, and the pilot's checks.

## What TARE needs that it does not have

| # | Gap | Found by | Generic fix (no Semgrep-specific code) |
|---|---|---|---|
| 1 | Reference format: a rule set is one YAML file with a top-level `rules:` list; each list item (keyed by `id`) is an entry. Semgrep rejects multi-document YAML and duplicate `rules:` keys, so a subset file must be `rules:` + the chosen items. | probe 2026-10-23 | A YAML-list reference parser: entries = items of one top-level list; key = a named scalar field (`id`); the writer emits the list header once. Applies to any tool whose reference is a YAML list of keyed items. |
| 2 | Output format: TARE reads line tables (tab or whitespace) and finds the record and entry columns by exact token match. Semgrep's line formats glue the rule id to other text (`--emacs`: `path:line:col:severity(rule-id):code:message`), so no column equals a rule id. JSON (`--json`) has `path` and `check_id` as separate fields. | probe 2026-10-23 | A JSON-records output parser: rows = elements of one top-level array (`results`), cells = flattened scalar fields; every other top-level field must match stock exactly. Applies to any JSON-emitting scanner (Semgrep, Bandit, Trivy, ESLint, Ruff). |
| 3 | Records: Semgrep takes target paths as arguments, not a list file. | probe | The `{input}` placeholder expands to the record subset's paths (caller data, like `--subset-aux`), or a target directory built per subset. |

## Determinism (stock vs stock, from G1)

Three repeats at f = 0.10, 0.50 and 1.00: `results`, `errors`, `paths`, `skipped_rules` and
`profiling_results` identical; only the top-level `time` field differs. The pilot must find
why `time` is present (likely the `-o` output path) and either remove it from the run or treat it
as the one declared volatile field. The 2–3 `errors` are per-file Python syntax errors in the
corpus (deterministic; they belong to records, not rules).

## Exactness claim for this domain

The goal is the paper's claim: output byte-identical to a full run. With JSON this holds only if
TARE re-serializes exactly as Semgrep does (key order, separators, number format). The pilot
tests byte identity first. If bytes cannot be matched, the claim for this domain is stated as
"parsed-JSON identical, all fields" and the paper says so explicitly. It is not quietly weakened.

## Couplings to check (semantics review, AGENTS.md step 1)

| Behavior | Risk | How the pilot detects it |
|---|---|---|
| `nosemgrep: rule-id` comments | Rule-addressed suppression; entry-local | Plant one; the replay must match stock |
| Rule-level `paths:` include/exclude | Entry-local | Covered by ordinary replay |
| Cross-rule deduplication of identical findings | Cross-entry coupling | Two rules that fire on the same span; compare replay vs stock |
| Per-rule timeouts (`--timeout`) and memory limits | Nondeterminism | Stock-vs-stock identity at full size; any timeout → refuse |
| Output order of `results` | Order coupling | Compare ordered; if stock order is a sort by (path, line, rule), TARE's merge must reproduce it |
| `paths.scanned`, `skipped_rules`, `errors` | Global fields | Must equal stock; a changed rule can change `skipped_rules` |
| Rule-set-wide options (e.g. `--severity` filters) | Argv knobs | Fixed argv; keyed in the namespace |

## G2 pilot (laptop, disjoint data, seed 20261322)

1. Code on its own branch with tests: parsers 1–3, each with a known-good and known-bad case.
2. Pilot corpus disjoint from G1's: different repositories, chosen by seed.
3. Releases: two consecutive semgrep-rules commits with a nonzero rule diff, chosen by seed.
4. Checks: stock-vs-stock identity; positive control (replay ships and equals stock); negative
   control (an injected dropped finding must be refused); inference finds no pin; each coupling
   above exercised; power floor of at least 500 findings in the replayed set.
5. Outcome: pass → pre-register G3 (CARC, fresh repos, three consecutive releases). A failed check
   gets one fix; a second failure becomes the stated limitation.

## Estimate

Parsers and tests: 3–4 days. Pilot: 1–2 days. G3 on CARC: 3–4 days wall. Paper: 1 day.
Total about 2 weeks, inside the December 8 deadline, running alongside the CARC queue.
