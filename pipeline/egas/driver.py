"""Lock → Amdahl → automated rungs → MATCH bake-off → ship / refuse / propose."""

from __future__ import annotations

from pathlib import Path

from egas.amdahl import AmdahlResult, evaluate_amdahl
from egas.contract import Contract, Workload
from egas.decide import DecideInput, Decision, DecisionRecord, decide
from egas.methods.base import BakeoffResult, Method
from egas.methods.generic import GenericMethod
from egas.methods.registry import get_method
from egas.profile_io import Profile, load_profile
from egas.report import RunReport, amdahl_dict, bakeoff_dict, format_human
from egas.rungs import Rung, propose_from_symbol


class Driver:
    def __init__(self, contract: Contract, *, out_dir: Path | None = None):
        self.contract = contract
        self.method: Method = get_method(contract)
        self.out_dir = out_dir or (Path.cwd() / "egas_out" / contract.name)
        self.applied: list[str] = []

    def load_profile(self, path: Path | None = None) -> Profile | None:
        p = path or self.contract.profile_path
        if p is None or not Path(p).is_file():
            return None
        return load_profile(Path(p))

    def gate(self, profile: Profile | None) -> AmdahlResult | None:
        if profile is None:
            return None
        return evaluate_amdahl(
            profile,
            self.contract.target_speedup,
            allow_t4_assist=self.contract.allow_t4_assist,
        )

    def propose(self, profile: Profile | None) -> list[Rung]:
        caps = self.method.capabilities()
        if self.contract.method == "star":
            return caps.source
        if profile and profile.hottest_legal:
            h = profile.hottest_legal
            return propose_from_symbol(h.symbol, h.fraction)
        return caps.source

    def run(
        self,
        *,
        profile_path: Path | None = None,
        apply_automated: bool = False,
        workloads: list[str] | None = None,
        skip_bakeoff: bool = False,
    ) -> RunReport:
        profile = self.load_profile(profile_path)
        artifacts_ready = self.method.stock_exists() and self.method.opt_exists()
        if profile is None and not artifacts_ready:
            rec = DecisionRecord(
                Decision.INCOMPLETE,
                "Method artifacts absent (no profile, no stock/opt binaries); "
                "cannot gate or bake off. Name a real Method or leave the contract incomplete.",
            )
            return self._finish(rec, None, [], [])

        amdahl = self.gate(profile)
        proposed = self.propose(profile)
        caps = self.method.capabilities()

        if isinstance(self.method, GenericMethod):
            self.method.ensure_built()

        if amdahl is not None and amdahl.status == "REFUSE":
            rec = decide(
                DecideInput(
                    match=None,
                    min_pair=None,
                    mean_speedup=None,
                    n_pairs=0,
                    target=self.contract.target_speedup,
                    amdahl_ok=False,
                    amdahl_t4_only=False,
                    automated_rungs_left=False,
                    source_rungs_left=bool(proposed),
                    runs_required=self.contract.runs,
                )
            )
            return self._finish(rec, amdahl, [], proposed)

        if skip_bakeoff:
            rec = decide(
                DecideInput(
                    match=None,
                    min_pair=None,
                    mean_speedup=None,
                    n_pairs=0,
                    target=self.contract.target_speedup,
                    amdahl_ok=amdahl is None or amdahl.proceed or amdahl.proceed_with_t4,
                    amdahl_t4_only=bool(amdahl and amdahl.proceed_with_t4),
                    automated_rungs_left=False,
                    source_rungs_left=bool(proposed),
                    runs_required=self.contract.runs,
                )
            )
            return self._finish(rec, amdahl, [], proposed)

        if apply_automated:
            for rung in caps.automated:
                try:
                    self.method.apply(rung)
                    self.applied.append(rung.id)
                except FileNotFoundError:
                    # Build scripts / Suite B data may be absent on a laptop smoke run.
                    break

        bakeoffs: list[BakeoffResult] = []
        if not skip_bakeoff and self.method.stock_exists() and self.method.opt_exists():
            for wl in self._select(workloads):
                bakeoffs.append(self.method.bakeoff(wl))
                if not bakeoffs[-1].match:
                    break

        match: bool | None = None
        min_pair: float | None = None
        mean_spd: float | None = None
        n_pairs = 0
        if bakeoffs:
            match = all(b.match for b in bakeoffs)
            pairs = [b.min_pair for b in bakeoffs if b.min_pair is not None]
            means = [b.mean_speedup for b in bakeoffs if b.mean_speedup is not None]
            min_pair = min(pairs) if pairs else None
            mean_spd = min(means) if means else None
            n_pairs = min((b.n for b in bakeoffs), default=0)

        rec = decide(
            DecideInput(
                match=match,
                min_pair=min_pair,
                mean_speedup=mean_spd,
                n_pairs=n_pairs,
                target=self.contract.target_speedup,
                amdahl_ok=amdahl is None or amdahl.proceed,
                amdahl_t4_only=bool(amdahl and amdahl.proceed_with_t4),
                automated_rungs_left=bool(caps.automated) and not bakeoffs and not apply_automated,
                source_rungs_left=bool(proposed),
                runs_required=self.contract.runs,
            )
        )
        return self._finish(rec, amdahl, bakeoffs, proposed)

    def _select(self, ids: list[str] | None) -> list[Workload]:
        if not ids:
            return list(self.contract.held_out())
        wanted = set(ids)
        found = [w for w in self.contract.workloads if w.id in wanted]
        missing = wanted.difference(w.id for w in found)
        if missing:
            raise ValueError(f"unknown workloads: {sorted(missing)}")
        return found

    def _finish(
        self,
        rec,
        amdahl: AmdahlResult | None,
        bakeoffs: list[BakeoffResult],
        proposed: list[Rung],
    ) -> RunReport:
        report = RunReport(
            contract=self.contract.name,
            method=self.contract.method,
            decision=rec.decision.value,
            reason=rec.reason,
            amdahl=amdahl_dict(amdahl) if amdahl else None,
            bakeoffs=[bakeoff_dict(b) for b in bakeoffs],
            proposed=[
                {"id": r.id, "cls": r.cls.value, "title": r.title, "hint": r.hint}
                for r in proposed
            ],
            applied=list(self.applied),
        )
        self.out_dir.mkdir(parents=True, exist_ok=True)
        report.write(self.out_dir / "report.json")
        (self.out_dir / "decision.txt").write_text(format_human(report, rec))
        if rec.decision is Decision.PROPOSE:
            (self.out_dir / "RUNG_PLAN.md").write_text(_plan_md(self.contract.name, proposed))
        return report


def _plan_md(name: str, rungs: list[Rung]) -> str:
    lines = [
        f"# T1–T3 plan — {name}",
        "",
        "These are **proposals**. Apply one class at a time, then re-run `egas verify`.",
        "Do not change threads, compression, or index knobs.",
        "",
    ]
    for r in rungs:
        lines += [f"## {r.id} ({r.cls.value})", "", r.title, "", r.hint, ""]
    return "\n".join(lines)
