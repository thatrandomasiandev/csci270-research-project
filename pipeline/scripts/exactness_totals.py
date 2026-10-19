"""Sum every exactness experiment into one table (Table 2 of the TARE paper), plus the headline's largest per-arm CV.

Reads committed result files only; writes pipeline/results/exact_replay/exactness_totals.json.
Each row counts body lines compared byte for byte with a stock run on the new release.
HMMER rows count hit-table plus domain-table lines. The CARC headline row counts one shipped
update per EXACT genome (the three repeats print the same bytes, so they are counted once).
The diverse-genome row counts genomes whose update shipped and matched (passed_lines_L).
"""
import glob
import json
from pathlib import Path

RES = Path(__file__).resolve().parents[1] / "results"


def load(rel):
    return json.loads((RES / rel).read_text())


rows = []
e12 = load("exact_replay/e1_e2.json")["E1"]["check1_R_vs_S"]
rows.append(("hmmer_replay_300", e12["tbl"]["lines_a"] + e12["dom"]["lines_a"]))
sc = load("exact_replay/e1scale.json")
rows.append(("hmmer_replay_3_genomes", sc["tblout_body_lines_total"] + sum(p["domtblout_body_lines"] for p in sc["proteomes"])))
cp = load("exact_replay/costpass_measured.json")["proteomes"]
rows.append(("hmmer_tool_2_laptop", sum(p["e2"]["tbl"]["lines_stock"] + p["e2"]["dom"]["lines_stock"] for p in cp)))

head = load("exact_replay/headline_carc.json")
exact = {g["proteome"] for g in head["genomes"] if g["outcome"] == "EXACT"}
server = 0
for path in sorted(glob.glob(str(RES / "exact_replay/headline_measured/headline_measured_*.json"))):
    d = json.loads(Path(path).read_text())
    if d.get("proteome") not in exact or "13208152_2" in path or "13208152_4" in path or "13208152_5" in path:
        continue
    b = [r for r in d.get("repeats", []) if r.get("arm") == "B" and r.get("compare")]
    if b:
        c = b[0]["compare"]
        server += c["tbl"]["lines_stock"] + c["dom"]["lines_stock"]
rows.append(("hmmer_tool_server_genomes", server))
dg = load("diverse_genomes/measured_score.json")
rows.append(("hmmer_tool_diverse_genomes", dg["passed_lines_L"]))

rows.append(("infernal_replay_10", load("infernal/test_i.json")["rows"]["noclan"]))
rows.append(("infernal_tool_family_removal", 459))  # INFERNAL_PROTOCOL.md, shipped GlmZ_SraJ removal
rows.append(("infernal_tool_10_genomes", load("infernal/measured2.json")["summary"]["noclan"]["body_lines"]))

total = sum(n for _, n in rows)
out = {
    "rows": dict(rows),
    "n_server_exact_genomes": len(exact),
    "n_diverse_passed_genomes": sum(v["pass"] for v in dg["by_group"].values()),
    "total_lines": total,
    "p_up": 1 - 0.05 ** (1 / total),
    "headline_max_cv": max(max(g["cv_A"] or 0, g["cv_B"] or 0) for g in head["genomes"]),
}
(RES / "exact_replay/exactness_totals.json").write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps(out, indent=1))
