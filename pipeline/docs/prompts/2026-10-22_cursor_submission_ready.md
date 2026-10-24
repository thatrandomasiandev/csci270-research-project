# TARE: make the OSDI '27 submission ready except for CARC results (2026-10-22)

Paste the block below into a NEW Cursor orchestrator session. It is self-contained.

```text
You are the ORCHESTRATOR and, for this pass only, the HUB for TARE (Tool Annotation Reuse, Exact), an OSDI '27
paper (deadline December 8, 2026). Goal: when you finish, the submission is complete except for results from CARC
jobs that are still queued or running. Finishing those must take one command. Launch subagents as needed (each in its
own git worktree), track them, and do not stop until every item under DEFINITION OF DONE is met or BLOCKED ON JOSH with
the exact action Josh must take.

READ FIRST
- Repo: /Users/joshuaterranova/Desktop/CSCI270/ACTS (package `acts`, run `python3 -m acts` from pipeline/; call the
  system TARE in prose). Start from up-to-date origin/main (b3cd9ad or later; it includes the console prototype).
- AGENTS.md: "Review standard", "Test design standard", "Paper ownership". STATUS.md.
- The paper: pipeline/paper/tare/main.tex (USENIX format, "Anonymous Submission"). Checker:
  python3 pipeline/artifact/check_paper_sources.py (every number carries a "% source:" comment; must report 0 mismatches).
- Round-2 orchestration: pipeline/docs/prompts/2026-10-20_orchestrator_round2.md and its report on branch
  exp/orchestrator-report-r2.
- Paper ownership: for this pass YOU are the only writer of main.tex. Subagents never edit it; they hand you proposed
  sentences with "% source:" keys. Nobody else edits main.tex while you run.

CARC STATE (2026-10-22 ~17:00 PT; re-check with squeue/sacct before acting)
- W13 headline re-timed under the bounded-audit default: pilot 13259408 COMPLETED 07:13 today; measured array
  13260162_[0-8] PENDING. HIGHEST PRIORITY. Branch exp/w13-bounded-headline. Leave it queued.
- W8 measured release chain 13260163: tasks 0,1 COMPLETED; task 2 RUNNING (limit 24 h). Branch exp/w8-release-chain.
- W5x baselines on x86 13260165: RUNNING (limit 16 h). Branch exp/w5x-baselines-x86.
- W12a expert-script measured 13260164: FAILED in 2 s: "slurm_script: line 41: syntax error near unexpected token
  `fi'" (log tare-w12a/logs/tare-w12a-measured-13260164.err). Its pilot 13241867 passed. Branch exp/w12a-expert-script.
- W12b iSeqSearch confirm 13260166: FAILED (exit 1). Known cause: the confirm script misclassifies DIAMOND's correct
  refusal as a failure. Branch exp/w12b-iseqsearch.
- WA2 PROSITE pfscanV3 fresh draw, correctness array 13259447_[0-19]: all COMPLETED 2026-10-20, NOT collected or
  scored. Timing v2 never submitted. Branch exp/a-unrelated-ship.
- Never touch job 12864756 (not ours to manage) or anyone else's jobs.

FREEZE (added 2026-10-22 evening; overrides S1 below)
While jobs 13260162 (W13), 13260163 (W8) and 13260165 (W5x) are pending or running: no sbatch of any kind, and no
rsync or write under their CARC directories (headline_bounded, tare-w8, tare-w5x). Reading finished results is fine.
S1a/S1b code fixes are committed and pushed but NOT submitted; submit them, and WA2 timing if eligible, only after all
three jobs have finished. WA2 correctness looked like 18/20 SHIP and 2 INCONCLUSIVE: score it under the pre-registered
rule before deciding timing eligibility. W12b: confirm from the job log whether the failure is the refusal
misclassification or the earlier pad_hit issue before changing anything; a script bug is a fix, a repeat of the same
method failure is the second locked failure and becomes a stated limitation.

WORKSTREAMS (run in parallel where independent)

S1 - CARC repairs and submissions (one subagent per item)
 a. W12a: fix the job-script syntax error, `bash -n` it, dry-run the staged entry point, resubmit the measured run.
    Same pre-registered design; record the fix as a dated addendum in docs/BASELINES_EXACT_PROTOCOL.md.
 b. W12b: fix the confirm classification so a correct DIAMOND refusal counts as the expected outcome (add a unit test
    with a known-good refusal and a known-bad ship), dated addendum, resubmit confirm, then the measured run if confirm
    passes. If confirm fails again for a different reason, that is the second locked failure: record it as a stated
    limitation and stop (no third redesign).
 c. WA2: rsync the 20 correctness results, score them under the pre-registered rules (docs/UNRELATED_SHIP_PROTOCOL_V2.md),
    commit pipeline/results/unrelated_ship/measured_v2.json. Only if exactness passes, submit timing v2 (5 genomes, r=3,
    exclusive). Report pass/fail and power honestly (INCONCLUSIVE, not KILL, below the power floor).
 Node cap: at most 6 exclusive EPYC nodes in use at once across everything. Priority W13 > W8 > W12a > W5x > W12b > WA2.

S2 - One-command finalize (the "only thing left is waiting" path)
 For each pending experiment (W13, W8, W5x, W12a, W12b, WA2 timing) write a collector that: rsyncs the CARC result,
 validates it against the pre-registration (all tasks present, controls passed, power floor), writes the committed JSON
 under pipeline/results/<area>/ with provenance, and exits non-zero with a clear message if anything is missing or failed.
 Then add pipeline/paper/tare/finalize.sh (or a Makefile target) that: runs every collector, regenerates every figure and
 every number macro from the result files, rebuilds main.pdf, runs the checker and the anonymity scan (S4), and prints a
 per-experiment table: COLLECTED / STILL RUNNING / FAILED. It must be safe to re-run any number of times.
 Pending numbers in the paper become macros (e.g. \HeadlineBoundedMedian) filled from result JSON. Until filled they
 render as a visible "PENDING" and make the checker FAIL, so the paper can never be submitted with a placeholder.
 Write pipeline/docs/FINALIZE_RUNBOOK.md: the one command, what each failure means, and for each pending result the
 pre-written paper wording for both outcomes (holds / does not hold), so a bad result needs no new writing.

S3 - The paper (you, the single writer)
 1. Page budget: main text at most 12 pages, references and appendix excluded (verify the exact OSDI '27 limits and
    format in the official call for papers; cite the URL in the checklist). The body currently runs past page 12. Cut to
    leave room for the pending results: tighten prose, merge redundant paragraphs, move secondary tables to the appendix.
    Do not drop any safety evidence or any negative result.
 2. Review pass against AGENTS.md's review standard, as an OSDI PC member: Amdahl decomposition visible, every number
    MEASURED or PROJECTED, strongest baselines named, kill experiments and ship controls stated. Write the three most
    dangerous reviewer attacks and make sure the paper answers each one in the text (expect "this is just caching /
    memoization", "the safety check is sampled, so it is not exact", "one tool family, so not general").
 3. Related work: state precisely what is new against incremental-build and caching systems (Riker, ProcessCache,
    INCR, ccache-style memoization) and against bioinformatics incremental tools (iSeqSearch). Credit borrowed mechanisms
    (group testing, sampling audits). No novelty claim without a citation check.
 4. Abstract and introduction: the problem, the 4.24x headline (to be replaced by the W13 macro), exactness, and the
    safety guarantee in plain words, with no number the evaluation does not support.
 5. Consistency: one name per concept, figure fonts and colors consistent, every figure readable in grayscale print,
    every table referenced in the text.
 6. Fold in the S1 results that land while you work. For anything still pending, use the S2 macros.
 7. Reviewer comments: Josh's professor and an external PhD student are reading the draft. If Josh pastes their
    comments, triage them into must-fix-before-submission and later, and fix the first group.

S4 - Anonymity and artifact
 - Anonymity scan (script, run by finalize): main.tex, main.pdf text and PDF metadata, figures, and the artifact must not
   contain: Terranova, Joshua, jjt_373, biyik, Biyik, USC, University of Southern California, CARC, discovery,
   /project2, /Users/, LIRA, lab names, emails. Self-citations in third person only.
 - Anonymized artifact: an export script that builds a clean tarball from the repo: pipeline/acts, tests, the scripts
   that produce every paper number and figure, the committed result files, pre-registrations and addenda, a README
   with exact reproduce commands (laptop-scale smoke test plus the full server commands), and a license. Exclude
   archive/, lab-notebook/, tools/carc-gpu-dashboard/, the console prototype, and anything with a name, host or path.
   Run the smoke test from the unpacked tarball on the laptop (at most 2 threads, nice -n 10).
 - Do NOT upload or host it. Hosting (for example an anonymous mirror) is Josh's action: list it in the checklist.

S5 - Submission package
 pipeline/docs/SUBMISSION_CHECKLIST.md with: the verified OSDI '27 facts with source URL (page limit, format, abstract
 registration deadline, paper deadline, artifact rules, anonymity policy); drafted submission-site fields (title,
 abstract text, topic areas, keywords); a conflicts section for Josh to fill; and a short list headed JOSH-ONLY ACTIONS
 (register the abstract, enter conflicts, host the artifact, press submit, anything needing Duo or approval).

SHARED RULES (copy verbatim into every subagent)
1. Own worktree and branch; never edit the shared checkout; never run `git worktree remove` (it has deleted ignored
   data before; check `git status --ignored` first if cleanup is ever needed).
2. Only the orchestrator edits pipeline/paper/tare/main.tex. Subagents return proposed sentences with exact
   "% source:" keys (file + JSON path = value).
3. Test design standard (AGENTS.md): pilot before lock, pre-register before measuring, positive and negative controls,
   power floor -> INCONCLUSIVE not KILL, difference classes on every failure, dated addenda for every deviation, no third
   redesign of the same question.
4. Code changes in pipeline/acts/ need tests; `cd pipeline && python3 -m pytest -q` stays green.
5. New seeds only from 20261301-20261319, and never a seed already in the repo (grep first).
6. Laptop: at most 2 threads and 3 GB RAM per subagent, nice -n 10; laptop times are never speed evidence.
7. Downloads and installs need Josh's approval first (one message: name, URL, exact size).
8. CARC only via the SSH alias `discovery` (ssh discovery '..', rsync -e ssh .. discovery:..). Never the raw host or
   IP, carc-transfer, -S none, -o ControlMaster=no, or ssh -O exit. Never retry a failed connection in a loop: ask Josh.
   sbatch only; no compute on the login node. Project dir /project2/biyik_1165/jjt_373/csci270-star/, scratch
   /scratch1/$USER/. Timing jobs: --exclusive --mem=0 --constraint=epyc-7542, alternating stock/TARE, r=3, crash
   handler writing partial JSON, time limit = pilot wall x 1.5 (never under 8 h for whole-genome HMMER). `bash -n` and
   dry-run every job script before sbatch.
9. Provenance in every committed result JSON: git head, frozen commit, seed, tool versions and checksums, host/CPU,
   argv, walls, per-run outcomes.
10. Never commit Josh's own uncommitted files: tools/carc-gpu-dashboard/, lab-notebook/, the research-plan PDF,
    .gitignore edits. Say TARE, not ACTS, in all prose.
11. Commit small. Do not add a Co-Authored-By line or any AI attribution to commit messages.
    Push branches. Never force-push.

MERGING
Subagents push their branches. You merge to main with --no-ff only when pytest is green, the checker reports 0
mismatches apart from the intended PENDING macros, and main.pdf builds. Never merge a half-collected result.

DEFINITION OF DONE
- S1: W12a and W12b resubmitted (or W12b recorded as a limitation after a second failure); WA2 correctness scored and
  committed; WA2 timing submitted if exactness passed. Job IDs recorded.
- S2: finalize.sh exists, re-runs cleanly, and reports every still-running experiment as STILL RUNNING; the runbook
  holds both-outcome wording for each.
- S3: main.pdf builds; main text within the verified page limit WITH the pending sections at their expected final
  length; the review pass and the three attacks answered in the text; the only checker failures are PENDING macros.
- S4: the anonymity scan passes on the paper and the artifact; the artifact tarball builds and its smoke test passes.
- S5: SUBMISSION_CHECKLIST.md complete with verified facts and the JOSH-ONLY list.
- Final report at pipeline/docs/prompts/2026-10-22_submission_ready_report.md on main: what was done, job IDs, what
  finalize still waits for, the JOSH-ONLY list, and any open risk. Poll CARC every 30-60 min while your own submissions
  are pending, but finishing does NOT require W13/W8/W5x to finish: that is what finalize is for.
```
