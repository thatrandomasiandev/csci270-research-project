# Fourth-tool screen (pre-registered) — 2026-09-27

Written **before** any fourth-tool timing run. Do not edit the locked
sections after seeing `results/fourth_screen.json`.

This is the screen for the top two from `docs/FOURTH_TOOL.md`.
It measures stock `t = a + b·n` in the tool’s **best** mode, then
applies the corrected ceiling. No ACTS cache is built. No speedup
is claimed. A tool that fails does not get a wrapper.

Survey: `docs/FOURTH_TOOL.md`. Method: `docs/HEADLINE_CANDIDATES.md`
and `docs/HEADLINE_SCREEN.md`. Predecessor formula: `docs/TOOL_SCREEN.md`
(commit `c51ed61`) and its 2026-09-25 erratum.

No timing, no CARC job, and no fetch over 1 GB in the session that
wrote this file.

---

## Advance rule (locked — corrected)

For miss fraction `m` (records still sent to the tool on the later run):

```
ceiling(m) = (a + b·N) / (a + b·m·N + w)
saved(m)   = (a + b·N) − (a + b·m·N + w)
```

- `a`, `b` from OLS on the per-size **mean** wall times (same estimator as
  `snpeff_timing_fit.json`).
- `w` is wrapper overhead, **measured**, not omitted (ruff failure mode).
- `m` is the **measured** exact-record miss fraction on the locked later
  input, not a hoped-for 0.2.

**A tool advances only if all of these hold:**

1. `a > 0` and `b > 0` (linear model did not fail).
2. `ceiling(m) ≥ 3.0`.
3. `saved(m) ≥ 60` seconds.

Wall time is the rule. User+sys CPU is logged, not the rule.

If `m ≥ 1/3`, `ceiling(m)` cannot reach 3 even at `a = w = 0`. Report that
as `REFUSE_M` and stop; do not loosen the gate.

Baseline is the tool’s **best** documented mode (built-in lookup/cache
**on** if it has one). Do not pass `--disable-cache`, `--no-cache`,
`--disable-precalc`, or an equivalent strawman. Whisper weights already
on disk count as cache-on. Mordred has no user-result switch to flip.

---

## Design (all tools that run)

- **Machine:** one exclusive node (later session). Record `hostname`,
  `lscpu` model, `nproc`, `uptime` before every timed run. This
  protocol does **not** name a CARC job or start one.
- **Random subsets, not prefixes.** One subset per `n`, reused for the
  3 runs at that size. Seed **20260927**.
- 3 runs each. Outputs under `/tmp/acts_fourth_screen/` (not the repo,
  not Drive).
- `resource.getrusage(RUSAGE_CHILDREN)` user+sys CPU per run, alongside
  `perf_counter` wall.
- One process / one GPU if the tool’s best mode documents GPU. Lock
  `--device` (Whisper) to `cuda` if `torch.cuda.is_available()` else
  `cpu`, and write that string into the JSON. Do not mix devices
  across sizes.
- **`w`:** same input at full `N`, tool binary replaced by a no-op that
  writes empty-but-valid output of the same format (empty TSV header,
  or empty per-file TSV directory). 3 runs. `w` = mean wall.

Sizes, omitting any `n > N`:

| Tool | Sizes |
|------|-------|
| Whisper | `{1, 20, 80, 320, N}` files |
| Mordred | `{1, 200, 1000, 5000, N}` molecules |

---

## Recurrence inputs (locked)

### Audio (Whisper)

LibriSpeech eval tarballs only ([OpenSLR 12](https://openslr.org/12);
Panayotov *et al.*, ICASSP 2015):

| Role | Archive | Compressed size |
|------|---------|-----------------|
| pool A | [test-clean.tar.gz](https://openslr.org/resources/12/test-clean.tar.gz) | 346 M |
| pool B | [test-other.tar.gz](https://openslr.org/resources/12/test-other.tar.gz) | 328 M |

Total **674 M**. No Josh approval. Do **not** fetch `train-clean-100`
(6.3 G) or larger.

Pool = all `*.flac` under both trees after extract, sorted by relative
path. Record key = SHA256 of the file bytes.

LibriSpeech splits are speaker-disjoint. Using test-clean as “prev”
and test-other as “later” would give **m = 1** (`REFUSE_M`). The
locked growing-archive split of the **union** is:

| Role | Slice of the sorted pool |
|------|--------------------------|
| prev A | first 40% of files |
| prev B | next 40% of files (40–80%) |
| later  | last 80% of files (20–100%) |

Then `A ∪ B` = first 80%, and later minus that set = last 20% of the
pool, so **expected m = 0.25** if later is the 80% slice. The screen
**measures** `m` from hashes; do not hard-code 0.25 in the gate.

Optional diagnostic (not the gate): Common Voice English `validated.tsv`
path overlap across two releases (Ardila *et al.*, LREC 2020). Metadata
only is small; full English audio is many GB — do not fetch it here.

### Molecules (Mordred)

ChEMBL chemical representations (SMILES + InChI + InChIKey):

| Role | File | Notes |
|------|------|-------|
| prev keys | [chembl_32_chemreps.txt.gz](https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_32/chembl_32_chemreps.txt.gz) | InChIKey set only; do not run Mordred on all of 32 |
| later pool | [chembl_33_chemreps.txt.gz](https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_33/chembl_33_chemreps.txt.gz) | Zdrazil *et al.*, *NAR* 2024; release notes: 2,399,743 compounds |

Each `chemreps` file is well under 1 GB. No Josh approval.

Record key = Standard InChIKey (Gaulton *et al.*, *NAR* 2012).
`N` = **20,000** molecules drawn from 33 with seed 20260927 (or all
rows if 33 has fewer after dropping empty SMILES — it will not).
`m` = fraction of those N InChIKeys that are **not** in the 32 key
set. Expected **m ≈ 0.019** if 33 is almost a superset
(2,354,965 → 2,399,743); withdrawals make this an estimate.

If measured `m ≥ 1/3`, `REFUSE_M`. If OLS `b` is so small that
`saved(m) < 60` at this N, the tool does not advance (ruff-class).
Do not silently raise N above 20,000 in the same JSON.

---

## Candidates

### 1. OpenAI Whisper CLI — run after small fetch

**Best mode (locked):**

```
whisper FILE [FILE ...] \
  --model small \
  --model_dir "$WHISPER_CACHE" \
  --device "$DEVICE" \
  --temperature 0 \
  --output_dir OUTDIR \
  --output_format tsv \
  --verbose False
```

- `--model small` is the heaviest official checkpoint **under 1 GB**
  (`small.pt` ~466 MB; README relative speed ~4× vs `large`).
  Default `turbo` is ~1.6 GB — **do not use** without Josh.
  `tiny` / `tiny.en` is a speed strawman — **do not use**.
- Weights already in `$WHISPER_CACHE` (default `~/.cache/whisper`)
  stay on. First timed run may download `small.pt` once; that
  download is not part of `b`.
- `$DEVICE` = `cuda` if available else `cpu`. Record it.
- `--temperature 0` is greedy decode (stock default). This screen
  still does **not** claim MATCH.

N = number of flac files in the locked later slice.

**Install (no >1 GB file):**

```
# later session — not this one
python3 -m pip install -U openai-whisper   # pulls torch; if the wheel
                                           # plus small.pt would exceed
                                           # policy, stop and ask Josh
# fetch the two OpenSLR tarballs (346 M + 328 M)
```

PyTorch wheels can exceed 1 GB on some platforms. If the installer
would pull a >1 GB artifact, **stop and ask Josh**. Do not fetch
`medium` / `turbo` / `large`.

**Expected (not a claim):** `a` = model load; `b·N` = minutes on GPU
or hours on CPU for ~8 h of later-slice audio; constructed `m ≈ 0.25`;
`ceiling` can pass 3× if `m < 1/3` and `w` is small. **New FORMAT:**
directory of per-file TSV, key = SHA256(audio).

### 2. Mordred CLI — run after small fetch

**Best mode (locked):**

```
python3 -m mordred -t smi -p "$NPROC" -q -o OUT.csv INPUT.smi
```

2D descriptors (no `-3`). `-p` = `nproc` on the exclusive node.
No user-result flag exists; do not invent one.

INPUT.smi is the locked N-slice of ChEMBL 33 (canonical SMILES, one
per line, no blank lines). N = 20,000.

**Install (no >1 GB file):**

```
# later session — not this one
conda install -c conda-forge rdkit
python3 -m pip install mordred
# curl the two chemreps .gz listed above
```

**Expected (not a claim):** Moriwaki *J. Cheminform.* 2018 — all
descriptors of maitotoxin ~1.2 s; several classes >0.1 s/mol.
Drug-like 2D-all **estimate** 0.05–0.5 s/mol so `b·N` is minutes at
N=20k. If measured `b` is a few milliseconds, `saved` fails and
Mordred does not advance. `m` from 32 keys, hoped `≪ 1/3`.

---

## Approval checklist (do not fetch until a later session)

| Item | Size | Needed for | Ask Josh? |
|------|------|------------|-----------|
| LibriSpeech test-clean + test-other | 346+328 M | Whisper | no |
| Whisper `small.pt` | ~466 MB | Whisper | no |
| PyTorch wheel | may be **>1 GB** | Whisper | **yes if the wheel is >1 GB** |
| Whisper `turbo` / `medium` / `large` | 1.4–2.9 GB | optional heavier | **yes** |
| ChEMBL 32+33 chemreps | tens–low hundreds of MB | Mordred | no |
| Mordred + RDKit | small | Mordred | no |
| OPERA + MATLAB Runtime | **~2–4 GB** | rejected | do not ask |
| Gaia / Nominatim planet / train-clean-100 | many GB | rejected | do not ask |

---

## What this is not

- Not a cached-path MATCH and not a speedup claim.
- Not permission to download anything in this writing session.
- Not a rewrite of `results/tool_screen.json` or `results/headline_screen.json`.
- Not STAR. Not ruff. Not Vina. Not ClamAV `--disable-cache`.
- Not a second tool wrapper. Whisper needs a new FORMAT if it advances;
  Mordred should use the generic table path.

```
# later session, after small fetches / any Josh approval
python3 scripts/run_fourth_screen.py   # does not exist yet; do not write it here
```

Report: `results/fourth_screen.json`.
