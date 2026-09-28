# ACTS usage (5 minutes)

This is a packaging and CLI guide. It is **not** a novelty claim.
Record memoization sits next to Rattle / ProcessCache / INCR (command
grain) and KumQuat (split, no cache). See the literature index.

Install from the **repo root** (editable; do not publish):

```bash
pip install -e pipeline/
acts --help
```

`pip` distribution name is **`acts-memo`**. PyPI already has `acts`
(Android Comms Test Suite 0.9) and `pyacts` (particle-tracking
bindings). The import package and console command stay `acts`.

Without install, from `pipeline/`:

```bash
export PYTHONPATH="$PWD"
python3 -m acts --help
```

## Fixture quickstart

All of these use in-tree tools. No HMMER, no SnpEff.

```bash
cd pipeline
export PYTHONPATH="$PWD"

# 1. Count duplicates (no tool)
python3 -m acts probe --kind lines --input fixtures/line_memo/input.txt

# 2. Memoize lines with cat (byte MATCH)
python3 -m acts run --kind lines --input fixtures/line_memo/input.txt -- cat

# 3. Incremental: second file reuses the first cache
python3 -m acts run --cache /tmp/acts.jsonl --kind lines \
  --input fixtures/line_memo/run_a.txt -- cat
python3 -m acts run --cache /tmp/acts.jsonl --kind lines \
  --input fixtures/line_memo/run_b.txt -- cat

# 4. VCF / FASTA fixtures (Python stand-ins)
python3 -m acts run --kind vcf --input fixtures/vcf_memo/tiny.vcf -- \
  python3 fixtures/vcf_memo/annotate_1to1.py
python3 -m acts run --kind fasta --input fixtures/fasta_memo/tiny.fa -- \
  python3 fixtures/fasta_memo/per_query_table.py

# 5. Predict (times random subsets, fits t = a + b·n, estimates m)
python3 -m acts predict --kind lines --input fixtures/line_memo/input.txt -- cat
python3 -m acts predict --kind vcf --input fixtures/vcf_memo/tiny.vcf -- \
  python3 fixtures/vcf_memo/annotate_1to1.py
python3 -m acts predict --kind fasta --input fixtures/fasta_memo/tiny.fa -- \
  python3 fixtures/fasta_memo/per_query_table.py
```

`predict` prints JSON plus a SHIP/REFUSE line. Fixtures are tiny: the
corrected screen rule also requires **≥ 60 s** saved, so they **REFUSE**
on absolute time even when the ratio looks fine. That is the point of
the ruff erratum.

`--cache C` (optional) sets miss fraction *m* from keys already in *C*
for this argv. Omit it and *m* is first-run unique_frac.

Predicted speedup in the JSON is the screen-rule **ceiling(m)** and
**does not include probe cost P**. That formula is Agent A’s; this
tree stubs it until merge.

## `--verify audit`

Default for `acts run`. After reassembly, re-run a random 2% of **cache
hits** (at least 20, or all hits if fewer; seed 20260927) as **one**
batch. Compare that batch to the cached reassembly. Mismatch →
`REFUSE_AUDIT`. There is **no** full stock run of the whole input.

`--verify full` is the experimental upper bound: run the stock tool on
the entire file and MATCH. Use it in tests / bake-offs, not as the
deployed default.

`SHIP` under `audit` does **not** mean the whole file matched a full
tool run.

## Limitations (stated)

- **F6-env.** Environment variables are not in the cache key. A tool
  that reads env (the probe-eval `F6-env` class) can pass probes and
  audit while the env stays fixed, then change later. Outside the
  method guarantee.
- **argv-only inputs on macOS.** Cache namespaces fingerprint the
  binary and paths **named in argv**. Files the tool opens that argv
  does not name need Linux `strace` at probe time. On macOS, tracing
  is unavailable (`trace=unavailable`); those files are unfingerprinted.
- **Whitespace MATCH for tables.** FASTA → table contracts may accept
  whitespace-normalized body equality (`split()`), not bytes, when
  column padding (HMMER `--tblout` style) would break `cmp`. VCF body
  MATCH ignores dated headers. Lines/`cat` still require bytes.

## Screen rule (predict)

```
ceiling(m) = (a + b·N) / (a + b·m·N + w)
saved(m)   = (a + b·N) − (a + b·m·N + w)
```

Advance only if `ceiling(m) ≥ 3` **and** `saved(m) ≥ 60 s`. If `a → 0`
the ratio cannot beat `1/m`, so `m` must be `< 1/3` (`REFUSE` otherwise).
`w` is measured no-op I/O, not omitted.

Do not publish this package to PyPI.
