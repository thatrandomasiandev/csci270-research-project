# Semgrep domain, prompt 1 of 4: build the opt-in features, prove zero regression (2026-10-23)

Paste the block below into a NEW Cursor agent session. It is self-contained.

```text
You are adding three OPT-IN features to TARE (Tool Annotation Reuse, Exact) so it can run Semgrep, a code-analysis tool,
as the paper's non-biology domain. This is prompt 1 of 4: build and prove ZERO regression. No pilot, no CARC, no paper
edits. The paper (OSDI '27, deadline December 8) must not lose anything: not a number, not a millisecond on existing
workloads. If you must choose between finishing and preserving existing behavior, preserve it and report.

READ FIRST
- Repo /Users/joshuaterranova/Desktop/CSCI270/ACTS. Package `acts` (run `python3 -m acts` from pipeline/). Call the system TARE.
- AGENTS.md: "Review standard", "Test design standard", "Paper ownership". Never edit pipeline/paper/tare/main.tex.
- Design and evidence on branch hub/collect-w8-w5x (read them with `git show origin/hub/collect-w8-w5x:<path>`):
  pipeline/docs/SEMGREP_G2_DESIGN.md, pipeline/docs/NONBIO_DOMAIN_PLAN.md, pipeline/docs/NONBIO_LITERATURE.md,
  pipeline/scripts/g1_cost_shape.py, pipeline/results/nonbio/g1_laptop.json.
- Code to understand before changing anything: pipeline/acts/reference_formats.py (Entry, parse_reference_text format
  detection, write_entries, read_records), pipeline/acts/table.py (line tables, tab or whitespace),
  pipeline/acts/reference_fit.py (record/entry columns found by exact token match), pipeline/acts/reference_run.py,
  pipeline/acts/__main__.py (the `run` subcommand flags).

FACTS ALREADY ESTABLISHED (laptop, 2026-10-23; do not re-derive)
- Semgrep 1.182.1 is installed in ~/tmp/tare_g1/venv (run ~/tmp/tare_g1/venv/bin/semgrep). Set
  XDG_CACHE_HOME=~/tmp/tare_g1/cache SEMGREP_SEND_METRICS=off SEMGREP_ENABLE_VERSION_CHECK=0, because ~/.cache is a
  symlink to an unmounted external drive. Always pass --metrics=off --disable-version-check.
- Rules: shallow clone at ~/tmp/tare_g1/rules (semgrep-rules commit 16b9e6d); 336 Python rule files.
- A Semgrep config is ONE YAML document with a top-level `rules:` list; each item has a unique `id`. Semgrep REJECTS
  multi-document YAML ("expected a single document") and mishandles duplicate `rules:` keys. A subset must therefore be
  written as one `rules:` header plus the chosen items.
- Line outputs glue the rule id to other text (`--emacs`: path:line:col:severity(rule-id):code:message), so TARE's exact
  token match cannot find the entry column. `--json` has separate `path` and `check_id` fields.
- Stock vs stock (3 repeats each at f = 0.10, 0.50, 1.00, files ~/tmp/tare_g1/semgrep/out_*_{0,1,2}.json): every top-level
  field is identical except `time`. Corpus syntax errors appear in `errors` deterministically.
- Semgrep takes target paths as command-line arguments, not a list file.

STEP 0 - BASELINE SNAPSHOT (before touching code)
Make your worktree ../ACTS-semgrep on a new branch exp/semgrep-domain from origin/main; record HEAD. Then record a
committed baseline at pipeline/results/nonbio/p1_baseline.json:
 a. `cd pipeline && python3 -m pytest -q`: pass/fail counts and the list of test ids.
 b. A regression corpus that exercises every existing reference format and output path on the laptop: find the
    existing laptop-scale fixtures and end-to-end tests (HMMER profile, FASTA, entry-line, generalized profile; line
    tables). If hmmscan, cmscan, diamond or pfscanV3 are on PATH, also run one tiny end-to-end `acts run --strategy
    reference` per available tool on fixtures already in the repo. Record decision.txt contents and sha256 of every
    output table. No downloads.
 c. A microbenchmark: median of 200 calls each of parse_reference_text and format detection on (i) a Pfam-style HMM
    excerpt already in the repo, (ii) a FASTA reference, (iii) an entry-line reference.

STEP 1 - IMPLEMENT, ALL OPT-IN (the default path must not execute any new code)
 1. Reference format `yaml-list`, selected ONLY by a new flag `--reference-format yaml-list` (default `auto` = the
    current detection, unchanged, and auto must never return yaml-list). Plus `--entry-key-field id`.
    Parse one YAML file whose top level is a mapping with exactly one list key (`rules`). Each list item is an Entry:
    raw = the item's exact original bytes (no re-dumping), key = its `id`, content hash over the raw bytes. Duplicate
    or missing ids raise FormatError, which makes TARE refuse. The writer emits the original header line(s) once, then
    the chosen items' raw bytes in original file order. Round trip: parse then write all entries must reproduce the
    input bytes exactly; if not, FormatError.
 2. Output format `json-records`, selected ONLY by `--output-format json-records --json-rows results` (default `table`,
    unchanged). Rows = elements of the named top-level array; cells = flattened scalar fields with dotted paths, so the
    existing exact-token column inference finds `path` and `check_id`. Every other top-level field is part of the body
    and must equal stock exactly. Rendering must reproduce Semgrep's bytes: find the serializer's key order, separators,
    escaping and number format from the real outputs, and render a merged result byte-identical to stock. If TARE cannot
    prove byte identity for a run, it REFUSES; it never ships a near match. Volatile fields: none by default. Find
    which option or condition adds the top-level `time` field and avoid it at the source if possible. If unavoidable,
    add `--volatile-json-field NAME` (caller-declared, recorded in decision.txt and the contract, default empty) and
    document it.
 3. Placeholder `{inputs}` (plural): expands to the record subset's file paths as separate argv tokens, in record order.
    The existing `{input}` is unchanged. A records file for this mode lists one path per line (read_records already
    treats non-FASTA input as one id per line; reuse it and do not change its behavior).
 Keep every change in its own small module where possible (e.g. reference_yaml.py, table_json.py) and touch
 the shared modules only at the opt-in dispatch points.

STEP 2 - TESTS (each with a positive and a negative control)
 - yaml-list: byte round trip on ALL 336 Python rule files in ~/tmp/tare_g1/rules (concatenated into one rules: list) and
   on 3 hand fixtures; duplicate id -> FormatError; missing id -> FormatError; a Pfam file passed with
   --reference-format yaml-list -> FormatError; auto detection on every existing fixture returns the same format as before.
 - json-records: render(parse(x)) == x byte-for-byte for all 15 G1 outputs with `time` handled as decided; a mutated
   result (one finding dropped, one field changed) -> parse succeeds and comparison FAILS; non-array field change -> FAIL.
 - {inputs}: expansion order and quoting with spaces in paths; {input} behavior unchanged.
 - CLI: `acts run --help` shows the defaults auto / table; a run without the new flags never imports the new modules
   (assert via sys.modules in a subprocess test).
 Put tiny fixtures under pipeline/tests/fixtures/semgrep/ (a few rules, a few Python files). Do NOT commit the G1
 corpus or the cloned rules.

STEP 3 - ZERO-REGRESSION GATES (all must pass; report each with numbers)
 G-a Full pytest: every baseline test still passes; new tests pass. 0 failures.
 G-b Regression corpus re-run: identical decision.txt contents (ignoring wall-time lines only) and identical output
     table sha256 for every case in the baseline.
 G-c Microbenchmark: each median within max(1%, 50 microseconds) of baseline. Report both.
 G-d Default path isolation: the sys.modules test above passes.
 If any gate fails, fix the cause, not the gate. Never loosen a gate. If you cannot pass it, stop and report.

STEP 4 - SMOKE ONLY (laptop, tiny, not evidence)
 On the hand fixtures: Semgrep stock run; TARE fill; then an update where one rule changed and one rule was added.
 TARE's output must equal stock byte-for-byte, or TARE must refuse with a clear reason. Record the commands and
 decision.txt. No timing claims.

RULES
1. Own worktree and branch; never edit the shared checkout; never run `git worktree remove`.
2. Never edit pipeline/paper/tare/main.tex. No CARC, no sbatch, no SSH.
3. Downloads and installs need Josh's approval first (name, URL, exact size). Everything needed is already on disk.
4. Laptop: at most 2 threads and 3 GB RAM, nice -n 10, scratch under ~/tmp/tare_semgrep_p1/.
5. Seeds: if any randomness is needed, use 20261323 and record it. Never reuse a seed found in the repo.
6. Never commit tools/carc-gpu-dashboard/, lab-notebook/, or the research-plan PDF. Say TARE, not ACTS, in prose.
7. Commit small, with tests alongside code. Every commit message ends with:
   Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
   Push the branch. Never merge to main and never force-push.

REPORT (write it to pipeline/docs/prompts/2026-10-23_semgrep_P1_report.md on the branch, and paste it back)
- Branch, base SHA, final SHA.
- Each gate G-a to G-d: PASS/FAIL with numbers (test counts; regression cases compared; benchmark medians before/after).
- How byte identity for json-records was achieved, or exactly where it is impossible.
- The decision on `time`, with evidence.
- Smoke result and decision.txt.
- Every file touched, and why each shared module had to change.
- Open risks for the pilot (prompt 2).
```
