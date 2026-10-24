#!/usr/bin/env python3
"""Prepare Semgrep measured assets: corpus (seed 20261351) + release chain (20261352).

Writes under --out (default ~/tmp/tare_semgrep_measured/). Does not run Semgrep
timing. Safe to run on a laptop; rsync the out dir to CARC staging.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from acts.reference_yaml import parse_yaml_list_text  # noqa: E402

CORPUS_SEED = 20261351
RELEASE_SEED = 20261352
N_FILES = 1000
POWER_FLOOR = 500


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_prior_exclusions() -> tuple[set[str], set[str]]:
    """Return (excluded_paths, excluded_content_hashes) from G1/P2/W2."""
    paths: set[str] = set()
    hashes: set[str] = set()
    home = Path.home()

    g1 = home / "tmp" / "tare_g1" / "semgrep" / "target"
    if g1.is_dir():
        for p in g1.rglob("*.py"):
            paths.add(str(p.resolve()))
            hashes.add(sha256_file(p))

    for corpus in (
        home / "tmp" / "tare_semgrep_p2" / "corpus",
        home / "tmp" / "w2" / "positive",  # may not hold files; skip if absent
    ):
        files_dir = corpus / "files"
        path_list = corpus / "path_list.txt"
        if path_list.is_file():
            for ln in path_list.read_text().splitlines():
                ln = ln.strip()
                if ln:
                    paths.add(ln)
        if files_dir.is_dir():
            for p in files_dir.glob("*.py"):
                hashes.add(sha256_file(p))
        manifest = corpus / "manifest.json"
        if manifest.is_file():
            data = json.loads(manifest.read_text())
            for entry in data.get("files") or []:
                if isinstance(entry, dict):
                    if entry.get("sha256"):
                        hashes.add(entry["sha256"])
                    if entry.get("src_path"):
                        paths.add(entry["src_path"])
                    if entry.get("path"):
                        paths.add(entry["path"])
    return paths, hashes


def discover_pool(site_packages: Path) -> list[Path]:
    out: list[Path] = []
    for p in site_packages.rglob("*.py"):
        if not p.is_file():
            continue
        # Skip caches / huge generated trees that are unstable.
        parts = set(p.parts)
        if "__pycache__" in parts or "site-packages" not in str(p):
            continue
        out.append(p)
    return out


def build_corpus(
    out: Path,
    *,
    site_packages: Path,
    n: int = N_FILES,
    seed: int = CORPUS_SEED,
) -> dict:
    excl_paths, excl_hashes = collect_prior_exclusions()
    pool = discover_pool(site_packages)
    eligible: list[Path] = []
    skipped_path = 0
    skipped_hash = 0
    for p in pool:
        sp = str(p.resolve())
        if sp in excl_paths:
            skipped_path += 1
            continue
        digest = sha256_file(p)
        if digest in excl_hashes:
            skipped_hash += 1
            continue
        eligible.append(p)
    if len(eligible) < n:
        raise SystemExit(
            f"eligible pool {len(eligible)} < {n} "
            f"(skipped path={skipped_path} hash={skipped_hash})"
        )
    rng = random.Random(seed)
    chosen = sorted(rng.sample(eligible, n), key=lambda p: str(p))
    files_dir = out / "corpus" / "files"
    if files_dir.exists():
        shutil.rmtree(files_dir)
    files_dir.mkdir(parents=True)
    records: list[str] = []
    path_list: list[str] = []
    manifest_files: list[dict] = []
    for i, src in enumerate(chosen):
        dst = files_dir / f"{i:04d}.py"
        data = src.read_bytes()
        dst.write_bytes(data)
        records.append(str(dst.resolve()))
        path_list.append(str(src.resolve()))
        manifest_files.append(
            {
                "index": i,
                "dst": dst.name,
                "src_path": str(src.resolve()),
                "sha256": sha256_bytes(data),
                "bytes": len(data),
            }
        )
    records_path = out / "corpus" / "records.txt"
    path_list_path = out / "corpus" / "path_list.txt"
    records_path.write_text("\n".join(records) + "\n")
    path_list_path.write_text("\n".join(path_list) + "\n")
    meta = {
        "seed": seed,
        "n_files": n,
        "site_packages": str(site_packages),
        "eligible_pool": len(eligible),
        "skipped_path": skipped_path,
        "skipped_hash": skipped_hash,
        "excl_paths_n": len(excl_paths),
        "excl_hashes_n": len(excl_hashes),
        "manifest_sha256": sha256_bytes(
            json.dumps(manifest_files, sort_keys=True).encode()
        ),
        "path_list_sha256": sha256_file(path_list_path),
        "records_sha256": sha256_file(records_path),
        "disjoint_from": [
            "G1 ~/tmp/tare_g1/semgrep/target (path+sha256)",
            "P2 ~/tmp/tare_semgrep_p2/corpus (path+sha256)",
        ],
    }
    (out / "corpus" / "manifest.json").write_text(
        json.dumps({"seed": seed, "n": n, "files": manifest_files, "meta": meta}, indent=2)
        + "\n"
    )
    (out / "corpus" / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


_ID_LINE = re.compile(r"^(\s*- id:\s*)(\S+)(.*)$", re.M)


def _normalize_rules_yaml(text: str) -> str:
    """Drop comment/blank lines between ``rules:`` and the first list item.

    Some older semgrep-rules files put a comment there; yaml-list parse refuses it.
    """
    lines = text.splitlines(True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        out.append(lines[i])
        if lines[i].rstrip("\n") == "rules:" or lines[i].rstrip("\n") == "rules: ":
            i += 1
            while i < len(lines):
                stripped = lines[i].lstrip()
                if stripped.startswith("- "):
                    break
                if stripped == "" or stripped.startswith("#"):
                    i += 1
                    continue
                break
            continue
        i += 1
    return "".join(out)


def _dedent_item(raw: str) -> str:
    """Match acts.reference_yaml._dedent_item for mixed indent sources."""
    lines = raw.splitlines(True)
    if not lines:
        return raw
    first = lines[0]
    if first.startswith("- "):
        return raw
    # Common: two-space indent before '- id:'
    if first.lstrip(" ").startswith("- "):
        pad = len(first) - len(first.lstrip(" "))
        out = [first[pad:]]
        for ln in lines[1:]:
            if ln.startswith(" " * pad):
                out.append(ln[pad:])
            else:
                out.append(ln)
        return "".join(out)
    return raw


def _split_rule_items(text: str) -> tuple[str, list[str]]:
    """Split a rules YAML into header + raw item strings (tolerant of dup ids)."""
    text = _normalize_rules_yaml(text)
    lines = text.splitlines(True)
    # Find 'rules:' line
    header_end = None
    for i, ln in enumerate(lines):
        if ln.rstrip("\n") in ("rules:", "rules: "):
            header_end = i + 1
            break
    if header_end is None:
        raise ValueError("no rules: header")
    header = "".join(lines[:header_end])
    items: list[str] = []
    cur: list[str] = []
    for ln in lines[header_end:]:
        if ln.startswith("- ") and cur:
            items.append("".join(cur))
            cur = [ln]
        elif ln.startswith("- "):
            cur = [ln]
        else:
            if not cur and ln.strip() == "":
                continue
            cur.append(ln)
    if cur:
        items.append("".join(cur))
    return header, items


def _item_bare_id(raw: str) -> str:
    m = _ID_LINE.search(raw)
    if not m:
        raise ValueError("item missing id")
    return m.group(2)


def qualify_concat(paths: list[Path], *, commit: str, seed: int) -> tuple[str, dict]:
    """Concatenate python rules; path-qualify duplicate bare ids."""
    bare_counts: dict[str, int] = defaultdict(int)
    parsed: list[tuple[Path, str, str]] = []
    for path in sorted(paths):
        try:
            _header, items = _split_rule_items(path.read_text())
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"split failed {path}: {exc}") from exc
        for raw in items:
            try:
                bare = _item_bare_id(raw)
            except Exception as exc:  # noqa: BLE001
                raise SystemExit(f"id failed {path}: {exc}") from exc
            bare_counts[bare] += 1
            parsed.append((path, bare, raw))

    dup_bares = {b for b, c in bare_counts.items() if c > 1}
    quals: list[dict] = []
    chunks: list[str] = []
    seen: set[str] = set()
    n_qualified = 0
    occ_counter: dict[tuple[str, str], int] = defaultdict(int)
    for path, bare, raw in parsed:
        s = str(path)
        rel_path = "python/" + s.split("/python/", 1)[1] if "/python/" in s else path.name
        if bare in dup_bares:
            qual = rel_path.replace("/", ".").removesuffix(".yaml").removesuffix(".yml")
            base = f"{qual}__{bare}"
            occ_counter[(rel_path, bare)] += 1
            occ = occ_counter[(rel_path, bare)]
            new_id = f"{base}.{occ}"
            n_qualified += 1
            quals.append(
                {
                    "bare": bare,
                    "path": rel_path,
                    "qualified": new_id,
                    "occurrence": occ,
                }
            )
        else:
            new_id = bare
        if new_id in seen:
            new_id = f"{new_id}.{sha256_bytes((rel_path + raw[:80]).encode())[:8]}"
        seen.add(new_id)

        item = _dedent_item(raw)
        item, n_sub = _ID_LINE.subn(rf"\g<1>{new_id}\3", item, count=1)
        if n_sub != 1:
            raise SystemExit(f"id rewrite failed for {rel_path} bare={bare}")
        if "tare_source_path:" not in item:
            if re.search(r"^(\s*)metadata:\s*$", item, re.M):
                item = re.sub(
                    r"^(\s*)metadata:\s*$",
                    rf"\1metadata:\n\1  tare_source_path: {rel_path}",
                    item,
                    count=1,
                    flags=re.M,
                )
            else:
                item = _ID_LINE.sub(
                    rf"\g<0>\n  metadata:\n    tare_source_path: {rel_path}",
                    item,
                    count=1,
                )
        if not item.endswith("\n"):
            item += "\n"
        if not item.startswith("-"):
            raise SystemExit(f"item not list-shaped: {rel_path}")
        chunks.append(item)

    header = (
        f"# TARE measured concat python rules commit={commit} "
        f"seed={seed} n_rules={len(chunks)}\n"
    )
    text = header + "rules:\n" + "".join(chunks)
    # Round-trip check
    parse_yaml_list_text(text)
    meta = {
        "commit": commit,
        "n_files": len(paths),
        "n_rules": len(chunks),
        "n_dupes_qualified": n_qualified,
        "duplicate_bare_ids": sorted(dup_bares),
        "id_qualification": quals,
        "sha256": sha256_bytes(text.encode()),
        "bytes": len(text.encode()),
    }
    return text, meta


def list_python_rule_commits(rules_repo: Path, *, max_commits: int = 5000) -> list[str]:
    """Newest-first commits that touch ≥1 python/**/*.yaml."""
    cmd = [
        "git",
        "-C",
        str(rules_repo),
        "log",
        f"--max-count={max_commits}",
        "--pretty=%H",
        "--",
        "python/",
    ]
    out = subprocess.check_output(cmd, text=True)
    commits = [ln.strip() for ln in out.splitlines() if ln.strip()]
    kept: list[str] = []
    for c in commits:
        names = subprocess.check_output(
            [
                "git",
                "-C",
                str(rules_repo),
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                c,
                "--",
                "python/",
            ],
            text=True,
        )
        if any(n.endswith((".yaml", ".yml")) and "/test" not in n for n in names.splitlines()):
            kept.append(c)
    return kept


def select_release_chain(rules_repo: Path, *, seed: int = RELEASE_SEED) -> dict:
    newest_first = list_python_rule_commits(rules_repo)
    # Need three consecutive in chronological order = three consecutive in
    # reversed newest-first list, i.e. windows of length 3 in newest-first
    # where window[0] is newest.
    if len(newest_first) < 3:
        raise SystemExit(f"need ≥3 python-rule commits, found {len(newest_first)}")
    # Windows: (newer, mid, older) as newest-first triples that are consecutive.
    windows = [
        (newest_first[i], newest_first[i + 1], newest_first[i + 2])
        for i in range(len(newest_first) - 2)
    ]
    rng = random.Random(seed)
    idx = rng.randrange(len(windows))
    newer, mid, older = windows[idx]
    # Return oldest → newest for fill→update chain.
    chain = [older, mid, newer]
    subjects = []
    for c in chain:
        subj = subprocess.check_output(
            ["git", "-C", str(rules_repo), "log", "-1", "--pretty=%s", c],
            text=True,
        ).strip()
        subjects.append(subj)
    return {
        "seed": seed,
        "n_candidate_windows": len(windows),
        "window_index": idx,
        "commits_oldest_to_newest": chain,
        "subjects": subjects,
        "n_python_rule_commits_scanned": len(newest_first),
    }


def checkout_python_yamls(rules_repo: Path, commit: str, dest: Path) -> list[Path]:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    # sparse checkout via git archive
    subprocess.check_call(
        ["git", "-C", str(rules_repo), "archive", commit, "python"],
        stdout=open(dest / "archive.tar", "wb"),
    )
    subprocess.check_call(["tar", "-xf", str(dest / "archive.tar"), "-C", str(dest)])
    (dest / "archive.tar").unlink(missing_ok=True)
    paths = sorted(
        p
        for p in (dest / "python").rglob("*.yaml")
        if "/test" not in str(p) and p.is_file()
    )
    paths += sorted(
        p
        for p in (dest / "python").rglob("*.yml")
        if "/test" not in str(p) and p.is_file()
    )
    return sorted(set(paths))


def build_releases(out: Path, rules_repo: Path, *, seed: int = RELEASE_SEED) -> dict:
    sel = select_release_chain(rules_repo, seed=seed)
    rules_out = out / "rules"
    rules_out.mkdir(parents=True, exist_ok=True)
    releases = []
    for commit in sel["commits_oldest_to_newest"]:
        tree = rules_out / f"tree_{commit[:12]}"
        paths = checkout_python_yamls(rules_repo, commit, tree)
        text, meta = qualify_concat(paths, commit=commit, seed=seed)
        yaml_path = rules_out / f"rules_{commit[:12]}.yaml"
        yaml_path.write_text(text)
        meta["path"] = str(yaml_path)
        meta["tree"] = str(tree)
        releases.append(meta)
    payload = {"selection": sel, "releases": releases}
    (rules_out / "meta.json").write_text(json.dumps(payload, indent=2) + "\n")
    (out / "release_chain.json").write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        type=Path,
        default=Path.home() / "tmp" / "tare_semgrep_measured",
    )
    ap.add_argument(
        "--rules-repo",
        type=Path,
        default=Path.home() / "tmp" / "tare_g1" / "rules",
    )
    ap.add_argument(
        "--site-packages",
        type=Path,
        default=Path(
            "/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages"
        ),
    )
    ap.add_argument("--skip-corpus", action="store_true")
    ap.add_argument("--skip-releases", action="store_true")
    ap.add_argument("--fetch-rules-depth", type=int, default=0, help="git fetch --depth N")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    if args.fetch_rules_depth > 0:
        subprocess.check_call(
            [
                "git",
                "-C",
                str(args.rules_repo),
                "fetch",
                "--depth",
                str(args.fetch_rules_depth),
                "origin",
                "develop",
            ]
        )

    summary: dict = {"corpus_seed": CORPUS_SEED, "release_seed": RELEASE_SEED}
    if not args.skip_corpus:
        summary["corpus"] = build_corpus(
            args.out, site_packages=args.site_packages, seed=CORPUS_SEED
        )
    if not args.skip_releases:
        summary["releases"] = build_releases(
            args.out, args.rules_repo, seed=RELEASE_SEED
        )
    (args.out / "prepare_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
