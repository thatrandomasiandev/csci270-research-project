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

---

## Addendum 2026-09-26 — format `fasta->table`

Written **before** implementing the parser or any fixture. Do not edit
this addendum after seeing `results/inference_*.json` or the new tests.

Per-**format** only. The code must not contain tool names, family-DB
names, or hard-coded output column titles. `{input}` substitution is the
same as VCF.

```
python3 -m acts run --kind fasta --cache C --input X -- <tool argv>
```

Stdout is a text table. That is format wiring, not a per-tool parser.

### Locked algorithm

- **Input record** = one FASTA entry (`name`, optional description after
  the first header token, sequence).
- **Cache key** = MD5 of the uppercase amino-acid sequence, every `*`
  stripped, whitespace ignored. The header (name and description) is
  **not** part of the key. Same object as `docs/RECURRENCE_PROTOCOL.md`.
- **Output** = text table. Lines starting with `#` are metadata (version,
  command, date) and are treated like a VCF header: MATCH is body-only.
  Split body lines on tab if any body line contains a tab; otherwise on
  whitespace.
- **A record’s output** = the body lines whose **query-name column**
  equals that record’s name. Find the column by probe: rename every
  query and see which column follows the new names. Do not assume a
  column index.
- **Zero-hit records** produce no body lines. Cache that as an explicit
  `EMPTY` result (`rows: []`). `cache.get` is a hit. Never treat empty
  as a miss.
- **Reassembly** writes the new record’s name into the query-name
  column of each cached row, and the new description into any column
  the perturbation probe classified as echoing the description.
  PRODUCED cells come from the cache.
- **Order probe** (after the query-name column is known):
  - **Grouped:** each query’s lines are contiguous, and the first
    appearance of each name follows input order (skipping zero-hit
    names). MATCH is **byte-order** on the body (header ignored).
  - **Global:** any other order (including interleaving or a score
    sort). MATCH is a **multiset** of body lines. The paper must say
    “order-insensitive MATCH” for that tool. Reassembly may still emit
    groups in input order; only the compare is a multiset.

### Probes (same battery as VCF)

On the first 500 FASTA records, or the whole file if shorter:

**a) Determinism.** Two runs on the same probe file. Body bytes differ
→ `REFUSE_NONDETERMINISTIC`.

**b) Independence.** Shuffle record order. Group output by the
query-name column. If any record’s lines differ → `REFUSE_NEIGHBORS`.

**b2) Subset-invariance.** Each record alone must emit the same body
lines as it did in the full probe (aligned by name). Any difference →
`REFUSE_GLOBAL`. This is the E-value / file-size hole.

**c) Perturbation.** Rename every query and replace every description.
Per output column:

| Observation | Role |
|-------------|------|
| follows the (new) name | **PASS-THROUGH name** |
| follows the (new) description | **PASS-THROUGH description** |
| unchanged across the two runs | **PRODUCED** — cache it |
| changes but equals neither name nor description | **DEPENDS-ON-NON-KEY** |

Sequence is the only cache-key field. If a column is still
DEPENDS-ON-NON-KEY after one widen attempt that is not possible here
(there is no extra FASTA field to add) → `REFUSE_AMBIGUOUS`.

**d) Late columns.** A later miss batch that emits more columns than
the contract saw: do not cache the new indices; re-run (c) on up to
200 rows that carry them; merge. Same as VCF unprobed INFO keys.

### Decisions (added)

| Decision | When |
|----------|------|
| SHIP | probes passed; body MATCH vs a full run (byte-order or multiset as contracted) |
| REFUSE_GLOBAL | (b2) failed |
| REFUSE_MATCH | reassembly body ≠ full-run body under the contracted MATCH |
| REFUSE_AMBIGUOUS | no query-name column, or a column still DEPENDS |

Existing VCF decisions still apply.

### Expected outcomes — fixtures (`fixtures/fasta_memo/`)

Written before the fixtures exist. Input: `tiny.fa`.

| Fixture | Probe | Decision | MATCH | Notes |
|---------|-------|----------|-------|-------|
| `per_query_table.py` | grouped; 0–3 lines per query; echoes the name | **SHIP** | byte-order | PRODUCED score; name PASS-THROUGH |
| `global_evalue.py` | a score scaled by the total query count | **REFUSE_GLOBAL** | — | (b2) singleton ≠ full-probe |
| `sorted_output.py` | global sort by score | **SHIP** | **multiset** | order-insensitive MATCH |
| `zero_hit.py` | some queries emit no lines | **SHIP** | byte-order | `EMPTY` cached; a later file with a new name and the same sequence must hit, not miss |

### Expected outcomes — real search (if binaries exist locally)

No download. Use `data/hmmer/Pfam-A.hmm.gz` already on disk and a few
fetched models. 200 K-12 proteins already on disk. If the binary is
absent, fixtures only; record INCOMPLETE. No speedup numbers.

| Mode | Expected |
|------|----------|
| scan vs a small model set, gathering threshold, table out, Z = number of models | grouped by query; subset-invariant; **SHIP**; byte-order MATCH |
| search, default Z | **REFUSE_GLOBAL** (E-values scale with the number of targets) |
| search, Z and domain-Z fixed at `1e6` | subset-invariant; order is global → **SHIP** with **multiset** MATCH |

Do not put those flag names or column titles in `acts/`.

### What this is not

- Not a timing run.
- Not permission to special-case a search binary.
- Not a rewrite of `results/snpeff_cached_identity.json` or
  `results/headline_*`.
- Not CARC. A headline screen may already be running; leave it alone.

---

## Addendum 2026-09-27 — Reuse test (FASTA→table)

Written **before** sampling the two genomes or running HMMER through
the cache. Do not edit this addendum after seeing
`results/inference_fasta_reuse.json`.

`results/inference_fasta_local.json` only populated (hits=0 every
mode). Reusing cached lines on a **new** genome, with **different
names and name widths**, is untested. RefSeq gives identical proteins
the same `WP_` accession, so name substitution never moved. Real
users have locus tags that change between assemblies, and `--tblout`
pads columns to name widths.

Local only. No CARC. No speedup numbers. No rewrite of
`results/inference_checks.json` or `results/inference_fasta_local.json`.

### Data (locked)

- Models: the same six as `inference_fasta_local.json`, fetched with
  `hmmfetch` from `data/hmmer/Pfam-A.hmm.gz`: `ABC_tran`, `GTP_EFTU`,
  `Response_reg`, `AAA`, `HATPase_c`, `Helicase_C`.
- Seed `20260927`. `N = 500`.
- **Genome 1:** 500 proteins sampled without replacement from
  `data/kprot/MG1655.faa.gz` (`Random(seed).sample`).
- **Genome 2:** 500 proteins from one collection-A *E. coli* already
  on disk (`results/recurrence_accessions.json`, collection A, first
  assembly in listed order whose shared-key count with genome 1 lands
  in **30–70%** under the construction below). Record the accession.
  Construction: take every collection-A protein whose sequence key is
  in genome 1 (first occurrence of each key); if that shared set is
  larger than `0.70 N`, subsample it with the seed down to `350`; if
  smaller than `0.30 N`, skip that assembly and try the next. Fill to
  500 from proteins whose keys are **not** in genome 1, shuffled by
  the seed.
- Then **rename every header** in both genomes to synthetic locus
  tags of varied lengths (`G1_1`, `G1_02`, `G1_0003`,
  `G1_00000123`, `G2_7`, …), assignment shuffled so identical
  sequences have different names and different name widths. Strip the
  original accession and description. Cache key remains the sequence
  MD5 (headers are not in the key).

### Modes and checks

For each mode, populate the cache from genome 1, then run genome 2
through the same cache. MATCH genome 2 against a stock tool run on
genome 2, using the MATCH type the contract inferred.

| Mode | Expected MATCH type | Expected |
|------|---------------------|----------|
| scan vs the six models, gathering threshold, table out | byte-order (as in the local SHIP) | hits ≈ overlap count; MATCH true |
| search, Z and domain-Z fixed at `1e6` | multiset | hits ≈ overlap count; MATCH true |

Queries with **zero hits** in genome 1 that recur in genome 2 must
come back as cached **EMPTY** (no tool call) and still MATCH. Report
`n_empty_hits` separately from ordinary hits.

Do not put those flag names or column titles in `acts/`.

### Padding (pre-registered fix)

`--tblout` pads columns to name widths in **that** invocation. A
cached raw line from genome 1 will not be byte-identical to the
genome-2 stock line after a naïve name substitution.

The fix, if padding breaks byte identity, is to **re-render** cached
rows at the widths the tool would use, inferred by probe from runs
with short names and long names. Per-format only — no per-tool code.
If that cannot be done generically (widths that depend on a `#`
header template, or a last field that contains spaces), the contract
falls back to **whitespace-normalized MATCH** (body lines equal after
`split()`), and the paper states that. Do not invent a HMMER parser.

### What this is not

- Not a timing run.
- Not permission to special-case a search binary.
- Not a claim about collection-A recurrence `m(k)` (that is
  `docs/RECURRENCE_PROTOCOL.md`).
- Not a rewrite of the VCF SnpEff / fill-tags numbers.

---

## Addendum 2026-09-27 — deployable verification, random probes, probe-time tracing

Written **before** the flag, the sampler, or `acts/trace.py` exist.
Locked sections above are unchanged. Closest occupied work: Dune
`cache-check-probability` (rule re-exec), Rattle / Riker / ProcessCache
(command-layer traces). This is a transfer to record granularity, not
a new theory.

### `--verify`

| Mode | Default? | What runs |
|------|----------|-----------|
| `audit` | **yes** | No full stock tool. After reassembly, re-run a random `AUDIT_P=0.02` of **hits** (at least 20 hits, or all hits if fewer; seed 20260927) as **one** batch. Compare that batch to the reassembled lines for the same records. Mismatch → `REFUSE_AUDIT`. First run (0 hits) SHIPs on probes alone. |
| `full` | no | Today’s behavior: run the stock tool on the whole input and MATCH. Experiments / `96f786b` only. |

`SHIP` in `audit` mode does **not** mean body MATCH vs a full tool run.
That sentence in “Decisions (locked)” applies to `--verify full`.

`--audit-p` overrides `AUDIT_P` in `audit` mode. `--audit-seed` overrides
the seed.

### Probe sample

Replace “first 500 body records” / “first *N*” with: `probe_n` distinct
records sampled uniformly without replacement from the **whole** input
(`random.Random(20260927)` unless `--probe-seed` is set). `probe_n`
default stays 500. If the file is shorter, use every record. Shuffle,
subset-invariance, and perturbation still run on that sample.

### Probe-time file tracing (Linux)

The first probe tool invocation is wrapped in
`strace -f -e trace=openat,open` when `strace` exists. Read-only regular
files (not `/proc`, `/sys`, `/dev`, the per-run input, `/tmp` / `$TMPDIR`)
are fingerprinted and added to the cache namespace as `kind=traced`.
Listed under that namespace in `<cache>.namespaces.json`.

macOS / no `strace`: skip; record `trace=unavailable` and warn. Env vars
are still uncovered.

Tracing is **not** applied to miss batches, audit batches, or later runs.
A file the tool opens only on a record the probe never sampled stays
unfingerprinted — stated limitation.

### New decision

| Decision | When |
|----------|------|
| `REFUSE_AUDIT` | `--verify audit` and a sampled hit’s re-execution ≠ cached reassembly |
