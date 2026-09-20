# Reproduce the Suite B ≥2× experiment (professor handoff)

This document is the **single entry point** for duplicating the graded STAR bake-off on another machine.

**Public GitHub repo:** [https://github.com/thatrandomasiandev/csci270-star-2x](https://github.com/thatrandomasiandev/csci270-star-2x)

## Figures (Josh’s Mac results — look here first)

Before or after you run the bake-off, browse the locked Suite B plots:

**→ [Figure gallery on GitHub](https://github.com/thatrandomasiandev/csci270-star-2x/tree/main/star/bench/results/figures)**

Quick links:

| Chart | Link |
|-------|------|
| Dashboard (overview) | [00_dashboard.png](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/00_dashboard.png) |
| Stock vs opt wall-clock | [01_suiteB_stock_vs_opt_wall.png](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/01_suiteB_stock_vs_opt_wall.png) |
| Mean speedup vs 2× | [02_suiteB_speedup.png](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/02_suiteB_speedup.png) |
| Every timed pair | [03_suiteB_per_pair_scatter.png](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/03_suiteB_per_pair_scatter.png) |
| min_pair pass board | [04_suiteB_pass_board.png](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/04_suiteB_pass_board.png) |
| Rung ladder (i01) | [05_rung_ladder_i01.png](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/05_rung_ladder_i01.png) |
| Index of all plots | [figures/README.md](https://github.com/thatrandomasiandev/csci270-star-2x/blob/main/star/bench/results/figures/README.md) |

In a local clone the same files live at `star/bench/results/figures/`.

## What will match vs what will not

| Guarantee | On the professor’s computer |
|-----------|-----------------------------|
| Same CLI, threads=1, datasets, indexes, MATCH check | **Yes** — identical protocol |
| Stock vs opt BAM / SJ.out.tab equivalence (`OUTPUT_MATCH`) | **Yes** — algorithmic claim |
| Stock vs opt ≥2× on each of 10 datasets | **Expected** on a modern CPU with jemalloc+PGO; re-check on *his* machine |
| Absolute wall-clock seconds equal to Josh’s Mac table | **No** — different CPU / OS / disk |
| Side-by-side scoreboard layout (CSV + printed table) | **Yes** — same columns as `STATUS.md` |

Zhang fairness: **same machine, same thread count, identical flags** for stock and optimized. Absolute times are machine-local; the claim is the **ratio** and **MATCH**.

## Fastest path (recommended): data package

Josh runs once (from the project repo):

```bash
./star/bench/scripts/package_for_professor.sh ~/Desktop/STAR_suiteB_repro.tar.gz
```

Send `STAR_suiteB_repro.tar.gz` (~300 MB). Professor:

```bash
tar -xzf STAR_suiteB_repro.tar.gz
cd STAR_2x_reproduce
bash RUN_ME.sh
```

That builds stock + optimized STAR from `star-2x-verified.patch`, skips re-download (indexes/FASTQs already in the pack), runs all 10 bake-offs, and prints the scoreboard.

### Dependencies (professor machine)

| Platform | Needs |
|----------|--------|
| macOS | Xcode CLT, [Homebrew](https://brew.sh) `gcc` + `jemalloc`, `samtools`, `python3`, `git` |
| Linux | `g++`, `make`, `zlib` headers, `libjemalloc-dev`, `samtools`, `python3`, `git`, `curl` |

```bash
# macOS
brew install gcc jemalloc samtools

# Debian/Ubuntu
sudo apt-get install -y g++ make zlib1g-dev libjemalloc-dev samtools python3 git curl xxd
```

## Alternate path: clone the public repo + fetch

```bash
git clone https://github.com/thatrandomasiandev/csci270-star-2x.git
cd csci270-star-2x

# 1) Build stock + opt (clones alexdobin/STAR tag 2.7.11b into star/upstream/)
./star/bench/scripts/build_stock_opt.sh

# 2) Download Suite B + build the three locked indexes
STOCK_BIN=./star/src/STAR_stock ./star/bench/scripts/fetch_suiteB.sh

# 3) Full bake-off (or use the one-shot below)
SKIP_BUILD=1 ./star/bench/scripts/reproduce_all.sh
```

One-shot from a clean tree (build + fetch + all 10):

```bash
./star/bench/scripts/reproduce_all.sh
```

## Locked experiment knobs (must not change)

| Knob | Value |
|------|-------|
| STAR tag | `2.7.11b` |
| Patch | `star/src/star-2x-verified.patch` (S1–S8) |
| Threads | `--runThreadN 1` |
| BAM | `SortedByCoordinate`, `--outBAMcompression 0` |
| RAM | `--limitBAMsortRAM 4000000000` |
| Indexes | human chr1 10 Mb `genomeSAindexNbases=10`; fly **2L:1–10 Mb** Nbases=10 overhang 47; nf-core Nbases=7 |
| Runs | ≥3 timed pairs after 1 warmup (`run_bakeoff.sh`) |
| Pass | every timed pair `MATCH` **and** `min_pair ≥ 2.0` |

Only the binary path differs between stock and optimized.

## Outputs to look for

- Per dataset: `star/bench/results/bakeoff_repro_iXX/timings.csv` + `console.txt`
- Summary: `star/bench/results/illumina10_repro.csv`
- Printed scoreboard (same shape as Josh’s Mac table in `STATUS.md`)
- Reference (Josh Mac, for comparison of **ratios** only): `star/bench/results/illumina10_s8j_mac.csv`
- Figures: `star/bench/results/figures/` (or the [GitHub gallery](https://github.com/thatrandomasiandev/csci270-star-2x/tree/main/star/bench/results/figures))

## Optional: match Josh’s Apple Silicon absolute times more closely

Josh’s graded Mac binary used PGO + LTO + jemalloc + `-mcpu=native`. The default `build_stock_opt.sh` uses PGO + LTO + jemalloc **without** `-mcpu=native` so Linux/other Macs build cleanly. To enable native CPU tuning on the professor’s machine:

```bash
NATIVE=1 ./star/bench/scripts/build_stock_opt.sh
```

That still will not reproduce Josh’s exact seconds unless the CPU is the same.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `samtools required` | Install samtools (MATCH check) |
| jemalloc WARN at build | Install jemalloc; rebuild opt — speedup may fall below 2× without it |
| `missing genome` | Unpack the data package, or re-run `fetch_suiteB.sh` |
| Output `DIFF` | Do not change CLI; confirm both binaries are 2.7.11b stock vs patched |
| Speedup &lt; 2× on one ID | Note machine + CSV row; try `NATIVE=1` + confirm jemalloc linked (`otool -L` / `ldd`) |

## Contact artifacts

- Scope lock: `star/docs/SCOPE.md`
- Algorithm: `star/docs/OPTIMIZATION.md`
- Living numbers: `STATUS.md`
- Figures: [gallery](https://github.com/thatrandomasiandev/csci270-star-2x/tree/main/star/bench/results/figures)
