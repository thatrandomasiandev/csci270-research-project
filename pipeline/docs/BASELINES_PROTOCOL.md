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

---

## Addendum 2026-10-09 — Riker Docker outcome

Written after the run. Locked sections are unchanged.
Result: `results/baseline_riker_docker.json`.

### Probe

`ptrace(PTRACE_GET_SYSCALL_INFO /* 0x420e */)` on a
syscall-stop returned **rc=24, errno=0** inside the
container. `uname` is `6.12.76-linuxkit` aarch64.
`/usr/include/linux/ptrace.h` in the image defines
`PTRACE_GET_SYSCALL_INFO` as `0x420e`. Contrast:
`results/baseline_ptrace_abi.json` on Discovery's
4.18 kernel returned `rc=-1 errno=5`. Flags were
`--platform linux/arm64 --cap-add SYS_PTRACE` and the
default seccomp profile.

### Binary

Riker `bae684b455a4d8fa010fc04b471f5ca9b408f6a8`,
`make release`, Ubuntu clang 15.0.7. The ELF is
aarch64 (`/opt/rkr.file` in the JSON). Copying only
that binary to `/usr/local/bin` segfaults in
`Build::launch` (exit 139) because `release/share/rkr`
is not beside it. **POST-HOC:** the recorded steps
invoke `/opt/riker/release/bin/rkr`, the in-tree
release binary. HMMER is 3.4 (Aug 2023). Tarball
sha256 `ca70d94fd0cf271bd7063423aabb116d42de533117343a9b27a65c17ff06fbf3`.

### Behavior

`rkr --show` prints a command only when it must run.
HMMER's own stdout follows that line in the same log
(`stdout_line_count` in the JSON). Both modes:

| Step | Trace | MATCH vs stock on this subset |
|------|--------|-------------------------------|
| genome 1 | **executed** | true, body non-empty |
| genome 2 | **executed** | true, body non-empty |
| replay of genome 2 | **executed** | true, body non-empty |

Genome 2 agrees with the locked prediction. The
falsifier for "whole-command is enough" does **not**
fire: a new FASTA did not skip HMMER.

The replay does **not** agree. Rikerfile sha256, FASTA
sha256, and HMM sha256 are the same on genome 2 and on
the replay (JSON). `rkr --show` still printed
`hmmscan` / `hmmsearch`, and HMMER's stdout followed.
The log does not say why. This note does not supply a
cause.

**POST-HOC harness note.** An earlier sequence wrote
the `--show` log inside the traced directory. That
sequence is not this JSON. The recorded run writes the
log outside that directory. Replay still executed.

### Projected cost (applies)

Genome 2 executed, so the pre-registered formula
applies. **PROJECTED.** Not a container wall time.
Not a measured HMMER tracing overhead. `0.088` is the
paper's median full-build overhead (abstract and
Figure 3), not the locked 1.2× job pad.

| Mode | Per genome | A × 30 | B × 40 |
|------|------------|--------|--------|
| hmmscan | 0.9248 h | 27.744 h | 36.992 h |
| hmmsearch | 0.1904 h | 5.712 h | 7.616 h |

The four collection jobs sum to **78.064 h**
(`71.75 × 1.088`). Assumptions are the ones in the
pre-registration: a new FASTA on every later genome,
stand-in proteome size, no scaling to 300 proteins.
The replay did not skip even an unchanged path, so
this projection is not an overestimate that assumes
only new FASTAs rerun. It is still not an HMMER
measurement of the 8.8%.

## Addendum 2026-10-09 — replay path and one container (pre-registered)

Written before the same-container Riker run and before
the ProcessCache rerun. Locked sections are unchanged.
The 2026-10-09 outcome addendum above stays as the
record of the per-container run.

### Harness audit

`scripts/riker_docker.py` `run_mode` reads `genome2.tbl`
for MATCH. It does not delete, move, truncate, or
rewrite that file between genome 2 and the replay.
Stock tables are `stock_genome1.tbl` and
`stock_genome2.tbl`, written before the Riker steps.

`scripts/baseline_smoke.py`, as run for ProcessCache
SHA-256 on CARC (job 12866390), set `--tblout` to
`{step}.tbl`. The replay command wrote
`hmmsearch/replay.tbl`. Genome 1 wrote
`hmmsearch/genome1.tbl`. ProcessCache's cache directory
on that job holds three command hashes:
`122050252428938832` contains `genome1.tbl`,
`3926956631370802838` contains `genome2.tbl`,
`2586913087825036546` contains `replay.tbl`.
The replay was a different command. Its wall was
5742.928985479055 s (`baseline_smoke_processcache_sha256.json`
on the project path, hmmsearch replay). That number
does not decide an identical-command replay.

The same log's tail is ProcessCache's own panic in
`background_thread_copying_outputs`
(`execution_utils.rs`): several threads copy one
`stdout_<pid>` and the first unlinks it. Cache entries
for those three commands were still written. This
rerun does not patch ProcessCache.

### What Riker named

On the saved `/tmp/acts-riker-docker` database from
the per-container run, `rkr check --log artifact` in a
new container reported one content mismatch per mode.

hmmscan: `/sys/devices/system/cpu/online`, expected
`mtime=1791595235.189925008 cached=false`, observed
`mtime=1791596308.450330009 cached=false`.

hmmsearch: the same path, expected
`mtime=1791595236.931925009 cached=false`, observed
`mtime=1791596465.559226013 cached=false`.

`cat` of that file is `0-13\n`. Three `stat` calls
inside one container, 1.2 s apart, shared mtime
`1791596366.812182903`. A later container had a
different mtime. Riker's fingerprint of an uncached
file is the mtime. The per-step `docker run` is what
changed it. HMMER's `--cpu` path reads the file; the
bytes did not change.

### Predictions for the rerun

Riker, one container, same subset as the Docker
addendum (73 models, first 300 proteins, genome 2's
Rikerfile left untouched on the replay):

| Step | Prediction |
|------|------------|
| genome 1 | executed |
| genome 2 | executed |
| replay | skipped |

`/sys/devices/system/cpu/online` bytes stay `0-13`
and its mtime is the same on all three steps.
Classification is still `rkr --show`. If the replay
prints `hmmscan` or `hmmsearch`, the same-container
`rkr check --log artifact` is the record of whichever
input changed. That result stays specific to the
named input.

ProcessCache SHA-256, CARC, hmmsearch only, fresh
work directory. Replay uses genome 1's argv,
including genome 1's `--tblout`. A copy for MATCH
is taken with `snapshot_output`, which refuses to
return if the source bytes or mtime change.
Prediction: genome 2 reruns; the replay skips under
the locked wall-time rule. hmmscan is omitted:
job 12866390 exited in about 15 s with
`use hmmpress first`, and MATCH was false. Pressing
the shared `Pfam-A.hmm` (2,246,909,846 bytes, no
`.h3m` siblings) would change a file other jobs read.

## Addendum 2026-10-09 — same-container Riker outcome

Written after the run. Result:
`results/baseline_riker_docker_samec.json`.
One container. `cpu_mtime` is `1791596929` on all
six steps. `cpu_bytes` is `0-13`. `rkr check` after
each mode printed `No commands to rerun`.

| Mode | genome 1 | genome 2 | replay | MATCH |
|------|----------|----------|--------|-------|
| hmmscan | executed | executed | **skipped** | true on every step |
| hmmsearch | executed | executed | **skipped** | true on every step |

Replay `--show` logs are empty (0 bytes). Replay
Rikerfile, FASTA, and HMM sha256 match genome 2.
Replay tblout sha256 is unchanged by the comparison
copy (`tblout_unchanged_by_copy` true). Genome 1 and
genome 2 show that flag false because the tblout
was absent before the command and present after it.

The pre-registered prediction holds. The
per-container replay executed because Riker
fingerprinted `/sys/devices/system/cpu/online` by
mtime, and each `docker run` changed that mtime.
With one container the replay skips. A same-command
replay is a skip. A new FASTA still executes, so
the PROJECTED per-genome cost in the Docker outcome
addendum still applies to a later genome.

ProcessCache was not rerun. After the earlier
successful SSH, connections to `10.72.0.13` and
`10.72.0.14` port 22 timed out. The job file is
`pipeline/jobs/riker_docker_pc_replay.job`. Submit
it when Discovery accepts SSH.

## Addendum 2026-10-09 — smoke walls, then a harness that was not running HMMER

Written after jobs **12866390**, **12866391**, and **12866392**
finished on shared `d11-42` (xeon-4116, not exclusive, not
epyc-7542). Git sidecar on those JSONs is `2791df5`. Locked
predictions are unchanged: genome 2 **RERUN**, replay **SKIP**,
annotations do not split FASTA records.

The old harness labeled every non-cold step by wall clock alone.
A 0.13 s exit 0 was therefore a **RERUN** whenever the cold step
was also ~0.15 s, and it would have been a **SKIP** if the cold
step had been a real HMMER run (`classify(0.13, 1200) = SKIP`).
That label is withdrawn. A step is **executed** only with a
non-empty newly written tblout that contains an HMMER banner or
the tblout header. A step is **replayed** only when that tblout
MATCHes stock and the log or the cache shows a restore. Anything
else with no HMMER output is **INVALID**, including exit 0.
`pipeline/tests/test_baseline_smoke.py` locks the 0.13 s empty
case to INVALID, and locks a refusal to start `hmmscan` when
`.h3m/.h3i/.h3f/.h3p` are missing.

### What 12866390–92 measured

| Tool | Mode | Step | Wall (s) | Old label | Re-score | MATCH |
|------|------|------|----------|-----------|----------|-------|
| ProcessCache SHA-256 | hmmsearch | genome 1 | 1200.0182 | COLD | executed | true |
| ProcessCache SHA-256 | hmmsearch | genome 2 | 5473.5058 | RERUN | executed | true |
| ProcessCache SHA-256 | hmmsearch | replay | 5742.9290 | RERUN | executed | true |
| ProcessCache SHA-256 | hmmscan | genome 1 | 15.2937 | COLD | INVALID | false |
| ProcessCache SHA-256 | hmmscan | genome 2 | 15.2388 | RERUN | INVALID | false |
| ProcessCache SHA-256 | hmmscan | replay | 15.2512 | RERUN | INVALID | false |
| INCR default | both | all six | 0.1317–0.1906 | COLD/RERUN | INVALID | false |
| INCR annotations | both | all six | 0.1322–0.1404 | COLD/RERUN | INVALID | false |

JSON: `results/baseline_smoke_processcache_sha256.json`,
`results/baseline_smoke_incr_default.json`,
`results/baseline_smoke_incr_annotations.json`. Re-score is a
reading of those logs under the new rule. It is not a second run.

ProcessCache hmmsearch did run HMMER. Genome 2 agrees with
**RERUN**. Replay does not agree with **SKIP**. The harness
gave replay its own `--tblout` (`replay.tbl`), so the argv was
not genome 1's command. After each run ProcessCache panicked in
`execution_utils.rs` copying `stdout_<pid>` into `./cache/`
(`No such file or directory`). The cache was not stored. Token
MATCH is true on all three hmmsearch tables. Replay's tblout is
4,968,549 bytes against genome 1's 4,968,550; MATCH is token
identity, not bytes. The hmmsearch genome-2 projection in that
JSON applies: `T = 5473.5058 s`, so `30 T / 3600 = 45.61 h` and
`40 T / 3600 = 60.82 h` on this shared xeon-4116, proteome size
not scaled, not the locked epyc-7542 table. The hmmscan
projection in the same file does **not** apply. Those steps
printed `use hmmpress first` and wrote 0 bytes.
`data/Pfam-A.hmm` had no binary auxfiles. The build copied
`hmmscan` and `hmmsearch` and not `hmmpress`.

INCR never executed HMMER. `incr.sh` (commit `4b8e5dd`, the
README command `bash ./src/incr.sh myscript.sh`) calls system
`python3` on `insert.py`. That interpreter has no `libbash`.
`incr.sh` has no `set -e`, so the traceback is discarded, the
script is replaced with an empty file, and bash exits 0. The
same log shows `git rev-parse` failing because the build copied
the tree without `.git`. With `INCR_TOP` set, that git line is
not what skipped HMMER.

### What is queued, and what a debug node already showed

Official reruns, `main`, `--constraint=xeon-4116`, 8 cpus, 48G,
pending Priority at the time of this addendum. Not started, so
they are not in the table above.

| Job | What |
|-----|------|
| **12898906** | ProcessCache SHA-256, hmmsearch only, genome 1's exact argv including `--tblout`. Script is a byte copy of `baseline_smoke.py` at `acts-baselines-20261009/scripts/baseline_smoke_replayfix.py`. |
| **12898907** | ProcessCache SHA-256, hmmscan only. Untimed `hmmpress -f` of the smoke HMM before any step wall. Guard refuses to start hmmscan if the auxfiles are absent. |
| **12898908** | INCR default, both modes. |
| **12899077** | INCR `--enable_annotations`, both modes. |

Before those jobs started, debug node `d05-41` (xeon-4116,
`/usr` is tmpfs) was used to see whether the documented
`incr.sh` can reach HMMER at all:

- Image `unshare` is util-linux **2.32.1** and rejects
  `unshare --root`, which `try.sh` requires. Module
  `util-linux/2.40` provides `--root`. The INCR jobs load it.
- Overlay of tmpfs `/usr` fails (`wrong fs type`). Without
  `/usr`, the sandbox has no `/bin/bash`. The image has no
  mergerfs. Static **mergerfs 2.42.0**
  (`mergerfs-2.42.0-static-linux_amd64.tar.gz`) is installed at
  `acts-baselines-20261009/bin/mergerfs`. `try.sh` autodetects
  it. That is their documented native dependency, not a patch
  to INCR.
- Job **12899318**: `cd` of the NFS checkout inside the sandbox
  returns `Operation not supported`. The smoke therefore runs
  `incr.sh` with cwd on node-local `/tmp`. The FASTA path in
  the script stays on `/project2`. Putting the FASTA on `/tmp`
  would drop it from INCR's dependency set.
- Job **12899342**: `hmmsearch -h` from a `/tmp` copy of the
  binary prints the HMMER 3.4 banner under `incr.sh` (rc 0).
  `wc` of the project-path FASTA from that same traced script
  returns `Operation not supported`. strace cannot stat
  `/project2`. The queued INCR jobs still point HMMER at the
  project-path binary and the project-path FASTA. If they fail
  the same way, those steps are INVALID, not a replay and not
  a genome-2 RERUN.

No whole-command falsifier is revised here. The Docker Riker
result above stands: a new FASTA executes, and a same-container
replay skips. ProcessCache hmmsearch on the host reran on a new
FASTA path, and the replay of a different `--tblout` also reran,
for the argv and cache-store reasons above. hmmscan and both
INCR columns did not run HMMER. Phase 2 is still not submitted.
Job **12898906** is the ProcessCache submit the previous
paragraph was waiting on.

---

## Addendum 2026-10-10 — uniform Docker behavioral smoke (pre-registered)

Written before any container build, ptrace probe, or HMMER
command of this smoke. Locked sections above are unchanged.
This addendum decides behavior and MATCH only. No container
wall time enters a cost.

### Environment

The same Docker Desktop Linux VM the Riker same-container
run used. Record `uname -a` from inside the container in
the result JSON. The expected kernel, from that earlier
run, is `6.12.76-linuxkit`, `aarch64`. Image base:
`ubuntu:22.04` digest
`sha256:5ec03bb3441e8b0bf3b4f9cd4629a1ae763010dc3035bb8da3ae6cf026486401`,
platform `linux/arm64`. Recipe:
`pipeline/docker/Dockerfile.baselines_uniform`. Driver:
`pipeline/scripts/baseline_docker_uniform.py`.

Capabilities are the ones each tool documents, not one
shared privileged flag:

| Column | Invocation | Capabilities |
|--------|------------|--------------|
| Riker | `/opt/riker/release/bin/rkr --show` | `--cap-add SYS_PTRACE`, default seccomp, not `--privileged` |
| ProcessCache SHA-256 | `RUST_LOG=debug /usr/local/bin/process_cache -- <argv>` | same as Riker |
| INCR default | `bash ./src/incr.sh <script> <cache>` from `/opt/incr` | `--privileged`, the README's Docker invocation at `4b8e5dd` |
| INCR annotations | the same, with `INCR_SYS_PATH` set to `incr --enable_annotations` | same privileged invocation |

`RUST_LOG=debug` is the README's documented way to see a
skip. The release binary's skip line is `debug!` and is
otherwise silent. It does not change `DONT_HASH_FILES`.

INCR's `DEBUG` constant stays false. Setting it switches
cache serialization from bincode to JSON
(`src/ops/data.rs`). `DEBUG_LOGS` is changed from
`DEBUG && true` to `true` so the tool's own log can print
`Cache valid:`. That is the only source edit. `rules.rs`
is not edited. `hmmscan` and `hmmsearch` are not added to
any annotation list.

`unshare --root` comes from Ubuntu 22.04's util-linux.
The image build refuses to finish if `unshare --help`
lacks `--root`. `pip3 install -r requirements.txt` is the
README's native install, so `incr.sh`'s `python3` can
import `libbash`. mergerfs is the apt package, the
documented native dependency.

Inputs are copied onto the container's own filesystem
(`/data`) at the start of the container. `/tmp` is not a
FASTA path: INCR's `DYNAMIC_EXCLUDED_PATHS` drops it.
One `docker run` per column holds genome 1, genome 2,
and the replay. `/sys/devices/system/cpu/online` is
recorded on every step. Its bytes are expected to stay
`0-13` and its mtime is expected to stay constant inside
that container.

### Workload

Same subset as the Riker Docker addendum. 73 models from
`scripts/repro_savings_desc_stop.py` `MODELS`, streamed
from the local `Pfam-A.hmm.gz`. No download. `hmmpress -f`
of that subset is untimed and runs once before any step.
The harness refuses to treat a missing `.h3m/.h3i/.h3f/.h3p`
as a run.

Collection A, `orderings[0]`, seed 20260926:

| Step | Accession | Kept |
|------|-----------|------|
| genome 1 | `GCF_002853805.1` | first 300 records, original FASTA text |
| genome 2 | `GCF_002090355.1` | first 300 records, original FASTA text |
| replay | genome 2 again | the same file, the same argv, the same `--tblout` |

argv shape, unchanged:

- hmmscan: `hmmscan --cpu 32 --cut_ga --noali --tblout TBL HMM FASTA`
- hmmsearch: `hmmsearch --cpu 32 --noali --tblout TBL -Z 1000000 --domZ 1000000 HMM FASTA`

`--cpu 32` stays. The VM has 14 CPUs. That flag is not
used to classify the run. Stock HMMER 3.4 of the same
argv writes `stock/<mode>/genomeN.tbl` in the same
container, before the wrapped steps. Both modes run in
that one container. Cache directories are not deleted
between the three steps of a mode.

The replay does not rewrite the Rikerfile, the INCR
`run.sh`, or the tblout. A comparison copy for MATCH is
taken after the step.

### Prediction

Copied from the locked sections. Applied to genome 2,
which is the command the replay repeats.

| Step | Prediction |
|------|------------|
| genome 1 | executed |
| genome 2 | executed |
| replay of genome 2 | replayed (skipped) |

INCR annotations do not split FASTA records. Genome 2
under `--enable_annotations` is still a full HMMER
re-execution. The falsifier for "whole-command is enough"
fires only if genome 2 is replayed.

### How executed / replayed / invalid is read

Wall time is not an input.

- **executed** — the tblout was absent or its content or
  mtime changed, the body is non-empty, the file contains
  an HMMER tblout header (`# hmmscan ::`, `# hmmsearch ::`,
  or `--- full sequence ----`), and the tool did not say
  it replayed.
- **replayed** — the tblout body is non-empty and MATCHes
  the stock table for that genome, and either the tool log
  contains `Skip the execution!` (ProcessCache) or
  `Cache valid:` (INCR), or `rkr --show` exited 0 and did
  not print `hmmscan` / `hmmsearch`.
- **invalid** — anything else, including exit 0 with no
  HMMER table and no replay line. A replay marker whose
  table does not MATCH stock is invalid, not replayed.

An `unshare` failure, a missing binary, or
`ModuleNotFoundError: libbash` is invalid. It is an
environment failure when the wrapper never started, and
it is not described as reuse or as a skip. A ProcessCache
or INCR binary that did not link is
`environment_blocked` on that column. That is not tool
behavior.

MATCH is `scripts/baseline_match.py`: hmmscan is order
plus `split()`; hmmsearch fixed-Z is multiset plus
`split()`.

### Projected cost (formula only; compute after the run)

Apply in the outcome addendum, and only for a mode whose
genome 2 action is **executed**.

`T = (T_sample / 6) * factor` hours per genome.

`T_sample` is **5.10 h** per 6 genomes for hmmscan and
**1.05 h** per 6 genomes for hmmsearch. Collection totals
are `n * T` with `n = 30` (A) and `n = 40` (B).

| Column | factor | Source |
|--------|--------|--------|
| Riker | 1.088 | ATC 2022 abstract and Figure 3, median full-build overhead 8.8% |
| ProcessCache SHA-256 | 1.69 | Shiptoski thesis 2023, mean empty-cache overhead under content hashing |
| INCR default | 2.0105 | OSDI 2026 introduction and §8.5, first-run overhead 101.05% |
| INCR annotations | 1.4355 | OSDI 2026 §8.5, annotated first-run overhead 43.55% |

Each factor is that paper's overhead on its own suite.
Transferring it to HMMER is an assumption. It is not a
container timing and not the locked 1.2× job pad. If
genome 2 is replayed, the falsifier fired and this
projection is not the paper cost. The annotations factor
does not mean records were split; the split prediction
is the behavior row above.

---

## Addendum 2026-10-10 — CARC reruns are environment failures

Written after copying the files below through `discovery`,
and before the uniform Docker smoke. Locked sections are
unchanged. None of these rows is tool behavior. A step
that did not provably run HMMER is INVALID. A step whose
wrapper could not start, or whose inputs were unreadable
because another job was pressing the shared HMM, is
ENVIRONMENT-BLOCKED.

`sacct` at the copy: kernel on the finished hosts is
`4.18.0-553.126.1.el8_10.x86_64`.

### INCR 12898908 and 12899077

Both FAILED, exit 1, elapsed 4 seconds. Logs:
`pipeline/results/baseline_carc_logs/incr_def_rerun-12898908.err`
and `incr_ann_rerun-12899077.err`. The stderr line is:

`unshare has no --root; incr.sh cannot start. Load util-linux/2.40. System unshare is 2.32.1.`

No result JSON was written (the stdout names
`baseline_smoke_incr_default_rerun.json` and
`baseline_smoke_incr_annotations_rerun.json`; those paths
are absent from the results directory). The module reload
printed in the same stderr is `python/3.11.9` only. The
`util-linux/2.40` load from commit `af4d0b6` did not take
effect inside the job. HMMER did not start. This is not a
skip and not a genome-2 rerun.

The earlier smokes 12866391 and 12866392 stay INVALID for
the reason already recorded: `incr.sh` called a `python3`
that could not import `libbash`, the script has no
`set -e`, and it exited 0 with an empty output.

### ProcessCache SHA-256 replay 12898906

Result:
`pipeline/results/baseline_riker_docker_pc_replay.json`.
Host `d05-30`, job elapsed 02:10:52, git sidecar
`6913af6`. hmmsearch only.

| Step | Wall (s) | tblout bytes | Status in the file | MATCH |
|------|----------|--------------|--------------------|-------|
| genome 1 | 17.15200762497261 | 0 | INVALID | false |
| genome 2 | 20.850172620033845 | 0 | INVALID | false |
| replay | 7809.07001763396 | 4968570 | executed, action AMBIGUOUS | true |

Genome 1 and genome 2 did not run a search. The log tail
is HMMER's open error: `File format problem in trying to
open HMM file .../data/Pfam-A.hmm. Opened .../Pfam-A.hmm.h3m,
a pressed HMM file; but format of` (the tail is cut there).
`log_shows_hmmer` is false and `log_says_replay` is false.
Job 12898907 started at the same second
(`2026-10-10T02:07:11`) and its untimed `hmmpress -f` of
that same `Pfam-A.hmm` is in
`baseline_smoke_processcache_sha256_hmmscan.json`
(`setup_hmmpress.wall_s` 51.54596920800395, exit 0). The
format error is that shared press, not a cache decision.

The replay's argv matches genome 1, including `--tblout`.
`log_says_replay` is false. `cache_unchanged` is false.
The log tail is the `execution_utils.rs:37` panic copying
`stdout_<pid>` (`No such file or directory`). The cache
was not stored. `projection.applies` is false. The 20.85 s
figure is the format-error exit, not a genome cost, and
it is not used below.

### ProcessCache hmmscan 12898907, still running

`sacct` state RUNNING, elapsed 11:40:02, at the copy.
The results file on disk is a partial snapshot,
`pipeline/results/baseline_smoke_processcache_sha256_hmmscan.json`,
`finished_utc` `2026-10-10T18:35:57Z`, host `d06-27`.
It contains genome 1 only. Untimed `hmmpress` had already
exited 0 and the four auxfiles were present. Genome 1's
row: wall 34054.85725250002 s, tblout 352256 bytes,
`log_shows_hmmer` true, `match` false, exit code 1. The
log tail is the same `stdout_<pid>` copy panic, then
`Unable to creat file. Error code: -24` (EMFILE) in
`redirection.rs`. Genome 2 and the replay are not in the
file. This is not a finished smoke and not a reuse result.

No whole-command falsifier is revised from these jobs.
The Docker smoke pre-registered above is the one that
decides behavior.

A later read-only `sacct` through `discovery`, after the
Docker measurement below, still showed 12898907 RUNNING,
elapsed 11:52:07. The job was not cancelled and the
partial JSON was not copied again.

---

## Addendum 2026-10-10 — uniform Docker behavioral outcome

Written after the run. Locked sections and the
pre-registration above are unchanged. The classification
rule was not edited after the result.

The recorded measurement is
`pipeline/results/baseline_docker_uniform.json`, produced
by `pipeline/scripts/baseline_docker_uniform.py` at git
`cd5fa72ec9e7f90010242b4a2ce737fc0f920f86`. `git_dirty` is
true in that file because an untracked copy of the same
JSON, from a superseded pass, was already on disk. That
pass used `stat -c %Y.%N`. GNU stat's `%N` is the quoted
file name, so a rewrite in the same second with identical
bytes was invisible. Commit `cd5fa72` switches the probe
to `stat -c %y` (seconds and nanoseconds) and gives each
INCR column its own debug-log copy. The rule
"content or mtime changed" is the pre-registered one.
The JSON below is the run after that fix.

Host: `Joshuas-MacBook-Pro-3.local`, Darwin 27.0.0 arm64,
Python 3.11.9. Inside every container: Linux
`6.12.76-linuxkit`, aarch64, Ubuntu util-linux 2.37.2
(`unshare --root` present), Python 3.10.12, HMMER 3.4
(Aug 2023). ptrace request `0x420e` returned `rc=24`,
`errno=0` in every column. `/sys/devices/system/cpu/online`
bytes stayed `0-13`. Its mtime is one value per container
(Riker `1791665789`, INCR default `1791665794`, INCR
annotations `1791665802`), constant across the six steps
of that container. Image `acts-baselines-uniform:local`.
Pins: Riker `bae684b455a4d8fa010fc04b471f5ca9b408f6a8`,
ProcessCache `a89d13214d8a0a9527ad4400a0a7284158d952a1`,
INCR `4b8e5ddf8e275d947518c7cc0f5d2713fe992307`. The only
INCR source change is `/opt/incr.diff`: `DEBUG_LOGS`
from `DEBUG && true` to `true`. `DEBUG` stays false.
`rules.rs` was not edited.

Workload in the JSON: 73 models, SHA-256
`dac6c8da1198e079caf549e1212ced608ea05197e562ee9661327b71e0029738`,
first 300 proteins of `GCF_002853805.1` and
`GCF_002090355.1`. `hmmpress` exited 0 before the steps
(`ACTS_PRESSED` 0). MATCH is true on every row that has
a table.

Container elapsed time is not a cost. The subset is 73
models by 300 proteins, and a stock hmmsearch on it
prints `Elapsed: 00:00:00.00`.

### Behavior

| Column | Mode | genome 1 | genome 2 | replay | MATCH | falsifier |
|--------|------|----------|----------|--------|-------|-----------|
| Riker | hmmscan | executed | executed | replayed | true | did not fire |
| Riker | hmmsearch | executed | executed | replayed | true | did not fire |
| ProcessCache SHA-256 | both | — | — | — | — | not run |
| INCR default | hmmscan | executed | executed | executed | true | did not fire |
| INCR default | hmmsearch | executed | executed | executed | true | did not fire |
| INCR annotations | hmmscan | executed | executed | executed | true | did not fire |
| INCR annotations | hmmsearch | executed | executed | executed | true | did not fire |

Riker proof. Genome 1 and genome 2 tblouts were newly
written and contain the HMMER header. The replay's
`rkr --show` output is empty (0 bytes) and exit 0, and
the genome 2 tblout mtime is unchanged at nanosecond
resolution (`2026-10-10 20:56:32.434178008 +0000` for
hmmscan, `2026-10-10 20:56:32.878178008 +0000` for
hmmsearch). That is a skip. Genome 2 executed, so the
whole-command falsifier did not fire.

ProcessCache did not run. `cargo build --release` of
`a89d132` failed: `could not compile process_cache due
to 76 previous errors`. `src/regs.rs` names x86_64
`user_regs_struct` fields (`gs_base`, `ds`, and the
rest of that struct). The aarch64 struct's fields are
`regs`, `sp`, `pc`, `pstate`. `/opt/ProcessCache.build`
is `FAILED`. The column's `binary_missing` is true and
both modes have zero steps. This is an environment
block on this arm64 image. It is not a cache hit, a
miss, or a skip. `regs.rs` was not patched.

INCR proof, both columns. Genome 2's tblout was newly
written and MATCHes stock, so genome 2 executed and the
falsifier did not fire. The replay's tblout mtime also
changed (default hmmscan
`20:56:39.312178011` to `20:56:41.049178012`; the other
three replays move the same way) and the body still
MATCHes, so the replay executed. The tool's own log has
no `Cache valid:` line. Each of the six steps is
`Cache invalid:` on the full `hmmscan` or `hmmsearch`
argv, including the replay, which repeats genome 2's
argv and the same stdin hash `3244421341483603138`.
The logs are
`pipeline/results/baseline_docker_uniform_incr_default_debug.txt`
and
`pipeline/results/baseline_docker_uniform_incr_annotations_debug.txt`.
One line per step, the whole command, so annotations
did not split FASTA records. `STATELESS_COMMANDS` was
not edited. Why INCR's dependency check rejects the
identical command is not established here; the log
states the decision and the new mtime shows HMMER wrote
the table again.

### Projected cost

PROJECTED, not timed. Applied only where genome 2's
action is executed. Formula, from the pre-registration:
`T = (T_sample / 6) * factor` hours per genome, then
`n * T` with `n = 30` (A) and `n = 40` (B). `T_sample`
is 5.10 h / 6 genomes (hmmscan) and 1.05 h / 6
(hmmsearch). The four-job sum is hmmscan A + hmmscan B
+ hmmsearch A + hmmsearch B. The stock stand-in for
that sum is 71.75 h. Each factor is the tool paper's
overhead on its own suite, transferred to HMMER as an
assumption. Proteome size is not scaled to 300
proteins. These are not container timings and not the
locked 1.2× job pad.

| Column | factor | hmmscan h/genome | hmmsearch h/genome | A scan | B scan | A search | B search | four-job h |
|--------|--------|------------------|--------------------|--------|--------|----------|----------|------------|
| Riker | 1.088 | 0.9248 | 0.1904 | 27.744 | 36.992 | 5.712 | 7.616 | 78.064 |
| INCR default | 2.0105 | 1.708925 | 0.3518375 | 51.26775 | 68.357 | 10.555125 | 14.0735 | 144.253375 |
| INCR annotations | 1.4355 | 1.220175 | 0.2512125 | 36.60525 | 48.807 | 7.536375 | 10.0485 | 102.997125 |

Sources, already named in the pre-registration: Riker,
Curtsinger and Barowy, USENIX ATC 2022, abstract and
Figure 3, median full-build overhead 8.8%. INCR default,
Xie, Lamprou, Xia, and Vasilakis, USENIX OSDI 2026,
introduction and §8.5, first-run overhead 101.05%
(Figure 5 mean first-run ratio 2.01×). INCR
annotations, the same section, annotated first-run
overhead 43.55%. The annotations factor is that
overhead. It is not evidence that records were split;
the behavior table says they were not.

ProcessCache's factor 1.69 (Shiptoski, University of
Pennsylvania, 2023, mean empty-cache overhead under
content hashing) is not applied. Genome 2 did not
execute, because the binary was not produced. The
four-job figure 121.2575 h stays a formula in the
harness and is not a result of this run.
