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
