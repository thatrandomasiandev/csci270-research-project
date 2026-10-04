# Related-work deep read (2026-09-27)

Read in full (PDFs/docs, not abstracts) before this file was written.
One-phrase quotes only; everything else is paraphrase.

**Novelty one-liner:** nothing occupies automatic record-level reuse
*inside one invocation* of an unmodified scientific CLI, persisted
across runs. Whole-command incrementalization of unmodified
binaries is occupied (ProcessCache, Rattle, Riker, and now INCR).
Hand-built per-record caches are occupied (eggNOG `-m cache`,
Oculus, SeAlM). Safety *theory* is occupied (Chen/Segura MRs;
Dune’s audit; vCache’s δ). Cost-model gating is engineering, not
a prior theorem.

The three ACTS claims are judged at the end.

---

## 1. Required works

For each: what it does, reuse grain, validity rule, tool changes,
correctness, evaluation, then the verdict on our core question
(*record-level reuse inside one invocation of an unmodified tool,
persisted across runs?*).

### 1.1 ProcessCache — Shiptoski, UPenn thesis 2023

Kelly Renee Shiptoski. *Reproducibility and Performance
Optimizations for Unmodified Linux Programs.* PhD dissertation,
University of Pennsylvania, 2023.
https://repository.upenn.edu/handle/20.500.14332/59482
· code https://github.com/upenn-acg/ProcessCache
Venue: thesis (not a conference paper). **trust** after a full
read of Ch. 3 (granularity + validity) and Ch. 4 (limits).

**What it does.** Userspace `ptrace` + seccomp-bpf memoizer for
unmodified Linux process trees. Companion system DetTrace is a
deterministic container (Ch. 2); ProcessCache is the cache (Ch. 3).
The cacheable object is an **exec-unit**: the suffix of a process
from a successful `execve` through termination of all descendants.
Nested exec-units form a tree. The system is always recording and
skipping in the same run.

**Granularity.** Process / `execve`. Chosen because `execve` resets
the address space, so the explicit inputs (binary, argv, envp) are
small enough to check. Caching a whole `fork` would require the
parent address space; caching arbitrary instruction ranges is
Shortcut (custom kernel; they could not rebuild it). Pipes, Unix
sockets, and shared memory force communicating processes into
**one** exec-unit, so `cat foo | wc` is skipped or rerun together.
Threads inside a process are one unit; BWA’s thread-level
parallelism cannot be skipped at thread grain (Ch. 3.5.3).

**Validity.** Formal criterion: “from scratch consistency.” If
exec-unit *e*’s **preconditions** hold, re-running *e* must issue
the same syscall sequence with the same returns. Preconditions
are computed from an ordered `SyscallEvent` list (open, stat,
unlink, …) by a forward pass that tracks each file’s initial vs
current state, so a truncate-then-read does *not* constrain
initial contents. Vocabulary (Table 3.3): Exists / DoesNotExist /
Traversible / HasPermissions / InputFilesMatch (mtime or SHA-256)
/ InitialContents / StatIs / … Failed syscalls generate
disjunctions. **Postconditions** are a recipe: create / delete /
chmod / rewrite contents, plus captured stdout/stderr. Cache
index is `(binary-path, argv)` → multimap of `StructEU`; at
`execve` pre-hook, the first StructEU whose preconditions hold
is applied (copy outputs, then rewrite `execve` to an empty
binary that exits with the recorded code). Implicit `execve`
state tracked: surviving FDs, signal mask, cwd, umask, alarm
timers (Table 3.1). Not all POSIX-surviving state is tracked.

**Tool changes / declarations.** None. `./process-cache ls -ahl`.
Needs `CAP_SYS_PTRACE`. Interactive stdin, `/dev/random`, and
clock consumers are not cached; networking is unimplemented.

**Correctness.** From-scratch consistency for the process tree
and for external observers *after* termination. Mid-run `/proc`
can see skipped children. Nondeterministic programs may pin a
buggy schedule in the cache. `mtime` checking is faster and
explicitly less sound than SHA-256. Ch. 3.5.4: bit-identical
outputs vs native on the reported suite. No statistical audit.

**Evaluation.** Bioinformatics (BWA, Clustal, HMMER 3.1b2,
Mothur, RAxML), 55 PaSh shell scripts (5 NLP shown), and three
C builds. Empty-cache overhead: 1.69× mean with hashing, worst
2.47× (RAxML). Unchanged inputs: up to 65× (hash) / 159×
(mtime). 5% of files changed (their “common” git delta): 2.05×
hash / 3.64× mtime. 10–25% often lose. They also skip
extraneous Makefile deps that `make` would rebuild.

**Verdict.** **No.** Closest unmodified-binary cache, and it
already targets bioinformatics workflows. One new record in a
FASTQ/VCF/FASTA is a changed input file → the whole exec-unit
reruns. HMMER under ProcessCache is one process.

### 1.2 Rattle — Spall, Mitchell, Tobin-Hochstadt, OOPSLA 2020

Sarah Spall, Neil Mitchell, Sam Tobin-Hochstadt. *Build Scripts
with Perfect Dependencies.* PACMPL 4(OOPSLA), 2020.
https://doi.org/10.1145/3428237
PDF: https://ndmitchell.com/downloads/paper-build_scripts_with_perfect_dependencies-18_nov_2020.pdf
**trust.**

**What it does.** Forward build system: a script is traced
(fsatrace) so dependencies are observed, not declared. A command
is skipped iff every traced input is unchanged. Cloud cache
copies outputs on exact input match. Speculation recovers
parallelism. Hazards (missing / extra / ordering) are formalized.

**Granularity.** Whole command.

**Validity.** Command traces: argv + environment + content hashes
of files read and written. Skip iff that set is identical.

**Tool changes.** None to the compiler; the user writes a build
script. Tracing is the declaration.

**Correctness.** “Perfect dependencies” relative to the trace.
What the trace misses (env they did not record, files opened
outside the tracer) is a hole. No record-level audit.

**Evaluation.** Converted Make projects; hazard theory plus
incremental rebuilds.

**Verdict.** **No.** Occupies traced *command* keys. ACTS probe-time
`strace` is this idea transferred to the first infer run, not a
new key theory.

### 1.3 Riker — Curtsinger & Barowy, ATC 2022 (best paper)

Charlie Curtsinger, Daniel W. Barowy. *Riker: Always-Correct and
Fast Incremental Builds from Simple Specifications.* USENIX ATC
2022, pp. 885–898.
https://www.usenix.org/system/files/atc22-curtsinger.pdf
**trust.**

**What it does.** Forward builder whose spec can be `gcc *.c`.
Syscall tracing compiles a TraceIR program over the full POSIX
filesystem (files, directories, pipes, links, sockets). Rebuilds
mix TraceIR emulation with re-execution of commands whose
dependencies moved. Infers fine-grained *compiler* steps (cc1 /
as / ld) from a monolithic recipe.

**Granularity.** Process / compile-step. A single
`snpeff -i cohort.vcf` is one step.

**Validity.** Every traced POSIX dependence is re-checked. Goal:
incremental output indistinguishable from a full build.

**Tool changes.** None to gcc. User supplies a short forward spec.

**Correctness.** “Always-correct” vs earlier forward builders
that missed directory/pipe deps. Still whole-command.

**Evaluation.** 14 packages including LLVM and memcached. Median
8.8% full-build overhead; incremental builds realize 94% of
make’s incremental speedup with no Makefile.

**Verdict.** **No.** Occupies complete POSIX models for *builds*.
Does not split scientific records inside one invocation.

### 1.4 vCache — Schroeder et al., ICLR 2026

Luis Gaspar Schroeder, Aditya Desai, Alejandro Cuadron, Kyle Chu,
Shu Liu, Mark Zhao, Stephan Krusche, Alfons Kemper, Matei Zaharia,
Joseph E. Gonzalez. *vCache: Verified Semantic Prompt Caching.*
arXiv:2502.03771 (v5 2026-02-21); ICLR 2026 (accepted).
https://arxiv.org/abs/2502.03771
https://doi.org/10.48550/arXiv.2502.03771
https://github.com/vcache-project/vCache
**trust** (venue + proofs in Appendix C; assumptions named).

**What it does.** Semantic *LLM* cache: embed the prompt, retrieve
the nearest cached prompt, and decide explore (call the LLM) vs
exploit (return the neighbor’s response). Replaces a global
similarity threshold with an online-learned logistic
similarity→correctness curve **per cached embedding**. User sets
an error tolerance δ.

**Granularity.** One prompt / one LLM response. Not a CLI, not a
record inside a file.

**Validity.** Not exact match. Exploit iff a random draw says
the conservative exploration probability τ̂ is not required.
Correctness of a hit is string match or LLM-as-judge.

**Tool changes.** Wrapper around the LLM API. No scientific
binary.

**Correctness.** Theorem 4.1: under i.i.d. prompts and a
correctly specified sigmoid, `Pr(vCache(x) = r(x)) ≥ 1 − δ`
for any prompt *x*. Conservative MLE bands (`t'`, `γ'`) make
the bound hold when samples are thin. If i.i.d. or the sigmoid
fails, the analysis does not apply (Limitations). This is a
**user-set error bound**, not a measured miss rate of
independence probes.

**Evaluation.** Three embedding models, two LLMs, four released
benchmarks (LM-Arena, classification, search queries, combo).
Meets δ; up to 12.5× hit rate and 26× lower error vs
static-threshold GPTCache on SemCacheLMArena. GPTCache error
rises with *n*.

**Verdict.** **No** on the core reuse question. **Yes** it occupies
“stated error-rate guarantee for a cache,” in the semantic-LLM
setting. ACTS `--verify audit` is Dune’s Bernoulli re-exec, not
this theorem. Do not claim we have a δ.

### 1.5 KumQuat — Shen, Rinard, Vasilakis, PPoPP 2022

Jiasi Shen, Martin Rinard, Nikos Vasilakis. *Automatic Synthesis
of Parallel Unix Commands and Pipelines with KumQuat.* PPoPP 2022.
https://doi.org/10.1145/3503221.3508400
https://arxiv.org/abs/2012.15443
**trust.**

**What it does.** Treats Unix commands as black boxes. Generates
shaped inputs, runs serial vs split-and-combine candidates from
a small combiner DSL (concat, stitch, merge, rerun, …), and
keeps combiners that satisfy
`f(x1 ++ x2) = g(f(x1), f(x2))`. Optional elimination of
intermediate combiners in a pipeline.

**Granularity.** Split of a *stream* for parallelism, then a
combiner. Not a persistent cache.

**Validity.** A combiner is kept only while every generated
input pair agrees with the serial command. Theorems 2 and 4
characterize when the remaining combiner is correct for the
seen inputs / the DSL.

**Tool changes.** None to the command. Synthesis is offline.

**Correctness.** Correct *parallel* execution given a true
combiner. Seven of 121 unique commands have no correct combiner
in the DSL. No cross-run memo.

**Evaluation.** 70 scripts, 121 unique stream-processing
commands; 113 combiners synthesized (median 60 s). Example
word-count pipeline: 14.4× at 16-way on 3 GB.

**Verdict.** **No.** Occupies black-box inference of *how to join
splits*. ACTS infers *field roles and independence* so it can
*cache*. Do not sell KumQuat’s probes as our probes.

### 1.6 eggNOG-mapper `-m cache` — wiki / USAGE

Cantalapiedra *et al.*, *Mol. Biol. Evol.* 2021 (tool paper).
USAGE: https://github.com/eggnogdb/eggnog-mapper/blob/main/USAGE.md
Wiki (v2.1.2–v2.1.4 and later):
https://github.com/eggnogdb/eggnog-mapper/wiki
**trust** as a product feature (docs read in full).

**What it does.** `emapper.py --md5` appends an MD5 of each query
sequence. Later, `-m cache -c FILE` annotates a new FASTA by
looking up those MD5s in a previous `.emapper.annotations`.
Misses can be written as FASTA and re-searched. `--resume` is
interrupt-resume of *this* run, not a second-genome memo.
Prebuilt `eggnog.db.*.bin` files are DB indexes, not user
results.

**Granularity.** Per sequence, exact amino-acid MD5. Hand-built
for this one tool.

**Validity.** MD5 match in the user-supplied cache file. No
independence probe, no namespace of hidden files.

**Tool changes.** The user must produce the cache (`--md5`) and
pass it (`-c`). Declarations are required.

**Correctness.** Exact-sequence identity. Wrong if the annotation
database or flags change while the cache file is reused; that
is the user’s problem.

**Evaluation.** Cantalapiedra *et al.* time proteomes/genomes
(minutes-scale). Wiki quotes hundreds of proteins/s for the
annotation stage with `eggnog.db` in `/dev/shm`. Not an
evaluation of `-m cache` as a general method.

**Verdict.** **Yes, for this one tool.** This is the hand-built
per-record cache we compete with. Occupies the *eggNOG
instance*. Does not infer records or field roles for an
unmodified third-party binary.

### 1.7 IncPy — Guo & Engler, ISSTA 2011

Philip J. Guo, Dawson Engler. *Using automatic persistent
memoization to facilitate data analysis scripting.* ISSTA 2011.
https://doi.org/10.1145/2001420.2001455
Earlier: TaPP 2010,
https://www.usenix.org/legacy/events/tapp10/tech/full_papers/guo.pdf
**trust.**

**What it does.** Modified CPython memos long-running pure
function calls to disk. Tracks code, globals, and file
dependencies so scientists stop hand-staging intermediates.

**Granularity.** Python function call.

**Validity.** Same function + same arguments + same tracked deps
→ return the memo. File deps are observed.

**Tool changes.** **Yes:** a different interpreter. Not a
closed binary.

**Correctness.** Persistent memo of a *pure* function. Impure
calls are the user’s problem. First run ~20% slower; later
runs can be orders of magnitude.

**Evaluation.** Data-analysis scripts; ISSTA 2011.

**Verdict.** **No.** Occupies interpreter-level persistent memo.
Cannot wrap STAR / SnpEff / HMMER.

### 1.8 Mandala — Makelov, SciPy 2024

Alexander Makelov. *Mandala: Compositional Memoization for
Simple & Powerful Scientific Data Management.* SciPy Proceedings
2024. https://proceedings.scipy.org/articles/JHPV7385
**provisional** (proceedings, not a PL venue).

**What it does.** `@op` + `Storage`: persist function calls,
retrace, version code deps. ComputationFrame queries the graph.

**Granularity.** Annotated Python function.

**Validity.** Call graph + code/data hashes.

**Tool changes.** User annotates functions.

**Correctness.** Incremental Python workflows. No binary wrap.

**Evaluation.** SciPy demo / workflows.

**Verdict.** **No.** Same layer as IncPy, nicer UX.

### 1.9 Dune `cache-check-probability` — docs

https://dune.readthedocs.io/en/stable/reference/config/cache_check_probability.html
https://dune.readthedocs.io/en/stable/reference/caches.html
(also `--cache-check-probability=FLOAT`). **trust** as a
shipped feature.

**What it does.** Shared Dune cache stores build-rule outputs.
Optionally, Dune “re-execute[s] randomly chosen build rules
and compare[s] their results with those stored in the cache.”
On disagreement it warns that the rule is not reproducible.
`(cache-check-probability p)` with *p* ∈ [0, 1]; 0 never, 1
always.

**Granularity.** Build rule / command.

**Validity.** Byte compare of re-exec vs cache.

**Tool changes.** Dune config or CLI flag. Not a wrapper around
an arbitrary scientific binary.

**Correctness.** Bernoulli audit of *cached rules*. No δ
theorem. No record grain.

**Evaluation.** Documentation / OCaml ecosystem use. Not a
miss-rate paper.

**Verdict.** **No** on record reuse. **Yes** it occupies the
audit *idea*. ACTS `--verify audit` (`p=0.02`, floor 20, one
batch) is this idea at record grain — engineering transfer,
not a new theory.

### 1.10 Oculus — Barrett et al., BMC Bioinformatics 2012

Barrett *et al.* *Oculus: faster sequence alignment by streaming
read compression.* BMC Bioinformatics 13:297, 2012.
https://doi.org/10.1186/1471-2105-13-297
**trust.**

**What it does.** Wraps Bowtie/BWA-class aligners: collapse
duplicate read sequences, align uniques, reprint SAM.

**Granularity.** Per unique read sequence, one aligner family.

**Validity.** Sequence identity. Output is reconstructed SAM,
not a cache of a later sample.

**Tool changes.** Hand-built wrapper. Grammar is FASTQ/SAM.

**Correctness.** “Nearly lossless” (>99.9%), **not** `cmp`.
RNA-seq often only 4–15% unique sequences at depth; WGS little
redundancy.

**Evaluation.** Up to ~2.7× (reported as 270% faster).

**Verdict.** **No** as a general method. Occupies the
aligner-specific instance. ACTS already killed STAR on
identity + Suite B overlap; do not claim we invented
align-uniques-once.

### 1.11 SeAlM — Stene & Banaei-Kashani, ICDMW 2019

Evan Stene, Farnoush Banaei-Kashani. *SeAlM: A Query Cache
Optimization Technique for Next Generation Sequence Alignment.*
IEEE ICDM Workshops 2019.
https://doi.org/10.1109/ICDMW.2019.00139
**provisional** (workshop).

**What it does.** Reorder alignment queries to raise redundancy,
then cache query results.

**Granularity.** Per alignment query, one aligner.

**Validity.** Query cache hit. Hand-built.

**Tool changes.** Yes — an aligner-specific optimizer.

**Correctness.** Throughput, not `cmp`. Single human ~6.5%;
population of 10 ~13–19% throughput (their numbers).

**Evaluation.** ICDMW 2019 experiments.

**Verdict.** **No** as a general CLI method. Occupies another
hand-built query cache.

---

## 2. Scholar / web sweep, 2023–2026

Queries (Scholar + web, 2026-09-27): record-level / fine-grained
memoization of black-box programs; incremental computation for
bioinformatics / Nextflow / Snakemake at sub-task grain; inferred
I/O contracts for caching; semantic caching with correctness
guarantees; cost-model “should I cache.” Every overlapping hit
is listed. Non-hits (memory *prediction* for scheduling, CXL,
RL memoization) are omitted.

| Work | Year / venue | Overlap | Verdict |
|------|----------------|---------|---------|
| **INCR** (Xie, Lamprou, Xia, Vasilakis). *Faster Re-execution via Bolt-on Incrementalization.* OSDI 2026. https://www.usenix.org/system/files/osdi26-xie-yizheng.pdf · https://github.com/atlas-brown/incr | 2026 / OSDI | Unmodified shell programs; syscall + OverlayFS probes; persist command effects across re-execs. Optional PaSh/POSH annotations chunk *declared-stateless* stdin or split per argument. 14 scripts, mean 34.2× / max 373× re-exec; 10,279/10,282 Bash-suite lines. | **Closest 2023–2026 neighbor.** Default grain is still the **command** (and its subprocesses). A lone `hmmsearch -i proteome.faa` is one probe; one new sequence changes the file → rerun. Chunk memo uses INCR’s “crowdsourced command annotations” (§7), not an inferred statelessness test. Does **not** occupy claim 1. Must cite. |
| Try / semisolate (Lamprou et al., OSDI 2026) | 2026 / OSDI | Isolation primitive INCR uses. | Mechanism, not a record cache. |
| Fractal (Huang et al., NSDI 2026) | 2026 / NSDI | Fault-tolerant shell *distribution*. | Parallel/distribute, not memo. KumQuat/PaSh family. |
| Koala benchmarks (Lamprou et al., ATC 2025) | 2025 / ATC | Shell workload suite INCR evaluates. | Benchmark, not a method. |
| DiSh (Mustafa et al., NSDI 2023) | 2023 / NSDI | Dynamic shell-script distribution. | Parallel, not cache. |
| PaSh (Vasilakis et al., EuroSys 2021; Kallas et al., OSDI 2022) | 2021–22 | Annotated data-parallel shell. INCR optionally consumes the annotations. | Occupies annotated Unix parallelism. Pre-2023; still the annotation source. |
| ProcessCache thesis (above) | 2023 | Unmodified Linux process memo. | Occupies process grain. |
| Mandala (above) | 2024 / SciPy | Python `@op` memo. | Python only. |
| Liu, *Incremental computation: What is the essence?* PEPM 2024 | 2024 / PEPM | Survey/position on incremental computation. | Background. No CLI record cache. |
| vCache (above) | 2026 / ICLR | Semantic LLM cache + δ. | Occupies bounded *semantic* cache. |
| GPTCache (Bang, NLP-OSS 2023) | 2023 | Static-threshold semantic LLM cache. 2–10× on hit. | No guarantee; LLM only. |
| MeanCache (Iffat et al., arXiv:2403.02694) | 2024 | User-centric / FL semantic cache vs GPTCache. | LLM; no δ theorem. |
| SCALM (Li et al., arXiv:2406.00025) | 2024 | Hierarchical semantic cache for chat. | LLM. |
| Zhu et al., *Efficient prompt caching via embedding similarity*, arXiv:2402.01173 | 2024 | Fine-tune embeddings for prompt cache. | vCache baseline. LLM. |
| WalmartCache (Dasgupta et al., ICPR 2025) | 2025 | Multi-tenant semantic cache. | LLM. |
| Agentic plan caching (Zhang et al., arXiv:2506.14852, 2025) | 2025 | Cache *agent plans*, not CLI records. | Adjacent vocab. |
| Nextflow `-resume` / task cache (Seqera docs; Langer et al., nf-core, bioRxiv 2024) | 2017–26 | Hash of task inputs + script; skip if outputs exist. | **Task** grain. One new record in the FASTA the task reads → rerun the task. Occupies workflow resume, not in-invocation records. |
| Snakemake output cache (`--cache`, Mölder *et al.* F1000 2021; docs v8–v9) | 2021–25 | Merkle hash of rule + software + inputs; share *between* workflows. Intra-workflow skip is already timestamp/content. | Rule/file grain. |
| Cromwell call caching (Broad docs) | current | Exact command + inputs (+ some runtime attrs). | Call grain. |
| Argo Workflows step memoization (docs) | current | Template-level cache; user supplies the key. | Declared step grain. |
| Flyte / Metaflow / DVC / Pachyderm caches | current | Task or dataset grain; user-declared. | Same as above. |
| Ponder / KS+ (Bader et al., BigData 2023; arXiv 2408.00047 / 2408.12290) | 2023–24 | Predict *memory* of Nextflow tasks. | Scheduling, not “should I install a record cache.” |
| SpecFaaS (HPCA 2023) | 2023 | Speculative FaaS + memo tables. | Serverless; not scientific CLIs. |
| Shortcut (instruction-range reuse; cited by ProcessCache) | older | Finer than process; custom kernel. | Not 2023–26; still not records. |

**Thin field on the exact object.** No 2023–2026 paper
automatic-infers per-record I/O contracts of an unmodified
SnpEff/HMMER-class binary and memos those records across runs.
INCR + workflow managers occupy everything *around* that object.

---

## 3. Novelty verdict

Three claims, judged after the reads.

### Claim 1 — Automatic record and field-role inference, no per-tool code

**Survives**, with a named neighbor.

- Occupied around it: KumQuat infers *combiners*; ProcessCache /
  Rattle / Riker / INCR infer *file* deps of a process or
  command; PaSh/POSH *declare* statelessness; eggNOG/Oculus/SeAlM
  hard-code one grammar.
- INCR’s optional chunking is the sharpest 2026 objection. It
  still needs a crowdsourced “stateless” / “argument-independent”
  annotation (“crowdsourced command annotations”, Xie et al. §7)
  and applies to Unix stream utilities, not inferred
  `CHROM,POS,REF,ALT` vs `INFO/ANN`. Confirmed on a reread of
  the chunking/memoization section (2026-09-27). The claim is
  correct: INCR does not infer statelessness.
- What we actually own: per-**format** probes (determinism,
  shuffle, subset-invariance, field-role perturbation, late keys)
  that produce a cache key and a reassembly contract for an
  unmodified VCF or FASTA→table binary.

### Claim 2 — Safety probes with a measured miss rate in deployment mode

**The measurement survives; the theory does not.**

- Occupied: Chen/Segura metamorphic testing (our shuffle /
  subset / perturbation *are* MRs). Dune occupies random
  re-exec + diff. vCache occupies a user-set δ for semantic
  LLM caches (different object, stronger claim).
- What we own: the **measured** unsafe-ship rate of *this*
  probe suite under `--verify audit` (probes + 2% hit audit,
  no full MATCH) on F1–F8 / C1–C5. Full-MATCH (`96f786b`) is
  an experimental upper bound, not the deployed number.
- Non-claim: F6-env. F6-file is a Rattle transfer (probe-time
  strace). Do not say “first statistical cache.”

### Claim 3 — Cost-model gating that predicts speedup before caching

**Survives as engineering, not as a literature gap worth a
paper by itself.**

- `t = a + b·n`, ceiling at a locked miss fraction, refuse if
  the predicted ratio cannot pay for wrapper `w`. Measured on
  SnpEff (`a_now` 15.98 s → 1.203× predicted vs 1.167×).
- 2023–2026 workflow papers predict *memory/runtime for
  scheduling* (Ponder, KS+), not “should this unmodified binary
  get a record cache.” ProcessCache reports overheads after
  the fact. Nobody we found gates installation of a
  black-box record memo on a two-parameter fit.
- Do not lead the paper with this. It is the screen, not the
  method.

---

## 4. Draft related-work section (~800 words)

Automatic incremental reuse is an old idea. The question is
the grain, and whether the tool must be changed.

At process or command grain, several systems already wrap
**unmodified** binaries. Rattle traces each build command and
skips it when argv, environment, and hashed file inputs match
(Spall, Mitchell, and Tobin-Hochstadt, OOPSLA 2020). Riker
extends that model to the POSIX filesystem — directories,
pipes, links — so a spec as short as `gcc *.c` still
rebuilds correctly (Curtsinger and Barowy, ATC 2022).
ProcessCache generalizes the same idea off the build system
and onto arbitrary Linux process trees (Shiptoski, UPenn
thesis 2023). It memos **exec-units** (from `execve` to the
end of the descendant tree), computes preconditions from a
syscall log, and skips when those preconditions hold. On
unchanged inputs it reports up to 65×; when a few input
*files* change, speedup collapses, and a changed FASTA is
one file. INCR (Xie, Lamprou, Xia, and Vasilakis, OSDI 2026)
is the 2026 form of this line: bolt-on incrementalization of
unmodified **shell programs**, OverlayFS isolation plus
strace, reuse of command effects across edits. With optional
PaSh/POSH annotations it can chunk stdin of a *declared*
stateless utility or split per argument. Default grain
remains the command. A lone `hmmsearch` on a proteome is
one command; one new sequence reruns it. We use their
tracing idea at **probe time** to fingerprint files the
tool opens. We do not claim first automatic cache keys.

Workflow managers occupy the next-coarser grain. Nextflow
`-resume`, Snakemake’s intra-workflow skip and `--cache`,
and Cromwell call-caching all hash a **task** and its
declared inputs. They are the right answer when the
scientist already split the work into processes. They do
not look inside `snpeff -i cohort.vcf`.

Finer grain exists if the language is under control. IncPy
(Guo and Engler, ISSTA 2011) memos Python functions inside a
modified CPython. Mandala (Makelov, SciPy 2024) does the same
with `@op` annotations. Neither reaches a closed binary.

Per-record reuse for *one* scientific tool is also occupied,
and we should say so. Oculus collapses duplicate reads
before Bowtie/BWA and reprints SAM; it is nearly lossless,
not byte-identical (Barrett et al., BMC Bioinformatics 2012).
SeAlM caches alignment queries (Stene and Banaei-Kashani,
ICDMW 2019). eggNOG-mapper’s `-m cache` is the cleanest
neighbor: `--md5` then a user-supplied annotations file,
exact amino-acid identity, misses re-searched. That is a
hand-built memo of prior user sequences — our job, for one
tool. Ensembl VEP `--cache` is the trap citation: it is a
**reference-data** store, not a memo of the user’s last VCF.

Black-box *structure* inference without caching is KumQuat
(Shen, Rinard, and Vasilakis, PPoPP 2022): combiners for
data-parallel Unix commands, 113 of 121 unique commands, no
cross-run store. PaSh and POSH annotate the same commands
for parallelism. We infer a different contract (which fields
are keys, which are produced, whether neighbors leak) so we
can memoize.

Correctness arguments for caches are also occupied, at other
grains. Dune’s `cache-check-probability` re-executes random
**build rules** and diffs them. vCache (Schroeder et al.,
ICLR 2026) gives a user-set error bound δ for *semantic*
LLM caches under i.i.d. prompts and a sigmoid model — a
stronger claim than we can make, on a different object.
Our shuffle, subset, and perturbation probes are metamorphic
relations (Chen, Cheung, and Yiu 1998; Segura et al., IEEE
TSE 2016). The paper’s correctness contribution is not a
new MR theory and not a δ. It is a **measured** unsafe-ship
rate of this probe suite in the mode we actually ship
(`--verify audit`: no full stock run; 2% hit audit, at least
20 hits). The earlier full-MATCH number is an experimental
upper bound.

What is left, and what we claim, is narrow: infer records
and field roles of an unmodified VCF or FASTA→table binary
with no per-tool code; memoize those records across runs;
refuse when the probes fail; and, in deployment, accept on
probes plus a Dune-style audit rather than a second full
run. ProcessCache, Rattle, Riker, and INCR will rerun the
process when any input byte changes. eggNOG will not
annotate a SnpEff VCF. KumQuat will parallelize `sort` and
leave tomorrow’s proteome uncached.

---

## 5. Reading status

| Work | Read | Rating |
|------|------|--------|
| ProcessCache thesis (Ch. 1–5, emphasis 3–4) | full | trust |
| Rattle | full | trust |
| Riker | full | trust |
| vCache v5 + App. C | full | trust (LLM setting) |
| KumQuat | full | trust |
| eggNOG USAGE + wiki cache mode | full | trust (feature) |
| IncPy | full | trust |
| Mandala | full | provisional |
| Dune cache-check docs | full | trust (feature) |
| Oculus | full | trust |
| SeAlM | full | provisional |
| INCR OSDI 2026 | full | trust |

Personal-store notes updated in the same pass
(`literature/topics/record-memoization-cli.md`, paper files
for ProcessCache, vCache, INCR).

## Addendum 2026-10-03 — Caruca and INCR, read in full

Sources read end to end: Caruca, arXiv 2510.14279v1 (Lamprou, Jung,
Keoliya, Lazarek, Kallas, Greenberg, Vasilakis; 11,846 words), and INCR,
"Faster Re-Execution via Bolt-On Incrementalization", USENIX OSDI 2026
(Xie, Lamprou, Xia, Vasilakis; `osdi26-xie-yizheng.pdf`, 13,654 words).
The 2026-09-27 review above missed Caruca.

### Caruca (specification mining for opaque commands)

- **What it infers.** An LLM turns a command's documentation into an
  invocation grammar. Sandboxed, strace-traced executions then classify
  each invocation: *stateless* if its output on input `i` equals the
  concatenation of its outputs on `n` partitions of `i` **split over
  lines**; *argument-splittable* if one invocation per argument,
  concatenated, equals the full invocation; plus input/output files and
  filesystem pre/post-conditions.
- **Records.** Always lines. A multi-line record (a FASTA entry) has no
  representation.
- **Reuse.** None. Specifications feed PaSh, POSH (parallelization),
  Shellcheck and Shseer (bug finding). No caching, no cross-run reuse.
- **Keys and fields.** None. No notion of which part of a record an
  output depends on, or of fields copied from input vs computed.
- **Evaluation.** 60 GNU Coreutils, POSIX and third-party commands.

### INCR (bolt-on incrementalization of shell scripts)

- **Default granularity.** Whole command invocations: a probe records each
  command's dependencies (inputs, stdin hash, environment, filesystem) and
  replays its memoized effects when all are unchanged.
- **Finer granularity needs annotations.** For commands that crowdsourced
  annotations (from PaSh/POSH) label *stateless*, INCR splits the input
  stream with **content-defined chunking** and memoizes each chunk
  separately, keyed by the chunk's content; unchanged chunks (e.g. a log
  extended with new events) are reused. For *argument-independent*
  commands it splits invocations per argument.
- **Keys and fields.** Chunk bytes only. No projection key, no field roles,
  no splicing of copied fields from new input.
- **Caruca.** Not cited; INCR's annotations come from PaSh and POSH.

### Verdict for ACTS

Neither work infers a **content key** (the projection of a record that a
tool's output depends on) or separates copied from computed fields.
Together they give byte-level reuse: line partitions (Caruca) and
content-defined byte chunks (INCR). ACTS's content-key claim is **not
occupied** by either.

The measured gap (`results/content_key_overlap.json`, pre-registered in
`docs/CONTENT_KEY_PROTOCOL.md`): byte-level record keys recover 0.56 of
inferred-key reuse on the 1000G VCF workload and 0.00 on GenBank E. coli
proteomes (RefSeq control 0.998). Argument, not yet measured: INCR's
chunks span several records, and a chunk is reusable only if all of its
bytes recur, so per-record byte-key recall is an upper bound on its chunk
reuse for these inputs. Running INCR itself (artifact requested) would
replace that argument with a measurement.

Claims that **are** occupied and must be cited, not claimed:
execution-based inference of line-level statelessness for opaque commands
(Caruca), and chunk-level memoization for stateless commands (INCR).

Positioning sentence for the paper: *Caruca infers whether an opaque
command can be split over lines, and INCR reuses unchanged byte chunks of
such commands. ACTS infers which part of each record a tool's output
depends on, so it reuses results when records recur with different bytes:
renamed proteins, variants carrying another sample's genotypes, compounds
with new IDs.*
