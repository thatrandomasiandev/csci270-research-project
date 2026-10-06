# Reference-side incrementality — prior-art verdict

Written 2026-10-06. This file is the prior-art pass for the claim in
[`REFERENCE_INCREMENTAL_PROTOCOL.md`](REFERENCE_INCREMENTAL_PROTOCOL.md).
It does not edit that protocol's locked text.

## Kill rule (locked before search)

The claim under test treats an unmodified CLI tool as
`F(records, reference)` and asks whether a system can infer, with **no
per-tool code**:

- **(a)** that the output decomposes over reference entries, so the output
  on reference `R` equals the merge of the outputs on a partition of `R`;
- **(b)** which numeric columns carry a global normalizer, and that
  normalizer's form, fitted from a small fixed family (example: HMMER
  `E = Z · P` with `Z` the number of reference models; c-Evalue rescaled
  by per-query `domZ`, the number of targets reported per sequence).

On a new reference release the system would rerun only new or changed
entries, reuse cached rows for unchanged entries, and rescale the
normalized columns.

**Verdict rule, fixed before any query was run:**

- **KILL** if any prior work infers **(a) and (b)** automatically for
  unmodified black-box tools.
- **NARROW** if prior work does **(a) or (b)** automatically for one tool
  family, or hand-builds the whole thing for a specific tool. The
  remaining delta must then be stated precisely.
- **SURVIVE** otherwise.

Search log, per-paper readings, and the verdict follow this rule and were
written after it.
