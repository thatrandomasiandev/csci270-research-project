# Fourth-tool survey — record memoization outside proteins/variants (2026-09-27)

Research and pre-registration only. No installs, no timing runs, no
downloads in this session. Same method as `docs/HEADLINE_CANDIDATES.md`.
Written so a later screen can pick a **fourth** unmodified CLI, outside
bioinformatics or at least outside proteins and variants, where
`b·N ≫ a`, records recur across runs, there is no user-result cache
(or ours clearly beats it), absolute time saved is ≥ 60 s, and output
is per-record in a format we parse or could parse with a new FORMAT.

HEADLINE_CANDIDATES.md already rejected AutoDock Vina as a headline
(format + unmeasured `m`) and kept it as an existence proof. This
survey does not rubber-stamp Vina.

**Gap we own:** reuse of the *user’s* prior per-record results across
runs. A public precomputed lookup, a signature/model/weight download,
or an in-memory clean-hash table that dies with the process is not
that gap. Built-in *reference* DBs are not user-result caches.

**Ceiling used below** (TOOL_SCREEN.md erratum + HEADLINE_SCREEN.md):

```
ceiling(m) = (a + b·N) / (a + b·m·N + w)
saved(m)   = (a + b·N) − (a + b·m·N + w)
```

Advance only if `ceiling(m) ≥ 3.0` *and* `saved(m) ≥ 60 s`. If
`a → 0`, the ratio cannot beat `1/m`, so **`m` must be `< 1/3`**.
Baseline is the tool’s own best mode (built-in cache **on**).
`--no-cache` / `--disable-cache` is a ruff-style strawman.

Every numeric cell is **estimate** unless marked measured. No timing
in this session.

---

## Recurrence priors (cited)

| Setting | Number | What it is | Rating |
|---------|--------|------------|--------|
| ChEMBL 32 → 33 unique compounds | 2,354,965 → 2,399,743 | Official release notes ([ChEMBL 32](https://chembl.blogspot.com/2023/03/chembl-32-is-released.html); [ChEMBL 33](https://chembl.blogspot.com/2023/06/release-of-chembl-33.html)). If 33 contains 32, new is about 44.8k and **m ≈ 0.019** on a full-33 later run. Withdrawals exist; screen *measures* InChIKey miss. | **provisional** as a pure-superset `m`; **trust** as release sizes |
| ChEMBL identity key | Standard InChI / InChIKey | Gaulton *et al.*, *Nucleic Acids Res.* 2012, [10.1093/nar/gkr777](https://doi.org/10.1093/nar/gkr777). Same InChI → same CHEMBL_ID. | **trust** |
| ChEMBL 33 scale | 2.4M unique compounds, 20.3M activities | Zdrazil *et al.*, *Nucleic Acids Res.* 2024, [10.1093/nar/gkad1004](https://doi.org/10.1093/nar/gkad1004) | **trust** |
| LibriSpeech test-clean / test-other | 5.4 h / ~5.1 h; tarballs 346 M / 328 M | Panayotov *et al.*, ICASSP 2015, [10.1109/ICASSP.2015.7178964](https://doi.org/10.1109/ICASSP.2015.7178964); [OpenSLR 12](https://openslr.org/12). Splits are **speaker-disjoint** — they do *not* share files. Growing-archive `m` must be constructed from one pool, or taken from a cumulative corpus (Common Voice). | **trust** for sizes; **not** a natural pairwise `m` |
| Common Voice | continually growing, prior clips persist | Ardila *et al.*, LREC 2020, [https://aclanthology.org/2020.lrec-1.520/](https://aclanthology.org/2020.lrec-1.520/) | **trust** for the growing-archive pattern; `m` unmeasured here |
| ClamAV clean-file cache | in-memory, default 65,536 entries; **not** on disk | Cisco-Talos [issue 1049](https://github.com/Cisco-Talos/clamav/issues/1049); `clamd.conf` `CacheSize` / `DisableCache` ([man](https://manpages.debian.org/unstable/clamav-daemon/clamd.conf.5.en.html)). Invalid after signature reload. | **trust** (vendor + maintainer) |

---

## Candidate table

“Built-in cache?” means a lookup that returns *results* for a record
the *user* has already run. Weight files, signature DBs, OSM planet
extracts, and DSSTox structure tables are reference data.

| Tool | Built-in cache? | a / b estimate | Recurrence | Per-record output? | Install / size | Verdict |
|------|-----------------|----------------|------------|--------------------|----------------|---------|
| **OpenAI Whisper CLI `whisper`** | **No** transcript memo. `--model_dir` / `~/.cache/whisper` stores **weights**, not `.tsv`/`.json` transcripts ([`transcribe.py` CLI](https://github.com/openai/whisper/blob/main/whisper/transcribe.py); [README](https://github.com/openai/whisper)). Third-party “skip if `.srt` exists” shells are not the stock CLI. | Radford *et al.*, ICML 2023 / PMLR 202:28492–28518, [proceedings](https://proceedings.mlr.press/v202/radford23a.html), [arXiv 2212.04356](https://arxiv.org/abs/2212.04356): model family, not a CLI wall-time table. Official relative speeds vs `large`: `small` ~4×, `base` ~7×, `tiny` ~10× ([README](https://github.com/openai/whisper/blob/main/README.md)). **Estimate:** `a` = weight load (tens of seconds). `b` scales with audio duration, not file count. GPU `small` on ~10 h of LibriSpeech eval audio is **minutes-scale**; CPU is **hours-scale**. `tiny` is the fast strawman — do not use it as baseline. Default CLI model is now `turbo` (~1.6 GB) — **Josh-gated**. | Growing archive: same bytes re-transcribed when new files are added. LibriSpeech splits are speaker-disjoint (Panayotov 2015) so test-clean versus test-other is **m = 1** if used as two “runs.” Screen uses a constructed 80/20 split of one pool, or Common Voice path overlap. **Estimate** constructed `m = 0.25 < 1/3`. | **Yes, awkwardly.** `--output_format tsv` writes `start_ms\\tend_ms\\ttext` per segment, **one TSV per audio file** (CLI `nargs="+"`). Not one concatenated TSV. **New FORMAT parser** (directory of per-file TSV, key = SHA256 of audio bytes). | `small.pt` **~466 MB** (under 1 GB). `medium.pt` ~1.42 GB, `turbo` ~1.6 GB, `large` ~2.9 GB: **Josh**. PyTorch. CARC GPU preferred; CPU exclusive is valid and slow. | **RANK 1 — screen.** No user memo. Real `b`. Install of `small` under 1 GB. |
| **Mordred `python -m mordred`** | **No** user-result cache in the paper or CLI. Internal caches are *within* one descriptor (e.g. MolecularId pure-function memo; Moriwaki §algorithm). Not a persistent InChIKey → row store. | Moriwaki *et al.*, *J. Cheminform.* 2018, [10.1186/s13321-018-0258-y](https://doi.org/10.1186/s13321-018-0258-y), [PMC5801138](https://pmc.ncbi.nlm.nih.gov/articles/PMC5801138/): “at least twice as fast as PaDEL”; all descriptors of maitotoxin **~1.2 s**; several descriptor classes mean **> 0.1 s**/mol (Fig. 5); Fig. 4 is all-descriptors vs atom count (no single number in the text). CLI is multiprocess (`-p`). **Estimate:** 2D-all on drug-like molecules is **~0.05–0.5 s/mol**; 20k mols is **minutes**; if `b` is only a few ms, `saved` dies and the tool is ruff-class. | ChEMBL 32→33 **m ≈ 0.019 estimate** if later is a 33-slice and prev keys are all of 32 (Gaulton InChI; release notes). Screen measures. | **Yes.** CSV, one row per molecule (`-o out.csv`). Fits TSV/CSV. | `pip`/`conda` + RDKit. ChEMBL `chemreps` files are tens–low-hundreds of MB. No >1 GB fetch. | **RANK 2 — screen.** Clean CSV; no user memo; recurrence is the ChEMBL increment. Strongest objection: `b` may be too small for 60 s at modest N. |
| OPERA `run_OPERA.sh` | **No** user-SDF memo. ID input (CAS / DTXSID / InChIKey) searches a local **DSSTox** table of ~900k public structures ([v2.5+ release notes](https://github.com/kmansouri/OPERA/releases)) — reference lookup, InterProScan-class, not last run’s CSV. CompTox Dashboard already publishes OPERA predictions (Williams *et al.* context; Mansouri 2018 applied to >750k chemicals). Fair baseline is SDF/SMILES compute with lookup **on**. | Mansouri *et al.*, *J. Cheminform.* 2018, [10.1186/s13321-018-0263-1](https://doi.org/10.1186/s13321-018-0263-1): no CLI wall-time table. Work is PaDEL/CDK descriptors + weighted kNN per endpoint. **Estimate:** heavier than Mordred-2D; minutes on thousands of mols. | Same ChEMBL InChI prior. | **Yes.** CSV/TXT, one row per molecule. | MATLAB Compiler Runtime **typically 2–4 GB** + OPERA installer. **Josh — >1 GB.** | **Reject for this screen.** Occupies the same instance as Mordred with a bigger install. Keep as a heavier chemistry follow-up if Mordred `b` is too small. |
| xtb GFN2-xTB | **No** user-molecule memo. ASE `cache_api` reuses the *API object* in-process ([xtb-python](https://github.com/grimme-lab/xtb-python/blob/main/xtb/ase/calculator.py)), not prior energies. Parameter files are reference data. | Bannwarth, Ehlert, Grimme, *J. Chem. Theory Comput.* 2019, [10.1021/acs.jctc.8b01176](https://doi.org/10.1021/acs.jctc.8b01176). WIREs review: Bannwarth *et al.* 2021, [10.1002/wcms.1493](https://doi.org/10.1002/wcms.1493). Single-point+gradient on small molecules is sub-second to seconds; `--opt` is much slower (community QM9-opt means ~2 min are **weak** / unreviewed arXiv). | Growing libraries: same InChI re-optimized. `m` unmeasured. | Per-molecule energy/XYZ. Stock `xtb` **reads only the first SDF record** ([docs](https://xtb-docs.readthedocs.io/en/latest/geometry.html); [issue 26](https://github.com/grimme-lab/xtb/issues/26)). Not one invocation over a library. | Binary small. | **Reject.** Fits the cost model per molecule (Vina-class existence proof) but fails the one-invocation multi-record rule. Do not rubber-stamp as headline. |
| AutoDock Vina `--batch` | **No** result cache (HEADLINE_CANDIDATES.md; Trott & Olson, *J. Comput. Chem.* 2010, [PMC3041641](https://pmc.ncbi.nlm.nih.gov/articles/PMC3041641/): **1.16 min/complex**). | Already surveyed. | Library re-screens; `m` unmeasured. | Per-ligand PDBQT; not generic TSV. | Small. | **Reject as headline** (unchanged). Existence proof only. |
| CREST | TTConf has an **energy cache** (`-ttnocache` disables it) — [CREST keywords](https://crest-lab.github.io/crest-docs/page/documentation/keywords.html). That is a within-search result memo. | Pracht, Bohle, Grimme, *Phys. Chem. Chem. Phys.* 2020, [10.1039/C9CP06869D](https://doi.org/10.1039/C9CP06869D). HPC notes: 65-atom GFN2 **5–8 h** ([TalTech](https://docs-staging.hpc.taltech.ee/chemistry/crest.html); **weak** as a timing source). | One molecule per invocation. | Ensemble files, not TSV. | Small + xtb. | **Reject.** Occupied cache + not multi-record. |
| ClamAV `clamdscan` | **Yes, in-memory user-hash memo.** `DisableCache` / `--disable-cache` is the strawman. Cache stores MD5 of files not flagged virus ([clamd.conf(5)](https://manpages.debian.org/unstable/clamav-daemon/clamd.conf.5.en.html)). **Not persistent** across `clamd` restart or CVD reload ([issue 1049](https://github.com/Cisco-Talos/clamav/issues/1049)). Signatures change daily — a file-hash-only ACTS key would be **wrong** after `freshclam`. | Official docs: `clamscan` reloads the DB every process ([Scanning](https://docs.clamav.net/manual/Usage/Scanning.html)); best mode is `clamd` + `clamdscan`. DB load is tens of seconds (community lists; **weak**). Per-file `b` after daemon-up is often small vs `a` of `clamscan`. Hash-AV (Erdogan & Cao, *Int. J. Security and Networks* 2007 / GLOBECOM 2005) is about *signature-filter* caches, not ClamAV user memos. | Growing malware corpora (same SHA256 re-scanned). | Per-file `path: OK/FOUND` lines. Parseable as lines. | Signatures hundreds of MB; official CVD under 1 GB in many setups, extra unofficial DBs are not required. | **Reject as headline.** Best mode already memos clean hashes for the daemon lifetime; persistence across CVD updates is scientifically a **new key** (file × signature version), not a free win. Running baseline later, not the fourth tool. |
| capa (Mandiant) | Rule-set pickle is a **compiled-rules** cache (~5 s startup; [issue 1212](https://github.com/mandiant/capa/issues/1212)), not prior-binary results. `CAPA_SAVE_WORKSPACE` writes `.viv` for *the same file* ([usage.md](https://github.com/mandiant/capa/blob/master/doc/usage.md)). IDA plugin caches in the IDB. Stock CLI is **one file**. `scripts/bulk-process.py` is not the stock CLI. | Seconds–minutes per binary (vivisect); large ELF can appear to hang ([discussion 2919](https://github.com/mandiant/capa/discussions/2919)). | VirusShare-style corpora; SHA256 recurrence. | `-j` JSON per file. New FORMAT. | Small. | **Reject.** One-file CLI; workspace cache occupies same-file reruns. |
| Semgrep | **Occupied.** Diff-aware scan skips unchanged files ([docs](https://docs.semgrep.dev/troubleshooting/semgrep-app)); `semgrep-core -use_parsing_cache` stores generic ASTs in `~/.semgrep/cache` ([PR 5539](https://github.com/returntocorp/semgrep/pull/5539)). | Minutes on large repos with many rules. | Growing monorepos. | JSON/SARIF per finding. | Small. | **Reject — occupied** (eggNOG-class: the tool already skips prior files). |
| STILTS `tskymatch2` | No user-object memo. Gaia/reference catalogs are reference data. | Taylor, *ASPC* / STILTS SUN/256: ~10⁵-row sky match **~60 s on 2005 laptop** ([SUN256](https://www.star.bris.ac.uk/~mbt/stilts/sun256/match.html)). Modern hardware is faster. Match against a large catalog makes **`a` = index/load** dominate. | User catalog grows; objects recur by `source_id` / RA,Dec key. Independence holds only if the *other* catalog is fixed. | TSV/FITS table. | Binary small; Gaia DR3 is **tens of GB — Josh / reject**. | **Reject.** Join cost is not a clean `b` per user row once the reference catalog is huge; small local tables fail 60 s. |
| SExtractor | No photometry memo. | Bertin & Arnouts, *A&AS* 1996, [ds1060](https://aas.aanda.org/articles/aas/pdf/1996/08/ds1060.pdf). Work is **per image**, not an independent function of one catalog row. | Objects across nights share sky positions but not pixel-independent records. | ASCII/FITS catalog. | Small. | **Reject.** Record independence fails (pixels + neighbours). |
| Nominatim / libpostal | Public Nominatim **usage policy requires clients to cache**; third-party caches occupy the API path ([Nominatim](https://nominatim.org/); wrappers). Self-hosted Nominatim is an OSM **reference** DB (planet extract is many tens of GB). libpostal is claimed at 10k-30k addresses/s (vendor; **provisional**). | Per-query `b` on a warm local Nominatim is milliseconds. | Address lists grow; strings recur. | JSON lines possible. | Planet install **Josh / reject**. | **Reject.** Too fast, or the install is the DB. |
| spaCy `en_core_web_trf` | No doc-result memo. Model download ≠ result cache. Honnibal *et al.*, Zenodo 2020 (software citation). Transformer CPU is slow (official: use GPU; community 10 s / 1k words — **weak**). Published speed table: `trf` ~0.7k words/s CPU, ~3.8k GPU ([spaCy facts](https://spacy.io/usage/facts-figures)). | Need large N or long docs for 60 s. | News/legal archives recur. | No first-class multi-doc TSV CLI comparable to Mordred/Whisper. | `trf` weights ~500 MB. | **Reject for this screen.** Library, not a clean multi-record CLI; CNN models are ruff-class. |

SnpEff, ruff, HMMER, VEP, ESM-2, InterProScan, eggNOG, Bakta, DIAMOND, Prokka, dbNSFP stay closed
(`HEADLINE_CANDIDATES.md`, `TOOL_SCREEN.md`). Not re-opened.

---

## Ranked shortlist (screen these)

### 1. OpenAI Whisper CLI — headline non-bio

Stock `whisper` accepts many audio files in one process, writes
per-file TSV, and does not memo transcripts. Weights-in-`~/.cache`
is the wrong competitor (same mistake as calling VEP `--cache` a
user-VCF memo). `b` is audio duration; a 10-hour growing archive
clears 60 s even at moderate real-time factors. Recurrence is
**byte-identical files** in a growing folder — not speaker overlap
across LibriSpeech splits.

Strongest objections: (i) default `turbo` is >1 GB — lock `small`;
(ii) output is a **directory of TSVs**, so a new FORMAT is required
(ESM-2-class, not VCF); (iii) `cmp` may fail on timestamps even at
`--temperature 0` — the screen times stock CLI only and does not
claim MATCH; (iv) constructed `m = 0.25` is a workload, not a
measured Common Voice increment.

### 2. Mordred CLI — headline chemistry (not proteins)

`python -m mordred` is FASTA-class in spirit: many molecules in,
one CSV out, no user memo. ChEMBL 32→33 is a cited growing
library with expected `m ≪ 1/3` if later rows are a 33-slice and
prev keys are 32. Format fits TSV/CSV without a new parser.

Strongest objections: (i) Moriwaki’s own point is that Mordred is
*fast* — this can fail `saved ≥ 60 s` the way ruff failed;
(ii) 3D (`-3`) needs conformers and is a different tool;
(iii) full ChEMBL is too big to time — the screen uses a locked
N-slice and measures `m` against the previous release’s InChIKey
set (key file only).

---

## Prior-art brief (this survey)

**Claim we are choosing a fourth instance for:** automatic
record-level reuse for an unmodified CLI, persisted across runs,
`cmp`/body-MATCH gated — now outside proteins/variants.

**Closest trusted work we are not reinventing**

- Whole-command: Rattle (OOPSLA 2020), Riker (ATC 2022), ProcessCache (2023), INCR (OSDI 2026).
- Hand-built per-record: Oculus, SeAlM, eggNOG `-m cache`.
- Public / reference lookups: InterProScan MLS, VEP `--cache`, OPERA DSSTox IDs, ClamAV CVD, Whisper weights.
- In-process user memos we must treat as the fair baseline: ClamAV clean-file cache (ON), Semgrep parse/diff cache, CREST TTConf energy cache.
- Vina (Trott 2010): cost-model existence proof, not this headline.

**Delta:** none of the rejected tools give us a *persistent user-result*
memo on Whisper transcripts or Mordred descriptor rows. ClamAV and
Semgrep already skip work we would skip — they are not the instance.

**Non-claims:** we are not inventing Whisper, Mordred, or ChEMBL
identity. We are not claiming 3× until the screen measures `a,b,m,w`.
We are not claiming Vina.

---

## Search trail (this pass)

Scholar + vendor docs, 2026-09-27. Queries included: GFN2-xTB timing
and SDF batch; xtb multi-molecule SDF; OPERA DSSTox cache; Mordred
CLI CSV speed; ChEMBL 32/33 counts and InChI identity; Whisper CLI
multi-file TSV and `~/.cache/whisper`; Radford ICML 2023; LibriSpeech
OpenSLR sizes; Common Voice growth; ClamAV `--disable-cache` /
`CacheSize` / persistent hash DB issue 1049; Hash-AV 2005/2007;
capa rule cache and `bulk-process.py`; Semgrep parsing cache and
diff-aware scan; STILTS tskymatch2 timing; SExtractor per-object vs
per-image; Nominatim usage-policy cache and libpostal rate; spaCy
trf throughput; CREST `-ttnocache`; Vina (re-read, not restated as
new). Shortlist ≥5 trusted/provisional works per non-empty area;
field is *not* thin.
