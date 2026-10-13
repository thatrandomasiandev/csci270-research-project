# Exact pinned-normalizer replay — prior-art verdict

Adversarial review of the claim in
[`EXACT_REPLAY_PROTOCOL.md`](EXACT_REPLAY_PROTOCOL.md) and
[`WHAT_WE_ARE_BUILDING.md`](../../WHAT_WE_ARE_BUILDING.md) §0.
This file does not edit those documents. Locked text below is never
rewritten; search notes are a dated addendum.

**Locked:** 2026-10-12, before any literature query for this pass.

## Claim under attack (verbatim)

> ACTS infers, from outside an unmodified CLI tool, (a) that its output
> decomposes over reference entries, (b) which output columns are global
> normalizers and which tool option sets them, and (c) which options are
> reporting thresholds; then, after a reference release, it rescans only
> new/changed entries, collects candidates including a slack band of
> near-threshold rows, and replays the tool on the candidate union with
> the normalizer pinned to the new release's value, producing output
> byte-identical to a full rerun — or refuses.

## Verdict rule (locked before search)

Apply mechanically after the readings. Do not renegotiate the bar
because a paper is close.

- **KILL** if a prior system does **both** of the following:
  1. automatic inference of **any two** of (a), (b), (c) for
     **unmodified binaries** (no per-tool plugin, no hand-written
     formula, no crowdsourced annotation of that tool);
  2. **exact** incremental maintenance across reference updates:
     output byte-identical or value-identical to a full rerun.
     Correlation, rank agreement, and "more hits" do not count.
- **NARROW** if prior work does one side fully (automatic inference of
  two of a/b/c, **or** exact incremental maintenance), or does both
  sides only by hand or only for one tool.
- **SURVIVES** if neither side is occupied.

"One side" means either the inference side or the exact-maintenance
side. A hand-built BLAST plugin that pins `-dbsize` and merges shards
occupies exactness for one tool; it does not by itself KILL. An
inferrer that discovers decomposition and a threshold, but never
maintains a reference update exactly, does not by itself KILL.

## Three attacks expected to be strongest (named before search)

These are hypotheses. They are not findings. Each is written so a
later reading can confirm or drop it.

**Attack 1 — pinned normalizer is already standard (highest priority).**
Sharded and parallel sequence search already fixes database size so
E-values match a serial run: mpiBLAST (Darling, Carey, Feng, ISCA or
Cluster 2003 — confirm venue on read), NCBI BLAST `-dbsize` /
`-searchsp`, HMMER `-Z` and `hmmpgmd_shard`, DIAMOND `--dbsize`,
MMseqs2 database splitting. If "replay the tool with Z pinned to the
full reference" is documented practice, the mechanism is prior art.
The claim then narrows to *inferring* the pin and the threshold and
using them for an incremental reference update, plus the slack band.
Expected verdict contribution: NARROW on the maintenance mechanism,
not KILL, unless some shard system also infers two of (a)/(b)/(c).

**Attack 2 — the slack band is top-k / threshold view maintenance.**
Yi, Yu, Lin, Zhang, "Efficient Maintenance of Materialized Top-k
Views" (ICDE 2003) and later top-k IVM keep a buffer (`k' > k`, or a
relaxed predicate) so the exact view can be restored from the buffer
when the underlying data changes. Threshold and HAVING view
maintenance are the same idea for a predicate rather than a rank.
If that literature already keeps near-threshold rows and recomputes
only when the buffer is insufficient, the slack band is prior art.
Novelty, if any, is inferring *which option is the threshold* and
*how wide the slack must be* for an opaque CLI. Expected verdict
contribution: NARROW. KILL only if some system also infers (a) and
(b) or (c) on an unmodified binary and emits a byte-identical rerun.

**Attack 3 — black-box incremental workflows already infer the
contract, or a hand-built bioinformatics plugin already emits exact
output.** Two prongs, either of which could KILL if it is stronger
than expected:

- *Declared or inferred black boxes.* Ikeda, Salihoglu, Widom
  (logical provenance / Panda, ICDE 2011–2013) incrementalize
  workflows that contain black-box modules. Nectar (OSDI 2010),
  Incoop (SoCC 2011), DryadInc, and later Spark / Delta Live Tables /
  Snowflake Dynamic Tables / Materialize / Feldera do incremental
  maintenance around UDFs. KumQuat and Caruca infer statelessness or
  a combiner for unmodified commands. If any of these **infers** two
  of (a)/(b)/(c) rather than taking a declaration, **and** maintains
  a reference update exactly, the kill rule fires.
- *Hand-built reference incrementality.* iBLAST, iSeqSearch, GeStore,
  InterProScan's precalculated match lookup, MMseqs2 `clusterupdate`,
  and any production Pfam/HMMER re-annotation pipeline may already
  rescan a diff and correct the normalizer. Prior reading
  ([`REFERENCE_PRIOR_ART.md`](REFERENCE_PRIOR_ART.md)) rated these
  hand-built and, for iSeqSearch, approximate. This pass re-reads
  them against **exactness** and against (c). Hand-built exactness
  for one tool is NARROW, not KILL.

Search log, per-work readings, and the mechanical verdict follow
this rule and were not written before the queries.
