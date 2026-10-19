# TARE Table 4 on one x86 node (pre-registered)

Written **2026-10-19, before** the pilot and before any timed run.
This file is the pre-registration for workstream W5x. Locked
sections stay locked after the pilot starts. The pilot addendum
is the only place that may add the stock-body checksum, the
data-row count, and the measured time limit, and it is written
after the pilot and before `sbatch` of the measured job.

Code freeze for every timed run: `1c65571538afcc139af560156147e4276905f9b4`.
The harness is `pipeline/scripts/baselines_x86.py`. It does not
modify `pipeline/acts/`.

Predecessor measurements, not reused as x86 numbers:

- `pipeline/results/baseline_overhead.json` — Riker and INCR
  ratios in an arm64 container (`comparable_to_epyc: false`).
- `pipeline/results/baseline_processcache_amd64.json` — ProcessCache
  could not load a seccomp filter under amd64 emulation.
- `pipeline/results/baseline_build.json` — on Rocky 8, ptrace and
  seccomp-bpf probes succeeded; Riker did not link
  (`struct __ptrace_syscall_info` incomplete in glibc 2.28);
  `PTRACE_GET_SYSCALL_INFO` (0x420e) returned EIO on that kernel
  (`pipeline/results/baseline_ptrace_abi.json`).
- `pipeline/results/exact_replay/headline_carc.json` —
  `first_run_overhead_median` 1.32 on nine full proteomes,
  `--cpu 4`, with `--domtblout`. That is a different workload.

---

## Question (locked)

On one exclusive EPYC 7542 node, for the Table 4 workload, what is
each system's first-run wall relative to stock HMMER, and what does
each system do on an identical rerun and on a new genome?

Systems, one row each: **Riker**, **INCR** (default, no
annotations), **ProcessCache** (SHA-256), **TARE** cache fill.

Primary endpoint, per system: the arithmetic mean of `n=4` paired
ratios `rho = T / T_stock`, with the sample standard deviation and
a two-sided 95% Student `t` interval on `df = 3`
(`t_0.975,3 = 3.1824463052842638`, the constant Table 4's source
line calls `t975_df3`). A ratio is computed only from a pair whose
stock run and system run are both valid. If fewer than 4 valid
pairs exist and the system was not stopped by a kernel restriction,
the row is **INCONCLUSIVE**, not a killed method and not a number
for the table.

## Workload (locked)

Not redrawn. Same proteins and database as
`baseline_overhead.json`:

| Item | Value |
|------|--------|
| Accession | `GCF_002853805.1` |
| Proteins | first 500 records, `copy_fasta_head`, original text |
| FASTA sha256 | `6ab83e19bdfc79bb46d63b69d495a3b41b5dd42c6ba8abf53a0faea17256a3a6` |
| Database | Pfam-A 38.2, all 30,134 models |
| HMM sha256 | `4b0da6399b97d2b23329de82190b2e5705bde1dea4cb2d028a52712d5966739e` |
| Command | `hmmscan --cpu 32 --cut_ga --noali --tblout T HMM FASTA` |

`Locked subset: 30134 models, 500 proteins of GCF_002853805.1.`

The measured run uses this same FASTA. Seed `20261262` is reserved
and is not a redraw. Seed `20261261` labels the pilot only.

If the extracted FASTA sha256 or the HMM sha256 or the model count
disagrees with the table above, the job writes that fact and does
not time anything.

New-genome behavior uses a different file: the first 500 records of
`GCF_002090355.1`, the second accession already in the baseline
smoke. It is not a substitute for the timed workload.

## What is timed (locked)

`hmmpress` is outside the clock. Pressed sidecars
(`.h3m`, `.h3i`, `.h3f`, `.h3p`) are reused. The HMM, the sidecars,
and both FASTA files are copied to `/scratch1/$USER/tare-w5x/`
before the clock. Node `/tmp` is not a Pfam destination.

Each paired first run starts from an empty tool cache and a new
tblout path. The kernel page cache is not flushed. Order is the
control for that: within repeat `r`, systems are rotated by `r`,
and stock and the system alternate which starts the pair.

`T` for Riker, INCR, and ProcessCache is the wrapper wall around
one `hmmscan` of the locked argv. `T` for TARE is the wall of
`python3 -m acts run --strategy reference` on an empty cache with
the explicit pin `-Z {entry_count}`, `--verify audit`, and the same
`hmmscan` flags. The pin is the shipped exact-mode pin. It is not
inferred in this run, so pin-search probes are not inside `T`.
Audit runs only when a later call reuses rows; a cold fill has
nothing reused, so the cold wall is parse, one scan, and the cache
write. TARE does not pass `--domtblout` and does not run `hmmpress`
inside the clock. Those two choices keep `T` on the Table 4 argv.
The headline median used both, on full proteomes, at `--cpu 4`.

Stock `T_stock` is the unpinned argv. TARE's `-Z` can change
E-values, so TARE output is not required to match stock. The ratio
is still fill wall over unpinned stock wall, which is the headline's
definition of first-run overhead.

## Behavior (locked, once per system, not in the mean)

After the cold run whose cache is kept (the pilot's only repeat;
measured repeat 4):

1. **Identical rerun.** Same argv, same paths, the first tblout left
   in place.
2. **New genome.** Same database and a new FASTA path
   (`GCF_002090355.1`, first 500). One stock scan of that FASTA is
   the MATCH reference. It is not a paired ratio.

Predictions, from the 2026-09-27 baseline protocol, before this run:

| System | Identical rerun | New FASTA path |
|--------|-----------------|----------------|
| Riker | SKIP | RERUN |
| INCR default | SKIP | RERUN |
| ProcessCache SHA-256 | SKIP | RERUN |
| TARE | replay, `n_fresh = 0`, decision SHIP | search runs again (`n_fresh > 0`); not a whole-command skip |

A prior arm64 container saw INCR re-execute an identical rerun.
That observation is not this host and is not the prediction.

TARE "replays the changed part" is a reference-side property. This
workload does not change Pfam. The new-genome step records query-side
behavior only. It does not re-measure the nine-genome reference update.

The action label is the `baseline_smoke.judge_step` rule: no wall
rule without proof the scan ran or proof of a replay; a fast exit 0
with an empty table is INVALID. TARE's label is taken from
`decision.txt` (`n_fresh`, `n_entries`, decision), not from that
wall rule.

## Kernel stop (locked)

Riker, INCR, and ProcessCache need `ptrace` and seccomp-bpf. INCR
also needs user-namespace `unshare` and `unshare --root`
(util-linux 2.40). The job probes these on the EPYC node before
any wrapper timing.

If a probe fails, or a run fails with the kernel's refusal
(`Unable to load seccomp`, `PTRACE_GET_SYSCALL_INFO` errno,
`Operation not permitted` on ptrace or unshare), that system is
**BLOCKED**. The JSON keeps the command, the errno or the log tail,
and no ratio. Remaining systems continue. Riker has no binary in
the reused build directory and no source tree there. This job does
not clone and does not rebuild. A missing binary after a passing
probe is BLOCKED with that fact, not a rebuilt substitute.

`EMFILE` or a panic while copying a trace is a failed run, not a
kernel-policy block. Those pairs are invalid. They do not become a
ratio.

## Builds (locked)

Reuse `/project2/biyik_1165/jjt_373/csci270-star/acts-baselines-20261009/`.
Record sha256 of `bin/hmmscan`, `bin/hmmpress`,
`bin/process_cache_sha256`, and `src/incr/target/release/incr`.
Do not rebuild those binaries. ProcessCache is the existing SHA-256
binary (`CheckMechanism::Hash`, `DONT_HASH_FILES` false), commit
`a89d13214d8a0a9527ad4400a0a7284158d952a1` as recorded in
`baseline_build.json`. INCR is commit
`4b8e5ddf8e275d947518c7cc0f5d2713fe992307`, default column
(`INCR_SYS_PATH` unset). `ulimit -n 65536` is set so a low open-file
cap is not the thing under test.

## Controls (locked)

Positive: two stock scans in the pilot, before any wrapper, must be
token-identical (`split()` of data lines, order kept). The
comparator must report the stock body as identical to itself.
Measured stock bodies must match each other and the pilot body
checksum locked in the addendum.

Negative: mutating one E-value token in a copy of the pilot stock
body must be classified `value-only` and not identical. If that
check does not fail the copy, the pilot does not pass.

Power floor, set before seeing the table: a stock body with fewer
than 100 data rows is **INCONCLUSIVE**. The addendum then locks the
pilot's exact row count. A measured stock body with a different
count is **INCONCLUSIVE**.

Wrapper validity: exit 0, tblout header present, data-row count
equal to that pair's stock, and token-identical to that stock.
TARE validity: process exit 0, decision `SHIP`, tblout header
present, data rows at least the power floor. TARE is not required
to match unpinned stock.

Difference classes, when two bodies differ: `value-only`,
`different-row`, `missing`, `extra`, `order`.

## Pilot and measured (locked)

Pilot: seed label `20261261`, one paired repeat, identity stocks,
both controls, behavior once. Disjoint redraw is not available:
the 500 proteins are the locked Table 4 set. The pilot repeat is
not one of the measured four.

Measured: four paired repeats, behavior once on repeat 4, no new
protein draw. Starts only after this file contains the addendum
with the pilot body checksum and the row count.

SLURM, measured job only: `--exclusive --mem=0 --constraint=epyc-7542`,
one node. Time limit = `1.5 × (4 × pilot paired-repeat wall + pilot
behavior wall + 20 minutes)`, rounded up to the next minute. The
paired-repeat wall is the sum of the timed stock and system walls
in the pilot's one repeat. A crash writes the partial JSON already
being updated after every run.

Laptop times are not evidence. The login node is not a compute host.

## Pass, fail, inconclusive (locked)

- **Pilot pass:** identity holds, both comparator controls behave,
  power floor met, checksums match the locked workload, and every
  system is either a valid cold run or BLOCKED with an exact error.
- **Measured row, number:** exactly 4 valid pairs. Report mean,
  sample sd, and the `t` interval.
- **INCONCLUSIVE:** power floor missed, stock bodies disagree, or
  fewer than 4 valid pairs for a reason other than a kernel stop.
- **BLOCKED:** kernel restriction or absent reused binary, with the
  exact error. No imputed ratio.
- **No third redesign.** If the pilot harness fails twice for the
  same reason, record the limitation and stop.
