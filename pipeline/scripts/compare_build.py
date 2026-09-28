#!/usr/bin/env python3
"""Build HMMER stock/tuned prefixes and a SnpEff AppCDS archive.

Locked by docs/COMPARISON_PROTOCOL.md. Local only. No Pfam. No timing.
PGO trains on data_compare/pgo_train.faa, never on the MATCH test FASTA
and never on the savings collections.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDS = ROOT / "builds"
DATA = ROOT / "data_compare"
SNPEFF_JAR = ROOT / "tools" / "snpEff" / "snpEff.jar"
SNPEFF_DATA = ROOT / "tools" / "snpEff" / "data"
EXAMPLE_VCF = ROOT / "tools" / "snpEff" / "examples" / "test.chr22.vcf"

HMMER_URLS = (
    "http://eddylab.org/software/hmmer/hmmer-3.4.tar.gz",
    "http://eddylab.org/software/hmmer3/3.4/hmmer-3.4.tar.gz",
)
MAX_TARBALL_BYTES = 80 * 1024 * 1024
N_VCF = 24
JOBS = str(os.cpu_count() or 2)

# Train proteome ≠ test proteome. Hand-written fragments, not collections A/B.
PGO_TRAIN_FAA = """\
>TRAIN_g1
MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSHGSAQVKGHGKKVADALTNAVAHVDDMPNALSALSDLHAHKLRVDPVNFKLLSHCLLVTLAAHLPAEFTPAVHASLDKFLASVSTVLTSKYR
>TRAIN_g2
MVLSGEDKSNIKAAWGKIGGHGAEYGAEALERMFASFPTTKTYFPHFDVSHGSAQVKGHGKKVADALTNAVAHVDDMPNALSALSDLHAHKLRVDPVNFKLLSHCLLVTLACHHPAEFTPAVHASLDKFLASVSTVLTSKYR
>TRAIN_g3
MVLSAADKTNVKAAWSKVGGHAGEYGAEALERMFLGFPTTKTYFPHFDLSHGSAQVKGHGKKVADALTNAVAHVDDMPNALSALSDLHAHKLRVDPVNFKLLSHCLLVTLAAHLPAEFTPAVHASLDKFLASVSTVLTSKYR
>TRAIN_k1
MKILITGSSGIGKSTLLKLIAGELKPTGGTVLLDGADPQSIQDRLYQELKEINVDIVDNLNVDLDERNLKELLKE
>TRAIN_k2
MKILVTGSSGIGKTTLLRLIAGELKPTGGTVLLDGADPQSIQDRLYQELKEINVDIVDNLNVDLDERNLKELLKE
>TRAIN_k3
MKVLITGSSGIGKSTLLKLIAGELKATGGTVLLDGADPQSIQDRLYAELKEINVDIVDNLNVDLDERNLKELLKE
"""

TEST_FAA = """\
>TEST_gA
MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSHGSAQVKAHGKKVADALTNAVAHVDDMPNALSALSDLHAHKLRVDPVNFKLLSHCLLVTLAAHLPAEFTPAVHASLDKFLASVSTVLTSKYR
>TEST_gB
MVLSGEDKSNIKAAWGKIGGHGAEYGAEALERMFASFPTTKTYFPHFDVSHGSAQVKGHGKKVADALTNAVAHVEDMPNALSALSDLHAHKLRVDPVNFKLLSHCLLVTLACHHPAEFTPAVHASLDKFLASVSTVLTSKYR
>TEST_kA
MKILITGSSGIGKSTLLKLIAGELKPTGGTVLLDGADPQSIQDRLYQELKEINVDIVDNLNVDLDERNLKELLKE
>TEST_kB
MKVLITGASGIGKSTLLKLIAGELKATGGTVLLDGADPQSIQDRLYAELKEINVDIVDNLNVDLDERNLKELLKE
>TEST_unrelated
MSEQNNTEMTFQIQRIYTKDISFEAPNAPHVFQKDWQPEVKLDLDTASSQLADDVYEVVLRVRRSA
"""

FAMILIES = {
    "globin_toy": [
        "TRAIN_g1",
        "TRAIN_g2",
        "TRAIN_g3",
    ],
    "gxxxxgk_toy": [
        "TRAIN_k1",
        "TRAIN_k2",
        "TRAIN_k3",
    ],
}


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        check=check,
        text=True,
        capture_output=False,
    )


def parse_faa(text: str) -> dict[str, str]:
    recs: dict[str, str] = {}
    name = ""
    chunks: list[str] = []
    for ln in text.splitlines():
        if ln.startswith(">"):
            if name:
                recs[name] = "".join(chunks)
            name = ln[1:].split()[0]
            chunks = []
        else:
            chunks.append(ln.strip())
    if name:
        recs[name] = "".join(chunks)
    return recs


def write_stockholm(dest: Path, family: str, recs: dict[str, str], names: list[str]) -> None:
    lines = ["# STOCKHOLM 1.0", f"#=GF ID {family}"]
    width = max(len(n) for n in names) + 2
    for n in names:
        lines.append(f"{n.ljust(width)}{recs[n]}")
    lines.append("//")
    dest.write_text("\n".join(lines) + "\n")


def insert_ga(hmm_text: str, ga: float = 10.0) -> str:
    lines = hmm_text.splitlines(keepends=True)
    out: list[str] = []
    inserted = False
    ga_line = f"GA    {ga:.2f} {ga:.2f}\nTC    {ga + 1:.2f} {ga + 1:.2f}\nNC    {ga - 1:.2f} {ga - 1:.2f}\n"
    for ln in lines:
        if not inserted and (ln.startswith("HMM ") or ln == "HMM\n"):
            if not any(x.startswith("GA") for x in out[-8:]):
                out.append(ga_line)
            inserted = True
        out.append(ln)
    if not inserted:
        raise RuntimeError("HMM line not found; cannot attach GA cutoffs")
    return "".join(out)


def download_hmmer(tarball: Path) -> None:
    if tarball.is_file() and 1_000_000 < tarball.stat().st_size < MAX_TARBALL_BYTES:
        print(f"reusing {tarball} ({tarball.stat().st_size} bytes)", flush=True)
        return
    tarball.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for url in HMMER_URLS:
        tmp = tarball.with_suffix(tarball.suffix + ".part")
        try:
            print(f"downloading {url}", flush=True)
            req = urllib.request.Request(url, headers={"User-Agent": "ACTS-compare/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                got = 0
                with tmp.open("wb") as fh:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        got += len(chunk)
                        if got > MAX_TARBALL_BYTES:
                            raise RuntimeError(f"tarball exceeded {MAX_TARBALL_BYTES} bytes")
                        fh.write(chunk)
            if got < 1_000_000:
                raise RuntimeError(f"tarball too small: {got} bytes")
            tmp.replace(tarball)
            print(f"saved {tarball} ({got} bytes)", flush=True)
            return
        except Exception as exc:  # noqa: BLE001 — try the next mirror
            last_err = exc
            print(f"failed {url}: {exc}", flush=True)
            if tmp.is_file():
                tmp.unlink()
    raise RuntimeError(f"could not download HMMER 3.4: {last_err}")


def extract_hmmer(tarball: Path, dest: Path) -> Path:
    if dest.is_dir() and (dest / "configure").is_file():
        return dest
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball, "r:gz") as tar:
        tar.extractall(dest.parent)
    extracted = dest.parent / "hmmer-3.4"
    if extracted.resolve() != dest.resolve():
        if dest.exists():
            shutil.rmtree(dest)
        extracted.rename(dest)
    if not (dest / "configure").is_file():
        raise RuntimeError(f"configure missing under {dest}")
    return dest


def copy_src(src: Path, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, symlinks=True)
    return dest


def configure_make_install(
    src: Path,
    prefix: Path,
    *,
    cflags: str,
    ldflags: str,
    env_extra: dict[str, str] | None = None,
) -> None:
    if prefix.exists():
        shutil.rmtree(prefix)
    prefix.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    run(
        [
            str(src / "configure"),
            f"--prefix={prefix}",
            f"CFLAGS={cflags}",
            f"LDFLAGS={ldflags}",
        ],
        cwd=src,
        env=env,
    )
    run(["make", f"-j{JOBS}"], cwd=src, env=env)
    run(["make", "install"], cwd=src, env=env)
    for name in ("hmmscan", "hmmsearch", "hmmbuild", "hmmpress"):
        bin_path = prefix / "bin" / name
        if not bin_path.is_file():
            raise RuntimeError(f"missing {bin_path}")


def llvm_profdata() -> str:
    for cand in ("llvm-profdata", "xcrun"):
        if cand == "xcrun":
            r = subprocess.run(
                ["xcrun", "--find", "llvm-profdata"],
                capture_output=True,
                text=True,
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
            continue
        path = shutil.which(cand)
        if path:
            return path
    brew = shutil.which("brew")
    if brew:
        r = subprocess.run(
            [brew, "--prefix", "llvm"],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            p = Path(r.stdout.strip()) / "bin" / "llvm-profdata"
            if p.is_file():
                return str(p)
    raise RuntimeError("llvm-profdata not found; cannot complete PGO")


def pgo_train(prefix: Path, hmm: Path, faa: Path) -> None:
    env = os.environ.copy()
    raw_dir = BUILDS / "pgo-raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for old in raw_dir.glob("*.profraw"):
        old.unlink()
    env["LLVM_PROFILE_FILE"] = str(raw_dir / "%p.profraw")
    scan_tbl = DATA / "pgo.hmmscan.tbl"
    search_tbl = DATA / "pgo.hmmsearch.tbl"
    run(
        [
            str(prefix / "bin" / "hmmscan"),
            "--cpu",
            "1",
            "--cut_ga",
            "--noali",
            "--tblout",
            str(scan_tbl),
            str(hmm),
            str(faa),
        ],
        env=env,
    )
    run(
        [
            str(prefix / "bin" / "hmmsearch"),
            "--cpu",
            "1",
            "--noali",
            "-Z",
            "1000000",
            "--domZ",
            "1000000",
            "--tblout",
            str(search_tbl),
            str(hmm),
            str(faa),
        ],
        env=env,
    )
    raw = list(raw_dir.glob("*.profraw"))
    if not raw:
        raise RuntimeError("PGO produced no .profraw files")
    merged = BUILDS / "pgo.profdata"
    run([llvm_profdata(), "merge", "-o", str(merged), *[str(p) for p in raw]])
    if not merged.is_file() or merged.stat().st_size < 16:
        raise RuntimeError("llvm-profdata merge produced an empty profile")


def build_models(hmmbuild: Path, hmmpress: Path, faa: Path, dest_hmm: Path) -> None:
    recs = parse_faa(faa.read_text())
    parts: list[str] = []
    tmp = dest_hmm.parent / "families"
    tmp.mkdir(parents=True, exist_ok=True)
    for fam, names in FAMILIES.items():
        sto = tmp / f"{fam}.sto"
        raw_hmm = tmp / f"{fam}.hmm"
        write_stockholm(sto, fam, recs, names)
        run(
            [
                str(hmmbuild),
                "--amino",
                "-n",
                fam,
                str(raw_hmm),
                str(sto),
            ]
        )
        parts.append(insert_ga(raw_hmm.read_text()))
    dest_hmm.write_text("".join(parts))
    run([str(hmmpress), "-f", str(dest_hmm)])


def write_small_vcf(dest: Path) -> int:
    if not EXAMPLE_VCF.is_file():
        raise RuntimeError(f"missing example VCF {EXAMPLE_VCF}")
    header: list[str] = []
    body: list[str] = []
    for ln in EXAMPLE_VCF.read_text().splitlines():
        if ln.startswith("#"):
            header.append(ln)
            continue
        if ln.strip():
            body.append(ln)
        if len(body) >= N_VCF:
            break
    if len(body) < 5:
        raise RuntimeError("example VCF too short for MATCH")
    dest.write_text("\n".join(header + body) + "\n")
    return len(body)


def snpeff_cmd(archive: Path | None, extra_java: list[str], vcf: Path) -> list[str]:
    cmd = ["java", "-Xmx2g", *extra_java]
    if archive is not None:
        cmd.extend(
            [
                f"-XX:SharedArchiveFile={archive}",
                "-Xshare:on",
            ]
        )
    cmd.extend(
        [
            "-jar",
            str(SNPEFF_JAR),
            "-dataDir",
            str(SNPEFF_DATA),
            "-noStats",
            "-noLog",
            "GRCh38.86",
            str(vcf),
        ]
    )
    return cmd


def dump_snpeff_cds(vcf: Path, archive: Path) -> None:
    if not SNPEFF_JAR.is_file():
        raise RuntimeError(f"missing SnpEff jar at {SNPEFF_JAR}")
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        archive.unlink()
    dump_out = archive.with_suffix(".dump.vcf")
    dump_err = archive.with_suffix(".dump.err")
    cmd = [
        "java",
        "-Xmx2g",
        f"-XX:ArchiveClassesAtExit={archive}",
        "-XX:TieredStopAtLevel=1",
        "-jar",
        str(SNPEFF_JAR),
        "-dataDir",
        str(SNPEFF_DATA),
        "-noStats",
        "-noLog",
        "GRCh38.86",
        str(vcf),
    ]
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    dump_out.write_text(proc.stdout)
    dump_err.write_text(proc.stderr)
    if not archive.is_file() or archive.stat().st_size < 1024:
        raise RuntimeError(f"AppCDS archive missing or tiny: {archive}")


def prepare_inputs() -> dict[str, Path]:
    DATA.mkdir(parents=True, exist_ok=True)
    BUILDS.mkdir(parents=True, exist_ok=True)
    train = DATA / "pgo_train.faa"
    test = DATA / "match_test.faa"
    vcf = DATA / "match_test.vcf"
    train.write_text(PGO_TRAIN_FAA)
    test.write_text(TEST_FAA)
    write_small_vcf(vcf)
    return {"train": train, "test": test, "vcf": vcf}


def build_all() -> dict[str, str]:
    paths = prepare_inputs()
    tarball = BUILDS / "hmmer-3.4.tar.gz"
    src = BUILDS / "hmmer-3.4-src"
    download_hmmer(tarball)
    extract_hmmer(tarball, src)

    stock_src = copy_src(src, BUILDS / "hmmer-stock-src")
    stock_prefix = BUILDS / "hmmer-stock"
    configure_make_install(
        stock_src,
        stock_prefix,
        cflags="-O2",
        ldflags="",
    )

    hmm = DATA / "toy.hmm"
    build_models(stock_prefix / "bin" / "hmmbuild", stock_prefix / "bin" / "hmmpress", paths["train"], hmm)

    gen_src = copy_src(src, BUILDS / "hmmer-pgo-gen-src")
    gen_prefix = BUILDS / "hmmer-pgo-gen"
    configure_make_install(
        gen_src,
        gen_prefix,
        cflags="-O3 -march=native -fprofile-instr-generate",
        ldflags="-fprofile-instr-generate",
    )
    pgo_train(gen_prefix, hmm, paths["train"])
    profdata = BUILDS / "pgo.profdata"

    tuned_src = copy_src(src, BUILDS / "hmmer-tuned-src")
    tuned_prefix = BUILDS / "hmmer-tuned"
    configure_make_install(
        tuned_src,
        tuned_prefix,
        cflags=(
            "-O3 -march=native -flto "
            f"-fprofile-instr-use={profdata}"
        ),
        ldflags="-flto",
    )

    archive = BUILDS / "snpeff" / "snpeff.jsa"
    dump_snpeff_cds(paths["vcf"], archive)

    return {
        "hmmer_stock": str(stock_prefix / "bin"),
        "hmmer_tuned": str(tuned_prefix / "bin"),
        "snpeff_cds": str(archive),
        "toy_hmm": str(hmm),
        "train_faa": str(paths["train"]),
        "test_faa": str(paths["test"]),
        "test_vcf": str(paths["vcf"]),
        "hmmer_tarball_bytes": str((BUILDS / "hmmer-3.4.tar.gz").stat().st_size),
    }


def main() -> int:
    info = build_all()
    for k, v in info.items():
        print(f"{k}={v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
