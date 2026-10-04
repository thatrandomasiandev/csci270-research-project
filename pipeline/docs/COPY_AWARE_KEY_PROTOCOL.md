# Copy-aware key vs dependency key (pre-registered 2026-10-03)

Written **before** any dependency-key number is computed. Locked text below
is never edited. Later changes are dated addenda.

## Why this test exists

A prior-art check on 2026-10-03 (addendum in `RELATED_WORK.md`) found that
**black-box dependency inference by perturbation** is occupied. Three
examples:

- Fuzzing-driven taint inference (GREYONE, Gan et al., USENIX Security
  2020) mutates input bytes one at a time and marks what changes.
- DUST (Bar-Yossef, Keidar, Schonfeld, WWW 2007) learns which URL
  components do not change page content.
- Param Miner (Kettle, PortSwigger 2018) finds request inputs that change
  the response.

A cache keyed by any of these methods keys on **every field the output
depends on** (call it $D$). That includes fields the tool only **copies**
into its output.

ACTS's candidate differentiator is narrower. It splits $D = K \sqcup U$:

- $U$ (transport) holds fields whose perturbation reappears verbatim at the
  copied positions and changes nothing else.
- $K$ (transform) holds the rest.

ACTS keys on $K$ and splices $U$ back in from the new record. The
`CONTENT_KEY_PROTOCOL.md` test compared $K$ against **byte** keys
(INCR/Caruca). The stronger baseline is $D$, so this test compares $K$
against $D$.

## Keys (from committed contracts only; no tool runs)

| Workload | Tool contract | $D$ (dependency key) | $K$ (copy-aware key) |
|---|---|---|---|
| VCF: HG00096 ∪ HG00097 → HG00099 (`-c1`) | SnpEff, `results/inference_checks.json` (`snpeff.contract`) | every field with role `key` or `pass` (all 8 columns, every INFO tag in the record, sample columns) | `CHROM POS REF ALT` |
| Proteins, GenBank (the 7 genomes in `results/content_key_overlap.json`) | hmmscan `--cut_ga`, `results/inference_fasta_local.json` (`modes.scan_cut_ga`): `query_col` copied, `desc_cols` empty | (record name, sequence) | sequence (`acts.fasta.seq_key`) |
| Proteins, RefSeq control (10 genomes) | same | (record name, sequence) | sequence |

Note, stated in advance: in the SnpEff contract every non-key field is
`pass`, so on VCF, $D$ is the whole record. The VCF $D$-recall therefore
equals the byte recall already recorded (0.438). The VCF row is reported
for completeness and is not a new measurement. For hmmscan, $D$ differs
from the byte key because the description is irrelevant (not copied).
The GenBank and RefSeq $D$ numbers are the new measurements.

hmmsearch is excluded. Its committed local contract was built on a fixture
without descriptions, and the 2026-09-28 savings failure shows it copies
descriptions. A $D$ taken from that contract would be wrong.

## Metric

Same as `CONTENT_KEY_PROTOCOL.md`: $\text{recall\_in\_new}$ of genome
$k{+}1$ against genomes $1..k$ (VCF: HG00099 against the union of the
other two), under $D$ and under $K$. Reported ratio: $D/K$.

## Kill rule (locked)

If $D$-recall ≥ 0.9 × $K$-recall on **both** VCF and GenBank at the last
$k$, copy-awareness adds nothing over prior-art dependency inference. In
that case, the paper does not claim it.

## Prediction (locked, so the test can be wrong)

GenBank: $D/K \le 0.05$ at every $k$, because protein IDs are per
submission. RefSeq control: $D/K \ge 0.9$ at every $k$, because `WP_` IDs
are shared. If the RefSeq control falls below 0.9, the $D$ construction is
suspect, and the GenBank result is not reported as support.

## Ship controls

Copy-awareness must not cost correctness. The committed results still
hold:

- SnpEff MATCH on 52,638 records (41,447 hits / 11,191 misses).
- fill-tags widened to `SAMPLES`, 23,072 hits.
- hmmscan `--cut_ga` byte MATCH (`results/inference_fasta_reuse_bytes.json`).

This test does not touch `acts/`. `bash run_tests.sh` must pass.

## Not in scope

No timing and no CARC. No new downloads: the inputs are on disk from the
content-key test.
