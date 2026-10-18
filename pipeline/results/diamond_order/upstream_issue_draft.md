# Draft for the DIAMOND maintainers

Not posted. Josh decides whether to send this.

## Stage-1 fingerprint reads past the sequence boundary

DIAMOND 2.2.5 (source commit `6dc57174369ba131d35a21db9735a48ac01e6610`). On a Mac the load is `FingerPrint::load` in `src/search/hamming/finger_print.h` (lines 146–158): it reads 16 bytes before the seed and 32 bytes after it, with no clip at the sequence boundary. Sequences are packed with one delimiter byte (`src/data/string_set.h`, `PERIMETER_PADDING` 256). The stage-1 gate is `match >= hamming_filter_id` (`src/search/hamming/kernel.h`). The default floor is 11 identities.

A seed near the start or end of an entry therefore contains the neighboring entry's bytes, or the perimeter padding when the entry is first or last in the block. The same protein can pass or fail that gate depending on which entry sits next to it in the database file.

## What we expected

Two databases built from the same sequences, differing only in entry order, should return the same hits for a fixed query file. A hit found against the full database should still be found when the database contains that subject and the query is unchanged, including when the subject's file-order neighbor is absent. The neighbor in the cases below is not itself a hit: `--min-score 1` against the full release does not report those six neighbor accessions.

## What we observed

Command, default sensitivity, one reference block (`-b 2.0`, log line `Block size = 2000000000`, `Algorithm: Double-indexed`):

```
diamond blastp --db DB --query Q --out OUT --min-score 40 -k 0 \
  --motif-masking 0 -b 2.0 --comp-based-stats 1 --threads 2 \
  --outfmt 6 qseqid sseqid pident length mismatch gapopen \
  qstart qend sstart send evalue bitscore
```

Database: UniProt Swiss-Prot 2026_03 (575,748 entries, 209,017,843 letters). Queries: the 300 proteins in `pipeline/data/reference_diamond_dx2/measured/e1_q.faa`.

1. The full database returns 31,377 rows (md5 `9bb21f2756244304d1849c0f0f0e290a`). The database restricted to subjects that appear in that output returns 31,371 rows. The six missing rows are byte-identical in the other 31,371. Adding one file-order neighbor back, and nothing else, restores that one row. The neighbor is not a reported hit.

| Missing subject | Neighbor that restores it | Position |
|---|---|---|
| `sp\|Q00407\|VHUA_METVO` | `sp\|Q58592\|VHUA_METJA` | predecessor |
| `sp\|Q31S42\|RPAA_SYNE7` | `sp\|Q01080\|RPA49_YEAST` | predecessor |
| `sp\|Q0WWW9\|XYLL3_ARATH` | `sp\|P23102\|XYLL_PSEPU` | successor |
| `sp\|Q39QB5\|NUOI2_GEOMG` | `sp\|Q746T4\|NUOI2_GEOSL` | successor |
| `sp\|A9BCC5\|CH10_PROM4` | `sp\|A2BYG2\|CH10_PROM5` | successor |
| `sp\|Q5GST6\|CH10_WOLTR` | `sp\|C0R2V4\|CH10_WOLWR` | successor |

2. Shuffling the same Swiss-Prot entries and rebuilding the database changes the full-database output. On a separate 300-query draw (`GCF_001650275.1`, seed 20261161), the release order produced 26,322 rows. Each of five shuffles (seeds 20261163–20261167) changed that body by 1–3 rows, all missing or extra, none a value change on a shared hit. Every changed alignment starts within 16 residues of the subject start or ends within 32 of the subject end. One recurring loss is `WP_000107391.1` versus `sp|Q00407|VHUA_METVO`, alignment subject positions 3–117 of a 420-residue protein. A default shape `111011010010111` sits at subject position 9 and reads before the entry. In release order the predecessor tail is `PTMEKAIQQAAQVIFK` (`sp|Q58592|VHUA_METJA`); after one shuffle it is `DLPSGKHYLRMVPHPK` (`sp|P52570|1CPX_ONCVO`). Building the release order twice gave the same database md5. Searching one database twice was byte-identical.

`--hamming-dist-boundary-check` makes the subset and the full database agree with each other (31,337 rows, same md5), by dropping 40 rows from the full-database output, including the six above. It does not bring those six back. Raising sensitivity, `--shapes-30x10`, `--algo ctg`, or `--id2 1` can bring the six back into the subset, and each of those commands still leaves the subset short of the full database by hundreds or thousands of other rows. We did not find a flag that keeps the default full-database output and also makes a subset replay match it.

The smallest reproduction we have is one query, one subject, and that subject's file-order neighbor: the subset of reported subjects loses the row, and adding the neighbor restores it. We have not packed that triple into a three-sequence FASTA in this draft.
