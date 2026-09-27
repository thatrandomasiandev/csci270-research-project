# Layman’s manual

This is the “explain it to a smart friend” version. No course jargon required.

The short lab-facing summary is [`WHAT_THIS_IS.md`](WHAT_THIS_IS.md). The locked numbers live in [`WHAT_WE_ARE_BUILDING.md`](WHAT_WE_ARE_BUILDING.md).

---

## What is this repo?

Two projects live in the same folder. They are not the same idea.

Think of a kitchen that has both a finished class project on the counter and a new experiment on the stove. Same kitchen. Different meals.

1. **The class project (done).** Make a famous biology program called STAR run twice as fast, without changing the answer.
2. **The research experiment (in progress).** Build a wrapper that sits in front of a biology program you do **not** rewrite, remembers answers it has already computed, and only asks the program about the new parts.

If someone asks “what are you building?”, pick one. Do not blend them.

---

## Project 1 — the class project (STAR)

### The everyday problem

STAR is a program that takes DNA/RNA reads from a sequencer and figures out where they sit on a genome. Labs run it a lot. It is slow enough that “make this twice as fast, same answer” is a real homework-sized win.

### What we did

We opened STAR’s source code, found a wasteful step (it was copying big objects over and over), and patched that path. Then we timed it against the original program on the same ten datasets, same machine, one CPU thread. The patched program was at least twice as fast, and the outputs matched.

### What this is not

This is not “we made STAR faster without touching it.” We edited the program. That is allowed for the class. It is a different game from project 2.

---

## Project 2 — the pipeline (the actual vision)

This is the part the folder `pipeline/` is for. The command is `python3 -m acts`.

### The everyday problem

A lot of biology software works like a clerk with a giant spreadsheet.

- Each **row** is one thing: one genetic variant, one line of a file.
- The program reads the whole spreadsheet and writes an answer for every row.
- Tomorrow you run it again on a spreadsheet that is *almost* the same — a new patient, a new sample, a few extra variants.
- The program does not remember last time. It starts from scratch. You pay for every row again, including the ones it already answered last week.

That is wasteful when:

- each row’s answer depends only on that row (row 7 does not change because row 8 exists), and
- many rows show up again across runs (the same variant appears in the next sample).

### What people already do

There are two common answers, and both are incomplete.

**“Remember the whole job.”**  
If you run the exact same command on the exact same file, some systems will replay the old result. Change one row — one new variant in a file of 50,000 — and they throw the memory away and rerun everything. That is like a restaurant that only reuses an order if you order the identical meal, down to the last french fry.

**“Build a custom memory for one program.”**  
Labs sometimes write a one-off cache for *their* annotator. It works. It does not travel. The next tool needs another custom cache. That is like hiring a different sous-chef for each recipe.

There is also a confusing namesake: some tools have a “cache” that is really a **reference library** (the textbook of known genes). That is not a memory of *your last run*. Adding patient 1,001 still annotates every variant in that patient’s file.

### The idea in one picture

```
You:   here is a file of 10,000 variants. run the annotator.
ACTS:  I have seen 8,000 of these before. I will only ask the
       annotator about the 2,000 new ones, then glue the old
       answers back in.
ACTS:  now I will run the annotator on the whole file once, in
       the background of the check, and compare.
       if every byte matches → keep the fast answer.
       if anything differs  → throw it away. we do not ship a lie.
```

The vision is that you do **not** rewrite the annotator. You wrap it. Same command, same binary, faster later runs when enough rows repeat.

### The honesty rule

Speed does not count if the answer changed.

The wrapper is allowed to be clever about *which* rows it pays for. It is not allowed to invent a close-enough answer. If the stitched file is not the same as doing the whole job from scratch, the run is a fail.

That is the whole scientific bet in one sentence:

> Remember answers per row, across runs, for a program we did not modify — and only keep the result if it is identical to a full run.

### When the idea dies

The idea is only useful if three things are true:

1. **Rows are independent.** The answer for variant A does not secretly depend on variant B sitting next to it. If they depend on each other, you cannot safely reuse A’s old answer.
2. **Rows actually repeat.** If almost every row is new every time, remembering is pointless. A “remember the whole job” cache would have done as well.
3. **You can prove the output matches.** If the program stamps the file with a timestamp, a command line, or mixes rows together so you cannot put the puzzle back, the check fails.

STAR failed this test as a *target of the wrapper*. Its output is not “one answer per read that you can file and reuse.” Also, the reads in one sample barely show up in the next sample. So we killed STAR as an instance of this idea. We did not kill the idea.

Variant files are a better bet: the same mutation shows up in many people. Annotate it once, reuse it.

### What “done” looks like

You install a normal biology tool. You do not patch it.

You run:

```text
acts -- the-tool my_file
```

The first time, it does the work and remembers each row.

The second time, on a similar file, it only pays for new rows, glues the file back together, checks that it matches a full run, and finishes sooner.

For that to be a real method — not a one-off hack — the wrapper has to **figure out what a “row” is** by itself. For variant files it now does: it probes which columns the program invents and which it copies. Protein FASTA going into a results table is the next format, not another hard-coded tool.

### What we have measured so far (in English)

- A toy “remember each line” demo works. That only proves the wiring.
- On a real annotator (SnpEff), the glued answers matched, and a later run was a bit faster — about 17% on the careful cluster timing. The program spends so long just starting up that even a perfect memory would only get you to roughly 30% faster. So SnpEff is the wrong headline tool, even though the idea is alive there.
- The next job is to find a program whose per-row work is expensive enough that remembering actually matters (SnpEff is too startup-heavy; the FASTA-to-table wrapper is now on disk).

---

## A 30-second script you can say out loud

> I have two things in this repo. For class, I made STAR twice as fast by editing its source. Separately, I am building a wrapper that sits in front of an unmodified biology program, remembers the answer for each row of the input, and only recomputes new rows on the next run. I throw the result away unless it matches doing the whole job from scratch. The point is to stop paying for the same variants over and over without writing a custom cache for every tool.

---

## Words you will see, translated

| Lab word | Plain meaning |
|----------|----------------|
| Record | One row. One variant, one line. |
| Memoization / cache | A notebook of answers we already computed. |
| Unmodified / black-box | We do not edit the program. We only wrap it. |
| Reassemble | Glue the remembered rows and the new rows back into one file. |
| `cmp` / MATCH / byte-identical | The fast file and the from-scratch file are the same, bit for bit. |
| Incremental | The second run pays only for what is new. |
| Identity | “Is the output even a function of one row?” If no, we refuse. |
| Overlap / recall | How many rows in the new file we already saw last time. |
| VEP / SnpEff | Programs that write a note on each genetic variant (what gene, how bad, …). |
| VEP’s official `--cache` | A textbook of genes, not a memory of your last patients. |
| EGAS | The helper that edited STAR’s source for the class project. Not the wrapper. |
| Suite B | The ten locked test datasets for the STAR class claim. |

---

## What this is not

- Not “make every program 2× faster.”
- Not “we sped up STAR without touching the code.”
- Not a second STAR timer.
- Not a promise that SnpEff is the paper result.
- Not a memory of hidden files the program reads behind your back. We do not claim that yet.

---

## If you want more detail

| You want | Open |
|----------|------|
| This, but in lab voice | [`WHAT_THIS_IS.md`](WHAT_THIS_IS.md) |
| Locked claims and numbers | [`WHAT_WE_ARE_BUILDING.md`](WHAT_WE_ARE_BUILDING.md) |
| STAR scoreboard | [`STATUS.md`](STATUS.md) |
| How to run the wrapper | [`pipeline/README.md`](pipeline/README.md) |
