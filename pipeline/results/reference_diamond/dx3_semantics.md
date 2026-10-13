# DX3 semantics review

Written before any IC2 run. The mechanism is the diagnosis in `dx3_rootcause.json`. This file states what IC2 is allowed to mean. It does not report a pilot or a measured outcome.

## What can make a check fail for a reason other than the claim

1. **Stage-1 fingerprint reads the previous entry.** `FingerPrint::load` (`finger_print.h:146-158`) loads `q-16..q+32` with no boundary clip. A seed within 16 residues of a sequence start includes the previous sequence's tail, or 256 bytes of perimeter padding if the sequence is first. The gate is 11 identities (`setup.cpp:559`, `kernel.h:39`). Adding one file-order neighbor to U restored each of the six DX2 stock lines, byte-identical. The same neighbor is not a hit at `--min-score 1`. A certificate that only pads with low-scoring subjects will not see this coupling. Pilot detection: the known-bad DX2 replay must fail the neighbor pad.

2. **The effect is not monotone.** A singleton subject can hit when U misses, and a local homolog window can suppress a hit that U plus one neighbor restores. Halving that removes entries from a working set can lose the trail. The minimization that found `|C|=1` added halves to U, which is the failing database. Pilot detection: judge R against R+, not against a hand-shrunk window.

3. **Query order uses the same fingerprint.** The full release with the replay query file equals stock on `q300`. The CH10 query alone, and the RPAA query alone, drop their stock rows on that same full release. IC2 holds the query file fixed between stock, R, and every R+. A control that rebuilds the query FASTA fails for a different reason.

4. **`--dbsize` does not pin the filter.** It sets the printed E-value. `--id2 0` is the unset sentinel and keeps the default floor of 11. `--id2 1` removes the six misses and changes other rows (33 extra, one different HSP). There is no second size flag to declare. A "pin" control that changes the argv is not a test of unmodified S1.

5. **Ranking, blocks, algorithm, composition stats.** `--no-ranking` leaves the six missing. Both sides stay double-indexed with one block of 2e9. `--comp-based-stats 0` changes values and HSPs. None of these is the miss. The pilot does not re-test them.

6. **Pad hits versus candidate-row changes.** DX2's predicate ignored an extra row whose subject was already in U. R+ recovered VHUA_METVO and NUOI2_GEOMG that way and still passed. IC2 fails on any extra or missing candidate line.

7. **HMMER is a different filter.** `hmmscan --cut_ga -Z` scores each model against a fixed Z. Entry-local filtering is why the positive control can pass. It is not evidence about DIAMOND.

8. **Threads.** DX2 B0 found `--threads 1` and `--threads 8` identical on its pilot queries. IC2 uses `--threads 8` on every arm, including stock.

## IC2, the candidate certificate

IC2 is a test. A pass is not a proof that the replay body is the stock body.

Fix the query file Q, the candidate set U, and S1 with the declared pin `--dbsize` equal to the full release's letter count. R is the search of U. For each pad P, R+ is the search of U ∪ P in release file order, same Q, same pin, same threads.

Pads, all required:

- Three independent uniform pads, each of size `max(200, |U|)`, drawn from entries not in U. Pilot seeds `20261025`, `20261026`, `20261027`. These seeds are not the DX2 pad seed `20261020` or the DX2 negative seed `20261022`.
- One adversarial neighbor pad: the release-file predecessor and successor of every subject in U, dropping any neighbor that is already in U. No seed. This is the pad the diagnosis says can contain C.
- One near-miss pad: subjects that hit the same queries at `--min-score 1` and do not hit at `--min-score 40`. The diagnosis already shows that the six coupling entries are not in this set. The pad stays in the candidate design because a later miss could be a low-scoring neighbor rather than an adjacent byte. The pilot records whether it, by itself, fails the known-bad case.

Pass rule for one pad. Let `rows_U` be the multiset of body lines whose subject is in U, and `rows_P` the lines whose subject is in the pad. The pad passes only when `rows_U(R+) = rows_U(R)` and `rows_P(R+)` is empty. Any extra candidate line, any missing candidate line, or any pad hit fails that pad. IC2 passes only when every pad passes.

What a pass implies, under stated assumptions, not in general.

- A1, measured on the six DX2 rows and not proved beyond them: a pad that contains that row's coupling entry changes `rows_U`.
- A2: a uniform pad of size `m` from `N` non-candidates includes one specific entry with probability `q = m/N`.
- From A1 and A2, k independent pads all miss that entry with probability `(1-q)^k`. At the DX2 sizes `m = 26797`, `N = 548951`, `q = 0.04881492155037517` and `(1-q)^3 = 0.860587604137852`. Three random pads are a weak probe of this mechanism.
- A3: the neighbor pad contains every immediate non-candidate neighbor. If the coupling entry is that neighbor, the pad contains it with probability 1, and under A1 the neighbor arm fails. A pass of the neighbor arm means no such adjacent entry changed the candidate multiset on this query file. It does not rule out a coupling set that is not an immediate neighbor.

The near-miss arm has `q = 0` for the six measured coupling entries. A pass of that arm alone says nothing about them.

## Controls the pilot must show

Pilot data for the DIAMOND controls is the DX2 measured replay, because the known-bad case is that replay. The rate sample, if the pilot needs one to size the measured draw, uses a genome other than `GCF_002853805.1` and `GCF_002090355.1`, and other than the genome later locked for the measured run.

- Known-bad: DX2-E1 R fails IC2.
- Injected negative: drop 10% of U with `random.Random(20261024)`, then run IC2. IC2 fails. Record whether the failure is a pad hit, a missing candidate row, or an extra candidate row.
- Positive: `hmmer_positive()` in `exact_replay_dx2.py` (Pfam 38.2, `--cut_ga`, `-Z 30134`). Re-judge its tblout and domtblout with the IC2 multiset rule. The control passes only if that re-judge passes and the replay body matches the stock body on the replayed queries. Zero needless refusals means IC2 does not fail when the body matches.

Overhead is the sum of R+ wall times divided by the stock wall on the same queries. It is a pilot number.

## Outcome rules, locked only after the pilot

Per arm, same names as DX2:

- EXACT: the replay body equals stock and IC2 passes.
- SAFE-REFUSE: IC2 fails. True when the body differs from stock. Needless when the body equals stock.
- UNSAFE: the body differs from stock and IC2 passes. That kills the certificate. There is no DX4 and no redesign.
- INCONCLUSIVE: the fresh run has fewer natural replay-differs-from-stock cases than the floor the addendum locks from the pilot rate. That arm is not EXACT.

A case is one stock row missing in the replay, one replay row absent from stock, or one shared key whose lines differ. Every failure reports the class: value-only, different row, missing, extra, or order, using `classify()` (`same_hsp_different_value`, `different_hsp`, `row_missing`, `row_extra`, `line_order_only`).

The measured query genome is chosen after the pilot, from `data/recurrence/A`, excluding the two genomes above and excluding the genome used for a rate sample. At least 1,000 queries. More if the pilot rate is below about 6 misses per 300 queries.
