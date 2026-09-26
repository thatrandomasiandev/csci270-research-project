"""Record-level incremental memoization.

Headline: a later run pays only for records the cache has not seen.
Within-file dedup is the first-run special case of the same cache.
"""

from __future__ import annotations

import random
import subprocess
from pathlib import Path

from acts.audit import AuditReport, sample_hits
from acts.cache import RecordCache
from acts.infer import identity_risk_for_argv
from acts.infer_vcf import InferError, run_vcf_tool
from acts.records import DupReport, probe_fastq_pe, probe_lines
from acts.strategies.base import Strategy, StrategyResult
from acts.vcf import bodies_equal, body_lines
from acts.vcf_memo import cached_annotate, contract_path_for, prepare_contract, read_vcf_parts

RARE = 0.95


class RecordMemo(Strategy):
    name = "record_memo"

    def __init__(
        self,
        *,
        kind: str,
        argv: list[str],
        input_path: Path | None = None,
        r1: Path | None = None,
        r2: Path | None = None,
        out_dir: Path,
        cache_path: Path | None = None,
        unique_frac_refuse: float = RARE,
        audit_p: float = 0.0,
        audit_seed: int = 0,
    ):
        self.kind = kind
        self.argv = argv
        self.input_path = input_path
        self.r1 = r1
        self.r2 = r2
        self.out_dir = out_dir
        self.cache_path = cache_path
        self.unique_frac_refuse = unique_frac_refuse
        self.audit_p = audit_p
        self.audit_seed = audit_seed

    def probe(self) -> DupReport:
        if self.kind == "fastq_pe":
            if self.r1 is None or self.r2 is None:
                raise ValueError("fastq_pe needs --r1 and --r2")
            return probe_fastq_pe(self.r1, self.r2)
        if self.kind == "lines":
            if self.input_path is None:
                raise ValueError("lines needs --input")
            return probe_lines(self.input_path)
        if self.kind == "vcf":
            if self.input_path is None:
                raise ValueError("vcf needs --input")
            return probe_lines(self.input_path)
        raise ValueError(f"unknown kind {self.kind!r}")

    def run(self) -> StrategyResult:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        risk = identity_risk_for_argv(self.argv)
        if risk and not risk.can_be_byte_identical:
            rec = StrategyResult(
                self.name,
                "REFUSE_IDENTITY",
                "; ".join(risk.reasons),
                {"tool": risk.tool},
            )
            rec.write(self.out_dir / "decision.txt")
            return rec

        report = self.probe()
        extra = {
            "n": report.n,
            "n_unique": report.n_unique,
            "unique_frac": f"{report.unique_frac:.4f}",
            "max_speedup_if_pure": f"{report.max_speedup_if_pure:.3f}",
        }

        if self.kind == "vcf" and self.argv:
            return self._run_vcf(extra)
        if self.kind != "lines" or not self.argv:
            if report.unique_frac >= self.unique_frac_refuse:
                rec = StrategyResult(
                    self.name,
                    "REFUSE_DUPS_RARE",
                    (
                        f"unique_frac={report.unique_frac:.3f} ≥ {self.unique_frac_refuse:.2f}; "
                        f"max speedup if pure is {report.max_speedup_if_pure:.3f}×."
                    ),
                    extra,
                )
            else:
                rec = StrategyResult(
                    self.name,
                    "INCOMPLETE",
                    "this kind has no memo runner yet (FASTQ→BAM is not 1:1).",
                    extra,
                )
            rec.write(self.out_dir / "decision.txt")
            return rec

        return self._run_lines(report, extra)

    def _run_vcf(self, extra: dict) -> StrategyResult:
        assert self.input_path is not None
        header, body = read_vcf_parts(self.input_path)
        cache_path = self.cache_path or (self.out_dir / "cache.jsonl")
        cache = RecordCache(cache_path, argv=self.argv, kind="vcf")
        extra.update({"n": len(body), "cache_size": len(cache)})
        try:
            contract = prepare_contract(
                self.argv, header, body, self.out_dir / "infer", cache_path
            )
        except InferError as exc:
            rec = StrategyResult(self.name, exc.decision, exc.reason, extra)
            rec.write(self.out_dir / "decision.txt")
            return rec

        extra["cache_key_fields"] = ",".join(contract.cache_key_fields)
        extra["produced_info"] = ",".join(contract.produced_info_order)
        extra["widen"] = ",".join(contract.widen_history)
        try:
            rebuilt, stats = cached_annotate(
                header,
                body,
                cache,
                contract,
                self.argv,
                self.out_dir / "memo",
                contract_path=contract_path_for(cache_path),
            )
            extra["late_key_probes"] = ",".join(contract.late_key_probes)
        except InferError as exc:
            rec = StrategyResult(self.name, exc.decision, exc.reason, {**extra, **{}})
            rec.write(self.out_dir / "decision.txt")
            return rec

        extra.update({k: stats[k] for k in ("n_hits", "n_misses", "n_cache_holes")})
        (self.out_dir / "reassembled.out").write_text(rebuilt)
        stock = run_vcf_tool(self.argv, self.input_path)
        (self.out_dir / "full.out").write_text(stock)
        extra["n_reassembled"] = len(body_lines(rebuilt))
        extra["n_stock"] = len(body_lines(stock))
        if not bodies_equal(rebuilt, stock) or stats["n_cache_holes"]:
            rec = StrategyResult(
                self.name,
                "REFUSE_MATCH",
                "reassembled body is not MATCH to a full run",
                extra,
            )
            rec.write(self.out_dir / "decision.txt")
            return rec

        cache.save()
        rec = StrategyResult(
            self.name,
            "SHIP",
            (
                f"MATCH body; hits={stats['n_hits']} misses={stats['n_misses']}; "
                f"key={','.join(contract.cache_key_fields)}"
            ),
            extra,
        )
        rec.write(self.out_dir / "decision.txt")
        return rec

    def _run_lines(self, report: DupReport, extra: dict) -> StrategyResult:
        assert self.input_path is not None
        src = self.input_path.read_text().splitlines()
        cache_path = self.cache_path or (self.out_dir / "cache.jsonl")
        cache = RecordCache(cache_path, argv=self.argv, kind=self.kind)

        unique: list[str] = []
        seen: set[str] = set()
        for line in src:
            if line not in seen:
                seen.add(line)
                unique.append(line)

        hits = [r for r in unique if cache.get(r) is not None]
        misses = [r for r in unique if cache.get(r) is None]
        miss_occ = sum(1 for line in src if cache.get(line) is None)
        miss_frac = (miss_occ / len(src)) if src else 1.0
        extra.update(
            {
                "cache_size": len(cache),
                "n_hits": len(hits),
                "n_misses": len(misses),
                "miss_frac": f"{miss_frac:.4f}",
            }
        )

        # Empty cache: first-run within-file dedup. Non-empty: incremental miss rate.
        pay_frac = report.unique_frac if len(cache) == 0 else miss_frac
        extra["pay_frac"] = f"{pay_frac:.4f}"
        extra["mode"] = "first_run" if len(cache) == 0 else "incremental"
        if pay_frac >= self.unique_frac_refuse:
            rec = StrategyResult(
                self.name,
                "REFUSE_DUPS_RARE",
                (
                    f"{extra['mode']} pay_frac={pay_frac:.3f} ≥ {self.unique_frac_refuse:.2f}; "
                    "almost every record is new, so a whole-command cache would do as well."
                ),
                extra,
            )
            rec.write(self.out_dir / "decision.txt")
            return rec

        miss_out_lines: list[str] = []
        if misses:
            u_in = self.out_dir / "miss.txt"
            u_out = self.out_dir / "miss.out"
            u_in.write_text("\n".join(misses) + ("\n" if misses else ""))
            self._exec(self.argv, u_in, u_out)
            miss_out_lines = u_out.read_text().splitlines()
            if len(miss_out_lines) != len(misses):
                rec = StrategyResult(
                    self.name,
                    "REFUSE_MATCH",
                    f"tool is not 1:1 on misses ({len(miss_out_lines)} outs / {len(misses)} ins)",
                    extra,
                )
                rec.write(self.out_dir / "decision.txt")
                return rec
            for rec_in, rec_out in zip(misses, miss_out_lines):
                cache.put(rec_in, rec_out)

        mapping = {r: cache.get(r) for r in unique}
        if any(v is None for v in mapping.values()):
            rec = StrategyResult(self.name, "REFUSE_MATCH", "cache hole after miss run", extra)
            rec.write(self.out_dir / "decision.txt")
            return rec

        if self.audit_p > 0 and hits:
            audit = self._audit(hits, mapping)
            extra["audit_checked"] = audit.n_checked
            extra["audit_mismatch"] = audit.n_mismatch
            if not audit.ok:
                rec = StrategyResult(
                    self.name,
                    "REFUSE_AUDIT",
                    f"{audit.n_mismatch} mismatched hit(s) of {audit.n_checked} re-executed",
                    extra,
                )
                rec.write(self.out_dir / "decision.txt")
                return rec

        f_out = self.out_dir / "full.out"
        r_out = self.out_dir / "reassembled.out"
        self._exec(self.argv, self.input_path, f_out)
        rebuilt = [mapping[line] for line in src]
        r_out.write_text("\n".join(rebuilt) + ("\n" if rebuilt else ""))
        if r_out.read_bytes() != f_out.read_bytes():
            rec = StrategyResult(
                self.name,
                "REFUSE_MATCH",
                "reassembled output is not byte-identical to a full run",
                extra,
            )
            rec.write(self.out_dir / "decision.txt")
            return rec

        cache.save()
        rec = StrategyResult(
            self.name,
            "SHIP",
            (
                f"MATCH byte-identical; miss_frac={miss_frac:.3f}; "
                f"{len(misses)} new / {len(unique)} distinct; cache={len(cache)}"
            ),
            extra,
        )
        rec.write(self.out_dir / "decision.txt")
        return rec

    def _audit(self, hits: list[str], mapping: dict[str, str | None]) -> AuditReport:
        rng = random.Random(self.audit_seed)
        chosen = sample_hits(hits, p=self.audit_p, rng=rng)
        bad = 0
        if chosen:
            a_in = self.out_dir / "audit.in"
            a_out = self.out_dir / "audit.out"
            a_in.write_text("\n".join(chosen) + "\n")
            self._exec(self.argv, a_in, a_out)
            got = a_out.read_text().splitlines()
            for rec_in, rec_out in zip(chosen, got):
                if rec_out != mapping[rec_in]:
                    bad += 1
        return AuditReport(n_hits=len(hits), n_checked=len(chosen), n_mismatch=bad, p=self.audit_p)

    def _exec(self, argv: list[str], stdin_path: Path, stdout_path: Path) -> None:
        with stdin_path.open() as inf, stdout_path.open("w") as outf:
            subprocess.run(argv, check=True, stdin=inf, stdout=outf, text=True)
