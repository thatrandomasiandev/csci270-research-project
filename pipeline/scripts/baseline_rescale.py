#!/usr/bin/env python3
"""Strongest honest E-value rescaler for Pfam 38.1 -> 38.2 hmmscan --cut_ga.

Z-scaled columns are multiplied by 30134/27481 and printed with HMMER 3.4's
snprintf conversions. c-Evalue scales by per-query domZ, not by Z. Changed
families are replaced by a pinned discovery scan. See
docs/BASELINES_EXACT_PROTOCOL.md.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import platform
import random
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acts.entry_hash import entry_content_hash  # noqa: E402
from acts.reference_formats import PROFILE_VOLATILE_TAGS  # noqa: E402

DATA = Path("/Users/joshuaterranova/Desktop/CSCI270/ACTS/pipeline/data")
SCRATCH = Path.home() / "tmp" / "tare_d"
E1_WORK = Path.home() / "tmp" / "e1scale_work" / "measured"
HMMSCAN = "/opt/homebrew/bin/hmmscan"
HMMPRESS = "/opt/homebrew/bin/hmmpress"
PFAM_NEW_GZ = DATA / "hmmer" / "Pfam-A.hmm.gz"
PFAM_OLD_GZ = DATA / "hmmer" / "pfam38.1" / "Pfam-A.hmm.gz"
Z_NEW = 30134
Z_OLD = 27481
CPU = "2"
OUT_DIR = ROOT / "results" / "baselines_exact"
WILSON_Z = 1.959963984540054
CUTOFFS = (1e-3, 1e-5, 1e-10)
FLOOR = 5000
PILOT_FLOOR = 30
PILOT_N = 100
PILOT_SEED = 20261133
PILOT_PROTEOME = "GCF_024585005.1_protein.faa.gz"
EXCLUDE = {
    "GCF_002853805.1_protein.faa.gz",
    "GCF_002090355.1_protein.faa.gz",
    "GCF_013315695.1_protein.faa.gz",
    "GCF_049201905.1_protein.faa.gz",
    "GCF_059719525.1_protein.faa.gz",
    "GCF_016806025.1_protein.faa.gz",
    "GCF_017165095.1_protein.faa.gz",
    "GCF_001515725.1_protein.faa.gz",
    "GCF_001513615.1_protein.faa.gz",
}
E1_GENOMES = [
    "GCF_013315695.1",
    "GCF_049201905.1",
    "GCF_059719525.1",
]
COSTPASS = ["GCF_016806025.1", "GCF_017165095.1"]
INPUT_MD5 = {
    "Pfam-A.hmm.gz": "7ab3c4e215d0daaea3004e37c4e24f8a",
    "pfam38.1/Pfam-A.hmm.gz": "dc814cc181ece09102c09c4e6c19f2fd",
}

TBL_NAMES = {
    0: "target_name",
    1: "target_accession",
    2: "query_name",
    3: "query_accession",
    4: "full_sequence_E",
    5: "full_sequence_score",
    6: "full_sequence_bias",
    7: "best_domain_E",
    8: "best_domain_score",
    9: "best_domain_bias",
    10: "exp",
    11: "reg",
    12: "clu",
    13: "ov",
    14: "env",
    15: "dom",
    16: "rep",
    17: "inc",
    18: "description",
}
DOM_NAMES = {
    0: "target_name",
    1: "target_accession",
    2: "tlen",
    3: "query_name",
    4: "query_accession",
    5: "qlen",
    6: "full_sequence_E",
    7: "full_sequence_score",
    8: "full_sequence_bias",
    9: "domain_index",
    10: "domain_of",
    11: "c_Evalue",
    12: "i_Evalue",
    13: "domain_score",
    14: "domain_bias",
    15: "hmm_from",
    16: "hmm_to",
    17: "ali_from",
    18: "ali_to",
    19: "env_from",
    20: "env_to",
    21: "acc",
    22: "description",
}
DOM_COORDS = (15, 16, 17, 18, 19, 20)

FORMATTER_C = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void die(const char *msg) { fprintf(stderr, "hmmer_fmt: %s\n", msg); exit(2); }
static int read_line(char *buf, size_t n) {
    if (!fgets(buf, (int)n, stdin)) return 0;
    size_t len = strlen(buf);
    if (len && buf[len - 1] == '\n') buf[len - 1] = 0;
    return 1;
}
int main(void) {
    char head[256], rec[8192], desc[8192], out[8192];
    setvbuf(stdout, NULL, _IOLBF, 0);
    while (read_line(head, sizeof head)) {
        if (!read_line(rec, sizeof rec) || !read_line(desc, sizeof desc)) die("short record");
        if (head[0] == 'T') {
            int tnw, taw, qnw, qaw, znum, zden;
            char name[256], acc[256], qname[256], qacc[256];
            double e1, score, bias, e2, ds, db, expv;
            int reg, clu, ov, env, dom, rep, inc;
            if (sscanf(head, "T %d %d %d %d %d %d", &tnw, &taw, &qnw, &qaw, &znum, &zden) != 6) die(head);
            if (sscanf(rec, "%255s %255s %255s %255s %lf %lf %lf %lf %lf %lf %lf %d %d %d %d %d %d %d",
                       name, acc, qname, qacc, &e1, &score, &bias, &e2, &ds, &db, &expv,
                       &reg, &clu, &ov, &env, &dom, &rep, &inc) != 18) die(rec);
            double zf = (double)znum / (double)zden;
            snprintf(out, sizeof out,
                "%-*s %-*s %-*s %-*s %9.2g %6.1f %5.1f %9.2g %6.1f %5.1f %5.1f %3d %3d %3d %3d %3d %3d %3d %s\n",
                tnw, name, taw, acc, qnw, qname, qaw, qacc,
                e1 * zf, score, bias, e2 * zf, ds, db, expv,
                reg, clu, ov, env, dom, rep, inc, desc);
        } else if (head[0] == 'D') {
            int tnw, taw, qnw, qaw, znum, zden, dnum, dden, tlen, qlen, nd, nof, hmmfrom, hmmto;
            char name[256], acc[256], qname[256], qacc[256];
            long long alifrom, alito, envfrom, envto;
            double e, score, bias, ce, ie, dscore, dbias, post;
            if (sscanf(head, "D %d %d %d %d %d %d %d %d",
                       &tnw, &taw, &qnw, &qaw, &znum, &zden, &dnum, &dden) != 8) die(head);
            if (sscanf(rec, "%255s %255s %d %255s %255s %d %lf %lf %lf %d %d %lf %lf %lf %lf %d %d %lld %lld %lld %lld %lf",
                       name, acc, &tlen, qname, qacc, &qlen, &e, &score, &bias, &nd, &nof,
                       &ce, &ie, &dscore, &dbias, &hmmfrom, &hmmto,
                       &alifrom, &alito, &envfrom, &envto, &post) != 22) die(rec);
            double zf = (double)znum / (double)zden;
            double df = (double)dnum / (double)dden;
            snprintf(out, sizeof out,
                "%-*s %-*s %5d %-*s %-*s %5d %9.2g %6.1f %5.1f %3d %3d %9.2g %9.2g %6.1f %5.1f %5d %5d %5lld %5lld %5lld %5lld %4.2f %s\n",
                tnw, name, taw, acc, tlen, qnw, qname, qaw, qacc, qlen,
                e * zf, score, bias, nd, nof, ce * df, ie * zf, dscore, dbias,
                hmmfrom, hmmto, alifrom, alito, envfrom, envto, post, desc);
        } else die(head);
        fputs(out, stdout);
        fflush(stdout);
    }
    return 0;
}
"""


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def git_head() -> str:
    repo = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    )
    return proc.stdout.strip()


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_lines(lines: list[str]) -> str:
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def body_lines(path: Path) -> list[str]:
    lines = []
    with path.open() as handle:
        for line in handle:
            if line.startswith("#") or not line.strip():
                continue
            lines.append(line.rstrip("\n"))
    return lines


def query_ids(path: Path) -> list[str]:
    ids = []
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as handle:
        for line in handle:
            if line.startswith(">"):
                ids.append(line[1:].split()[0])
    return ids


def write_sample(src: Path, indices: list[int], dest: Path) -> None:
    records: list[tuple[str, list[str]]] = []
    opener = gzip.open if str(src).endswith(".gz") else open
    with opener(src, "rt") as handle:
        header = ""
        chunk: list[str] = []
        for line in handle:
            if line.startswith(">"):
                if header:
                    records.append((header, chunk))
                header = line
                chunk = []
            else:
                chunk.append(line)
        if header:
            records.append((header, chunk))
    if indices[-1] >= len(records):
        raise SystemExit(f"sample index past end of {src.name}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w") as handle:
        for index in indices:
            header, chunk = records[index]
            handle.write(header)
            handle.writelines(chunk)


def token_spans(line: str) -> list[tuple[int, int]]:
    spans = []
    i = 0
    n = len(line)
    while i < n:
        while i < n and line[i] == " ":
            i += 1
        if i >= n:
            break
        j = i
        while j < n and line[j] != " ":
            j += 1
        spans.append((i, j))
        i = j
    return spans


def fields_of(line: str, n_fixed: int) -> tuple[list[str], str]:
    spans = token_spans(line)
    if len(spans) < n_fixed:
        raise SystemExit(f"short line ({len(spans)} fields): {line[:80]}")
    fields = [line[a:b] for a, b in spans[:n_fixed]]
    desc = line[spans[n_fixed - 1][1] + 1 :] if len(spans) > n_fixed else ""
    return fields, desc


def recovered_target_widths(line: str, kind: str) -> tuple[int, int]:
    """Recover HMMER's target-name and accession widths from a printed line.

    Those widths include unreported hits, so they can exceed every reported
    name. Query widths do not: HMMER sets them from the query string alone.
    In domtblout the field after the accession is a right-justified %5d.
    """
    spans = token_spans(line)
    tnamew = spans[1][0] - spans[0][0] - 1
    if kind == "tbl":
        taccw = spans[2][0] - spans[1][0] - 1
    else:
        acc = line[spans[1][0] : spans[1][1]]
        tlen = line[spans[2][0] : spans[2][1]]
        gap = spans[2][0] - spans[1][1]
        leading = max(0, 5 - len(tlen))
        pad = gap - 1 - leading
        if pad < 0:
            raise SystemExit(f"dom accession width recovery failed: {line[:100]}")
        taccw = len(acc) + pad
    return tnamew, taccw


def compile_formatter() -> Path:
    dest = SCRATCH / "hmmer_fmt"
    source = SCRATCH / "hmmer_fmt.c"
    SCRATCH.mkdir(parents=True, exist_ok=True)
    source.write_text(FORMATTER_C)
    if dest.is_file() and dest.stat().st_mtime >= source.stat().st_mtime:
        return dest
    proc = subprocess.run(
        ["clang", "-O2", "-o", str(dest), str(source)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(f"clang failed: {proc.stderr[-500:]}")
    return dest


class Printer:
    def __init__(self, binary: Path) -> None:
        self.proc = subprocess.Popen(
            [str(binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def emit(self, header: str, fields: list[str], desc: str) -> str:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(header + "\n")
        self.proc.stdin.write(" ".join(fields) + "\n")
        self.proc.stdin.write(desc + "\n")
        self.proc.stdin.flush()
        out = self.proc.stdout.readline()
        if not out:
            raise RuntimeError("formatter exited")
        return out.rstrip("\n")

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.wait(timeout=10)


def run_hmm(cmd: list[str]) -> float:
    # macOS rejects RLIMIT_AS/RLIMIT_DATA/RLIMIT_RSS and ulimit -v
    # ("current limit exceeds maximum limit" / "invalid argument") because
    # the process virtual size is already above any cap we can set. The
    # pressed Pfam indexes are about 2.4 GB, so a 3 GB address cap could
    # not map them anyway. Threads stay at 2 and the process is niced.
    log(" ".join(cmd))
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, check=False)
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        raise SystemExit(f"command failed ({proc.returncode}): {' '.join(cmd[:6])}")
    return wall


def hmmscan(db: Path, queries: Path, tag: Path, z: int | None) -> float:
    stamp = tag.with_suffix(".stamp.json")
    tbl = Path(str(tag) + ".tbl")
    dom = Path(str(tag) + ".dom")
    argv = [
        "nice", "-n", "10", HMMSCAN, "--cut_ga", "--noali", "--cpu", CPU,
        "--tblout", str(tbl), "--domtblout", str(dom), "-o", os.devnull,
    ]
    if z is not None:
        argv += ["-Z", str(z)]
    argv += [str(db), str(queries)]
    if stamp.is_file() and tbl.is_file() and dom.is_file():
        old = json.loads(stamp.read_text())
        if old.get("argv") == argv and old.get("returncode") == 0:
            log(f"reuse {tag.name}")
            return float(old["wall_s"])
    tag.parent.mkdir(parents=True, exist_ok=True)
    wall = run_hmm(argv)
    stamp.write_text(json.dumps({"argv": argv, "wall_s": wall, "returncode": 0}) + "\n")
    return wall


def press(text: Path) -> None:
    marker = Path(str(text) + ".h3m")
    if marker.is_file():
        return
    run_hmm(["nice", "-n", "10", HMMPRESS, "-f", str(text)])


def iter_models(path: Path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as handle:
        buf: list[str] = []
        name = cksum = ""
        for line in handle:
            buf.append(line)
            if line.startswith("NAME "):
                name = line.split()[1]
            elif line.startswith("CKSUM "):
                cksum = line.split()[1]
            elif line.startswith("//"):
                yield name, cksum, "".join(buf)
                buf, name, cksum = [], "", ""


def family_partition() -> dict:
    cache = SCRATCH / "families.json"
    changed_path = SCRATCH / "hmm" / "changed.hmm"
    if cache.is_file() and changed_path.is_file():
        return json.loads(cache.read_text())
    for label, path in ("new", PFAM_NEW_GZ), ("old", PFAM_OLD_GZ):
        found = md5_file(path)
        if found != INPUT_MD5[path.name if label == "new" else "pfam38.1/Pfam-A.hmm.gz"]:
            raise SystemExit(f"STOP md5 {path.name} {found}")
    log("hash Pfam 38.1")
    old: dict[str, tuple[str, str]] = {}
    for name, cksum, block in iter_models(PFAM_OLD_GZ):
        old[name] = (entry_content_hash(block, PROFILE_VOLATILE_TAGS), cksum)
    stable: list[str] = []
    changed: list[str] = []
    cksum_stable = 0
    strict_but_not_cksum = 0
    cksum_but_not_strict = 0
    changed_path.parent.mkdir(parents=True, exist_ok=True)
    log("hash Pfam 38.2 and write changed families")
    with changed_path.open("w") as out:
        new_names: list[str] = []
        for name, cksum, block in iter_models(PFAM_NEW_GZ):
            new_names.append(name)
            digest = entry_content_hash(block, PROFILE_VOLATILE_TAGS)
            prev = old.get(name)
            same_ck = prev is not None and prev[1] == cksum and cksum != ""
            same_strict = prev is not None and prev[0] == digest
            if same_ck:
                cksum_stable += 1
            if same_strict and not same_ck:
                strict_but_not_cksum += 1
            if same_ck and not same_strict:
                cksum_but_not_strict += 1
            if same_strict:
                stable.append(name)
            else:
                changed.append(name)
                out.write(block)
    removed = sorted(set(old) - set(new_names))
    payload = {
        "z_old": len(old),
        "z_new": len(new_names),
        "stable": len(stable),
        "changed": len(changed),
        "removed": len(removed),
        "cksum_stable": cksum_stable,
        "strict_stable_cksum_differs": strict_but_not_cksum,
        "cksum_stable_strict_differs": cksum_but_not_strict,
        "stable_names": stable,
        "changed_names": changed,
        "removed_names": removed,
    }
    if (payload["z_old"], payload["z_new"]) != (Z_OLD, Z_NEW):
        raise SystemExit(f"STOP model counts {payload['z_old']} {payload['z_new']}")
    cache.write_text(json.dumps(payload))
    log(f"families stable={len(stable)} changed={len(changed)} removed={len(removed)}")
    return payload


def group_lines(lines: list[str], q_index: int) -> dict[str, list[tuple[int, str]]]:
    grouped: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for index, line in enumerate(lines):
        grouped[line.split()[q_index]].append((index, line))
    return grouped


def target_set(rows: list[tuple[int, str]]) -> set[str]:
    return {line.split()[0] for _index, line in rows}


def rescore(
    printer: Printer,
    old_tbl: list[str],
    old_dom: list[str],
    disc_tbl: list[str],
    disc_dom: list[str],
    order: list[str],
    stable: set[str],
    *,
    z_num: int,
    z_den: int,
) -> tuple[list[str], list[str]]:
    """Reprint one release update.

    A query whose target list is unchanged keeps file order. Re-sorting
    that list by the printed E-value breaks byte identity: HMMER's
    sort key is the full-precision bit score, and printed E-values tie.
    A query that gains or loses a target is sorted by ascending rescaled
    full-sequence E-value, then target name.
    Widths come from every merged tblout target, including a target with
    no domain row. c-Evalue uses domZ_merged/domZ_source. Discovery lines
    were printed at Z_new, so their Z factor is 1.
    """
    old_t = group_lines(old_tbl, 2)
    old_d = group_lines(old_dom, 3)
    disc_t = group_lines(disc_tbl, 2)
    disc_d = group_lines(disc_dom, 3)
    out_t: list[str] = []
    out_d: list[str] = []
    for query in order:
        cached_t = [(i, ln) for i, ln in old_t.get(query, []) if ln.split()[0] in stable]
        found_t = list(disc_t.get(query, []))
        if not cached_t and not found_t:
            continue
        hits = []
        z_factor = z_num / z_den
        for index, line in cached_t:
            fields, desc = fields_of(line, 18)
            hits.append((index, "cache", fields, desc, fields[0], float(fields[4]) * z_factor))
        for index, line in found_t:
            fields, desc = fields_of(line, 18)
            if fields[0] in stable:
                raise SystemExit(f"discovery target {fields[0]} is stable")
            hits.append((index, "disc", fields, desc, fields[0], float(fields[4])))
        original = [ln.split()[0] for _, ln in old_t.get(query, [])]
        if [hit[4] for hit in hits] != original:
            hits.sort(key=lambda hit: (hit[5], hit[4]))
        dom_old = len(target_set(old_t.get(query, [])))
        dom_disc = len(target_set(found_t))
        dom_new = len(hits)
        tnw = max(20, max(len(hit[4]) for hit in hits))
        taw = max(10, max(len(hit[2][1]) for hit in hits))
        qnw = max(20, len(hits[0][2][2]))
        qaw = max(10, len(hits[0][2][3]))
        dom_by: dict[str, list[tuple[str, int, list[str], str]]] = defaultdict(list)
        for _index, line in old_d.get(query, []):
            if line.split()[0] not in stable:
                continue
            fields, desc = fields_of(line, 22)
            dom_by[fields[0]].append(("cache", int(fields[9]), fields, desc))
        for _index, line in disc_d.get(query, []):
            fields, desc = fields_of(line, 22)
            dom_by[fields[0]].append(("disc", int(fields[9]), fields, desc))
        for _index, origin, fields, desc, name, _score in hits:
            if origin == "cache":
                header = f"T {tnw} {taw} {qnw} {qaw} {z_num} {z_den}"
            else:
                header = f"T {tnw} {taw} {qnw} {qaw} 1 1"
            out_t.append(printer.emit(header, fields, desc))
            for dom_origin, _domain_i, dom_fields, dom_desc in sorted(dom_by.get(name, []), key=lambda row: row[1]):
                if dom_origin == "cache":
                    if dom_old <= 0:
                        raise SystemExit(f"domZ old is 0 for {query}")
                    header = f"D {tnw} {taw} {qnw} {qaw} {z_num} {z_den} {dom_new} {dom_old}"
                else:
                    if dom_disc <= 0:
                        raise SystemExit(f"domZ discovery is 0 for {query}")
                    header = f"D {tnw} {taw} {qnw} {qaw} 1 1 {dom_new} {dom_disc}"
                out_d.append(printer.emit(header, dom_fields, dom_desc))
    return out_t, out_d


def wilson(k: int, n: int) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = k / n
    den = 1 + WILSON_Z ** 2 / n
    centre = p + WILSON_Z ** 2 / (2 * n)
    margin = WILSON_Z * math.sqrt(p * (1 - p) / n + WILSON_Z ** 2 / (4 * n * n))
    return ((centre - margin) / den, (centre + margin) / den)


def line_key(line: str, kind: str) -> tuple:
    fields = line.split()
    if kind == "tbl":
        return (fields[2], fields[0])
    return (fields[3], fields[0], fields[9])


def column_tokens(line: str, kind: str) -> list[str]:
    n_fixed = 18 if kind == "tbl" else 22
    fields, desc = fields_of(line, n_fixed)
    return fields + [desc]


def compare_bodies(stock: list[str], other: list[str], kind: str) -> dict:
    names = TBL_NAMES if kind == "tbl" else DOM_NAMES
    stock_by: dict[tuple, list[str]] = defaultdict(list)
    other_by: dict[tuple, list[str]] = defaultdict(list)
    for line in stock:
        stock_by[line_key(line, kind)].append(line)
    for line in other:
        other_by[line_key(line, kind)].append(line)
    identical = 0
    token_identical = 0
    padding = 0
    value_cols: dict[str, int] = defaultdict(int)
    different_row = 0
    used_other: dict[tuple, int] = defaultdict(int)
    for key, rows in stock_by.items():
        partners = other_by.get(key, [])
        for row in rows:
            cursor = used_other[key]
            if cursor >= len(partners):
                continue
            partner = partners[cursor]
            used_other[key] = cursor + 1
            if row == partner:
                identical += 1
                token_identical += 1
                continue
            a = column_tokens(row, kind)
            b = column_tokens(partner, kind)
            if a == b:
                padding += 1
                token_identical += 1
                continue
            if len(a) != len(b):
                different_row += 1
                continue
            coord_diff = kind == "dom" and any(a[i] != b[i] for i in DOM_COORDS)
            if coord_diff:
                different_row += 1
            for index, (left, right) in enumerate(zip(a, b)):
                if left != right:
                    value_cols[names.get(index, f"col_{index}")] += 1
    missing = sum(len(rows) - min(len(rows), len(other_by.get(key, []))) for key, rows in stock_by.items())
    extra = sum(len(rows) - min(len(rows), len(stock_by.get(key, []))) for key, rows in other_by.items())
    # The loop above consumes partners only up to stock rows, so missing/extra
    # from the length difference is the right count. Recompute explicitly.
    missing = 0
    extra = 0
    for key in set(stock_by) | set(other_by):
        s_n = len(stock_by.get(key, []))
        o_n = len(other_by.get(key, []))
        if s_n > o_n:
            missing += s_n - o_n
        elif o_n > s_n:
            extra += o_n - s_n
    classes = []
    if value_cols and different_row == 0:
        classes.append("value-only")
    elif value_cols:
        classes.append("value-only")
    if different_row:
        classes.append("different-row")
    if padding:
        classes.append("padding-only")
    if missing:
        classes.append("missing")
    if extra:
        classes.append("extra")
    bodies_equal = stock == other
    multiset_equal = identical == len(stock) == len(other) and not missing and not extra and not padding and not value_cols and not different_row
    if not bodies_equal and multiset_equal:
        classes.append("order")
    interval = wilson(identical, len(stock))
    return {
        "stock_lines": len(stock),
        "rescaler_lines": len(other),
        "byte_identical": identical,
        "byte_identical_over_stock": (identical / len(stock)) if stock else None,
        "token_identical": token_identical,
        "wilson95": {"low": interval[0], "high": interval[1]} if interval else None,
        "padding_only": padding,
        "value_only_by_column": dict(value_cols),
        "different_row": different_row,
        "missing": missing,
        "extra": extra,
        "order_only": (not bodies_equal) and multiset_equal,
        "bodies_equal": bodies_equal,
        "difference_classes": classes,
    }


def cutoff_report(stock: list[str], other: list[str], kind: str) -> dict:
    e_index = 4 if kind == "tbl" else 6
    stock_by: dict[tuple, list[str]] = defaultdict(list)
    other_by: dict[tuple, list[str]] = defaultdict(list)
    for line in stock:
        stock_by[line_key(line, kind)].append(line)
    for line in other:
        other_by[line_key(line, kind)].append(line)
    report = {}
    for cut in CUTOFFS:
        flip = lost = gained = 0
        keys = set(stock_by) | set(other_by)
        for key in keys:
            s_rows = stock_by.get(key, [])
            o_rows = other_by.get(key, [])
            n = min(len(s_rows), len(o_rows))
            for index in range(n):
                s_pass = float(s_rows[index].split()[e_index]) <= cut
                o_pass = float(o_rows[index].split()[e_index]) <= cut
                if s_pass != o_pass:
                    flip += 1
            for row in s_rows[n:]:
                if float(row.split()[e_index]) <= cut:
                    lost += 1
            for row in o_rows[n:]:
                if float(row.split()[e_index]) <= cut:
                    gained += 1
        report[f"{cut:.0e}"] = {"flip": flip, "lost": lost, "gained": gained}
    return report


def round_trip(printer: Printer, lines: list[str], kind: str) -> list[str]:
    n_fixed = 18 if kind == "tbl" else 22
    grouped: dict[str, list[str]] = defaultdict(list)
    q_index = 2 if kind == "tbl" else 3
    order = []
    for line in lines:
        query = line.split()[q_index]
        if query not in grouped:
            order.append(query)
        grouped[query].append(line)
    out = []
    for query in order:
        rows = grouped[query]
        tnw = max(recovered_target_widths(line, kind)[0] for line in rows)
        taw = max(recovered_target_widths(line, kind)[1] for line in rows)
        for line in rows:
            fields, desc = fields_of(line, n_fixed)
            if kind == "tbl":
                qnw = max(20, len(fields[2]))
                qaw = max(10, len(fields[3]))
                header = f"T {tnw} {taw} {qnw} {qaw} 1 1"
            else:
                qnw = max(20, len(fields[3]))
                qaw = max(10, len(fields[4]))
                header = f"D {tnw} {taw} {qnw} {qaw} 1 1 1 1"
            out.append(printer.emit(header, fields, desc))
    return out


def _z_columns_only(stock: list[str], other: list[str], kind: str) -> tuple[int, int, list[str]]:
    """Return (changed lines, c-Evalue mismatches, unexpected column names)."""
    z_cols = {4, 7} if kind == "tbl" else {6, 12}
    c_e = 11
    changed = 0
    c_bad = 0
    unexpected: set[str] = set()
    names = TBL_NAMES if kind == "tbl" else DOM_NAMES
    if len(stock) != len(other):
        unexpected.add("line_count")
    for left, right in zip(stock, other):
        if left == right:
            continue
        changed += 1
        a = column_tokens(left, kind)
        b = column_tokens(right, kind)
        if len(a) != len(b):
            unexpected.add("width")
            continue
        for index, (x, y) in enumerate(zip(a, b)):
            if x == y:
                continue
            if kind == "dom" and index == c_e:
                c_bad += 1
            if index not in z_cols:
                unexpected.add(names.get(index, f"col_{index}"))
    return changed, c_bad, sorted(unexpected)


def selftest() -> None:
    binary = compile_formatter()
    printer = Printer(binary)
    base = E1_WORK / "GCF_013315695.1"
    failures = 0
    tables = {}
    for kind, name in (("tbl", "S382.tbl"), ("dom", "S382.dom")):
        lines = body_lines(base / name)
        got = round_trip(printer, lines, kind)
        bad = sum(a != b for a, b in zip(lines, got))
        log(f"selftest round_trip {kind} lines={len(lines)} differ={bad} len_ok={len(lines)==len(got)}")
        failures += bad + abs(len(lines) - len(got))
        tables[kind] = lines
    order = query_ids(base / "queries.faa")
    stable = {line.split()[0] for line in tables["tbl"]} | {line.split()[0] for line in tables["dom"]}
    pos_t, pos_d = rescore(
        printer, tables["tbl"], tables["dom"], [], [], order, stable, z_num=1, z_den=1,
    )
    if pos_t != tables["tbl"] or pos_d != tables["dom"]:
        log(f"selftest ratio-1 FAIL tbl {sum(a!=b for a,b in zip(pos_t, tables['tbl']))} dom {sum(a!=b for a,b in zip(pos_d, tables['dom']))}")
        failures += 1
    else:
        log("selftest ratio-1 pass")
    neg_t, neg_d = rescore(
        printer, tables["tbl"], tables["dom"], [], [], order, stable, z_num=Z_NEW, z_den=Z_OLD,
    )
    for kind, stock, other in (("tbl", tables["tbl"], neg_t), ("dom", tables["dom"], neg_d)):
        changed, c_bad, unexpected = _z_columns_only(stock, other, kind)
        log(f"selftest pfam-ratio {kind} changed={changed} c_E_bad={c_bad} unexpected={unexpected}")
        if not changed or c_bad or unexpected or stock == other:
            failures += 1
    printer.close()
    if failures:
        raise SystemExit(f"SELFTEST_FAIL {failures}")
    log("selftest pass")


def discovery(queries: Path, tag: Path) -> tuple[list[str], list[str], float]:
    families = family_partition()
    changed = SCRATCH / "hmm" / "changed.hmm"
    press(changed)
    wall = hmmscan(changed, queries, tag, Z_NEW)
    return body_lines(Path(str(tag) + ".tbl")), body_lines(Path(str(tag) + ".dom")), wall


def score_pair(
    printer: Printer,
    old_tbl: Path,
    old_dom: Path,
    new_tbl: Path,
    new_dom: Path,
    queries: Path,
    disc_tag: Path,
    stable: set[str],
) -> dict:
    stock_t = body_lines(new_tbl)
    stock_d = body_lines(new_dom)
    pos_t = round_trip(printer, stock_t, "tbl")
    pos_d = round_trip(printer, stock_d, "dom")
    positive = pos_t == stock_t and pos_d == stock_d
    if not positive:
        raise SystemExit(f"POSITIVE_CONTROL_FAIL {queries.name}")
    disc_t, disc_d, wall = discovery(queries, disc_tag)
    order = query_ids(queries)
    got_t, got_d = rescore(
        printer, body_lines(old_tbl), body_lines(old_dom), disc_t, disc_d, order, stable,
        z_num=Z_NEW, z_den=Z_OLD,
    )
    neg_t, neg_d = rescore(
        printer, body_lines(old_tbl), body_lines(old_dom), disc_t, disc_d, order, stable,
        z_num=1, z_den=1,
    )
    negative_differs = neg_t != stock_t or neg_d != stock_d
    if not negative_differs:
        raise SystemExit(f"NEGATIVE_CONTROL_FAIL {queries.name}")
    return {
        "queries": queries.name,
        "n_records": len(order),
        "positive_control": positive,
        "negative_control_differs": negative_differs,
        "discovery_wall_s": wall,
        "walls_are_evidence": False,
        "tbl": compare_bodies(stock_t, got_t, "tbl"),
        "dom": compare_bodies(stock_d, got_d, "dom"),
        "cutoffs_full_sequence_E": {
            "tbl": cutoff_report(stock_t, got_t, "tbl"),
            "dom": cutoff_report(stock_d, got_d, "dom"),
        },
        "stock_body_sha256": {"tbl": sha256_lines(stock_t), "dom": sha256_lines(stock_d)},
    }


def require_inputs() -> None:
    for key, path in ("Pfam-A.hmm.gz", PFAM_NEW_GZ), ("pfam38.1/Pfam-A.hmm.gz", PFAM_OLD_GZ):
        found = md5_file(path)
        if found != INPUT_MD5[key]:
            raise SystemExit(f"STOP md5 {key} {found}")
    free = shutil.disk_usage(SCRATCH if SCRATCH.exists() else Path.home()).free
    if free < 8 * 1024 ** 3:
        raise SystemExit(f"STOP free bytes {free}")


def pilot() -> None:
    require_inputs()
    pool = sorted(p.name for p in (DATA / "recurrence" / "A").glob("*.faa.gz") if p.name not in EXCLUDE)
    rng = random.Random(PILOT_SEED)
    proteome = rng.choice(pool)
    if proteome != PILOT_PROTEOME:
        raise SystemExit(f"STOP pilot draw {proteome}")
    src = DATA / "recurrence" / "A" / proteome
    n_records = len(query_ids(src))
    indices = sorted(rng.sample(range(n_records), PILOT_N))
    work = SCRATCH / "pilot"
    work.mkdir(parents=True, exist_ok=True)
    queries = work / "queries.faa"
    if not queries.is_file():
        log(f"write pilot sample {proteome} n={PILOT_N}")
        write_sample(src, indices, queries)
    db_new = SCRATCH / "hmm" / "pfam38.2.hmm"
    db_old = SCRATCH / "hmm" / "pfam38.1.hmm"
    for text in (db_new, db_old):
        if not text.is_file():
            raise SystemExit(f"STOP pressed text missing {text}; press both databases first")
        press(text)
    # Stock-vs-stock on 38.2, then one 38.1.
    w1 = hmmscan(db_new, queries, work / "S382_a", None)
    w2 = hmmscan(db_new, queries, work / "S382_b", None)
    if body_lines(work / "S382_a.tbl") != body_lines(work / "S382_b.tbl") or body_lines(work / "S382_a.dom") != body_lines(work / "S382_b.dom"):
        raise SystemExit("INCONCLUSIVE stock-vs-stock failed on the pilot")
    w_old = hmmscan(db_old, queries, work / "S381", None)
    families = family_partition()
    stable = set(families["stable_names"])
    printer = Printer(compile_formatter())
    try:
        row = score_pair(
            printer, work / "S381.tbl", work / "S381.dom", work / "S382_a.tbl", work / "S382_a.dom",
            queries, work / "disc", stable,
        )
    finally:
        printer.close()
    if row["tbl"]["stock_lines"] < PILOT_FLOOR:
        label = "INCONCLUSIVE"
    else:
        label = "PILOT_OK"
    report = {
        "pilot": True,
        "protocol": "docs/BASELINES_EXACT_PROTOCOL.md",
        "git_head": git_head(),
        "seed": PILOT_SEED,
        "proteome": proteome,
        "n_records_file": n_records,
        "indices_head": indices[:10],
        "n_sample": PILOT_N,
        "host": platform.node(),
        "python": platform.python_version(),
        "hmmscan": subprocess.run([HMMSCAN, "-h"], capture_output=True, text=True).stdout.splitlines()[1],
        "cpu": int(CPU),
        "walls_are_evidence": False,
        "stock_walls_s": {"S382_a": w1, "S382_b": w2, "S381": w_old},
        "stock_vs_stock": True,
        "families": {k: families[k] for k in (
            "z_old", "z_new", "stable", "changed", "removed",
            "cksum_stable", "strict_stable_cksum_differs", "cksum_stable_strict_differs",
        )},
        "label": label,
        "result": row,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / "rescale_pilot.json"
    dest.write_text(json.dumps(report, indent=2) + "\n")
    log(f"{label} wrote {dest}")


def adopt_e1(stem: str) -> dict:
    folder = E1_WORK / stem
    stock_t = body_lines(folder / "S382.tbl")
    stock_d = body_lines(folder / "S382.dom")
    paired = (folder / "S382_a.tbl").is_file() and (folder / "S382_b.tbl").is_file()
    if paired:
        if (
            body_lines(folder / "S382_a.tbl") != body_lines(folder / "S382_b.tbl")
            or body_lines(folder / "S382_a.dom") != body_lines(folder / "S382_b.dom")
            or stock_t != body_lines(folder / "S382_a.tbl")
            or stock_d != body_lines(folder / "S382_a.dom")
        ):
            raise SystemExit(f"INCONCLUSIVE stock-vs-stock {stem}")
    return {
        "tbl": folder / "S382.tbl",
        "dom": folder / "S382.dom",
        "old_tbl": folder / "S381.tbl",
        "old_dom": folder / "S381.dom",
        "queries": folder / "queries.faa",
        "stock_vs_stock": paired,
    }


def measured() -> None:
    pilot_path = OUT_DIR / "rescale_pilot.json"
    if not pilot_path.is_file():
        raise SystemExit("STOP pilot json missing")
    pilot_report = json.loads(pilot_path.read_text())
    if pilot_report.get("label") != "PILOT_OK":
        raise SystemExit(f"STOP pilot label {pilot_report.get('label')}")
    require_inputs()
    head = git_head()
    families = family_partition()
    stable = set(families["stable_names"])
    printer = Printer(compile_formatter())
    rows = []
    try:
        for stem in E1_GENOMES:
            adopted = adopt_e1(stem)
            log(f"e1scale {stem}")
            rows.append(score_pair(
                printer, adopted["old_tbl"], adopted["old_dom"], adopted["tbl"], adopted["dom"],
                adopted["queries"], SCRATCH / "measured" / stem / "disc", stable,
            ) | {"proteome": stem, "source": "e1scale_reuse", "stock_vs_stock": adopted["stock_vs_stock"]})
        db_new = SCRATCH / "hmm" / "pfam38.2.hmm"
        db_old = SCRATCH / "hmm" / "pfam38.1.hmm"
        press(db_new)
        press(db_old)
        for index, stem in enumerate(COSTPASS):
            work = SCRATCH / "measured" / stem
            work.mkdir(parents=True, exist_ok=True)
            queries = work / "queries.faa"
            if not queries.is_file():
                write_gzip_copy(DATA / "recurrence" / "A" / f"{stem}_protein.faa.gz", queries)
            if index == 0:
                hmmscan(db_new, queries, work / "S382_a", None)
                hmmscan(db_new, queries, work / "S382_b", None)
                if body_lines(work / "S382_a.tbl") != body_lines(work / "S382_b.tbl") or body_lines(work / "S382_a.dom") != body_lines(work / "S382_b.dom"):
                    raise SystemExit("INCONCLUSIVE costpass stock-vs-stock")
                stock_tbl, stock_dom = work / "S382_a.tbl", work / "S382_a.dom"
                paired = True
            else:
                hmmscan(db_new, queries, work / "S382", None)
                stock_tbl, stock_dom = work / "S382.tbl", work / "S382.dom"
                paired = False
            hmmscan(db_old, queries, work / "S381", None)
            rows.append(score_pair(
                printer, work / "S381.tbl", work / "S381.dom", stock_tbl, stock_dom,
                queries, work / "disc", stable,
            ) | {"proteome": stem, "source": "rerun", "stock_vs_stock": paired})
    finally:
        printer.close()
    total = sum(row["tbl"]["stock_lines"] for row in rows)
    label = "INCONCLUSIVE" if total < FLOOR else "MEASURED"
    report = {
        "pilot": False,
        "protocol": "docs/BASELINES_EXACT_PROTOCOL.md",
        "git_head": head,
        "host": platform.node(),
        "python": platform.python_version(),
        "hmmscan": subprocess.run([HMMSCAN, "-h"], capture_output=True, text=True).stdout.splitlines()[1],
        "cpu": int(CPU),
        "z_new": Z_NEW,
        "z_old": Z_OLD,
        "z_factor": "30134/27481",
        "walls_are_evidence": False,
        "power_floor": FLOOR,
        "tblout_body_lines_total": total,
        "label": label,
        "pooled": {"tbl": pool_tables(rows, "tbl"), "dom": pool_tables(rows, "dom")},
        "families": {k: families[k] for k in (
            "z_old", "z_new", "stable", "changed", "removed",
            "cksum_stable", "strict_stable_cksum_differs", "cksum_stable_strict_differs",
        )},
        "proteomes": rows,
    }
    dest = OUT_DIR / "rescale.json"
    dest.write_text(json.dumps(report, indent=2) + "\n")
    log(f"{label} tbl {report['pooled']['tbl']['byte_identical']}/{report['pooled']['tbl']['stock_lines']} wrote {dest}")


def pool_tables(rows: list[dict], kind: str) -> dict:
    keys = (
        "stock_lines", "rescaler_lines", "byte_identical", "token_identical",
        "padding_only", "different_row", "missing", "extra",
    )
    pooled = {key: sum(row[kind][key] for row in rows) for key in keys}
    columns: dict[str, int] = defaultdict(int)
    classes = []
    cuts: dict[str, dict[str, int]] = {}
    for row in rows:
        for name, count in row[kind]["value_only_by_column"].items():
            columns[name] += count
        for name in row[kind]["difference_classes"]:
            if name not in classes and name != "order":
                classes.append(name)
        for cut, counts in row["cutoffs_full_sequence_E"][kind].items():
            slot = cuts.setdefault(cut, {"flip": 0, "lost": 0, "gained": 0})
            for field, count in counts.items():
                slot[field] += count
    pooled["byte_identical_over_stock"] = (
        pooled["byte_identical"] / pooled["stock_lines"] if pooled["stock_lines"] else None
    )
    pooled["wilson95"] = _wilson_dict(pooled["byte_identical"], pooled["stock_lines"])
    pooled["value_only_by_column"] = dict(columns)
    pooled["order_only"] = False
    pooled["difference_classes"] = classes
    pooled["cutoffs_full_sequence_E"] = cuts
    return pooled


def _wilson_dict(k: int, n: int) -> dict | None:
    interval = wilson(k, n)
    if interval is None:
        return None
    return {"low": interval[0], "high": interval[1]}


def write_gzip_copy(src: Path, dest: Path) -> None:
    log(f"decompress {src.name}")
    with gzip.open(src, "rt") as inp, dest.open("w") as out:
        shutil.copyfileobj(inp, out)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if mode == "selftest":
        selftest()
    elif mode == "pilot":
        pilot()
    elif mode == "measured":
        measured()
    else:
        raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    main()
