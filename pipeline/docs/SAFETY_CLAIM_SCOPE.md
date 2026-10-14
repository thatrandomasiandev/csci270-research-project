# Safety claim scope

Replacement text for the paper's safety claim. This file is not
`main.tex`. The measured arm is `results/reference_diamond/dx3.json`.
Version (i) is the one that applies. Version (ii) is the text that would
have applied if IC2 had passed over a wrong body, or if the arm had been
underpowered.

## Version (i), the one that applies

Exact replay is certified by IC2, with measured miss bound 0.325.

IC2 passes only when three uniform pads and the file-order neighbor pad
leave the candidate-row multiset unchanged and hit no pad subject. On
the DX3 arm a uniform pad included one specific non-candidate with
probability `q = 137090/438658 = 0.31252137200279034`, so the
probability that all three miss it is `(1-q)^3 = 0.3249208679849812`,
under the assumption that a pad containing that one entry changes the
candidate rows. The neighbor pad contains every immediate non-candidate
neighbor. A pass is a test, not a proof that the replay equals stock.
The assumption was measured for the six DX2 rows, each of which came
back when its one neighbor was added, and is not a theorem about every
query.

DX3 on `GCF_001515725.1` (2,000 queries) was SAFE-REFUSE. The replay
differed from stock in 22 rows (20 missing, 2 extra, the other 227,203
shared rows byte-identical). IC2 failed on every pad. The refusal is
true. The case count is above the floor of 6. The arm is not UNSAFE.
The HMMER control in the pilot passed with no needless refusal.

## Version (ii), not the one that applies

Exact replay is offered only for tools whose semantics review shows
entry-local filtering (HMMER and Infernal with `-Z`). For everything
else ACTS refuses. DIAMOND is SAFE-REFUSE: the shipped fit refused in
DX2-E2, and no deployed run emitted a wrong body.

## Contribution 4

Fail-closed certificate. Exact mode runs IC2 before it writes a replay.
IC2 reruns the replay with three random pads (seeds `20261031`,
`20261032`, `20261033`) and with the file-order neighbors of the
candidate subjects. Any extra or missing candidate row, or any pad hit,
refuses the run, so that replay is not the output. The measured random-pad
miss bound for one named neighbor is 0.325. The certificate does not
claim that a pass equals the stock body. The near-miss score pad from
the DX3 lock is not in the generic runner: a score floor is not a
property of every tool. On the measured arm that pad also failed, and
the pads that did ship failed as well.

## EV4

Generality of the certificate across tools whose replay is entry-local,
and across DIAMOND, where it is not. Primary metric:
EXACT / SAFE-REFUSE / UNSAFE / INCONCLUSIVE per tool. UNSAFE still kills
the claim that a certified replay was the stock body. SAFE-REFUSE does
not. DX2-E1, judged by the old certificate, was UNSAFE and retired that
certificate. DX3, judged by IC2, was SAFE-REFUSE (22 cases, true
refusal, overhead 3.059). An equal body below the power floor is
INCONCLUSIVE, not EXACT.

## Addendum 2026-10-13 — what the check caught

The text above stays as it was locked. This addendum is the wording
that applies to the shipped check. A pass is a check.

The shipped check refused every known failure that was run: the DX2
known-bad replay (`pad_hit`), the injected 5% candidate drop at sample
size 50, and a regeneration of DX3's locked draw (stock 227,223 rows,
replay 227,205, neighbor pad `pad_hit`; the original m8 files were
absent, and the row counts match `dx3.json`). No UNSAFE output was
seen in any run. File-order neighbor coupling is caught by construction:
the neighbor pad is searched for every replayed record.

`(1−q)^3 = 0.3249208679849812` is only the random-pad miss rate for one
unknown coupling entry, with `q = 137090/438658`. It is not the
headline. With a sample of 50 out of 2,000 records the counting
identity raises that miss rate to 0.711 when the entry affects 22
records. DX3's 22 cases are file-order neighbors, so that identity does
not describe them. For coupling that is not a file-order neighbor, the
random pads on 50 records miss with probability 0.711 in the DX3
example, so the neighbor pad is the protection that the evidence supports.

DIAMOND exact mode refuses because its stage-1 fingerprint reads
neighbor bytes. The fresh sample, seed 20261017, genome
`GCF_023657995.1`, 300 queries, was SAFE-REFUSE (stock 37,211 rows,
replay 37,208, neighbor pad `pad_hit`). A pilot on `GCF_013085185.1`
was the same outcome. Neither arm was UNSAFE.

On HMMER the check passed with no needless refusal. On the two fresh
proteomes the neighbor pad plus the three sample pads took 34.6 s and
37.3 s, which is 0.053 and 0.054 of those stock walls. The cap was 0.10.
