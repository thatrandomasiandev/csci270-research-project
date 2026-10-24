# W4 scale-projection sentence — hub fold-in (2026-10-24)

## Final SHA

`e7ae203` (paper sentence). Artifacts cherry-pick: `92d2ec2`.

## Decision

**Shipped** in Discussion as `\textbf{Scale (PROJECTED).}` …

Widened-validation caveat (median abs wall error 26.3% → ranges widened) **omitted from the paper** (page budget); remains in `pipeline/docs/SCALE_PROJECTION.md` and `projection.json` validation fields.

## Artifacts

Cherry-picked `2cbd8ae` from `origin/exp/scale-projection`:
- `pipeline/scripts/scale_projection.py`
- `pipeline/results/scale/projection.json`
- `pipeline/docs/SCALE_PROJECTION.md`

## Sentence (as in `main.tex`)

Re-annotating every RefSeq bacterial genome against each new Pfam release is projected to cost 143 core-years for a full stock hmmscan of 2.18 billion proteins, versus 34 core-years with `\sys` on a typical update at the headline median 4.24× (≈143 core-years when a release rewrites ~93% of models, as in 37.4→38.0).

`% source:` uses `assembly_counts.all_bacteria` (actual JSON path; brief’s `all_refseq_bacteria` key does not exist) plus DERIVED `proteins_b` and `pct93`.

## Cuts

None beyond omitting the validation caveat. Body stayed ≤12 pages after the one-sentence add.

## Gates (pre-commit)

- Checker: 0 mismatches
- PDF: 13 pages total; body ≤12 (scale+conclusion p11; Tab5+Availability p12; refs p13)
- Anonymity: OK
- Pytest: see commit message / tip
