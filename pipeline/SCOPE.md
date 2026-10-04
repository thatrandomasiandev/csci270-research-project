# SCOPE — record-level incremental memoization

**Not the CSCI 270 graded STAR claim.** That claim stays in `star/docs/SCOPE.md`.

## Claim

If a black-box tool is per-record, ACTS memoizes distinct records **across runs** and reassembles. Accept only if the reassembly is **byte-identical** to a full run.

**Falsifier:** independence is false, cross-run overlap is rare (`recall_in_new` ≈ 0), or `cmp` fails.

STAR is a kill test for the *aligner instance*. VEP (when present) is the intended scientific instance. The official VEP `--cache` is reference data, not this cache.

VEP MATCH is the **record body**, not full-file `cmp`. Overlap is `-c1` per-sample extracts only. Locked flags and the shuffle test: `docs/VEP_PROTOCOL.md`.

## Decisions

| Decision | When |
|----------|------|
| SHIP | `cmp` identical; pay_frac < 0.95 (within-file unique_frac on first run, miss_frac later) |
| REFUSE_DUPS_RARE | almost every record is new — a whole-command cache would do as well |
| REFUSE_IDENTITY | output is not a per-record function (STAR BAM) |
| REFUSE_MATCH | reassembly ≠ full run |
| REFUSE_AUDIT | `--audit-p` re-exec of a hit disagreed (Dune-style; not a novelty claim) |
| INCOMPLETE | no runner for this grammar |

## Non-claims

- Not ProcessCache / Rattle / Riker (whole command).
- Not IncPy / Mandala (Python).
- Not KumQuat (split, no cache) and not Oculus (hand-built, not `cmp`).
- Not “first automatic cache keys” and not “first statistical cache audit.”
- Not the graded STAR source 2×.

## Addendum 2026-10-03 — reference-side MATCH type `ref-merge`

Reference-side reuse (a new reference release reuses results for unchanged
entries) is accepted under **`ref-merge`**, not `cmp`. The full definition
is in `docs/REFERENCE_INCREMENTAL_PROTOCOL.md`.

Under `ref-merge`:

- Hit and domain sets and every unnormalized column are byte-identical.
- Normalized columns are consistent with the inferred normalizer only
  within printed precision.
- Columns with no fitting normalizer are recomputed, not reused (hmmscan
  c-Evalue).

It is never described as byte-identical.

Scope: score-thresholded modes only (`--cut_ga`). The E-value-thresholded
negative control fails the decomposition test, as required
(`results/reference_kill_r2n.json`). Re-annotation speedup is PROJECTED
until a measured 38.1 → 38.2 run exists.

**Addendum 2026-10-03 (later), superseding the c-Evalue line above.**
hmmscan c-Evalue is reusable. It rescales by domZ, defined as the number of
targets reported for that query in **tblout** (per-sequence). Confirmed on
fresh data: 511/511 lines, pre-registered at `8c52c9f`, result in
`results/reference_kill_r3c.json`.

This normalizer depends on the data: it comes from the *merged* hit set,
so the rescale runs after the merge, not before. It is stable only because
`--cut_ga` fixes the per-sequence reporting threshold.
