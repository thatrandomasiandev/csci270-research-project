# Semgrep domain pilot (TARE)

Pilot only. Numbers here are not measured CARC results and must not enter the paper.

## What ran

- Branch `exp/semgrep-domain`, scratch `~/tmp/tare_semgrep_p2/`, Semgrep 1.182.1, `-j 2`, seeds **20261322** (pilot), **20261324** (min-delta fix), **20261325** (errors subsets).
- Release pair (seeded among consecutive commits that touch Python rules): `241477b` → `46a0ecf` (OWASP 2025 mapping). Concatenated 378 Python rules per commit with duplicate bare ids path-qualified.
- Corpus: 1000 Python files on disk, disjoint from G1’s `~/tmp/tare_g1/venv/lib` by path and content hash. Power: **3269** findings on the newer concat (floor 500).

## What it found

1. **GATE R PASS** on every committed tool table found (HMMER tblout fixture; DIAMOND/BLAST+ `reference_boundary_tables/*.tsv`) and on live hmmscan tblout/domtblout. No committed Infernal tblout or pfscanV3 tables. Shared tab-aware parse matches origin/main on these files; no shared-path revert required.
2. **Stock vs stock PASS** (only `time` differs).
3. **Positive control FAIL (limitation).** Fill on the older concat SHIPs under identity. Update to the newer concat **REFUSE**s (`IC2 neighbor missing_candidate` on the full OWASP pair; `REFUSE_MATCH` non-candidate pair on a one-rule min-delta fix). Hand-fixture v1→v2 still SHIPs. Semgrep shows cross-rule couplings that exact replay’s IC2/candidate check catches.
4. **Negative control PASS** (drop-one-finding hook → refuse on row-key set difference).
5. **Inference PASS:** identity normalizer, no pin; declare `--volatile-json-field time`.
6. **Errors dependence:** on 10 seeded half-rule subsets, **70%** had a different top-level `errors` list than the full-rule run on the same files (Timeout / syntax warnings are rule-set dependent). Envelope mismatch implies **REFUSE_MATCH** under `verify full` unless `errors` is handled explicitly — this is the main barrier to a Semgrep speedup story.
7. **Laptop shape (not evidence):** stock newer ~76–78 s; TARE fill ~670–690 s (many exact-mode scans); refused updates ~124–212 s.

Pilot code fixes (json-records only): lock flat columns across probe parts; sanitize newlines/tabs in scalar cells so Semgrep messages cannot split the synthetic line table.

## Proposed pre-registration (prompt 3 / CARC measured)

Lock after this pilot’s limitations are accepted or mitigated.

| Item | Proposed lock |
|---|---|
| Goal | Decide whether TARE can **SHIP** Semgrep rule-set updates with equal non-volatile JSON and report a wall-time ratio vs stock on an exclusive node |
| Releases | **Three consecutive** semgrep-rules commits that change ≥1 Python rule, drawn with a fresh seed; concatenate with the same unique-id qualification |
| Corpus | **Fresh** ≥1000 Python files, disjoint from pilot and G1 by path+hash; enlarge until stock on the newest release has ≥**500** findings |
| Machine | Exclusive **EPYC 7542**, one job; no other user load |
| Design | `r = 3` alternating **stock / TARE** pairs on the same inputs (stock, TARE, stock, TARE, stock, TARE) |
| TARE argv | `--strategy reference --reference-format yaml-list --output-format json-records --json-rows results --volatile-json-field time --pin --verify full` plus Semgrep `--json --no-rewrite-rule-ids --metrics=off --disable-version-check` |
| Pass | Every TARE update **SHIP**s; output equals stock except `time`; stock-vs-stock (except `time`) holds on the node |
| Fail | Any SHIP with a non-volatile mismatch; or IC2/candidate refuse on a release pair intended to demonstrate reuse (record as Semgrep coupling limitation and stop) |
| Power | ≥500 findings on the newest release stock output; else **INCONCLUSIVE** |
| Errors | Pre-declare whether top-level `errors` is volatile or must match; if must match, require errors-dependence rate **0** on a 10-subset pilot replay on the CARC corpus before timing |
| Primary metric | Median wall ratio stock/TARE over the three TARE updates (laptop timings are not this metric) |

Do not start CARC until: (a) a laptop release pair **SHIPs** an update under IC2, or (b) the measured claim is explicitly “refuse on coupling” rather than speedup.
