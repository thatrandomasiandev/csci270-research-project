# Baseline comparisons (pre-registered)

Written **2026-09-27, before** any baseline install, timing run, or
CARC submit. Do not edit locked sections after a job starts. No
timing in this commit. No `sbatch`. No download ≥1 GB in this
session.

This file **is** the pre-registration. Expected behavior is written
down here so a later “they skipped the new genome” cannot be
back-fitted.

Predecessor: `docs/SAVINGS_PROTOCOL.md` (collections A/B, MATCH,
HMMER argv, exclusive-node budget). Related-work grain:
`docs/RELATED_WORK.md`. Headline occupation:
`docs/HEADLINE_CANDIDATES.md` (eggNOG `-m cache` occupies
*user-result* memo). Claim lock: `WHAT_WE_ARE_BUILDING.md`.

---

## Question (locked)

On the **same** savings workloads (collections A and B, HMMER
`hmmscan --cut_ga` and `hmmsearch -Z 1e6 --domZ 1e6`, same order,
same `--cpu 32 --noali --tblout`), do whole-command caches (Riker,
ProcessCache, INCR) or eggNOG’s own `-m cache` reuse work **inside**
a later proteome the way ACTS record memoization claims to?

**Falsifier for “whole-command is enough”:** if any of Riker /
ProcessCache / INCR skips `hmmscan`/`hmmsearch` on genome *k*+1
when genome *k*+1 is a **new FASTA file** (even when many protein
records already appeared in genomes 1…*k*), the grain claim in
`RELATED_WORK.md` is wrong and we must revise it.

**Falsifier for “eggNOG occupies the instance”:** if `-m cache`
does **not** skip exact-MD5 proteins on a later genome of the same
collection, the occupation claim in `HEADLINE_CANDIDATES.md` is
wrong.

ACTS is **not** timed in this protocol. The savings jobs remain
the ACTS measurement. These baselines are the paper’s comparison
table, run after (or interleaved with) savings, never instead of it.

---

## Shared workload (locked; copied from SAVINGS_PROTOCOL.md)

Same orderings as `recurrence_curves.json` → `orderings[0]`, seed
**20260926**. Accessions: `recurrence_accessions.json`.

| Workload | What |
|----------|------|
| **B** | O157:H7, all 40 genomes |
| **A** | diverse *E. coli*, first 30 of the first ordering |

Collection C is out. A genomes 31–100 are out.

HMMER 3.4, Pfam-A 38.2, same argv templates as
`headline_screen.json`. MATCH on tblout is **token identity**, not
bytes (`SAVINGS_PROTOCOL.md`): hmmscan `--cut_ga` = order +
`split()`; hmmsearch fixed-Z = **multiset** + `split()`.

Each genome is a **distinct FASTA path** (`protein.faa` per
accession). That fact is the independent variable for
whole-command caches.

---

## Fairness (locked)

| Baseline | Best documented mode we run | Strawman we will not run |
|----------|-----------------------------|---------------------------|
| **Riker** | Linux `rkr` **release** build (`make release` / `make install-release`), one-command `Rikerfile` that is the stock HMMER argv. README’s documented user path is `rkr` (optional `--show`). | Debug-only as the timed path; wrapping `make` around HMMER; macOS (unsupported). |
| **ProcessCache** | **SHA-256 content hash** of inputs (`CheckMechanism::Hash`, `generate_hash` → `sha2::Sha256`; compile-time `DONT_HASH_FILES = false` is the default). | `DONT_HASH_FILES = true` (mtime) as the *only* number. Mtime is an extra **reported** column because the thesis calls it faster and less sound. |
| **INCR** | Two columns: **(1) default, no PaSh/POSH annotations**; **(2) with the artifact’s crowdsourced annotations enabled** (paper §7 / Appendix A). Native Ubuntu 22.04 path if CARC cannot run `--privileged` Docker. | Annotating `hmmscan`/`hmmsearch` ourselves as “stateless.” That would be our method, not theirs. |
| **eggNOG-mapper** | The tool’s **own user-result cache**: first genome `emapper.py --md5`; later genomes `-m cache -c FILE` with the accumulated `.emapper.annotations`. Default search `-m diamond`. | `--resume` (interrupt-resume of *this* run, not a second genome). Strawman “diamond with no cache.” `--dbmem` only if Josh approves **≥44 GB RAM** (wiki). |

Do not compare ACTS hmmscan 3× to eggNOG wall. Different binary,
different output, different scientific question. eggNOG is the
**hand-built per-record** neighbor on the **same FASTA
collections**, not a wrap of HMMER.

---

## 1. Riker (Curtsinger & Barowy, ATC 2022)

**Citation.** Charlie Curtsinger, Daniel W. Barowy. *Riker:
Always-Correct and Fast Incremental Builds from Simple
Specifications.* USENIX ATC 2022, pp. 885–898.
https://www.usenix.org/system/files/atc22-curtsinger.pdf
https://www.usenix.org/conference/atc22/presentation/curtsinger
**trust** (ATC best paper; 14 packages).

**Artifact (found).** Open-source at https://rkr.sh (paper) and
https://github.com/curtsinger-lab/riker (README clone target;
`git clone --recursive`). GitHub `README.md` on `main` currently
says the project **migrated to Codeberg**; the ATC-era GitHub
tree remains the cited artifact. No public Zenodo snapshot for
*this* paper was found (a Zenodo “ATC2022-paper647” record
exists but is a **different** ATC 2022 paper; do not use it).

**Install.** Linux **x86_64** (ARM64 “much less testing”). **Not**
Windows or macOS (README: syscall tracing not ported). Ubuntu
20.04 packages: `make clang llvm git gcc python3-cram file
graphviz`. Build: `make` (debug; README: “only marginally slower”)
or `make release`. Binary: `rkr`. Spec: a `Rikerfile` that can be
`gcc *.c` or any executable full-build script.

**Kernel / tracing.** Paper §4: `ptrace` on 75 filesystem / fd /
process syscalls, **seccomp BPF** to drop the rest, plus an
injected libc interceptor (`open`/`stat`) to cut ptrace overhead
(memcached: 95% of syscalls in the library). Needs a kernel with
`ptrace` + `CONFIG_SECCOMP_FILTER`. No OverlayFS. No stated
multi-GB data besides the project under build. HMMER+Pfam-A is
the existing savings install (~399 MB Pfam), not Riker’s.

**How it runs on A/B.** One working directory per (collection,
mode). `Rikerfile` is a single line: the stock HMMER command with
that genome’s FASTA and that mode’s tblout path. Sequential over
the locked order. Persistent `.rkr/` cache directory **kept**
across genomes (otherwise we are measuring cold start, not
incremental). Do not rewrite the FASTA in place; each accession
is a new path, as in the savings jobs.

**Expected behavior (before any run).** Riker’s grain is
process / compile-step (paper; `RELATED_WORK.md` §1.3). A
`Rikerfile` that is one `hmmscan` is **one command**. Genome
*k*+1’s FASTA is a file Riker has not seen → that command’s
TraceIR dependencies moved → **full re-execution every genome**.
Replay of *the same* FASTA path with unchanged Pfam-A and binary
**should skip**. Pipe-connected helper commands, if any, rerun
together (paper: pipes are not cached).

**Quality.** **trust.** Artifact is source + README, not a
packaged AE VM. Alpha-quality per README.

---

## 2. INCR (Xie, Lamprou, Xia, Vasilakis, OSDI 2026)

**Citation.** Yizheng Xie, Evangelos Lamprou, Jerry Xia, Nikos
Vasilakis. *Incr: Faster Re-execution via Bolt-on
Incrementalization.* USENIX OSDI 2026, pp. 683–699.
https://www.usenix.org/system/files/osdi26-xie-yizheng.pdf
https://www.usenix.org/conference/osdi26/presentation/xie-yizheng
**trust.**

**Artifact (found).** Paper Appendix A:
- GitHub https://github.com/atlas-brown/incr
- Zenodo archival https://zenodo.org/records/19488802
  (cited in the PDF; HTTP fetch from this session returned
  **403**, so treat GitHub as the runnable copy and Zenodo as
  the archival URL to re-check at install time).

README + `INSTRUCTIONS.md`: Docker is the default
(`ghcr.io/atlas-brown/incr:latest`, `docker run --privileged`).
Native Ubuntu 22.04: `git mergerfs strace python3 python3-pip
build-essential pkg-config libssl-dev libtool` + Rust/`cargo`;
`pip3 install -r requirements.txt`; `cargo build --release`;
`bash ./src/incr.sh myscript.sh`.

**Install / kernel.** Linux. **OverlayFS** per command (lowerdir
+ upperdir, `unshare` of user / pid / mount namespaces — paper
§4). Read deps via **strace** `%file` + **seccomp-BPF**.
`mergerfs` is a documented native dependency. Docker path
requires **`--privileged`**. Network/clock/entropy (`-N` in the
paper’s related-work notes; commands with unsupported effects)
disable reuse. HMMER itself is small; cache is “avg 6.05× of
original input size” (paper) — proteome FASTAs are small, Pfam-A
is shared.

**How it runs on A/B.** A POSIX script per (collection, mode)
that loops the locked order and runs **one** `hmmscan`/`hmmsearch`
per genome (not `xargs` over all FASTAs: paper default grain
treats `xargs` as **one** unit). Invoke `incr` / `incr.sh` on
that script. Keep `--cache` on a persistent directory across the
collection. Column 1: default (no annotation extra). Column 2:
artifact annotations on (paper: +1.46× mean on *their* Unix
benchmarks; **not** a claim they chunk HMMER).

**Expected behavior (before any run).** Default grain is the
**command plus subprocesses** (paper; `RELATED_WORK.md` §2).
`hmmscan` on a new proteome FASTA is a new file read → **rerun
every genome**. Optional chunk memo applies to *declared
stateless* stdin (PaSh/POSH). **No public annotation marks
`hmmscan`/`hmmsearch` as stateless** in the INCR/PaSh docs we
found; column 2 is still run so a reviewer cannot say we hid
their best mode, but the **pre-registered prediction** is that
annotations do **not** split FASTA records inside HMMER. Same-file
replay should skip. `xargs` wrapping would hide per-genome
reruns — forbidden.

**Quality.** **trust.** Artifact available (GitHub). Zenodo
access not confirmed in this session (403). Privileged Docker
may be **impossible on CARC** — native OverlayFS path is the
fallback, still Linux-only.

---

## 3. ProcessCache (Shiptoski, UPenn thesis 2023)

**Citation.** Kelly Renee Shiptoski. *Reproducibility and
Performance Optimizations for Unmodified Linux Programs.* PhD
dissertation, University of Pennsylvania, 2023.
https://repository.upenn.edu/handle/20.500.14332/59482
**trust** (full read of Ch. 3–4). Code:
https://github.com/upenn-acg/ProcessCache

**Artifact (found).** GitHub `upenn-acg/ProcessCache` (Rust,
`cargo build`, rustc 1.67.0+). README: `./target/release/process_cache -- <cmd>`.
**No Zenodo / packaged AE** found. “Benchmarks: link coming
soon” on the README (retrieved 2026-09-27). Thesis PDF is the
eval source. Bioinformatics suite in the thesis **includes HMMER
3.1b2** — still one process.

**Install / kernel.** Linux. Userspace **`ptrace` + seccomp-bpf**
(source `src/main.rs` loads a seccomp `RuleLoader` after
`PTRACE_TRACEME`). Needs `CAP_SYS_PTRACE` / Yama
`ptrace_scope` that allows tracing children (Linux
`ptrace(2)`). `os::linux::fs::MetadataExt` in `cache_utils.rs` —
Linux-only build. No OverlayFS. Interactive stdin, `/dev/random`,
and clocks are not cached; **networking unimplemented** (README).
Empty-cache overhead: **1.69× mean (hash), worst 2.47×** (thesis).
Unchanged inputs: up to **65× hash / 159× mtime**. 5% files
changed: ~2× hash.

**Hash vs mtime (locked fairness).**
`src/syscalls.rs` documents three `CheckMechanism`s: `DiffFiles`
(strong, slow, fat), `Mtime` (“basic” correctness, fast), `Hash`
(strong, slower, compact). `generate_hash` is **SHA-256**
(`sha2::{Digest, Sha256}`). `condition_generator.rs`:
`const DONT_HASH_FILES: bool = false` — **hash is the default**.
The public CLI (`structopt` in `main.rs`) has **no**
`--mtime`/`--hash` switch; toggling mtime is a **recompile**.
Primary numbered comparison: **SHA-256**. Mtime is a second
binary, reported separately, labeled less sound (thesis Ch. 3.5).

**How it runs on A/B.** Persistent `./cache/` in the job directory
(README). One invocation per genome:
`process_cache -- hmmscan … genome_k.faa`. Do not delete `./cache`
between genomes. HMMER threads (`--cpu 32`) stay inside one
exec-unit (thesis: threads are not skipped separately; BWA is
the worked example).

**Expected behavior (before any run).** Cacheable object is the
**exec-unit** (`execve` → descendant termination). A new FASTA
fails `InputFileHashesMatch` / mtime preconditions → **the whole
HMMER process reruns every genome**. Replay of the identical
FASTA + Pfam-A + argv **should skip** (hash) or skip if mtimes
are untouched (mtime). Pipes collapse into one unit (`cat | wc`
is not split).

**Quality.** **trust** as a design; **provisional as a runnable
CARC package** (no AE README for HPC, ptrace/Yama unknown on
Discovery).

---

## 4. eggNOG-mapper `-m cache`

**Citation.** Cantalapiedra *et al.*, *Mol. Biol. Evol.* 2021
(tool paper). Feature: v2.0.5 release notes (“`-m cache` mode
and `-c FILE` … annotations file with md5 hashes”;
https://github.com/eggnogdb/eggnog-mapper/releases/tag/2.0.5).
Still in `emapper.py` on `master` (2026-09-27):
`-m cache` “skip seed orthologs search and annotate based on
cached results (`-i` and `-c` are required)”; `-c/--cache FILE`
“annotations and md5 hashes of queries”; `--md5` “md5 hash of
each query.” Wiki v2.1.2–v2.1.4:
https://github.com/eggnogdb/eggnog-mapper/wiki/eggNOG-mapper-v2.1.2-to-v2.1.4
**trust** as a shipped feature.

**Current USAGE.md (v3 / eggNOG 7)** documents **core DB ~45 GB**
(annotation ~22 GB + DIAMOND ~23 GB + taxonomy/GO/caches
<0.4 GB) but does **not** spell out `-m cache` in the sections
fetched 2026-09-27. The CLI on `master` still has the mode. If a
v3 checkout drops `-m cache`, **stop** and say the occupation
claim is v2-only; do not invent a replacement.

**Install / data — JOSH MUST APPROVE ~45 GB.**

| Item | Size / constraint | Source |
|------|-------------------|--------|
| Core DBs (`download_eggnog_data.py -y --data_dir`) | **~45 GB** | USAGE.md v3 (GitHub `main`) |
| v2 wiki (older) | ~40 GB `eggnog.db` + ~9 GB Diamond | wiki v2.1.2–2.1.4 |
| Optional MMseqs2 | +~25 GB (v3) / ~11–86 GB (v2 wiki) | same |
| `--dbmem` | **~44 GB RAM** | v2 wiki “Other Requirements” |
| Software | Python ≥3.9 (v3) / ≥3.7 (v2); diamond on PATH | USAGE / wiki |
| OS | Linux typical; not a ptrace tool | docs |

**Do not download the 45 GB tree in this session or any session
without Josh’s written OK.** Disk + CARC quota + egress are his
call. Until approved, eggNOG stays **protocol-only**.

`--resume` is **not** the user memo (USAGE.md: continue a
previous run). Prebuilt `eggnog.db.*.bin` files are **DB indexes**,
not prior user FASTAs (`RELATED_WORK.md` §1.6).

**How it runs on A/B (same FASTAs, different tool).** Sequential
over the locked accessions. Genome 1: `emapper.py -i faa -o g1
--md5 --data_dir $DB --cpu 32` (default `-m diamond`). Each later
genome: `emapper.py -m cache -c acc_so_far.emapper.annotations
-i faa_k -o gk --md5`. Concatenate new annotations into the cache
file after each genome (exact-MD5 hits reused; misses written as
FASTA for a follow-up diamond run — v2.0.5 notes + Galaxy help
on “sequences without annotation”). Do **not** wrap HMMER.

**Expected behavior (before any run).** Per-sequence **exact
amino-acid MD5**. Proteins already in the cache file are
annotated without a new seed search; novel sequences miss and
must be searched. On collection **B** (clonal O157:H7) miss
fraction should fall. On collection **A** (diverse) misses stay
higher. This **is** record-level user memo — for eggNOG only.
It does not produce HMMER tblout and is **not** an ACTS speedup
number.

**Quality.** **trust** (feature). v3 docs lag the CLI.

---

## Discriminating smoke (locked; cheap; run first)

Before any full-collection baseline job:

1. **Capability probe (one exclusive node, ≤2 h wall).** Confirm
   `ptrace` of a child, seccomp-bpf, and (INCR) OverlayFS/`unshare`
   actually work on Discovery. If any fail, that baseline is
   **CARC-blocked** (report; do not silently drop it from the
   paper table).
2. **Two genomes + replay.** For each wrapper: genome 1 (cold),
   genome 2 (new FASTA), then **replay genome 1’s exact path**.
   Expect: genome 2 **reruns**; replay **skips** (Riker /
   ProcessCache hash / INCR). eggNOG: genome 2 should hit some
   MD5s if the two proteomes share exact sequences.

This smoke is enough to defend the grain claim. Full A/B is
only for a paper wall-time table, and is expected to show
**no** whole-command savings vs stock.

---

## CARC plan (jobs **not** submitted)

Same account / node class as savings unless a baseline needs
more RAM:

- Account **`biyik_1165`**, partition `main`, **exclusive**,
  `--cpus-per-task=32`, `--constraint=epyc-7542`.
- Default `--mem=64G`. eggNOG `--dbmem` would need **Josh to
  raise this** (wiki ~44 GB **plus** Diamond + OS).
- HMMER 3.4 + Pfam-A 38.2 as job 12377262 / savings.
- JSON after every genome. MATCH vs stock tblout on the savings
  stock-sample positions only (do not duplicate all stock runs).

### Predicted exclusive-node wall

Stock collection walls use the same N=4,192 stand-in as
`SAVINGS_PROTOCOL.md` (`5.10 h` / `1.05 h` per 6-genome stock
sample):

| Workload | Pred. stock wall |
|----------|------------------|
| A hmmscan ×30 | 5.10 × 30/6 = **25.5 h** |
| A hmmsearch ×30 | 1.05 × 30/6 = **5.25 h** |
| B hmmscan ×40 | 5.10 × 40/6 = **34.0 h** |
| B hmmsearch ×40 | 1.05 × 40/6 = **7.0 h** |
| **Sum (one wrap of all four)** | **71.75 h** |

Whole-command tools are predicted to **pay this every genome**
plus empty-cache / first-run overhead (new FASTA ⇒ miss):

| Wrapper | Overhead source | Pred. wall (all four jobs) | `--time` request (1.5× + 1 h/job, 4 jobs) |
|---------|-----------------|----------------------------|-------------------------------------------|
| ProcessCache SHA-256 | 1.69× mean empty-cache (thesis) | 121 h | **4× 48 h ≈ 192 node-h** (cap per job: A-scan 43.1×1.5+1 ≈ **66 h** → request **72:00:00**) |
| ProcessCache mtime | extra column; same rerun prediction | same order | **do not request until SHA-256 smoke passes** |
| Riker release | 8.8% median full-build (paper; **build**, not HMMER) | ~78 h (use **1.2×** as HMMER tracing pad; not a measured HMMER number) | **4 jobs, ~120 node-h** |
| INCR default | ~2× first-run (paper 101% overhead) | ~144 h | **~220 node-h** |
| INCR + annotations | 43.55% first-run if annotations apply; **predicted not to chunk HMMER** | still ~ stock×1.44 if they only cut tracing | **same 220 until smoke says otherwise** |

Those full-collection numbers are **too large to submit on
speculation.** Pre-registered budget for Josh:

| Phase | What | Requested exclusive node-h | Submit? |
|-------|------|----------------------------|---------|
| **0** | Capability probe (ptrace / OverlayFS / `rkr --help`) | **2** | **No. Ask Josh.** |
| **1** | Discriminating 2-genome + replay × {Riker, PC-hash, INCR-default, INCR-ann} × {A-scan, A-search} (B optional if A smoke is clean) | **16** (1.5× pred. + pad; 8 short jobs × 2 h) | **No. Ask Josh.** |
| **2** | Full A/B under wrappers | **192–220 per wrapper** (table above) | **No until Phase 1 matches the expected rerun/skip pattern.** |
| **eggNOG** | DB download **~45 GB** + A/B diamond/`-m cache` | Disk/quota + **32** node-h (15 min/genome × 70, 1.5× pad; Cantalapiedra minutes-scale, **not** a measured number) | **No until Josh OKs 45 GB.** |

**Josh: approve Phase 0 (2 h) and the 45 GB eggNOG tree
separately. Do not approve Phase 2 on this commit.** Real `N_i`
moves the wall; the 1.5× pad is the slack. Privileged Docker
and `ptrace_scope` are **unknown on Discovery** until Phase 0.

Riker/INCR/ProcessCache **software clones are small** (<1 GB).
eggNOG data is the only ≥1 GB fetch.

---

## Correctness (locked)

- HMMER wrappers: same MATCH as savings on every genome that
  has a stock sample. Fail → STOP that baseline, report.
- Replay skip must still MATCH the stock tblout (not an empty
  file).
- eggNOG: exact-MD5 occupation is checked by counting cache
  hits vs `md5` column, not by HMMER MATCH.
- Do not require byte-identical HMMER tblout.

---

## What this is not

- Not a CARC submit and not a timing run in the commit that
  adds this file.
- Not permission to download eggNOG’s ~45 GB without Josh.
- Not a claim that INCR annotations split HMMER records.
- Not ProcessCache mtime as the fair headline (less sound).
- Not STAR. Not a second ACTS method.

---

## Search trail (this pass)

Scholar + web, 2026-09-27. Queries: Riker ATC 2022 artifact /
`rkr.sh` / GitHub / ptrace seccomp; INCR OSDI 2026
`atlas-brown/incr` / Zenodo 19488802 / OverlayFS privileged
Docker; ProcessCache `upenn-acg` ptrace seccomp SHA-256 mtime
`DONT_HASH_FILES`; eggNOG `-m cache` `-c` `--md5` 45 GB
USAGE.md. Shortlist ≥5 neighbors was already on disk
(`RELATED_WORK.md`). New facts: INCR `INSTRUCTIONS.md` +
`--privileged`; ProcessCache default **hash** via
`DONT_HASH_FILES = false` and SHA-256 in `cache_utils.rs`;
eggNOG v3 USAGE **~45 GB** explicit; Riker GitHub→Codeberg
note; Zenodo 19488802 **403** from this network.

---

## Requests for other agents

- **Savings / CARC agent:** do not `sbatch` baseline jobs. Share
  hostname/`lscpu` from savings so Phase 1 can request the same
  constraint. Confirm whether Discovery allows `ptrace`, user
  namespaces, OverlayFS, and `--privileged` Docker.
- **HMMER / inference agent:** keep tblout MATCH and argv
  templates unchanged; baselines consume them.
- **Related-work agent:** if INCR Zenodo 403 persists, say
  “GitHub live, Zenodo unverified” rather than dropping the cite.
- **Do not** implement wrappers in this commit. Protocol only.

---

## Addendum 2026-10-09 — host capability (smoke walls not measured)

Written after the build and the ptrace-ABI probe, before any
wrapper timing. Locked sections above are unchanged. No number
below is a genome wall. `results/baseline_smoke.json` does not
exist yet, so the rerun/skip falsifier is **not** decided.

### What was measured

Build report: `results/baseline_build.json`, job **12865942**,
debug node `d05-41`, xeon-4116, not exclusive, not epyc-7542.
Git sidecar `2791df5`. HMMER 3.4 binaries are installed.
ProcessCache SHA-256 commit `a89d132` linked (unmodified
`CheckMechanism::Hash`). ProcessCache mtime binary linked and
**not** submitted. INCR commit `4b8e5dd` built; `STATELESS_COMMANDS`
is empty. Probes on that node: ptrace ok, seccomp-bpf ok,
user-namespace unshare ok, OverlayFS ok, strace 5.18, `ptrace_scope`
0. Docker is absent (exit 127). mergerfs is absent (exit 1).
INCR's native path is the one the queued jobs will run.

Riker did not link. `g++ -D_GNU_SOURCE` still stops in
`src/rkr/tracing/Thread.cc:95`: `struct __ptrace_syscall_info`
is an incomplete type. glibc 2.28 does not declare it. The job's
commit file is empty because `git rev-parse` is written only
after `make` succeeds. Codeberg HEAD observed via the API on
this date is `bae684b455a4` (2026-09-04); that is an API
observation, not a line in the build JSON.

ABI probe: `results/baseline_ptrace_abi.json`, job **12866431**,
same node. `ptrace(PTRACE_GET_SYSCALL_INFO /* 0x420e */)` returned
`rc=-1 errno=5` (EIO). Installed headers jump from `0x420d` to
`0x420f`. A header shim would not make the release run. No older
Riker was substituted.

### What is queued, and what is not

Pending on `main`, `--constraint=xeon-4116`, 8 cpus, 48G,
1-20:00:00, not exclusive: **12866390** ProcessCache SHA-256,
**12866391** INCR default, **12866392** INCR `--enable_annotations`.
At submit, `squeue --start` was N/A, reason Priority, priority
3222, and `squeue -p main -t PENDING` counted 1849 jobs. No
xeon-4116 was idle. Debug's 1 hour limit cannot hold an HMMER
smoke, so these stay on main.

Not submitted: Riker smoke, ProcessCache mtime smoke, eggNOG,
full collection A (30) or B (40).

### Projection and recommendation

Genome-2 wall is unmeasured, so this addendum does **not**
compute `n_genomes * T_genome2_s / 3600`. That formula is the
one to apply after a genome-2 **RERUN**, on this shared
xeon-4116 allocation, with the assumptions stated in the harness
(later genomes cost the same as genome 2; proteome size is not
scaled; this is not the locked exclusive epyc-7542 table).

The smoke has not decided the falsifier. Riker's missing run
is a host limit, not evidence about whole-command reuse.
Exclusive Phase 2 node-hours are not worth buying until
12866390, 12866391, and 12866392 finish and show genome 2
RERUN and the replay SKIP. Josh decides. A Riker release run
needs a kernel that accepts request `0x420e`.

---

## Addendum 2026-10-09 — Riker behavioral falsifier in Docker (pre-registered)

Written after the host-capability addendum above, and **before**
any container ptrace probe, Riker build, or HMMER command.
Locked sections above are unchanged. This addendum decides
only whether Riker **re-executes** `hmmscan` / `hmmsearch`,
and whether the tblout **MATCH**es a stock run of the same
argv. It is not a timing measurement. No Docker wall time
enters a cost.

### Environment (characterized, not a falsifier result)

Docker Desktop engine **29.4.1**. The Linux VM kernel, from
`docker info` and from `uname -a` inside the image below, is
`6.12.76-linuxkit` (`#1 SMP Fri Apr 17 14:56:37 UTC 2026`),
`aarch64`. `nproc` in that VM is 14. Image:
`ubuntu:22.04.5` (`docker.io/library/ubuntu:22.04`),
platform `linux/arm64`, digest
`sha256:5ec03bb3441e8b0bf3b4f9cd4629a1ae763010dc3035bb8da3ae6cf026486401`.
Every container is started with `--platform linux/arm64` and
`--cap-add SYS_PTRACE`. Seccomp stays the **default** Docker
profile. That profile allowlists the `ptrace` syscall, with
no request-argument filter, once `CAP_SYS_PTRACE` is present
(moby `profiles/seccomp/default.json`, kernels ≥ 4.8). This
run does **not** pass `seccomp=unconfined` and does **not**
pass `--privileged`.

The probe is the same program as
`pipeline/jobs/baseline_ptrace_abi.job`: child
`PTRACE_TRACEME`, stop, parent `PTRACE_SYSCALL` until a
syscall-stop, then `ptrace(PTRACE_GET_SYSCALL_INFO /* 0x420e */)`.
Success is `rc != -1` on that syscall-stop. The Discovery
result in `results/baseline_ptrace_abi.json` is the contrast
(`rc=-1 errno=5` on kernel 4.18).

### What is built

Riker commit `bae684b455a4d8fa010fc04b471f5ca9b408f6a8`
(Codeberg `curtsinger/riker`, the HEAD the 2026-10-09 CARC
clone targeted; that job's commit file is empty because
`make` failed before `rev-parse`). Build is `make release`.
The binary is `rkr`. HMMER is 3.4 from
`http://eddylab.org/software/hmmer/hmmer-3.4.tar.gz`,
installed under `/opt/hmmer`. Recipe:
`pipeline/docker/Dockerfile.riker_docker`. Driver:
`pipeline/scripts/riker_docker.py`. README notes ARM64 has
had much less testing than x86_64; the architecture stays
arm64.

### Workload (subset; argv shape unchanged)

Same argv shape as the savings jobs
(`scripts/baseline_smoke.py` `hmmer_argv` /
`scripts/run_hmmer_savings.py` `stock_argv`):

- hmmscan: `hmmscan --cpu 32 --cut_ga --noali --tblout TBL HMM FASTA`
- hmmsearch: `hmmsearch --cpu 32 --noali --tblout TBL -Z 1000000 --domZ 1000000 HMM FASTA`

`--cpu 32` stays even though the VM reports 14 CPUs. That
flag is not used to classify the run.

HMM is not full Pfam-A. It is the model list in
`scripts/repro_savings_desc_stop.py` (`MODELS`). That list
has **73** names. A later docstring calls the same list
"78-model"; the length of `MODELS` is 73, and all 73 `NAME`
lines are present in the local
`pipeline/data/hmmer/Pfam-A.hmm.gz` (418,160,514 bytes,
already on disk, not re-downloaded). The subset is streamed
out of that gzip. No download ≥ 1 GB.

Collection A, `orderings[0]`, seed 20260926, the two
accessions already named in `scripts/baseline_smoke.py`:

| Step | Accession | Proteins in the file | Kept |
|------|-----------|----------------------|------|
| genome 1 | `GCF_002853805.1` | 5117 | first **300** records, file order |
| genome 2 | `GCF_002090355.1` | 4091 | first **300** records, file order |

The prefix is the original FASTA text
(`acts.fasta.copy_fasta_head`), not a rewritten FASTA.
300 is the fixed local-subset count already used for a
small collection-A extract. One working directory per mode.
`.rkr` is kept across the three steps of that mode. The
`Rikerfile` is one line, the stock argv, absolute paths.
It is not marked executable, so `rkr` runs it with `/bin/sh`
(`src/rkr-launch/launch.c`).

### Prediction (copied from the locked Riker section)

Riker's grain is one command. Genome 2's FASTA is a file
Riker has not seen, so that command's dependencies moved
and genome 2 is a **full re-execution**. A second `rkr`
invocation on genome 2's exact `Rikerfile` bytes, with the
FASTA, the HMM subset, the pressed HMMER indexes, and the
`rkr` binary unchanged, **should skip**.

The locked smoke paragraph says the replay is genome 1's
path. This run replays **genome 2**. The prediction being
tested is the locked sentence "replay of the same FASTA
path … should skip," applied to genome 2. Genome 1 is the
cold start. The falsifier for "whole-command is enough"
fires only if genome 2 **skips**.

### How executed / skipped is read

`rkr --show` (the README's documented flag) prints a
command only when that command `mustRun()`
(`src/rkr/runtime/Build.cc`). The printed line starts
with the executable's basename (`getShortName`).

- **executed** — stdout has a line whose first field is
  `hmmscan` or `hmmsearch` (the mode's binary).
- **skipped** — `rkr` exits 0 and no such line appears.
- **unresolved** — any other exit, or no parseable trace.

Wall time is not an input to this rule. MATCH uses
`scripts/baseline_match.py`: hmmscan is order plus
`split()`; hmmsearch fixed-Z is multiset plus `split()`.
The stock tblout is a run of the **same** HMMER 3.4
binary on this same 300-protein / 73-model argv, not the
full-Pfam savings tables. Replay skip must still MATCH
and the body must be non-empty.

### Projected cost on the real workload (formula only)

Apply this only in the outcome addendum, and only for a
mode whose genome 2 trace is **executed**. It is not
computed from the container.

`T_riker = (T_sample / 6) * (1 + 0.088)` hours per genome.

`T_sample` is the locked stand-in in the table above:
**5.10 h** per 6 genomes for hmmscan, **1.05 h** per 6
genomes for hmmsearch. `0.088` is the median full-build
overhead Riker reports for 14 software packages
(Curtsinger and Barowy, USENIX ATC 2022, abstract and
Figure 3: "median overhead of 8.8%"). That figure is a
**build** overhead, not a measured HMMER overhead.
Transferring it to HMMER is an assumption. The locked
table's **1.2×** pad is a different number (job-time
slack) and is not this projection.

Assumptions, if genome 2 executed: every later genome is
also a new FASTA, so the replay skip does not apply
across the collection; proteome size stays the locked
stand-in and is not scaled to 300 proteins; this is not
a Docker timing. Collection totals are `n * T_riker`
with `n = 30` (A) and `n = 40` (B). If genome 2 skipped,
the falsifier fired and this projection is not the
paper cost.

### Compiler (after the clang failure, before the probe)

The first `make release` in this image uses the Makefile's
default `clang++`. It stopped in `src/rkr/util/log.hh`:
`no type named 'source_location' in namespace 'std'`.
Ubuntu 22.04's clang is too old for this commit's C++20.
No ptrace probe and no HMMER command ran in that attempt.
The rebuild, still before the probe, uses the invocation
already written in `pipeline/jobs/baseline_build.job`:

`make release CC=gcc CXX="g++ -D_GNU_SOURCE"`

Same commit. Same `make release` target. `_GNU_SOURCE` is
what exposes `struct __ptrace_syscall_info` in glibc.

That g++ is Ubuntu 11.4.0. It rejects
`AccessFlags::operator+` as a hard error (`call to
non-'constexpr' function`). `-fpermissive` does not
downgrade it. `g++-12` 12.3.0 fails the same way. No
ptrace probe and no HMMER command ran.

Ubuntu clang 15.0.7 accepts `std::source_location`. It
prints the same `[-Winvalid-constexpr]` diagnostic the
CARC log shows as a warning, except clang 15 makes that
diagnostic an error. The release build passes
`-Wno-error=invalid-constexpr`, which restores the
warning, and does not edit Riker. Still before the probe:

`make release CC=clang-15 CXX="clang++-15 -Wno-error=invalid-constexpr -fuse-ld=lld"`
