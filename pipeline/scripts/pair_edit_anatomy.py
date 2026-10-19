"""Which lines differ between edited entries of two Pfam releases?

For every accession stem present in both releases whose strict hash differs (same definition as
release_chain_pairs.py: drop DATE, BM, SM, COM lines), classify the differing lines by their tag
(first token; model-body lines are grouped as MODEL). Writes a JSON summary to the path given.

usage: pair_edit_anatomy.py OLD.hmm.gz NEW.hmm.gz OUT.json
"""
import collections
import gzip
import hashlib
import json
import sys

VOLATILE = {"DATE", "BM", "SM", "COM"}
HEADER = {"NAME", "ACC", "DESC", "LENG", "ALPH", "RF", "MM", "CONS", "CS", "MAP", "NSEQ", "EFFN", "CKSUM",
          "GA", "TC", "NC", "STATS", "HMM", "COMPO"}


def entries(path):
    block = []
    with gzip.open(path, "rt") as fh:
        for line in fh:
            block.append(line)
            if line.startswith("//"):
                yield "".join(block)
                block = []


def stem(text):
    for line in text.splitlines():
        if line.startswith("ACC"):
            return line.split()[1].split(".")[0]
    return None


def kept(text):
    return [l for l in text.splitlines() if not (l.split() and l.split()[0] in VOLATILE)]


def tag(line):
    tok = line.split()[0] if line.split() else ""
    if line.startswith("HMMER3"):
        return "FORMAT_LINE"
    if tok in HEADER:
        return tok + (" " + line.split()[1] if tok == "STATS" and len(line.split()) > 2 else "")
    return "MODEL"


old = {stem(t): t for t in entries(sys.argv[1])}
changed_tags = collections.Counter()
only_tags = collections.Counter()
n_edited = 0
example = {}
for t in entries(sys.argv[2]):
    s = stem(t)
    if s not in old:
        continue
    a, b = kept(old[s]), kept(t)
    if hashlib.sha256("\n".join(a).encode()).digest() == hashlib.sha256("\n".join(b).encode()).digest():
        continue
    n_edited += 1
    tags = set()
    if len(a) != len(b):
        tags.add("LINE_COUNT")
    for x, y in zip(a, b):
        if x != y:
            tags.add(tag(x))
            example.setdefault(tag(x), [x[:80], y[:80]])
    for t_ in tags:
        changed_tags[t_] += 1
    only_tags[tuple(sorted(tags))] += 1
out = {"old": sys.argv[1], "new": sys.argv[2], "n_edited": n_edited,
       "entries_with_tag_changed": dict(changed_tags.most_common()),
       "top_tag_sets": [[list(k), v] for k, v in only_tags.most_common(8)],
       "example_line": example}
json.dump(out, open(sys.argv[3], "w"), indent=1)
print(json.dumps({k: out[k] for k in ("n_edited", "entries_with_tag_changed", "top_tag_sets")}, indent=1)[:2500])
