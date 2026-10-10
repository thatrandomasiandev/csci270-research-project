# Artifact evaluation

This directory is the artifact for the paper in `pipeline/paper/main.tex`.
It re-runs small committed fixtures and checks every paper number that carries a `% source:` comment against the committed file named in that comment.
It does not write `pipeline/results/`, and it does not replace a number in the paper with a freshly measured one.

Two badges are exercised here. **Available** is this directory plus the committed result files it cites. **Functional** is the image and the kick-the-tires path below. **Reproduced** splits in two: the laptop path re-derives the safety, fitter, and reuse decisions on fixtures that are in the repository; the cluster path is the job that produced each timing file, and the expected numbers are the committed files themselves.

## Hardware and software

Laptop and image:

- One CPU, about 2 GB of RAM, and about 2 GB of free disk for the image.
- Python 3.11 or newer (`tomllib` is in the standard library). The image is Ubuntu 22.04 and installs the `python3.11` package, because that release's default `python3` is 3.10.
- HMMER 3.4 (`hmmbuild`, `hmmscan`, `hmmpress`) on `PATH` for the reference-merge smoke. The image builds HMMER 3.4 from `http://eddylab.org/software/hmmer/hmmer-3.4.tar.gz` and checks SHA-256 `ca70d94fd0cf271bd7063423aabb116d42de533117343a9b27a65c17ff06fbf3`.
- `pipeline/artifact/requirements.txt` pins `numpy==1.26.4` and `matplotlib==3.8.4`. The unit suite imports them. The kick-the-tires scripts use the standard library.

Cluster claims use the scheduler scripts under `pipeline/jobs/`. The timing host in the paper is one exclusive node with an AMD EPYC 7542. Pfam and the proteome collections are not in this repository. Those jobs are documented below so a reviewer can see the request and the committed output. They are outside the one-hour laptop path.

The image reproduces decisions and the paper-number check. It does not reproduce the exclusive-node wall times.

## Kick the tires (under 30 minutes)

From the repository root, with Python 3.10+ and HMMER 3.4 on `PATH`:

```bash
./pipeline/artifact/kick_the_tires.sh
```

In the image, after the build in the next section:

```bash
docker run --rm acts-artifact /src/pipeline/artifact/kick_the_tires.sh
```

The script runs, in order:

1. `pipeline/artifact/laptop/t3_synthetic.py`
2. `pipeline/artifact/laptop/record_reuse.py`
3. `pipeline/artifact/laptop/ref_merge_smoke.py`
4. `pipeline/artifact/laptop/probe_eval_smoke.py`
5. `pipeline/artifact/check_paper_sources.py`

Each smoke prints `PASS` or `FAIL` and a `wall_s=` line. The checker prints `source_comments=181 mismatches=0`. Any `FAIL` exits non-zero. Nothing is written under `pipeline/results/`.

On a laptop this path is a few minutes. The slow step is the five probe-eval cells.

## Image

From the repository root:

```bash
docker build -f pipeline/artifact/Dockerfile -t acts-artifact .
docker run --rm acts-artifact
```

The default command is `pipeline/artifact/run_in_image.sh`: `pipeline/run_tests.sh`, then the kick-the-tires path. `pipeline/run_tests.sh` is `python3 -m unittest discover -s tests -v` with `PYTHONPATH` set to `pipeline/`. The image compiles `pipeline/fixtures/fat_copy/` during the build so those two programs are Linux executables, and it creates a git repository inside the image so the provenance checks can run `git rev-parse`. The strace unit test stays skipped; the image does not install `strace`.

## Claims

Paper numbers below are the values stored in the cited file. The printed paper rounds them; `check_paper_sources.py` accepts a displayed decimal only when it is that value rounded to the printed number of places. Runtime budgets are upper bounds for the laptop commands, measured by the scripts as `wall_s`.

| Claim | Command | Expected | Budget | Committed file |
|---|---|---|---|---|
| RQ1 safety cells | `python3 pipeline/artifact/laptop/probe_eval_smoke.py` | `PASS` for vcf C1 `SHIP` / `unsafe_ship=False`; vcf F1 `REFUSE_NONDETERMINISTIC`; vcf F4 `p=0.01` `unsafe_ship=True`; fasta F6-env `unsafe_ship=True`; fasta C4 `SHIP` | under 5 minutes | `pipeline/results/probe_eval_audit.json` |
| RQ1 deployed and full-MATCH counts | `python3 pipeline/artifact/check_paper_sources.py` | `mismatches=0`. The comments require audit in-scope `4/224`, full MATCH in-scope `1/224`, false-refuse `0/20`, F6-env `32/32`, F6-file `32/32`, and in-scope `0/56` at probe sizes 500 and 2000 | under 1 minute | `pipeline/results/probe_eval_audit.md`, `pipeline/results/probe_eval.md`, `pipeline/results/probe_eval_audit.json` |
| RQ2 record-side reuse | `python3 pipeline/artifact/laptop/record_reuse.py` | `PASS` within-file `SHIP` `n=8` `n_unique=4`; first run `n_hits=0`; second run `SHIP` `n_hits=2` `n_misses=2` `mode=incremental` | under 1 minute | `pipeline/fixtures/line_memo/` |
| RQ2 corrected hmmsearch speedups | checker, as above | collection A `cum_speedup_wall=1.8561541144638773`, with probe `1.5126488173514772`; collection B `4.4038095881881` and `3.1519938702250814` | checker | `pipeline/results/savings_sensitivity.json` |
| RQ2 locked (pre-registered) totals | checker | A `cum_speedup_wall=2.740193934015858` and `cum_speedup_wall_with_P=2.23308564806322`; B `6.846592216443059` and `4.900397318731101` | checker | `pipeline/results/savings_summary.json` |
| RQ3 T3 ship and refuse | `python3 pipeline/artifact/laptop/t3_synthetic.py` | A `SHIP` `entry_count` tie-break; B `SHIP` `total_entry_length` tie-break; C `SHIP` `per_key_row_count`; D `REFUSE`; E `REFUSE` with `row-key`; GeStore baseline on A `REFUSE` with `normalizer` | under 1 minute | `pipeline/docs/REFERENCE_INCREMENTAL_PROTOCOL.md` (T3 table); fixtures in `pipeline/tests/fixtures/reference_fitter/` |
| RQ3 reference-merge MATCH | `python3 pipeline/artifact/laptop/ref_merge_smoke.py` | base `SHIP` `rows=2` `reused_rows=0`; release `SHIP` `rows=2` `reused_rows=1` | under 1 minute | decisions of the same wrapper as the paper; profiles in `pipeline/artifact/fixtures/profiles/` |
| RQ3 T1 / T2 | checker | T1 tie-break residuals and T2 reason `tblout: column 16 matches no normalizer` match the comments in `main.tex` | checker | `pipeline/results/reference_fitter_t1.json`, `pipeline/results/reference_fitter_t2.json`, `pipeline/results/reference_kill_r2p.json`, `pipeline/results/reference_kill_r2n.json`, `pipeline/results/reference_kill_r3c.json` |
| RQ4 Pfam 38.1 to 38.2 | checker | `timed=false` in the churn file. The paper marks the speedup pending. Projected `P`, `c*`, and `S` recompute from the screen fit and the churn counts | checker | `pipeline/results/reference_reannot_churn.json`, `pipeline/results/headline_screen.json`, `pipeline/results/reference_kill_r1.json` |
| RQ5 DIAMOND smoke | checker | `reference_diamond_d2.json` `decision=SHIP` `smoke=true`; `reference_diamond_d2n.json` `decision=REFUSE` `smoke=true`. The paper marks the full comparison pending | checker | `pipeline/results/reference_diamond_smoke/` |
| RQ6 identity-only baseline | `python3 pipeline/artifact/laptop/t3_synthetic.py` (GeStore row) | `REFUSE` on law A | under 1 minute | protocol T3; the timed head-to-head is pending in the paper |
| RQ7 BLAST+ blastp B1 | checker | `decision=REFUSE`, `blastp` `2.14.1`, `queries.n=20`, `reference.n_entries=575748`, `reference.total_entry_length=209017843`, reason `out: column 2 matches no normalizer` | checker | `pipeline/results/reference_boundary_blast.json` |

`check_paper_sources.py` reads `pipeline/paper/main.tex` and the files named in `% source:` comments. It does not modify them. A comment that states a closed form (`(1-0.01)^n`, `3a+2bn_p`, `(a+bN)/(a+w)`) is recomputed from the cited screen fit, the kill-test counts, and `n_p = 300` in `pipeline/docs/REFERENCE_INCREMENTAL_PROTOCOL.md`.

## Laptop path

These four commands are the reproductions that finish on a laptop from committed inputs.

**T3 synthetic oracle.** `pipeline/artifact/laptop/t3_synthetic.py` loads the laws in `pipeline/tests/test_reference_fitter.py` and the fixtures in `pipeline/tests/fixtures/reference_fitter/`. A, B, and C must ship the member named in the protocol table. D and E must refuse. The GeStore baseline must refuse law A because it does not infer a normalizer. There is no results JSON for T3; the protocol says so.

**Reference-merge smoke.** Pfam-A is not in the repository. `pipeline/artifact/laptop/ref_merge_smoke.py` builds four HMMER 3.4 profiles from `pipeline/artifact/fixtures/profiles/ToyA.sto`, `ToyB.sto`, `ToyC.sto`, and `ToyD.sto` (`hmmbuild --amino`, gathering threshold 15), concatenates them, and runs `ReferenceIncremental` with `hmmscan --cpu 1 --cut_ga --noali`, `prep=hmmpress -f {reference}`, and `verify=full`. The base reference ships with 2 rows and 0 reused rows. A release that edits the `DESC` line of ToyA and appends a clone of ToyD ships with 2 rows and 1 reused row. `SHIP` under `verify=full` is ref-merge MATCH against stock `hmmscan`. The pinned counts are this HMMER 3.4 behavior on these four profiles. The paper's 38.1 to 38.2 timing is a separate claim and is pending.

**Record-side reuse.** `pipeline/artifact/laptop/record_reuse.py` runs `RecordMemo` with `kind=lines`, `argv=["cat"]`, and `verify=full` on `pipeline/fixtures/line_memo/`. `input.txt` ships with `n=8` and `n_unique=4`. `run_a.txt` fills an empty cache (`n_hits=0`). `run_b.txt` on that cache ships with `n_hits=2`, `n_misses=2`, and `mode=incremental`. The match relation is byte-identical. These counts are properties of the fixtures.

**Probe-eval safety.** `pipeline/artifact/laptop/probe_eval_smoke.py` calls `run_cell` from `pipeline/scripts/run_probe_eval.py` into a temporary directory. The five cells are the smallest committed probe size (`probe_n=50`): vcf C1, vcf F1, vcf F4 at `p=0.01` (the in-scope miss), fasta F6-env, and fasta C4. Each cell's `input1.decision`, `unsafe_ship`, and `false_refuse` must equal the one matching row in `pipeline/results/probe_eval_audit.json`. F6-file is omitted: the committed audit was taken where file tracing was unavailable, and a Linux `strace` would be a different measurement. The headline fractions `4/224` and `1/224` are checked by the source checker against the committed writeups, not by re-running the 308-cell grid.

## Cluster path

The laptop does not re-time these jobs. Each script below is the one that writes the cited result. Scheduler account lines inside the job files are site configuration; the reproduction interface is the environment variables and the result file.

**RQ1.** The full grid is `python3 pipeline/scripts/run_probe_eval.py`, which writes `pipeline/results/probe_eval_audit.json`. That command is not part of kick-the-tires because it replaces the committed audit. The committed audit and `pipeline/results/probe_eval.md` are the paper's counts. The run is a decision measurement, not an exclusive-node timing.

**RQ2.** `pipeline/jobs/hmmer_savings.job`, submitted by `pipeline/scripts/submit_hmmer_savings.sh`, runs `pipeline/scripts/run_hmmer_savings.py`. The request is one exclusive node, 32 CPUs, 64 GB, HMMER 3.4. `ACTS_SAVINGS_COLLECTION` is `A` or `B`. `ACTS_SAVINGS_MODE` is `hmmsearch` for the primary (30 genomes in A, 40 in B) and `hmmscan` for the post-hoc file. Expected primary output:

- `pipeline/results/savings_20261006/A_hmmsearch.json` and `B_hmmsearch.json`
- `pipeline/results/savings_summary.json` (locked totals; probe `P_s=1595.4474956459528` on sizes `[8, 8, 8, 8, 1, 1, 1, 1, 1, 1, 1, 1]`; scheduler ids `12739228` and `12739230`)
- `pipeline/results/savings_sensitivity.json` (post-hoc corrected wall speedups in the table above)

The post-hoc hmmscan numbers live in `pipeline/results/savings_sensitivity_hmmscan.json` and are marked `paper_uses=false` in the summary. An earlier stop is `pipeline/results/savings_failed_20260928/STOP.json` (`position=5`, `decision=STOP_MATCH`) and is not a speedup.

**RQ3 T1 and T2.** `pipeline/scripts/reference_fitter_accept.py` reads the historical half-databases from the kill tests. Those halves are not in the small fixture directory. The laptop covers T3 and the toy ref-merge. The committed outcomes are the JSON files in the table.

**RQ4.** `pipeline/jobs/reference_reannot.job`, submitted by `pipeline/scripts/submit_reference_reannot.sh`, runs `pipeline/scripts/run_reference_reannot.py`. The request is one exclusive node, 32 CPUs, 128 GB. The expected committed state is `pipeline/results/reference_reannot_churn.json` with `timed=false`. Superseded job ids are recorded in `pipeline/docs/REFERENCE_INCREMENTAL_PROTOCOL.md` and are not a measurement. There is no measured 38.1 to 38.2 speedup in the repository.

**RQ5.** `pipeline/jobs/reference_diamond.job` requests one exclusive node, 32 CPUs, 64 GB. The full comparison is pending. The committed smoke outcomes are `pipeline/results/reference_diamond_smoke/reference_diamond_d2.json` (`SHIP`) and `reference_diamond_d2n.json` (`REFUSE`), both with `smoke=true`.

**RQ6.** `pipeline/jobs/baseline_smoke.job` requests a shared node, 8 CPUs, 48 GB. A head-to-head wall time is pending. The implemented baseline check is the GeStore refusal in the T3 laptop script.

**RQ7.** `pipeline/jobs/reference_boundary.job` runs `pipeline/scripts/run_reference_boundary.py` on a shared node, 4 CPUs, 16 GB. It is a correctness fit, not a timing run. The expected file is `pipeline/results/reference_boundary_blast.json` with the refusal in the table. Swiss-Prot is not in the repository, so this is not re-run on the laptop. The source checker is the reproduction of the printed numbers.
