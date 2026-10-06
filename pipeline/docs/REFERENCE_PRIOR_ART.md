# Reference-side incrementality — prior-art verdict

Written 2026-10-06. This file is the prior-art pass for the claim in
[`REFERENCE_INCREMENTAL_PROTOCOL.md`](REFERENCE_INCREMENTAL_PROTOCOL.md).
It does not edit that protocol's locked text.

## Kill rule (locked before search)

The claim under test treats an unmodified CLI tool as
`F(records, reference)` and asks whether a system can infer, with **no
per-tool code**:

- **(a)** that the output decomposes over reference entries, so the output
  on reference `R` equals the merge of the outputs on a partition of `R`;
- **(b)** which numeric columns carry a global normalizer, and that
  normalizer's form, fitted from a small fixed family (example: HMMER
  `E = Z · P` with `Z` the number of reference models; c-Evalue rescaled
  by per-query `domZ`, the number of targets reported per sequence).

On a new reference release the system would rerun only new or changed
entries, reuse cached rows for unchanged entries, and rescale the
normalized columns.

**Verdict rule, fixed before any query was run:**

- **KILL** if any prior work infers **(a) and (b)** automatically for
  unmodified black-box tools.
- **NARROW** if prior work does **(a) or (b)** automatically for one tool
  family, or hand-builds the whole thing for a specific tool. The
  remaining delta must then be stated precisely.
- **SURVIVE** otherwise.

Search log, per-paper readings, and the verdict follow this rule and were
written after it.

## Search log

Date of every query below: **2026-10-06**. Google Scholar was reached in
the browser and did not present a CAPTCHA. Scholar no longer puts an
"About N results" count in the page text, so each Scholar row records
the page-1 titles actually returned and any Cited-by count on those
hits. OpenAlex counts were taken the same day as a second surface;
counts above a few thousand on broad phrases are retrieval noise and
are not used as evidence.

| ID | Query | Surface | What came back |
|---|---|---|---|
| S1 | `incremental BLAST e-value correction iBLAST` | Scholar | Page 1: iBLAST (PLoS ONE 2021, Cited by 11), Dash et al. bioRxiv 2018 (Cited by 1), a VT PDF of the same work, Dash thesis 2020 (Cited by 2), iSeqSearch (no Cited-by link), then unrelated application papers. |
| S2 | Cited-by of iBLAST, `cites=11450129303198851719` | Scholar | 11 citing works. Page 1 is application papers plus Complet+ (Sokhansanj, Polikar, Rosen) and **iSeqSearch**. No generic black-box inferrer. |
| S3 | `KumQuat Shen Rinard Vasilakis combiner` | Scholar | Page 1 led by the PPoPP 2022 paper (Cited by 11), then PaSh-family shell papers (Koala, DiSh, JIT parallelization). |
| S4 | Cited-by of KumQuat, `cites=1860323079174577664` | Scholar | Page 1: Profix, **INCR** (Cited by 3), Koala, shell static analysis and reordering. No sequence-search or E-value paper. |
| S5 | `"incremental" HMMER OR Pfam "E-value" database update OR reannotation` | Scholar | Page 1 led by **GeStore** (Pedersen, Willassen, Bongo, Cited by 8), nf-core/proteinfamilies, iBLAST, UniRef, Yooseph incremental clustering, SWISS-MODEL, CDD, JCVI SOP. |
| S6 | `iSeqSearch incremental protein search` | OpenAlex | 1 work. |
| S7 | `search-based inference of polynomial metamorphic relations` | OpenAlex | 192. |
| S8 | `MMseqs2 clusterupdate incremental clustering` | OpenAlex | 7. |
| S9 | `InterProScan precalculated match lookup service` | OpenAlex | 9. |
| S10 | `eggNOG-mapper diamond cache mode` | OpenAlex | 30. |
| S11 | `KumQuat automatic synthesis parallel unix commands` | OpenAlex | 10. |
| S12 | broad phrases (`incremental view maintenance`, `Karlin-Altschul`, `infer E-value scaling`) | OpenAlex | 1.7e5, 3.5e5, 9.9e4. Discarded as hit counts. |

Semantic Scholar's citation API returned iBLAST at 9 citations
(DOI `10.1371/journal.pone.0249410`) before rate-limiting further
batch queries. PubMed abstracts were fetched for Karlin and Altschul
(PMID 2315319). Springer PDF for Turcu, Nestorov, and Foster (DaWaK
2008) was not obtained; that paper is positioned only through
GeStore's description of it.

## Readings

Each note states what is automatic, what is hand-coded, and whether
(a) and (b) are covered. "(a)" and "(b)" mean the locked definitions
above, not a loose cousin.

### iBLAST — Dash, Rahman, Hines, Feng, PLoS ONE 2021

DOI `10.1371/journal.pone.0249410`. PMC full text read: Abstract,
Introduction, Methods through "iBLAST implementation," Case study I
(Table 2), and the comparison with mpiBLAST and NOBLAST (Table 1).

- **Hand-coded, not inferred.** Python wrappers around NCBI BLAST+.
  Delta databases are built with `blastdbcmd` / `blastdbalias` by
  comparing filenames and sizes. The E-value repair is a derivation
  the authors write down: Karlin–Altschul recomputed from
  \(n_t = n_c + n_d\) (their Eq. 2), or Spouge rescaled by
  \(E_{\mathrm{total}} = E_{\mathrm{part}} \cdot n_{\mathrm{total}} / n_{\mathrm{part}}\)
  (Eq. 4). "Automated" means the user does not type the formula.
- **(a)** for BLAST, by construction: search the new sequences, merge
  hits. Not a probed partition of an arbitrary reference. Growth is
  append-shaped (new sequences), plus a spatial merge of taxon
  databases.
- **(b)** for BLAST E-values only, and the form is derived from the
  known statistic, not fitted from a family. Bit scores are left
  alone. They store \(2\times\) `max_target_seqs` because the merge
  can surface hits NCBI's heuristic missed.
- Case study I reports 100% e-value match and 100% hit match on their
  nt slices. That is a fidelity check of a hand-built tool, not an
  inference result.
- mpiBLAST and NOBLAST, as iBLAST describes them, also correct
  Karlin–Altschul E-values, but only when the full database length is
  known in advance and the split was planned. They do not reuse an
  old search.

### iSeqSearch — Yoo et al., PeerJ 2025

DOI `10.7717/peerj.19171`. Full article HTML read (Background through
Conclusions, Table 1, Methods).

- Extends iBLAST's merge to MMseqs2 and DIAMOND by requiring m8, or
  their m8e format whose first line stores database length. Spouge
  rescaling is "directly adopted from the iBlast framework" (Methods).
- **(a)** and **(b)** are hand-coded for tools that already emit m8.
  "Any tool that outputs m8" still receives one written rescale. The
  system does not discover which column is normalized or fit the form.
- Correctness is Pearson correlation of E-values on overlapping hits
  (1.0 for iMMseqs2 and iDiamond against the full tools; 0.97 for
  iBlastp) and Kendall tau on ranks. They also report **more** hits
  than the non-incremental run. That is a different bar from
  `ref-merge`.
- They note MMseqs2's own incremental mode is clustering
  (`clusterupdate`), not search, and that BLAST, MMseqs2, and DIAMOND
  have no native incremental search.

### GeStore — Pedersen, Willassen, Bongo, Euro-Par HiBB 2013

PDF `https://www.cs.uit.no/hdl/papers/hibb13.pdf`, read in full
(469 lines of text).

- Closest systems neighbor. Unmodified genomics tools, including
  BLASTP and HMMER against Pfam, get incremental updates by rewriting
  input files and merging outputs. The tool binary is not modified.
- **Hand-coded per tool.** An administrator writes a plugin: parser,
  incremental file generator, output merger (§2.2). "Typically a few
  tens of lines." The METApipe integration was 844 lines of Java for
  file-format plugins plus tool plugins (§3).
- **(a)** only inside those plugins. **(b)** for BLAST: the plugin
  "corrects incremental e-values as discussed in" Turcu, Nestorov,
  and Foster, DaWaK 2008, during merge (§3). The HMMER plugin "only
  generates input files." Pfam change detection "marks all changes as
  significant" (Table 1: Pfam-A, 100% of updates significant, 3.25%
  new entries). They say a better Pfam plugin would be future work.
- So GeStore occupies "unmodified HMMER, rerun on a reference diff"
  only in the weak sense that every Pfam change is treated as
  significant. It does not decompose HMMER output or rescale HMMER
  E-values.
- Turcu et al. 2008 was not read (Springer). GeStore is the source
  for the claim that their BLAST repair is a hand-written e-value fix.

### KumQuat — Shen, Rinard, Vasilakis, PPoPP 2022

Poster: DOI `10.1145/3503221.3508400`. Long form read: arXiv
`2012.15443` HTML, Abstract, §1 (the equation and the footnote that
the command is a black box), and §5 Related Work. Theorems in the
middle of the draft were not line-checked.

- **Automatic (input stream, not reference).** For an unmodified
  command, synthesize a combiner \(g\) in a DSL such that
  \(f(x_1 \mathbin{+\kern-0.2em+} x_2) = g(f(x_1), f(x_2))\).
  DSL operators named in the poster and the draft: concat, merge,
  rerun, stitch, add, first, second. No multiplicative database-size
  term.
- This is (a) for a **stdin / argument split** of Unix commands, not
  for a reference argument, and it is not (b). There is no cross-run
  cache. 113 of 121 unique commands got a combiner; 7 had none.
- §5 contrasts Smith and Albarghouthi (PLDI 2016), who synthesize
  MapReduce programs from input/output examples, and Farzan and
  Nicolet (PLDI 2017, 2019), who synthesize divide-and-conquer from
  a semantic characterization of loops. KumQuat's own comparison:
  those are not black-box Unix commands, and Smith and Albarghouthi
  do not preserve stream order.

### Caruca — Lamprou et al., arXiv 2510.14279 (2025)

PDF text read: Abstract, §1, Fig. 1, and §6.1 (parallelizability
classes).

- Mines specifications of opaque shell commands by executing them
  under syscall and filesystem tracing. Parallelizability classes:
  stateless, pure, side-effectful. §6.1 states that distinguishing
  parallelizable pure from non-parallelizable pure "amounts to being
  able to synthesize an aggregator, which is out of scope for Caruca
  but covered in prior work" (KumQuat).
- **Input-side.** No reference partition, no numeric column, no
  normalizer. Does not occupy (a) or (b) as locked.

### INCR — Xie, Lamprou, Xia, Vasilakis, OSDI 2026

PDF read: §1, §5 (safe reuse), §7 (optional annotations), §9
(related work, including the reactivity / view-maintenance
paragraph).

- Bolt-on incremental re-execution of unmodified shell scripts.
  Default grain is the command: dependencies and effects are memoized;
  a changed input file reruns that command.
- Finer chunks require **crowdsourced** PaSh/POSH annotations
  (`stateless`, `pure`, argument-splittable). INCR does not infer
  those labels. §7 is explicit.
- §9 points at view maintenance and self-adjusting computation as
  other incremental traditions and says INCR does not target
  reactivity. No reference argument and no statistical column.
  Input-side only. Does not occupy (a) or (b).

### Zhang, Chen, Hao, Xiong, Xie, Zhang, Mei — ASE 2014

PDF `https://xiongyingfei.github.io/papers/ASE14.pdf`. Read: Abstract,
§1, §3.2–3.4, §4.

- MRI infers polynomial metamorphic relations for numeric library
  functions (Apache, JDK, GSL, MATLAB; 189 functions) by particle
  swarm optimization over a parameterized linear or quadratic
  relation between two scalar executions, then filters on random
  inputs.
- The relation is between \(P(I)\) and \(P(I')\) for affinely related
  numeric inputs (their running example is \(\sin(x+\pi)=-\sin(x)\)).
  Each output is one scalar. Coefficient bounds were set by a trial
  on `sin` (§4).
- This is automatic inference of a polynomial identity for a callable
  numeric function. It is not (a): there is no reference partition
  and no merge of tabular hits. It is not (b): no column is selected,
  and the coefficient is not tied to a measured property of a
  reference (\(|R|\), domZ). A reviewer can still say the algebra of
  (b) is an instance of this search. That attack is answered below;
  the paper itself does not do the instance.

### MMseqs2 `clusterupdate` — Steinegger and Söding user guide

Read: "Updating a clustering database using mmseqs clusterupdate"
in the current user guide (the `mmseqs clusterupdate oldDB newDB ...`
section and the greedy-incremental clustering description).

- Hand-built incremental **clustering**: add sequences that are new,
  drop sequences that disappeared, keep stable numeric ids, start a
  new cluster when a sequence matches nothing. This is the mode
  iSeqSearch explicitly sets aside.
- Not a search-result cache, not an E-value rescale, not inferred.
  Neither (a) nor (b) for `hmmscan`-style output.

### InterProScan precalculated match lookup

Read: InterProScan 5 docs, "Running InterProScan," the
`--disable-precalc` section
(`https://interproscan-docs.readthedocs.io/en/v5/HowToRun.html`),
and the v6 rename to `--no-matches-api`.

- Lookup is an MD5 of the **query** amino-acid sequence against
  matches EBI already computed for UniProtKB. Identical sequences
  return the stored matches. One residue of difference is a miss.
- Hand-built service for one pipeline. It does not diff a member
  database (Pfam models added, removed, or edited) and reuse the
  unchanged models' rows. When InterPro's member databases move,
  EBI rebuilds the lookup. Neither (a) nor (b).

### eggNOG-mapper `-m cache`

Read: eggNOG-mapper wiki for v2.0.2–v2.0.8 (`-m cache`, `-c FILE`,
`--md5`) and the v3 `USAGE.md` description of seed-ortholog files and
database versioning.

- Cache mode looks up an annotations file keyed by the MD5 of the
  **query** sequence and writes the queries that missed, for a later
  real search. One tool, one hand-built mode.
- A new eggNOG database is a new data directory (v3: a minor version
  bump forces a re-download). The cache does not rescale E-values
  against a larger reference. Query-side memoization. Neither (a)
  nor (b).

### DIAMOND

Read: DIAMOND command-line documentation (makedb, blastx, block size,
`--iterate`). No database-update or incremental-search command
appears in that option list. iSeqSearch's introduction states the
same absence and then wraps DIAMOND by hand. Neither (a) nor (b)
inside DIAMOND itself.

### HMMER `hmmpgmd`

Read: Ubuntu man page for `hmmpgmd` (master loads `--seqdb` /
`--hmmdb` into memory; workers attach) and the HMMER web-server
paper's description of the same daemon (Finn, Clements, Eddy, Nucleic
Acids Research 2011, via the PMC passage quoted in search). The
daemon keeps one database resident so many queries avoid reload. It
does not diff a later Pfam release or rescale E-values. Neither (a)
nor (b).

### UniRule, and how UniProt reapplies family signatures

Read: MacDougall et al., "UniRule: a unified rule resource for
automatic annotation in the UniProt Knowledgebase," Bioinformatics
2020 (DOI `10.1093/bioinformatics/btaa485`), the sections on
InterPro/Pfam conditions and on the pipeline.

- Rules are expert-written conditions on InterPro signatures
  (including Pfam), plus taxonomy. Each UniProtKB release
  **recomputes predictions for all unreviewed proteins** against the
  latest rules and the latest protein attributes (they report ~1.5 h
  on 100 cores for release 2020_01). Third parties run InterProScan,
  then UniFIRE.
- That is a full re-annotation keyed by freshly computed signatures,
  not reuse of unchanged reference entries and not an inferred
  normalizer. ARBA, UniProt's later association-rule annotator, was
  not read as a methods paper; a 2024 GST-classification paper
  (PMID 39407545) only uses ARBA/UNI labels as a reference. Nothing
  in the UniRule text occupies (a) or (b).

### Ensembl VEP cache

Read: current Ensembl VEP cache documentation
(`vep_cache.html` on the June 2026 archive), "Cache version" and
"Limitations of the cache."

- The cache is a per-release dump of transcripts, regulatory
  features, and known variants. Cache 116 is for VEP 116 because the
  format and the data are regenerated every release. It is reference
  data for consequence prediction, not a memo of a previous VCF and
  not a decomposition over changed transcript entries. Neither (a)
  nor (b).

### Karlin–Altschul statistics

Read: PubMed abstract, PMID 2315319 (PNAS 1990), and the formulas as
iBLAST quotes them (Methods, "BLAST statistics").

- This is the statistic \(E = K m' n' e^{-\lambda S}\), with \(n'\) the
  effective database length. It is why (b) exists for BLAST. It is
  not a system that discovers the dependence from a black box.
  iBLAST, iSeqSearch, and GeStore's BLAST plugin are applications of
  this statistic, written by hand.

### Incremental view maintenance; self-adjusting computation; differential dataflow

- Blakeley, Larson, and Tompa (SIGMOD 1986) and the later IVM line
  maintain a **known** relational view. INCR §9 cites this tradition
  and disclaims it. GeStore's related-work list (Incoop, Percolator,
  DryadInc, HaLoop) is the same family: incremental dataflow when
  the computation is already expressed in the framework.
- Acar, Blelloch, and Harper, "Selective memoization" (POPL 2003),
  is cited by INCR. Self-adjusting computation needs a language in
  which dependencies are explicit. It does not take an unmodified
  CLI and a reference file.
- McSherry's differential dataflow (the Naiad line) maintains
  collections under changes inside a dataflow program the user
  wrote. Same limitation.
- These occupy incremental **maintenance of a specified computation**.
  They do not infer (a) or (b) for a black-box tool. Depth: INCR §9
  and GeStore's citation list were read; the POPL 2003 and
  differential-dataflow papers were not re-read in full this session.

### Black-box memoization over a second input, and workflow cache keys

- Nectar (Gunda et al., SOSP 2010), Incoop (Bhatotia et al., SOCC
  2011), DryadInc (Popa et al., HotCloud 2009), and CIEL (Murray et
  al., NSDI 2011) reuse work by lineage or content hashes inside
  their own runtimes. GeStore cites DryadInc and Incoop as systems
  that do **not** give transparent updates of an unmodified genomics
  tool. None infers a normalizer.
- Vassiliadis, Johnston, and McDonagh, "Fast, Transparent, and
  High-Fidelity Memoization Cache-Keys for Computational Workflows"
  (IEEE SCC 2022). Read via the IBM Research abstract and the
  description quoted in arXiv `2206.06217`: a walk of the workflow
  graph hashes a task's interface and its producer chain, ignoring
  instance-specific details. Equivalence is bit-identity of external
  inputs. A changed reference file changes the key and misses. No
  decomposition, no rescale. The SCC PDF was not obtained.

### MapReduce / divide-and-conquer synthesis

Positioned from KumQuat §5, which was read, plus the Semantic Scholar
record for Smith and Albarghouthi, PLDI 2016 (96 citations). The PLDI
PDFs were not re-read.

- Smith and Albarghouthi synthesize a MapReduce program from
  examples. Farzan and Nicolet synthesize divide-and-conquer for
  loops from a semantic model. Both want a structured program, not
  an opaque CLI, and neither fits a statistical column to a
  reference cardinality.

## Verdict: NARROW

Nothing read infers **(a) and (b) together**, automatically, for an
unmodified black-box tool. The kill rule's KILL branch does not fire.

The NARROW branch does fire, twice:

1. **Hand-built whole thing, specific tools.** iBLAST writes both the
   partition (new sequences only) and the E-value formula for NCBI
   BLAST. iSeqSearch copies the Spouge rescale onto any m8 producer
   (BLAST, MMseqs2, DIAMOND). GeStore does the same for BLAST with a
   per-tool plugin and explicitly does **not** do it for HMMER.
   Turcu et al. 2008 is the BLAST-warehouse ancestor GeStore cites.
2. **Automatic (a)-style decomposition, one family, no (b).** KumQuat
   infers a combiner for unmodified Unix commands split on their
   input stream. Caruca infers statelessness and stops before the
   aggregator. Neither binds a numeric column to a measured size of
   a reference.

**Surviving claim, one sentence.** No prior system infers, for an
unmodified CLI and with no per-tool plugin, both that the output
decomposes over reference entries and which numeric columns are
global normalizers of a form fitted from a small fixed family, so
that a later reference release can rerun only new or changed entries
and rescale those columns.

What that sentence does **not** say: it does not say incremental
search is new, it does not say E-value correction is new, and it does
not say black-box decomposition of an input stream is new. The
projected 7.4× in the protocol stays a projection. The R1–R3c files
show that `hmmscan --cut_ga` has the property; they do not show that
a generic fitter discovered it. Building the fitter is the work this
verdict leaves open. A hand-coded HMMER plugin would collapse into
GeStore and would not meet the claim.

## Three reviewer attacks

**1. "GeStore and iBLAST already did this, including HMMER."**
GeStore §3: the BLAST plugin corrects E-values by hand, following
Turcu et al. 2008; the HMMER plugin only generates input files, and
Table 1 marks 100% of Pfam-A updates significant. iBLAST's correction
is a derived Karlin–Altschul/Spouge formula in BLAST-specific code
(Eqs. 2 and 4), and "automated" means the user does not retype it.
Defeat is that pair of texts, plus a build that has no HMMER module:
the same fitter has to accept a tool whose normalizer was not written
down. The existing R2p/R3c checks are the specification of the
property, written before the runs, not that fitter.

**2. "KumQuat already infers (a) for black boxes."**
KumQuat's equation (arXiv 2012.15443 §1) splits the command's input
stream, and the combiner DSL has no term for a global scale factor
tied to a reference. Caruca §6.1 leaves aggregator synthesis to
KumQuat and still does not rescale a column. A naive merge is exactly
what R2n rejects: without `--cut_ga`, the union of the halves is a
strict superset of the full run
(`results/reference_kill_r2n.json`). A combiner that demands
byte-equality would refuse or rerun. It would not fit
\(E \propto Z\) or c-Evalue \(\propto\) domZ. Defeat is that equation,
that DSL, and R2n.

**3. "Zhang et al. ASE 2014 already infers (b), because
\(E_{\mathrm{total}} = E_{\mathrm{part}} \cdot n_{\mathrm{total}}/n_{\mathrm{part}}\)
is a polynomial relation."**
MRI §3.2–3.4 searches linear and quadratic relations between two
scalar outputs of a library function on affinely related numeric
inputs, as a test oracle. It does not partition a reference, choose
a column of a table, or identify the coefficient with a count of
reference entries or of targets reported for a query. Coefficient
ranges were tuned on `sin` (§4). Defeat is those sections. The
experiment that would make the attack real — fitting the
pre-registered family on partition probes of an unmodified CLI — is
the system this verdict says is not yet built, and it is not a result
in the ASE paper.
