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

## Addendum 2026-10-12 — search, readings, verdict

Written after the queries. The locked rule above is unchanged.
One quoted phrase per source; the rest is paraphrase. Read status
is what this pass actually opened, not what an earlier file claimed.

### Search log

Date of every query: **2026-10-12**, after commit `ab0b993`.
Surfaces: web search, Exa, OpenAlex, Semantic Scholar. Google
Scholar was not used (no browser session this pass). Brave search
was down.

| ID | Query (compressed) | What came back |
|---|---|---|
| Q1 | mpiBLAST E-value identical to serial | 2003 paper (performance, no pin); BOSC 2005 talk and the 1.3.0 note (exact E-values); iBLAST's later description of the same pin. |
| Q2 | HMMER `-Z`, `hmmpgmd_shard` | Current User Guide, jackhmmer section, states the parallel-split use; `hmmscan` man page has the flag; `hmmpgmd_shard` shards sequence RAM and does not set Z. |
| Q3 | BLAST `-dbsize` / `-searchsp` / blastall `-z` | blastall man page; BLAST book chapter on `-z`; MMseqs2 issue #505 names `blastp -dbsize` as the missing analogue. NCBI Bookshelf returned 403. |
| Q4 | DIAMOND `--dbsize` | Wiki: effective size in letters, affects E-values. |
| Q5 | MMseqs2 split and database size | User guide (split for memory); issue #505 still a request, last comment 2023-08-28; no `--dbsize`. |
| Q6 | Yi et al. ICDE 2003 and follow-ups | Conference PDF and the journal full version; Das et al. DAPD 2010 (`kcomp > k`). |
| Q7 | Quass, Gupta, Mumick, Widom, PDIS 1996 | PDF of the auxiliary-view paper. |
| Q8 | Panda / Ikeda, Salihoglu, Widom | IEEE Data Engineering Bulletin 2010 overview in full; CIKM 2011 and ICDE 2013 via abstracts and the Bulletin's own summary. |
| Q9 | Nectar, DryadInc, differential dataflow | Nectar OSDI PDF (incremental-plans section); DryadInc HotCloud 2009 PDF; McSherry et al. CIDR 2013 on Incoop. |
| Q10 | Feldera UDF docs; Databricks incremental refresh | Feldera UDF page; Databricks incremental-refresh matrix and the `UDF_NOT_DETERMINISTIC` error. |
| Q11 | incremental Pfam / HMMER 2015–2026 | Pfam relnotes; InterPro `pyinterprod` task list; InterProScan match-lookup docs; HMMER web server NAR 2026 (Nextflow reload, not a diff). |
| Q12 | iBLAST, iSeqSearch | PMC full text; NSF PAR full text of iSeqSearch. Semantic Scholar: iSeqSearch cited by 0. OpenAlex: iBLAST cited by 13, of which 6 are from 2024 onward. |
| Q13 | Caruca, PaSh, Smith & Albarghouthi, Presyn | Caruca alphaXiv + extracted PDF text; PaSh EuroSys 2021 PDF (annotation language); PLDI 2016 PDF (partial); Presyn arXiv (partial). |
| Q14 | INCR OSDI 2026 and nearby | INCR PDF re-fetched; lexical-tracing PACMPL and a PLDI 2026 probabilistic incrementalizer are language-level, not CLIs. |
| Q15 | citers of KumQuat since 2024 | OpenAlex: HotOS 2025 shell static analysis; Koala benchmarks. No sequence-search paper. |

### Readings

"(a) (b) (c)" are the locked definitions. "Exact" means byte-identical
or value-identical to a full rerun. Correlation is not exact.

#### 1. Pinned normalizer

**HMMER User's Guide, current** (eddylab.org/software/hmmer/CURRENT/Userguide.pdf).
The `-Z` block in the jackhmmer manual, repeated for the other search
programs, tells the user to declare the database size used for E-values
rather than the number of targets actually searched, with the explicit
case of a target database split across files for parallelization.
The Debian `hmmscan(1)` page carries the same flag for profile
databases: the asserted count replaces the number of targets seen.
**Grain:** one search invocation. **Inferred vs declared:** the user
types the flag. **Exact vs approximate:** the tool then prints E-values
against that count; the guide does not claim a byte-identical merge of
an incremental release. **Side:** reference-size statistic, not a
release diff. **(a)** no. **(b)** the option exists and is documented;
nothing infers it. **(c)** the same pages document `-E`, `-T`,
`--cut_ga` as reporting controls, again declared. **Exactness:** not a
maintenance system. **trust. full** (option sections and the
parallel-split paragraph; not every tutorial chapter).

**`hmmpgmd_shard` man page** (HMMER source `hmmpgmd_shard.man`).
Shards a protein *sequence* database across workers for RAM. HMM
databases are not sharded. No `-Z`, no E-value correction, no release
diff. **Negative finding:** this is not the pin. **trust. full** (man page).

**mpiBLAST — Darling, Carey, Feng, 2003.**
PDF `people.cs.vt.edu/~feng/pubs/papers/darling-cwce2002-mpiblast.pdf`
(OSTI dates the report 2003). Segments the database, searches
fragments, merges by score, prints with NCBI's output routines.
The 2003 text does not pass a full-database length into the statistics.
**Not the pin.** **trust. full.**

**mpiBLAST 1.3.0 note (Dec 2004) and BOSC 2005 talk** (Darling).
The release note, as posted by the team, says E-values are identical
to NCBI BLAST because both effective query length and effective
database length are used. The 2005 slides say the master computes
those lengths on the whole database and broadcasts them, and that
earlier versions were approximate. **Hand-built, one tool, planned
partition, not a later release.** iBLAST (below) is the peer-reviewed
confirmation of the same design. **provisional** (talk + release note).
**full** for those two short sources.

**blastall `-z` / `-Y`.** man page via manned.org. `-z` is the
effective database length; zero means the real size. The BLAST
statistics chapter reproduced in Korf, Yandell, and Bedell states that
`-z` is for keeping statistics consistent as a database grows.
**Declared flag. Not an inferrer. Not a release-diff engine.**
Modern `blastp -dbsize` was not on the Bookshelf this pass (HTTP 403);
MMseqs2 issue #505 (2021) asks for an option "the way blastp allows
with the `-dbsize` option," which is independent evidence the flag is
the known pin. **trust** for blastall; **provisional** for the BLAST+
name. **full** (man page and the book section that was fetched);
BLAST+ help text **not read**.

**DIAMOND `--dbsize`.** Buchfink wiki, Advanced options.
Effective database size in letters; setting it changes E-value
computation and skips a counting pass over a FASTA database.
**Declared. Not incremental. Not inferred.** Heuristic block size is
a different knob and is not this pin. **trust** (project docs).
**partial** (the option entry, not the Nature Methods paper).

**MMseqs2.** User guide PDF (split-for-memory, `clusterupdate` as
clustering). GitHub issue #505, opened 2021-11-15, maintainer reply
the same day: there is no effective-database-size option; a 2023-08-28
comment repeats the request. **Negative finding:** splitting MMseqs2
does not pin the normalizer, and `clusterupdate` is not search
maintenance. **trust. partial** (issue in full; user-guide chapters
on splitting and the earlier `clusterupdate` section, not every page).

#### 2. Slack / superset buffers

**Yi, Yu, Yang, Xia, Chen. ICDE 2003, pp. 189–200.**
PDF `cse.ust.hk/~yike/topk/icde03.pdf`, plus the longer Duke technical
report. A top-k view is not self-maintainable under deletion unless it
holds the whole base table. They keep a top-k′ view, k′ moving between
k and a kmax, and query the base table only when the buffer falls below
k. The view definition is known SQL. **(a)(b)(c)** no. **Exact** for
that SQL view, by refill. **Declared query, not an opaque CLI.**
This is the slack band. **trust. full** (conference paper).

**Quass, Gupta, Mumick, Widom. PDIS 1996, pp. 158–169.**
PDF of "Making Views Self-Maintainable for Data Warehousing."
Auxiliary views, derived from a known SPJ definition plus keys, make
the warehouse view maintainable without going back to the sources.
The auxiliary data is a superset chosen by the algorithm from the
declared query, not a probed CLI threshold. **trust. partial** (abstract,
algorithm statement, and the auxiliary-view form; not every proof).

**Das, Koudas, et al., DAPD 2010** (and the 2007 MPref workshop
version). Keep kcomp = k + Δk so a top-k view survives a high deletion
rate. Same family as Yi. Known view. **provisional** (workshop ancestor)
/ **trust** for the journal claim as read. **partial.**

No paper in this cluster infers which flag of an unmodified binary is
the threshold, or sets the buffer width from a fitted database-size
ratio.

#### 3. Black-box modules in workflows

**Panda — Ikeda and Widom, IEEE DEBULL 2010; Ikeda, Salihoglu,
Widom, CIKM 2011; Ikeda, Das Sarma, Widom, ICDE 2013.**
Bulletin read in full. Refresh traces provenance backward and reruns
the workflow on that slice. Logical provenance is a specification
language of attribute mappings and filters. Black-box nodes are legal;
their provenance is supplied, not discovered. Properties that make
refresh cheap are identified as assumptions, not probed out of a
binary. No reference file, no numeric normalizer, no reporting
threshold. **Exact** when the stated provenance is right, because the
module is rerun. **trust** for the Bulletin; **partial** for the two
conference papers (not opened as PDFs this pass).

**Nectar — Gunda, Ravindranath, Thekkath, Yu, Zhuang. OSDI 2010.**
For a repeated DryadLINQ program on an append, the rewriter finds a
combiner for most LINQ operators. User-defined code is handled by a
static analyzer of that source, not by executing an unmodified binary.
No statistical column. **trust. partial** (incremental-plans and
related-work sections of the OSDI PDF).

**DryadInc — Popa, Budiu, Yu, Isard. HotCloud 2009.**
A mergeable function needs a merge the programmer writes. Identical
sub-DAGs can be reused without that. **Declared. trust. full** (short
paper).

**Incoop — Bhatotia et al., SoCC 2011.** Not opened this pass.
Positioned only from McSherry, Murray, Isaacs, and Isard, CIDR 2013,
which describes Incoop as caching MapReduce reduce inputs and
re-executing the reducers that changed. Declared MapReduce. **not
read; do not cite beyond that sentence.**

**Feldera UDF documentation** (docs.feldera.com/sql/udf, read 2026-10-12).
Incremental SQL. A Rust UDF is declared in SQL and implemented by the
user. The compiler does not check determinism; the documentation puts
that duty on the author. A changed UDF body is not detected unless the
name changes. **Declared. trust** (docs). **full** (UDF page).

**Databricks Lakeflow / Delta Live Tables, incremental refresh**
(docs.databricks.com, incremental-refresh page and
`MATERIALIZED_VIEW_NOT_INCREMENTALIZABLE`, read 2026-10-12).
Incremental refresh covers a listed set of SQL operators. A UDF
participates only if the user marks it deterministic
(`UDF_NOT_DETERMINISTIC` otherwise). Behavior changes inside a UDF are
the user's full-refresh problem. **Declared. Not inferred. trust**
(docs). **full** for those two pages. Snowflake Dynamic Tables were
not fetched; no claim about them.

**DBToaster — Ahmad, Kennedy, Koch, Nikolic, VLDB 2012.** Not opened.
It is higher-order IVM of a SQL view, cited as such by the Noria UDTF
paper. Not a black-box CLI. **not read.**

#### 4. Black-box property inference

**KumQuat — Shen, Rinard, Vasilakis. PPoPP 2022.**
Prior full read (RELATED_WORK.md); this pass used that reading.
Infers a combiner for an unmodified Unix command split on its input
stream. DSL has no reference-cardinality scale and no threshold flag.
No cross-run store. **(a)** only for a stdin split, which is not a
reference partition. **(b)(c)** no. **trust. full** (earlier pass).

**Caruca — Lamprou et al., arXiv:2510.14279 (2025).**
Mines an invocation grammar from documentation, then classifies an
opaque command as stateless, pure, or side-effectful by sandboxed
execution, including how flags change that class. Records are lines.
Aggregator synthesis is explicitly left to KumQuat. No numeric column,
no normalizer option, no reporting threshold, no reference release.
**Does not supply two of (a)(b)(c).** **trust. partial this pass**
(alphaXiv and the extracted specification sections); **full** on
2026-10-03.

**PaSh — Vasilakis et al., EuroSys 2021.**
Annotation language, hand-written, for parallelizability class and for
how flags change inputs and outputs. The paper reports about 708 lines
of JSON for 47 commands. **Declared. trust. partial** (annotation
section of the PDF).

**Smith and Albarghouthi, PLDI 2016.**
Synthesize a MapReduce program from input/output examples and check
that the reducer is a commutative semigroup. The program is generated
source, not an opaque scientific CLI, and the check is algebraic on
the reducer, not a column tied to a reference size. **trust. partial.**

**Presyn — Collie, Woodruff, O'Boyle, GPCE 2020.**
Synthesize a program equivalent to a black-box API from probabilistic
fragment models. No view maintenance, no normalizer. **provisional.
partial.**

**GREYONE — Gan et al., USENIX Security 2020; Zhang et al., ASE 2014.**
Not re-opened. Prior readings stand: byte-dependence inference, and
polynomial metamorphic relations for scalar numeric functions. Neither
selects a table column, binds it to a reference count, nor names a
CLI flag. **trust. full in the 2026-10-06 pass.**

#### 5. Incremental bioinformatics, reference side

**iBLAST — Dash, Rahman, Hines, Feng. PLoS ONE 2021.**
DOI 10.1371/journal.pone.0249410. PMC text read (abstract through
discussion and Table 1). Hand-written BLAST wrappers. New sequences
only; E-values rescaled from the known Karlin–Altschul or Spouge
formula using the summed database length. They describe mpiBLAST and
NOBLAST as passing the full length in so the statistics module is
correct from the start, and as useless once the database later
changes. Case study I reports 100% E-value match and 100% hit match
on their nt slices. The discussion also says iBLAST reports additional
high-scoring hits that NCBI's heuristic dropped, because they keep
extra targets. **So the output is not the full rerun.** **(a)(b)** by
hand, for BLAST, append-shaped growth. **(c)** no. **Exactness:**
fails the locked bar (superset, and a rescaled number rather than the
tool's own reprint). **trust. full** (PMC article; S1 not every table).

**iSeqSearch — Yoo et al., PeerJ 2025.** DOI 10.7717/peerj.19171.
NSF PAR full text. Spouge rescale copied from iBLAST onto m8/m8e for
BLAST, MMseqs2, and DIAMOND. Pearson correlation of E-values on
overlapping hits is what they treat as agreement (0.97 and 1.0 in the
body). The body text's Kendall τ on ranks is 0.57 (iBlastp) and 0.48
(iDiamond); the figure caption states higher τ. Either reading is
rank correlation. The abstract and the discussion both say the
incremental run returns more hits. **Not exact. Hand-built. (c)** no.
Semantic Scholar citation count on 2026-10-12: 0. **trust** for the
negative result (they do not claim byte identity); the internal τ
disagreement is why it is not a methods baseline for exactness.
**full.**

**GeStore — Pedersen, Willassen, Bongo, Euro-Par HiBB 2013.**
Not re-fetched. The 2026-10-06 full read stands: per-tool plugins;
BLAST E-values corrected from Turcu et al. 2008; the HMMER plugin
only rewrites inputs, and every Pfam change is treated as significant.
**Hand-built. No HMMER pin, no HMMER rescale. trust. full then, not
re-read today.**

**InterPro production and InterProScan lookup.**
`pyinterprod` README: a member-database update is a scripted sequence
(load signatures, track changes, delete obsoletes, update matches),
repeated per member database with a name and a version. That is EBI's
own pipeline, with parsers, not a wrapper around an unmodified binary
and not an inferred normalizer. InterProScan's match lookup, v5 and
v6 docs, keys on the MD5 of the query sequence against UniParc.
When member databases move, EBI rebuilds the lookup. **Query-side.
Hand-built. (a)(b)(c)** no. **trust** (docs and the task list).
**partial** (README task graph and the lookup pages, not the Python).

**Pfam relnotes (38.2) and the HMMER web server NAR 2026 update.**
Releases are full rebuilds. The web server reformats databases with a
Nextflow pipeline into `hmmpgmd` inputs. No diff, no pin, no slack.
**trust. partial.**

**eggNOG-mapper `-m cache`.** Prior full read. Query MD5. A new
database is a new directory. **(a)(b)(c)** no.

#### 6. Exact incremental computation of opaque programs

**INCR — Xie, Lamprou, Xia, Vasilakis. OSDI 2026.**
Prior full read; PDF re-fetched. Default grain is the command. Finer
chunks need PaSh/POSH annotations that INCR does not infer. A changed
reference file reruns the command. No normalizer, no threshold, no
reference decomposition. Behaviorally matched to a full re-exec on
their suite, at command grain. **trust. full** (earlier pass).

**ProcessCache, Rattle, Riker.** Prior full reads. Process or command
grain. One new reference entry is a changed input file. They do not
infer (a)(b)(c).

**IncPy, Mandala, Adapton, self-adjusting computation.** Interpreter,
Python annotations, or a language in which dependencies are explicit.
Adapton and Acar's self-adjusting computation were not re-opened; the
limitation is the programming model, already recorded in
REFERENCE_PRIOR_ART.md. **not re-read today.**

**Lexical tracing (PACMPL, the page fetched 2026-10-12) and the PLDI
2026 probabilistic incrementalizer.** Both rewrite or cache a language
they control. Not unmodified CLIs. **partial** (opening pages).

#### 7. Citers since 2024

OpenAlex, 2026-10-12. iBLAST (W3153753638, 13 cites total; 6 since
2024): five are application papers (proteome annotation, guide RNA,
siRNA, therapeutic targets, toxin systems). The sixth is iSeqSearch.
KumQuat (W3193444021, 2 cites since 2024): HotOS 2025 shell static
analysis, and the Koala shell benchmarks. Neither cite is a system
that infers a normalizer or maintains a reference update exactly.
iSeqSearch: 0 Semantic Scholar citations. No 2023–2026 OSDI, SOSP,
NSDI, EuroSys, ATC, VLDB, SIGMOD, PLDI, or OOPSLA paper found that
infers two of (a)(b)(c) for an unmodified scientific binary. The
venue neighbors that did appear (INCR, Caruca's shell line, Databricks
incremental SQL) are the systems already read above.

### Verdict: NARROW

Applied to the locked rule, in order.

**KILL does not fire.** No system read here both (1) infers any two of
(a), (b), and (c) for an unmodified binary and (2) maintains a
reference update so the output is byte-identical or value-identical
to a full rerun. KumQuat and Caruca infer stream decompositions and
stop before a normalizer, a threshold flag, and a reference release.
iBLAST and iSeqSearch maintain reference growth and do not infer.
HMMER, BLAST, and DIAMOND expose a pin the user must type. Yi and
Quass keep a superset of a view the user defined. Panda, Nectar,
DryadInc, Feldera, and Databricks incrementalize a declared
computation. INCR, ProcessCache, Rattle, and Riker stay at command
grain unless someone annotates them.

**NARROW does fire**, on three independent grounds:

1. **One side, the maintenance mechanism, is occupied as standard
   practice.** Replaying or sharding a search with the database-size
   statistic fixed to the full reference is documented for HMMER
   (`-Z`), blastall (`-z`) and `blastp -dbsize`, DIAMOND (`--dbsize`),
   and mpiBLAST after 1.3.0. iBLAST then uses the summed length to
   rescale a previous BLAST run by hand.
2. **The slack band is occupied.** Yi et al. keep k′ > k; Quass et al.
   store auxiliary views so a declared query need not be recomputed
   from the sources. A widened reporting predicate is that technique.
3. **Both sides, done by hand for one tool family.** iBLAST writes the
   partition and the E-value formula for NCBI BLAST. It is not exact
   under this rule (extra hits; rescaled cells). That still satisfies
   "both sides only by hand / for one tool," because the inference
   side is replaced by a plugin and the maintenance side is the whole
   product. GeStore's BLAST plugin is the same shape and explicitly
   does not do it for HMMER.

**SURVIVES does not fire.**

### Prior art that must be cited, not claimed

- **Pinned normalizer.** HMMER User's Guide (`-Z` / `--domZ`) for a
  split search; NCBI `-dbsize` / `-searchsp` / blastall `-z`; DIAMOND
  `--dbsize`; mpiBLAST 1.3.0 / the account in iBLAST. The phrase
  "replay with Z pinned" is prior art. MMseqs2 is the exception that
  lacks the flag (issue #505), not a counterexample to the practice.
- **Slack buffer.** Yi et al., ICDE 2003, and the auxiliary-view line
  (Quass et al., PDIS 1996). Do not claim the superset.
- **Hand-built reference incrementality.** iBLAST and iSeqSearch
  (rescale, not byte-identical), GeStore (BLAST plugin; HMMER plugin
  does not correct). Do not claim incremental search.
- **Black-box decomposition of an input stream.** KumQuat and Caruca.
  Do not claim that probing an opaque command for a split is new.
  Their split is not a reference partition and has no normalizer.
- **Command-grain exact re-execution.** INCR, ProcessCache, Rattle,
  Riker. They rerun when the reference file changes.

`hmmpgmd_shard` is not in this list. It does not pin Z.

### Surviving claim, one sentence

ACTS is the first system to infer, from outside an unmodified CLI and
with no per-tool formula, that the output decomposes over reference
entries and which numeric columns are global normalizers, and then to
maintain a later reference release by rescanning only new or changed
entries and replaying the tool on a candidate superset with a
caller-supplied size pin, building on the documented database-size pin
(HMMER `-Z`, BLAST `-dbsize`, DIAMOND `--dbsize`) and on superset
buffers for view maintenance (Yi et al. 2003; Quass et al. 1996).

That sentence is narrower than the claim under attack, on purpose.

- The pin string is caller-declared data (`--pin '-Z {entry_count}'`
  in EXACT_REPLAY_PROTOCOL.md). The system can check that the supplied
  pin sets a fitted normalizer. It does not infer which flag to pass.
  Clause (b) of the attacked claim overreaches on "which tool option
  sets them."
- Clause (c), "which options are reporting thresholds," is not shown
  as option mining. The existing refusal is behavioral: reporting that
  reads reference size is refused (R2n). Naming `-E` versus `--cut_ga`
  is not an inferred result in the protocol.
- iBLAST already rescans an append-only BLAST delta and repairs
  E-values by a written formula. The delta is inference across tools,
  the tool reprinting its own bytes under a pin, and a refusal when
  the pin or the threshold story fails. A hand-written HMMER plugin
  that passes `-Z` would fall under GeStore plus the User's Guide and
  would not meet this sentence.

### Three reviewer attacks, and what defeats each

**1. "Passing `-Z` is in the HMMER manual. You reinvented a flag."**
This attack lands on the mechanism. The User's Guide tells the user to
set `-Z` when the searched file is not the whole database, including a
parallel split. Defeat is not a denial. It is the scope cut: the
manual does not infer that a column is Z, does not diff a Pfam
release, and does not decide the candidate set. The experiment that
would make the attack fatal is a second tool whose pin was never
written into `acts/` (DIAMOND `--dbsize` is the one named in
WHAT_WE_ARE_BUILDING.md §0) failing byte-identity, or succeeding only
because a DIAMOND formula was compiled in. Until that run exists, the
HMMER result is an instance of a documented flag, not a method.

**2. "The slack band is Yi et al., and the width is iBLAST's rescale."**
This attack lands on the buffer. Yi et al. keep extra ranked tuples of
a known query and refill from the base table when the buffer is
exhausted. iBLAST already multiplies an E-value by the ratio of
database lengths. Widening `-E` by Z_old/Z_new and letting HMMER
re-filter is those two ideas composed. Defeat: neither paper discovers
that an opaque tool's reporting flag is a threshold, nor refuses when
it is not (`--cut_ga` does not read Z). The discriminating experiment
is the locked E3c control: s = 1 must differ from stock on a shrinking
release, and s = 2 must match, with no cell rewritten by ACTS. If E3c
does not differ, the slack is not load-bearing and must not be
claimed. Cite Yi and iBLAST either way.

**3. "iBLAST already did exact incremental maintenance, and KumQuat
already infers the decomposition, so the conjunction is obvious."**
iBLAST's case study I is 100% E-value match on a hand-written BLAST
plugin, and the discussion states that iBLAST also returns hits NCBI
missed. That is not byte-identical, and nothing in iBLAST is inferred.
KumQuat's combiner DSL has no term for a reference-sized scale and no
release store; a byte-equality combiner refuses or reruns, which is
R2n, not a fitted normalizer. No citation since 2024 of either paper
closes the gap. Defeat is that pair of texts plus a build with no
BLAST formula and no HMMER formula: the same fitter, the caller-supplied
pin, and a body `cmp`. A plugin per tool loses this attack.

### Novelty rating: low

The operational pieces — the size pin, the superset buffer, hand-built
reference incrementality, and black-box stream splitting — are prior
art, and the claim as written overstates inference of the flag and of
the threshold option. What remains is a real but thin composition:
infer the reference decomposition and the normalizer column, then drive
those known mechanisms, or refuse. That is not a kill under the locked
rule, and it is not a strong claim.

### Hypothesis check (the three attacks named before search)

Attack 1 landed: pinned replay is standard. It narrows; it does not
kill. The 2003 mpiBLAST paper and `hmmpgmd_shard` were the wrong
citations for the pin; the User's Guide, blastall `-z` / `blastp
-dbsize`, DIAMOND `--dbsize`, and mpiBLAST 1.3.0 are the right ones.
Attack 2 landed: the slack band is top-k / auxiliary-view maintenance.
Attack 3 did not land as a kill: black-box workflow systems declare
module properties, and the hand-built bioinformatics plugins are not
byte-identical. NARROW is the mechanical outcome.
