# Submission-ready slice report (2026-10-22 / 2026-10-23)

Freeze still in force for `13260162`, `13260163`, `13260165` (pending/running at report time). No `sbatch`. No rsync/write into `headline_bounded`, `tare-w8`, or `tare-w5x`.

## Done this slice

### WA2 (exp/wa2-unrelated-ship)
- Correctness scored under the pre-registered rule → **INCONCLUSIVE** (18/20 SHIP, pooled lines below floor; 0 UNSAFE).
- `pipeline/results/unrelated_ship/measured_v2.json` committed on the WA2 branch tip.
- **Timing not eligible** (correctness did not PASS). Do not submit WA2 timing until a PASS redraw (not in this freeze window).

### W12a (exp/w12a-expert-script)
- Orphan `fi` syntax fixed; `bash -n` clean; committed and pushed. **Not submitted** (freeze).

### W12b (exp/w12b-iseqsearch)
- Confirm failure diagnosed as **script bug** (refusal misclassification / declared-pin confirm), not a second method KILL.
- Fix + tests committed and pushed. **Not submitted** (freeze). Still alive for post-freeze sbatch.

### S2 — finalize path
- `pipeline/paper/tare/collectors/` (W13/W8/W5x/W12a/W12b/WA2)
- `pipeline/paper/tare/fill_macros.py` + `macros_pending.tex` (visible `\pending{...}`; finalize exits non-zero while any remain)
- `pipeline/paper/tare/finalize.sh` (exit 0 ready / 2 still running / 1 hard fail)
- `pipeline/docs/FINALIZE_RUNBOOK.md` with both-outcome wording per experiment

### S3 — paper (hub only)
- `main.tex` cut: appendix removed (OSDI refs unlimited, appendices not free pages); Q3/Q4/related/discussion compressed.
- Hardcoded `4.24×` → `\HeadlineBoundedMedian` / CI macros.
- Stage rename **Discovery → Selection** (anonymity: no `discovery` / `CARC` on paper surfaces).
- Three reviewer attacks answered in Discussion.
- `main.pdf` builds; **12 pages of body** (refs continue on p12–13). Verified against https://www.usenix.org/conference/osdi27/call-for-papers and requirements-authors.

### S4 — anonymity + artifact
- `pipeline/artifact/anonymity_scan.py` — **OK** on paper surfaces (TeX comments stripped for provenance keys).
- `pipeline/artifact/export_tarball.sh` — tarball builds; smoke: `acts` import OK.

### S5 — checklist
- `pipeline/docs/SUBMISSION_CHECKLIST.md` with verified OSDI facts, draft fields, JOSH-ONLY list.

## Post-freeze queue (do when 13260162/163/165 all finished)

Priority under exclusive EPYC cap 6:

1. **W12a** timing job (fixed script)
2. **W12b** timing if still alive after confirm fix
3. **WA2 timing** — only if correctness later PASSes (currently ineligible)
4. `./pipeline/paper/tare/finalize.sh` → expect exit 0 when W13/W8/W5x collected and macros filled

Record new job IDs here when submitted: _pending freeze lift_

Hub branch: `hub/submission-ready` @ `708b658` (pushed). Not merged to `main` until finalize fills PENDING macros and pytest stays green.

Finalize dry-run (2026-10-23): discovery SSH timed out; collectors correctly reported STILL RUNNING (exit 2). Checker: 0 mismatches. Anonymity OK. WA2 local COLLECTED (INCONCLUSIVE).

## JOSH-ONLY
See `pipeline/docs/SUBMISSION_CHECKLIST.md` (abstract registration 2026-12-01, paper 2026-12-08, conflicts, artifact host, submit).

## Open risks
- W13/W8/W5x still running; headline and Table-4 macros remain PENDING (checker must fail until finalize fills them).
- WA2 unrelated-ship claim stays supporting/inconclusive until a powered PASS.
- Infernal fill payback and BLAST+ pin probe remain future work (stated in paper).
