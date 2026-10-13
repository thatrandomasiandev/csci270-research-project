# DX3 root cause (diagnosis only)

Class **(b)**, refusal class F2. Restricting Swiss-Prot drops six stock rows because DIAMOND's stage-1 fingerprint reads the previous sequence's tail. No second declared size pin reproduces the stock body.

Stock versus stock on the DX2 queries is identical (31,377 rows, MD5 `9bb21f2756244304d1849c0f0f0e290a`, the same file as DX2 `e1_stock.m8`). The declared-pin replay R matches DX2 `e1_R.m8`: 31,371 rows, the same six missing, the other 31,371 byte-identical. The full 2026_03 release searched with R's query file is byte-identical to stock, so the misses come from the database subset.

For each missing row, adding non-candidates to U in halves, in release order, reached a single entry. U plus that entry restores the stock line and leaves the other five missing.

| Row | Coupling entry | Distance |
|---|---|---|
| VHUA_METVO | VHUA_METJA | predecessor |
| RPAA_SYNE7 | RPA49_YEAST | predecessor |
| XYLL3_ARATH | XYLL_PSEPU | successor |
| NUOI2_GEOMG | NUOI2_GEOSL | successor |
| CH10_PROM4 | CH10_PROM5 | successor |
| CH10_WOLTR | CH10_WOLWR | successor |

`--min-score 1` on the stock query file against the full release (35,019 rows) does not hit any of those six accessions. They are adjacent bytes, not sub-threshold alignments.

On this Mac the load is `FingerPrint::load` at `src/search/hamming/finger_print.h:146-158`: 16 bytes before the seed and 32 after, with no clip at the sequence boundary. Sequences are packed with one delimiter byte (`src/data/string_set.h:36`, perimeter padding 256). A seed near the start of a sequence therefore contains the previous entry's tail, or padding when the sequence is first. The stage-1 gate is `match >= hamming_filter_id` (`src/search/hamming/kernel.h:39`). The default floor is 11 identities (`src/search/setup.cpp:46`, applied at line 559). `--id2 0` is the unset sentinel (`src/basic/config.h:460`) and leaves the six missing. `--id2 1` finds them and adds 33 rows plus one different HSP, so it is not a pin of unmodified S1. `--no-ranking` leaves the six missing. `--dbsize` only sets the printed E-value.

A random pad of size `|U|` includes one specific neighbor with probability `q = 26797/548951 = 0.0488`. Three such pads all miss it with probability 0.861, under the measured fact that a pad containing that neighbor changes the candidate rows. That is why DX2's random certificate passed.
