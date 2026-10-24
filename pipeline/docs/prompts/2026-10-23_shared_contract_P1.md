# Shared contract across genomes, prompt 1 of 3: decompose, predict, build opt-in (2026-10-23)

Paste the block below into a NEW Cursor agent session. It is self-contained.

```text
You are making TARE's first run cheaper by learning genome-independent facts ONCE per (tool binary, argv, reference
release) and reusing them across a batch of genomes. This is prompt 1 of 3: decompose the cost, predict the gain, build
the feature OPT-IN, and prove zero regression. No CARC runs, no paper edits. The OSDI '27 paper (deadline December 8)
must not lose anything: every existing result, default behavior and safety property stays exactly as it is.

WHY (measured, do not re-derive)
W5x (branch hub/collect-w8-w5x, file pipeline/results/baselines_x86/measured.json; job 13260165, one exclusive EPYC
7542 node, 500 proteins, Pfam-A 30,134 models) measured TARE's first run at 4.20x a stock hmmscan run (95% CI
4.17-4.24), against INCR 1.50x and ProcessCache 14.49x. The paper currently shows 1.32x (whole genomes, server) beside
laptop numbers for the other tools. That is an unfair comparison and must be fixed honestly, not hidden.
TARE run r0 decision.txt (CARC /scratch1/jjt_373/tare-w5x/13260165/pairs/r0/tare/out/decision.txt), total 1013.7 s
vs stock about 250 s:
  parse_s 48.9 | prep_s 9.7 | tool_s 405.5 | discovery_s 246.5 (discovery_scan_s 245.1) | pin_check_s 151.8 |
  replay_s 5.3 | cache_store_s 1.1 | probe_phases: prep_s 80.5, tool_s 453.4, subref_build_s 4.6
Hypothesis: parse, prep (press), pin check and the probe's tool-behavior conclusions depend on (binary, argv,
release), not on the genome; fill and discovery do depend on the genome. Some of these phase timers may overlap,
so establish which phases are nested before adding anything up.

READ FIRST
- Repo /Users/joshuaterranova/Desktop/CSCI270/ACTS; package `acts` (python3 -m acts from pipeline/); call it TARE.
- AGENTS.md: "Review standard" (Amdahl first: w, a, b*n, P), "Test design standard", "Paper ownership".
- pipeline/acts/reference_run.py (phases, probe, pin inference and pin check, discovery, contract storage),
  reference_cache.py, reference_fit.py, entry_hash.py, provenance.py, __main__.py (`run` flags; --cache, --pin,
  --probe-n, --audit-*), predict.py (cost model).
- The paper's description of the design and the first-run claim: pipeline/paper/tare/main.tex (read only).

STEP 0 - BASELINE SNAPSHOT (before touching code)
New worktree ./ACTS-sharedcontract, branch exp/shared-contract from origin/main; record HEAD. Commit
pipeline/results/shared_contract/p1_baseline.json with:
 a. full pytest result (`cd pipeline && python3 -m pytest -q`): counts and test ids;
 b. a regression corpus: every existing laptop-scale end-to-end fixture for the reference strategy (and one tiny real
    run per tool available on PATH), recording decision.txt and sha256 of every output table;
 c. phase timings for one laptop first run and one update on the same fixture (shape only; not speed evidence).

STEP 1 - DECOMPOSE AND PREDICT (no code changes yet)
 1. From the code, build a table: every phase of a first run and of an update, whether it is nested inside another
    timer, and what it reads (binary, argv, reference release, genome records, cache). Classify each phase as SHAREABLE
    (depends only on binary + argv + release) or PER-GENOME. Justify every SHAREABLE label from the code, not intuition.
 2. List every fact the probe and pin check conclude (column roles, normalizer kind per column, pin template,
    identity-normalizer status, row-key and index columns, coupling flags, etc.). For each, say whether it could differ
    between genomes with the same binary, argv and release, and give a concrete way it could (e.g. a column that is
    constant on one genome's sample but varies on another's). These are the soundness risks.
 3. Predict, as a closed form with the W5x numbers: first-run ratio rho(N) for a batch of N genomes when shareable
    phases are paid once, rho(N) = (per-genome + shareable/N) / stock, for N = 1, 5, 20, 100. Write it in
    pipeline/docs/SHARED_CONTRACT_DESIGN.md as PROJECTED with assumptions.
 GATE 1: if the predicted rho(20) is not at least 25% below 4.20 (i.e. at most 3.15), STOP after writing the design
 doc and report: the feature is not worth its risk, and the paper's fix is the honest matched table instead.

STEP 2 - BUILD, OPT-IN ONLY
 - New flag `--contract-store DIR` (default: unset = today's behavior, byte-for-byte). When set, TARE stores the
   SHAREABLE results keyed by sha256(program binary) + normalized argv template + reference release content hash (the
   same namespace ingredients the cache already uses), and reuses them for later genomes in the batch.
 - Never share anything labeled PER-GENOME or any fact with a soundness risk from STEP 1.2 unless a cheap per-genome
   check confirms it on that genome first (e.g. verify the stored column roles and normalizer on this genome's probe
   sample at reduced n). If the check disagrees, discard the stored entry for this genome, run the full probe, and
   record it in decision.txt. Never ship on a stored fact that this genome contradicts.
 - Unchanged per genome, always: the check (neighbor pad, random pads), the bounded audit (s = 299), refusal rules,
   the break-even fallback, exactness against stock in tests.
 - decision.txt records whether the contract was reused, its key, and which per-genome confirmations ran.
 - Concurrency: two genomes in a batch may start at once. Writes to the store must be atomic (write temp + rename) and
   a reader must never see a partial entry.

STEP 3 - TESTS (positive and negative control for each)
 - Reuse: genome B reuses A's stored contract and its output is byte-identical to B's stock run and to B run without
   the store.
 - Key isolation: a different binary sha, a different argv, or a different release must NOT hit the stored entry.
 - Contradiction: a fixture where genome B's sample contradicts a stored fact; TARE must detect it, fall back to the
   full probe, and still produce correct output (or refuse).
 - Corruption: truncated or tampered store entry -> ignored with a recorded reason, never trusted.
 - Concurrency: two processes racing on one key -> one entry, no partial reads.
 - Default path: a run without --contract-store never imports the new module (sys.modules check in a subprocess).

STEP 4 - ZERO-REGRESSION GATES (report numbers; never loosen a gate)
 G-a full pytest: all baseline tests pass, new tests pass, 0 failures.
 G-b regression corpus without the flag: identical decision.txt (ignoring wall-time lines) and identical output sha256.
 G-c laptop phase timings without the flag within noise of the baseline (report both).
 G-d default-path isolation test passes.

STEP 5 - LAPTOP SMOKE (shape only, not evidence)
 On existing small fixtures, a batch of 3-5 genomes with the store: show which phases were skipped for genomes 2.N,
 that every output equals stock, and the per-genome confirmations that ran. No speed claims.

RULES
1. Own worktree and branch; never edit the shared checkout; never run `git worktree remove`.
2. Never edit pipeline/paper/tare/main.tex. No CARC, no sbatch, no SSH except reading the W5x decision.txt quoted above
   if you need more of it (`ssh discovery`, read-only; never retry a failed connection in a loop).
3. Downloads and installs need Josh's approval first (name, URL, exact size).
4. Laptop: at most 2 threads, 3 GB RAM, nice -n 10, scratch ~/tmp/tare_sharedcontract/.
5. Seeds: 20261331-20261339 only, after grepping the repo for collisions; record each.
6. Never commit tools/carc-gpu-dashboard/, lab-notebook/, or the research-plan PDF. Say TARE, not ACTS, in prose.
7. Commit small with tests alongside code. Do not add a Co-Authored-By line or any AI attribution to commit messages.
   Push the branch; never merge to main; never force-push.

REPORT (write pipeline/docs/prompts/2026-10-23_shared_contract_P1_report.md on the branch, and paste it back)
- Branch, base SHA, final SHA.
- The STEP 1 phase table (SHAREABLE vs PER-GENOME, nesting) and the fact list with soundness risks.
- The predicted rho(N) closed form and values; GATE 1 outcome.
- If built: gates G-a to G-d with numbers, test list, smoke result, every file touched and why.
- Open risks for prompt 2 (laptop pilot with controls) and prompt 3 (CARC measured, N = 1, 5, 20 genomes).
```
