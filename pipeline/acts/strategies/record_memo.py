"""Record-level incremental memoization.

Headline: a later run pays only for records the cache has not seen.
Within-file dedup is the first-run special case of the same cache.
"""

from __future__ import annotations

import json
import random
import subprocess
from pathlib import Path

from acts.audit import AUDIT_FLOOR, AUDIT_P, AUDIT_SEED, AuditReport, pick_audit, sample_hits
from acts.cache import RecordCache
from acts.infer import identity_risk_for_argv
from acts.infer_vcf import InferError, reassemble_record, run_vcf_tool, write_vcf
from acts.fasta import read_fasta
from acts.infer_fasta import InferError as FastaInferError
from acts.infer_fasta import run_table_tool
from acts.records import DupReport, count_keys, iter_lines, probe_fasta, probe_fastq_pe, probe_lines
from acts.sample import PROBE_SEED
from acts.strategies.base import Strategy, StrategyResult
from acts.table import tables_match
from acts.vcf import bodies_equal, body_lines
from acts.vcf_memo import cached_annotate, contract_path_for, prepare_contract, read_vcf_parts
from acts.vcf_fields import cache_key

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
        audit_p: float | None = None,
        audit_seed: int = AUDIT_SEED,
        probe_n: int = 500,
        probe_seed: int = PROBE_SEED,
        verify: str = "audit",
    ):
        self.kind = kind
        self.argv = argv
        self.input_path = input_path
        self.r1 = r1
        self.r2 = r2
        self.out_dir = out_dir
        self.cache_path = cache_path
        self.unique_frac_refuse = unique_frac_refuse
        self.verify = verify if verify in {"audit", "full"} else "audit"
        self.audit_p = AUDIT_P if audit_p is None and self.verify == "audit" else (audit_p or 0.0)
        self.audit_seed = audit_seed
        self.probe_n = probe_n
        self.probe_seed = probe_seed

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
        if self.kind == "fasta":
            if self.input_path is None:
                raise ValueError("fasta needs --input")
            return probe_fasta(self.input_path)
        if self.kind == "files":
            from acts.infer_files import file_sha256, list_input_files

            if self.input_path is None:
                raise ValueError("files needs --input")
            files = list_input_files(self.input_path)
            return count_keys((file_sha256(p) for p in files), kind="files")
        if self.kind == "linetable":
            if self.input_path is None:
                raise ValueError("linetable needs --input")
            return count_keys(iter_lines(self.input_path), kind="linetable")
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
        if self.kind == "fasta" and self.argv:
            return self._run_fasta(extra)
        if self.kind == "files" and self.argv:
            return self._run_files(extra)
        if self.kind == "linetable" and self.argv:
            return self._run_linetable(extra)
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
        extra.update({"n": len(body), "verify": self.verify})
        try:
            contract = prepare_contract(
                self.argv,
                header,
                body,
                self.out_dir / "infer",
                cache_path,
                probe_n=self.probe_n,
                probe_seed=self.probe_seed,
            )
        except InferError as exc:
            rec = StrategyResult(self.name, exc.decision, exc.reason, extra)
            rec.write(self.out_dir / "decision.txt")
            return rec

        cache = RecordCache(
            cache_path, argv=self.argv, kind="vcf", extra_files=contract.traced_files
        )
        extra["cache_size"] = len(cache)
        extra["trace_status"] = contract.trace_status
        extra["traced_n"] = str(len(contract.traced_files))
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
            rec = StrategyResult(self.name, exc.decision, exc.reason, extra)
            rec.write(self.out_dir / "decision.txt")
            return rec

        extra.update({k: stats[k] for k in ("n_hits", "n_misses", "n_cache_holes")})
        (self.out_dir / "reassembled.out").write_text(rebuilt)
        extra["n_reassembled"] = len(body_lines(rebuilt))
        if stats["n_cache_holes"]:
            rec = StrategyResult(self.name, "REFUSE_MATCH", "cache hole after miss run", extra)
            rec.write(self.out_dir / "decision.txt")
            return rec

        if self.verify == "full":
            stock = run_vcf_tool(self.argv, self.input_path)
            (self.out_dir / "full.out").write_text(stock)
            extra["n_stock"] = len(body_lines(stock))
            if not bodies_equal(rebuilt, stock):
                rec = StrategyResult(
                    self.name,
                    "REFUSE_MATCH",
                    "reassembled body is not MATCH to a full run",
                    extra,
                )
                rec.write(self.out_dir / "decision.txt")
                return rec
            why = (
                f"MATCH body; hits={stats['n_hits']} misses={stats['n_misses']}; "
                f"key={','.join(contract.cache_key_fields)}"
            )
        else:
            audit = self._audit_vcf(header, stats.get("hit_records") or [], cache, contract)
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
            why = (
                f"audit p={audit.p} checked={audit.n_checked}; "
                f"hits={stats['n_hits']} misses={stats['n_misses']}; "
                f"key={','.join(contract.cache_key_fields)}"
            )

        cache.save()
        rec = StrategyResult(self.name, "SHIP", why, extra)
        rec.write(self.out_dir / "decision.txt")
        return rec

    def _run_fasta(self, extra: dict) -> StrategyResult:
        from acts.fasta_memo import cached_search, contract_path_for, prepare_table_contract

        assert self.input_path is not None
        recs = read_fasta(self.input_path)
        cache_path = self.cache_path or (self.out_dir / "cache.jsonl")
        extra.update({"n": len(recs), "verify": self.verify})
        try:
            contract = prepare_table_contract(
                self.argv,
                recs,
                self.out_dir / "infer",
                cache_path,
                probe_n=self.probe_n,
                probe_seed=self.probe_seed,
            )
        except FastaInferError as exc:
            rec = StrategyResult(self.name, exc.decision, exc.reason, extra)
            rec.write(self.out_dir / "decision.txt")
            return rec

        cache = RecordCache(
            cache_path, argv=self.argv, kind="fasta", extra_files=contract.traced_files
        )
        extra["cache_size"] = len(cache)
        extra["trace_status"] = contract.trace_status
        extra["traced_n"] = str(len(contract.traced_files))
        extra["match"] = contract.match
        extra["query_col"] = str(contract.query_col)
        try:
            rebuilt, stats = cached_search(
                recs,
                cache,
                contract,
                self.argv,
                self.out_dir / "memo",
                contract_path=contract_path_for(cache_path),
            )
            extra["late_key_probes"] = ",".join(contract.late_key_probes)
        except FastaInferError as exc:
            rec = StrategyResult(self.name, exc.decision, exc.reason, extra)
            rec.write(self.out_dir / "decision.txt")
            return rec

        extra.update({k: stats[k] for k in ("n_hits", "n_misses", "n_cache_holes")})
        (self.out_dir / "reassembled.out").write_text(rebuilt)
        extra["n_reassembled"] = len(rebuilt.splitlines())
        if stats["n_cache_holes"]:
            rec = StrategyResult(self.name, "REFUSE_MATCH", "cache hole after miss run", extra)
            rec.write(self.out_dir / "decision.txt")
            return rec

        if self.verify == "full":
            stock = run_table_tool(self.argv, self.input_path)
            (self.out_dir / "full.out").write_text(stock)
            matched = tables_match(
                rebuilt, stock, contract.match, match_ws=contract.match_ws
            )
            if not matched:
                rec = StrategyResult(
                    self.name,
                    "REFUSE_MATCH",
                    "reassembled body is not MATCH to a full run",
                    extra,
                )
                rec.write(self.out_dir / "decision.txt")
                return rec
            why = (
                f"MATCH {contract.match}; hits={stats['n_hits']} "
                f"misses={stats['n_misses']}"
            )
        else:
            audit = self._audit_fasta(stats.get("hit_recs") or [], cache, contract)
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
            why = (
                f"audit p={audit.p} checked={audit.n_checked}; "
                f"hits={stats['n_hits']} misses={stats['n_misses']}"
            )

        cache.save()
        rec = StrategyResult(self.name, "SHIP", why, extra)
        rec.write(self.out_dir / "decision.txt")
        return rec

    def _run_files(self, extra: dict) -> StrategyResult:
        from acts.files_memo import cached_files, contract_path_for, prepare_files_contract
        from acts.infer_files import InferError as FilesInferError
        from acts.infer_files import dirs_match, list_records, run_files_tool

        assert self.input_path is not None
        recs = list_records(self.input_path)
        cache_path = self.cache_path or (self.out_dir / "cache.jsonl")
        extra.update({"n": len(recs), "verify": self.verify})
        try:
            contract = prepare_files_contract(
                self.argv,
                recs,
                self.out_dir / "infer",
                cache_path,
                probe_n=self.probe_n,
                probe_seed=self.probe_seed,
            )
        except FilesInferError as exc:
            rec = StrategyResult(self.name, exc.decision, exc.reason, extra)
            rec.write(self.out_dir / "decision.txt")
            return rec

        cache = RecordCache(
            cache_path, argv=self.argv, kind="files", extra_files=contract.traced_files
        )
        extra["cache_size"] = len(cache)
        extra["trace_status"] = contract.trace_status
        extra["traced_n"] = str(len(contract.traced_files))
        extra["match"] = contract.match
        extra["stem_rule"] = contract.stem_rule
        extra["cache_key_fields"] = ",".join(contract.cache_key_fields)
        extra["widen"] = ",".join(contract.widen_history)
        extra["suffixes"] = ",".join(contract.suffixes)
        rebuilt_dir = self.out_dir / "reassembled"
        try:
            rebuilt_dir, stats = cached_files(
                recs,
                cache,
                contract,
                self.argv,
                self.out_dir / "memo",
                rebuilt_dir,
                contract_path=contract_path_for(cache_path),
            )
            extra["late_key_probes"] = ",".join(contract.late_key_probes)
        except FilesInferError as exc:
            rec = StrategyResult(self.name, exc.decision, exc.reason, extra)
            rec.write(self.out_dir / "decision.txt")
            return rec

        extra.update({k: stats[k] for k in ("n_hits", "n_misses", "n_cache_holes")})
        extra["n_reassembled"] = len(recs)
        if stats["n_cache_holes"]:
            rec = StrategyResult(self.name, "REFUSE_MATCH", "cache hole after miss run", extra)
            rec.write(self.out_dir / "decision.txt")
            return rec

        if self.verify == "full":
            stock = self.out_dir / "full"
            run_files_tool(self.argv, self.input_path, stock)
            if not dirs_match(rebuilt_dir, stock):
                rec = StrategyResult(
                    self.name,
                    "REFUSE_MATCH",
                    "reassembled files are not MATCH to a full run",
                    extra,
                )
                rec.write(self.out_dir / "decision.txt")
                return rec
            why = (
                f"MATCH bytes; hits={stats['n_hits']} misses={stats['n_misses']}; "
                f"key={','.join(contract.cache_key_fields)}"
            )
        else:
            audit = self._audit_files(stats.get("hit_recs") or [], cache, contract)
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
            why = (
                f"audit p={audit.p} checked={audit.n_checked}; "
                f"hits={stats['n_hits']} misses={stats['n_misses']}; "
                f"key={','.join(contract.cache_key_fields)}"
            )

        cache.save()
        rec = StrategyResult(self.name, "SHIP", why, extra)
        rec.write(self.out_dir / "decision.txt")
        return rec

    def _run_linetable(self, extra: dict) -> StrategyResult:
        from acts.infer_linetable import InferError as LineInferError
        from acts.infer_linetable import linetable_match, read_lines, run_linetable_tool
        from acts.linetable_memo import (
            cached_linetable,
            contract_path_for,
            prepare_linetable_contract,
        )

        assert self.input_path is not None
        lines = read_lines(self.input_path)
        cache_path = self.cache_path or (self.out_dir / "cache.jsonl")
        extra.update({"n": len(lines), "verify": self.verify})
        try:
            contract = prepare_linetable_contract(
                self.argv,
                lines,
                self.out_dir / "infer",
                cache_path,
                probe_n=self.probe_n,
                probe_seed=self.probe_seed,
            )
        except LineInferError as exc:
            rec = StrategyResult(self.name, exc.decision, exc.reason, extra)
            rec.write(self.out_dir / "decision.txt")
            return rec

        cache = RecordCache(
            cache_path, argv=self.argv, kind="linetable", extra_files=contract.traced_files
        )
        extra["cache_size"] = len(cache)
        extra["trace_status"] = contract.trace_status
        extra["traced_n"] = str(len(contract.traced_files))
        extra["match"] = contract.match
        extra["query_col"] = str(contract.query_col)
        extra["correspondence"] = contract.correspondence
        try:
            rebuilt, stats = cached_linetable(
                lines,
                cache,
                contract,
                self.argv,
                self.out_dir / "memo",
                contract_path=contract_path_for(cache_path),
            )
            extra["late_key_probes"] = ",".join(contract.late_key_probes)
        except LineInferError as exc:
            rec = StrategyResult(self.name, exc.decision, exc.reason, extra)
            rec.write(self.out_dir / "decision.txt")
            return rec

        extra.update({k: stats[k] for k in ("n_hits", "n_misses", "n_cache_holes")})
        (self.out_dir / "reassembled.out").write_text(rebuilt)
        extra["n_reassembled"] = len(rebuilt.splitlines())
        if stats["n_cache_holes"]:
            rec = StrategyResult(self.name, "REFUSE_MATCH", "cache hole after miss run", extra)
            rec.write(self.out_dir / "decision.txt")
            return rec

        if self.verify == "full":
            stock = run_linetable_tool(self.argv, self.input_path)
            (self.out_dir / "full.out").write_text(stock)
            if not linetable_match(rebuilt, stock, contract.match):
                rec = StrategyResult(
                    self.name,
                    "REFUSE_MATCH",
                    "reassembled body is not MATCH to a full run",
                    extra,
                )
                rec.write(self.out_dir / "decision.txt")
                return rec
            why = (
                f"MATCH {contract.match}; hits={stats['n_hits']} "
                f"misses={stats['n_misses']}"
            )
        else:
            audit = self._audit_linetable(stats.get("hit_recs") or [], cache, contract)
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
            why = (
                f"audit p={audit.p} checked={audit.n_checked}; "
                f"hits={stats['n_hits']} misses={stats['n_misses']}"
            )

        cache.save()
        rec = StrategyResult(self.name, "SHIP", why, extra)
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

        if self.verify == "audit":
            if hits:
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
        else:
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
            self._exec(self.argv, self.input_path, f_out)
            rebuilt = [mapping[line] for line in src]
            r_out = self.out_dir / "reassembled.out"
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

        if self.verify == "audit":
            rebuilt = [mapping[line] for line in src]
            (self.out_dir / "reassembled.out").write_text(
                "\n".join(rebuilt) + ("\n" if rebuilt else "")
            )

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

    def _audit_vcf(self, header: list[str], hits: list[str], cache, contract) -> AuditReport:
        rng = random.Random(self.audit_seed)
        chosen = pick_audit(hits, p=self.audit_p, floor=AUDIT_FLOOR, rng=rng)
        if not chosen:
            return AuditReport(n_hits=len(hits), n_checked=0, n_mismatch=0, p=self.audit_p)
        work = self.out_dir / "audit"
        path = write_vcf(work / "audit.vcf", header, chosen)
        got = run_vcf_tool(self.argv, path)
        expected_body = []
        for ln in chosen:
            raw = cache.get(cache_key(ln, contract.cache_key_fields))
            if raw is None:
                return AuditReport(n_hits=len(hits), n_checked=len(chosen), n_mismatch=1, p=self.audit_p)
            expected_body.append(reassemble_record(ln, json.loads(raw), contract))
        expected = "\n".join(header + expected_body) + "\n"
        bad = 0 if bodies_equal(got, expected) else 1
        return AuditReport(n_hits=len(hits), n_checked=len(chosen), n_mismatch=bad, p=self.audit_p)

    def _audit_fasta(self, hits: list, cache, contract) -> AuditReport:
        from acts.fasta import write_fasta
        from acts.fasta_memo import cached_search

        rng = random.Random(self.audit_seed)
        chosen = pick_audit(
            hits, p=self.audit_p, floor=AUDIT_FLOOR, rng=rng, key=lambda r: r.key
        )
        if not chosen:
            return AuditReport(n_hits=len(hits), n_checked=0, n_mismatch=0, p=self.audit_p)
        work = self.out_dir / "audit"
        path = write_fasta(work / "audit.fa", chosen)
        got = run_table_tool(self.argv, path)
        rebuilt, _ = cached_search(chosen, cache, contract, self.argv, work / "re")
        bad = 0 if tables_match(rebuilt, got, contract.match, match_ws=contract.match_ws) else 1
        return AuditReport(n_hits=len(hits), n_checked=len(chosen), n_mismatch=bad, p=self.audit_p)

    def _audit_files(self, hits: list, cache, contract) -> AuditReport:
        from acts.files_memo import cached_files
        from acts.infer_files import dirs_match, materialize, run_files_tool

        rng = random.Random(self.audit_seed)
        chosen = pick_audit(
            hits, p=self.audit_p, floor=AUDIT_FLOOR, rng=rng, key=lambda r: r.sha256 + "\t" + r.name
        )
        if not chosen:
            return AuditReport(n_hits=len(hits), n_checked=0, n_mismatch=0, p=self.audit_p)
        work = self.out_dir / "audit"
        batch_dir = work / "in"
        materialize(chosen, batch_dir)
        run_files_tool(self.argv, batch_dir, work / "got")
        rebuilt, _ = cached_files(chosen, cache, contract, self.argv, work / "re", work / "reassembled")
        bad = 0 if dirs_match(rebuilt, work / "got") else 1
        return AuditReport(n_hits=len(hits), n_checked=len(chosen), n_mismatch=bad, p=self.audit_p)

    def _audit_linetable(self, hits: list[str], cache, contract) -> AuditReport:
        from acts.infer_linetable import linetable_match, run_linetable_tool, write_lines
        from acts.linetable_memo import cached_linetable

        rng = random.Random(self.audit_seed)
        chosen = pick_audit(hits, p=self.audit_p, floor=AUDIT_FLOOR, rng=rng)
        if not chosen:
            return AuditReport(n_hits=len(hits), n_checked=0, n_mismatch=0, p=self.audit_p)
        work = self.out_dir / "audit"
        path = write_lines(work / "audit.txt", chosen)
        got = run_linetable_tool(self.argv, path)
        rebuilt, _ = cached_linetable(chosen, cache, contract, self.argv, work / "re")
        bad = 0 if linetable_match(rebuilt, got, contract.match) else 1
        return AuditReport(n_hits=len(hits), n_checked=len(chosen), n_mismatch=bad, p=self.audit_p)

    def _audit(self, hits: list[str], mapping: dict[str, str | None]) -> AuditReport:
        rng = random.Random(self.audit_seed)
        chosen = pick_audit(hits, p=self.audit_p, floor=AUDIT_FLOOR, rng=rng)
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
