# Generic record inference (pre-registered) — 2026-09-25

Written **before** any generic-path run on a real tool (SnpEff, bcftools, …).
Do not edit the locked sections after seeing `results/inference_*.json`.

This is the probe that makes “automatic record-level memoization, no per-tool
code” true. Per-**format** parsers are allowed (`lines`, `vcf`; later `fasta` /
`tsv`). Per-**tool** parsers are not. `acts/snpeff_ann.py` (hard-coded
ANN/LOF/NMD) is the thing this protocol replaces.

No timing and no speedup claims in this protocol. MATCH is body-only
(`docs/VEP_PROTOCOL.md`).

```
python3 -m acts run --kind vcf --cache C --input X -- <tool argv>
```

`{input}` in argv is replaced with the VCF the runner wrote (probe, miss
subset, or 1-record header harvest). If `{input}` is absent, the path is
appended as the last argument. stdout is the VCF. That is format wiring, not
a per-tool parser.

## Locked algorithm — format `vcf`

- **Record** = every non-`#` line.
- **Correspondence** = `variant_key` = `CHROM POS REF ALT` (full ALT), as in
  `acts/vcf.py`.
- **Output order** = input order.
- **Probe sample** = first 500 body records of the first input, or the whole
  body if shorter. Same records, two copies.
- **Header** = header of the tool run on the misses. If every record is a hit,
  harvest the header from a 1-record tool run. MATCH stays body-only.

On the probe sample:

**a) Determinism.** Run the tool twice on the same probe file. If the bodies
differ → `REFUSE_NONDETERMINISTIC`.

**b) Independence.** Shuffle the probe body (`acts.vcf.shuffle_body`), run
again. If bodies are not equal → `REFUSE_NEIGHBORS` (neighbors leak). The
existing `annotate_neighbors` fixture must fail this test.

**c) Field roles by perturbation.** Build a second probe in which every
**non-key** field is replaced with a different valid value:

| Field | Perturb to |
|-------|------------|
| ID | `PERTURB_<n>` |
| QUAL | a different numeric (or `.` ↔ `99`) |
| FILTER | `PASS` ↔ `PERT` |
| each existing INFO subfield | replace the value after `=`; flags become `PERTURB_<key>` |
| FORMAT and every sample column | replace with a different valid token of the same arity |

CHROM, POS, REF, ALT stay put. Run the tool on the original probe and on the
perturbed copy. Align output records by `variant_key`. Per output column, and
per INFO subfield (split on `;`, key before `=`):

| Observation | Role |
|-------------|------|
| equal to the (perturbed) input value | **PASS-THROUGH** — take from the new query record |
| unchanged between the two runs, and not present in the input | **PRODUCED** — cache it, keyed by the current cache key |
| changed between the runs but not equal to the input | **DEPENDS-ON-NON-KEY** — widen the cache key to include the input fields that were perturbed, re-probe **once** |

If after one widen the same field is still DEPENDS-ON-NON-KEY, or the role is
ambiguous (e.g. missing on one side, duplicate keys, column count mismatch)
→ `REFUSE_AMBIGUOUS`.

A field the tool **rewrites** (output ≠ input, stable across perturbation)
is PRODUCED, never PASS-THROUGH. Silently treating a rewrite as pass-through
is a protocol violation.

**d) Cache value** = PRODUCED parts only. **Reassembly** = new input record +
cached PRODUCED parts, inserted where the probe observed the tool putting
them (INFO key order / column index). PASS-THROUGH columns and INFO keys
come from the new query record, not the cache.

**e) Record contract.** Write a JSON contract next to the cache
(`<cache>.contract.json`). Every role, the final cache-key fields, INFO
insert position, and the refuse/widen history must be auditable. Reuse a
saved contract on later runs of the same argv; do not silently re-infer a
different role set.

## Decisions (locked)

| Decision | When |
|----------|------|
| SHIP | probe passed; reassembly body MATCH vs a full tool run |
| REFUSE_NONDETERMINISTIC | (a) failed |
| REFUSE_NEIGHBORS | (b) failed |
| REFUSE_AMBIGUOUS | (c) still ambiguous after one widen |
| REFUSE_MATCH | reassembly body ≠ full-run body |
| REFUSE_IDENTITY | STAR argv (existing `infer.py` special case; BAM is not VCF) |

No per-tool branch. SnpEff, `bcftools +fill-tags`, and `bcftools annotate`
go through this same probe.

## Expected outcomes — fixtures (`fixtures/vcf_memo/`)

Written before the new fixtures exist. The two existing scripts keep their
VEP_PROTOCOL meanings.

| Fixture | Probe | Decision | Cache key | Notes |
|---------|-------|----------|-----------|-------|
| `annotate_1to1.py` | (a) pass, (b) pass; ANN-like field PRODUCED; ID PASS-THROUGH | **SHIP** | `variant_key` | Same as today’s shuffle test. |
| `annotate_neighbors.py` | (b) fails | **REFUSE_NEIGHBORS** | — | Output includes previous POS. |
| `annotate_uses_id.py` *(new)* | (a)(b) pass; an output field changes when ID is perturbed and is not a copy of ID | **SHIP** after one widen | `variant_key` **+ ID** | If the widen is still ambiguous → REFUSE_AMBIGUOUS. Pre-registered preference is widen-then-SHIP. |
| `annotate_rewrites_filter.py` *(new)* | (a)(b) pass; FILTER output ≠ input FILTER and is stable across ID/QUAL/INFO perturbation | **SHIP** | `variant_key` | FILTER is **PRODUCED**. Reassembly must use the cached FILTER, never the query FILTER. A pass-through misclassification is a fail. |

`tiny.vcf` (4 records) is the probe input for all four fixtures.

## Expected outcomes — real tools

No speedup numbers. Identity and hit/miss counts only.

### SnpEff 5.4c GRCh38.86 (`-noStats -noLog`)

Same inputs as `results/snpeff_cached_identity.json`: populate HG00096 then
HG00097, then HG00099 (`data/vep_chr22/HG000{96,97,99}.c1.vcf.gz`). Generic
path only — do not call `acts/snpeff_ann.py` for the result.

| Check | Expected |
|-------|----------|
| (a) determinism | pass |
| (b) shuffle | pass |
| roles | ANN, LOF, NMD **PRODUCED**; ID, QUAL, FILTER, FORMAT, GT, non-SnpEff INFO **PASS-THROUGH** |
| cache key | `variant_key` (not widened) |
| HG00099 MATCH | `bodies_equal = true` on all **52,638** records |
| HG00099 hits / misses | **41,447 / 11,191** (same as the hand-built run) |

After MATCH, `acts/snpeff_ann.py` is deleted from the runtime path (moved
under `tests/` as an oracle, or removed). The generic contract is the
implementation.

### `bcftools +fill-tags` (AF/AC from sample columns)

One small multi-sample or single-sample `-c1` VCF already on disk (chr22
extracts). Plugin computes AF/AC from genotypes.

| Check | Expected |
|-------|----------|
| (a)(b) | pass (per-site, order-independent) |
| (c) | AF/AC **DEPENDS-ON-NON-KEY** (they move when FORMAT/sample columns are perturbed) |
| decision | **REFUSE_AMBIGUOUS**, *or* key widened to include sample columns so same-site hits **collapse** |

Either outcome is evidence the probe refuses a wrong `variant_key`-only
cache. Report which one happened. Do not silently cache AF under
`variant_key`.

### `bcftools annotate` (small chr22 annotation file)

If a small annotation table can be built from files already on disk (no new
download): tag a few INFO keys from `CHROM,POS,REF,ALT`. Expected: probe
classifies those keys as PRODUCED; **SHIP** + body MATCH. Zero new Python
beyond the format probe.

If no annotation file can be built without a download: record INCOMPLETE and
skip. Do not fetch.

## What this is not

- Not a timing run. Do not write speedups into the result JSON.
- Not permission to keep `snpeff_ann.py` as the SnpEff path.
- Not an LLM grammar. Probes only.
- Not STAR. Not `lines` (that runner is unchanged).
- Not a rewrite of `results/snpeff_cached_identity.json`.

## Addendum 2026-09-26 — subset-invariance and unprobed keys

Written **before** implementing either probe. Do not edit this addendum after
seeing the new fixture or real-tool JSON.

Two holes in the 2026-09-25 algorithm:

1. The shuffle test cannot catch a value that depends on the **size of the
   file** (HMMER E-values with implicit `-Z` / `--domZ`; any rank/count
   annotation). Neighbors can stay independent while the whole-file
   denominator moves.
2. `extract_produced` cached any output INFO key that was not in the query,
   even if the 500-record probe never saw it (SnpEff LOF/NMD). That is
   silent per-key invention.

### (b2) Subset-invariance (all formats)

After (b) Independence, before (c) field roles. On the same probe sample
of `k` records:

- Run the tool once on the full probe (already done in (a)).
- For each of the `k` records, write a one-record file (same header) and
  run the tool on that file alone.
- Align by the format key (`variant_key` for VCF). If that record’s output
  **body line** differs from the full-probe line → `REFUSE_GLOBAL`
  (“output depends on the rest of the file”).

This is not optional and is not sampled. A tool that fails (b2) does not
get a cache.

New decision:

| Decision | When |
|----------|------|
| REFUSE_GLOBAL | (b2) singleton output ≠ full-probe output for any probe record |

New fixture `fixtures/vcf_memo/annotate_global.py`: writes
`RANK=<i>/<N>` into INFO, where `N` is the number of body records in
**this** invocation. Expected: **REFUSE_GLOBAL**. `tiny.vcf` is the input.

### Unprobed output keys

When a later run (miss batch or a new file) emits an INFO key that is
**not** in `contract.info_roles`:

- Do **not** cache that key.
- Collect up to **200** records whose output carries the new key.
- Re-run (c) field-role perturbation on that subset; merge the new roles
  into the contract; append the key name to `late_key_probes`; save the
  contract.
- Then extract. If the new key is DEPENDS-ON-NON-KEY, apply the same
  one-widen rule as (c). If still ambiguous → `REFUSE_AMBIGUOUS`.

New fixture `annotate_rare_key.py`: every record gets `ANN=…`; a record
with `POS=99999999` also gets `RARE=1`. Infer on `tiny.vcf` (no rare
POS), then run a file that adds one `POS=99999999` record. Expected:
`RARE` is **not** cached on first sight; the late probe classifies it
**PRODUCED**; SHIP + MATCH; `late_key_probes` contains `RARE`.

### Real-tool check added

`bcftools +fill-tags -t AF,AC` on the locked chr22 `-c1` files:
populate HG00096 then HG00097, MATCH HG00099. Report hits/misses under
the genotype-widened key. SnpEff numbers in the 2026-09-25 table still
hold: MATCH 52,638; hits/misses 41,447 / 11,191.
