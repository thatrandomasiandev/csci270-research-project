"""All data figures for the TARE paper, generated from committed result files.

Run:  python3 make_figures.py      (writes PDF + PNG next to this file)

Sources (relative to pipeline/results/ unless noted):
  exact_replay/costpass_baseline.json, exact_replay/costpass_measured.json
  exact_replay/e1_e2.json, exact_replay/e1scale.json
  reference_diamond/dx.json            (iSeqSearch / iDiamond comparison)
  infernal/test_i.json
  Pfam release table: pipeline/docs/MOTIVATION_EVIDENCE.md (relnotes for 38.2, CITED)
  Pfam 38.1 -> 38.2 strict-hash counts: results/reference_kill_r1.json (MEASURED)
Curves labelled "model" are PROJECTED from the closed forms in the paper.
"""
import json
from math import comb
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

HERE = Path(__file__).resolve().parent
RES = HERE.parents[2] / "results"

plt.rcParams.update({
    "pdf.fonttype": 42, "ps.fonttype": 42,
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5,
    "legend.fontsize": 6.5, "xtick.labelsize": 6.5, "ytick.labelsize": 6.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "grid.linewidth": 0.4, "grid.alpha": 0.35,
})

# One palette for the whole paper.
C = {
    "stable": "#9ecae1", "edited": "#fd8d3c", "new": "#e6550d", "removed": "#636363",
    "diff": "#bdbdbd", "discovery": "#2171b5", "replay": "#6baed6", "check": "#e6550d",
    "verify": "#756bb1", "parse": "#969696", "other": "#d9d9d9",
    "tare": "#2171b5", "stock": "#252525", "bad": "#cb181d", "ok": "#31a354",
    "model": "#2171b5", "proj": "#9ecae1", "warn": "#e6550d",
}
ONE = 3.35   # single column width, inches
TWO = 7.0    # full width


def save(fig, name):
    fig.savefig(HERE / f"{name}.pdf", bbox_inches="tight", pad_inches=0.02)
    fig.savefig(HERE / f"{name}.png", dpi=220, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    print("wrote", name)


def load(rel):
    return json.loads((RES / rel).read_text())


# ---------------------------------------------------------------------------
# Figure: how much of Pfam changes per release (CITED table + MEASURED split)
# ---------------------------------------------------------------------------
def fig_churn():
    releases = ["37.0", "37.1", "37.2", "37.3", "37.4", "38.0", "38.1", "38.2"]
    families = [21979, 23794, 24076, 24424, 24736, 25545, 27481, 30134]
    dates = ["05/24", "11/24", "02/25", "04/25", "06/25", "10/25", "01/26", "06/26"]
    kill = load("reference_kill_r1.json")
    unchanged = kill["unchanged_strict"]
    added = kill["added"]
    removed = kill["removed"]
    edited = kill["shared"] - unchanged

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(TWO, 1.85), gridspec_kw={"width_ratios": [1.35, 1]})
    net = [families[i] - families[i - 1] for i in range(1, len(families))]
    x = range(len(releases))
    ax.plot(x, families, color=C["tare"], marker="o", ms=3, lw=1.2, zorder=3)
    for i, (f, d) in enumerate(zip(families, dates)):
        ax.annotate(f"{f:,}", (i, f), textcoords="offset points", xytext=(0, 5), ha="center", fontsize=5.6)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{r}\n{d}" for r, d in zip(releases, dates)])
    ax.set_ylabel("Pfam families")
    ax.set_ylim(20000, 32500)
    ax.grid(axis="y")
    ax2 = ax.twinx()
    ax2.spines["right"].set_visible(True)
    bars = ax2.bar([i + 0.5 for i in range(len(net))], [100 * n / families[i + 1] for i, n in enumerate(net)],
                   width=0.35, color=C["new"], alpha=0.55, zorder=1)
    for b, n in zip(bars, net):
        ax2.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.3, f"+{n:,}", ha="center", fontsize=5.4, color=C["new"])
    ax2.set_ylim(0, 30)
    ax2.set_ylabel("net families added (% of release)", color=C["new"])
    ax2.tick_params(axis="y", colors=C["new"])
    ax.set_title("(a) Eight Pfam releases in 25 months", loc="left")

    total = unchanged + edited + added
    parts = [("identical", unchanged, C["stable"]), ("edited", edited, C["edited"]), ("new", added, C["new"])]
    left = 0
    for name, val, col in parts:
        bx.barh(0, val, left=left, color=col, edgecolor="white", height=0.5)
        label = f"{name}\n{val:,} ({100 * val / total:.1f}%)"
        if val / total > 0.2:
            bx.text(left + val / 2, 0, label, ha="center", va="center", fontsize=6.4)
        else:
            tx = left + val / 2 + (-5200 if name == "edited" else -300)
            bx.annotate(label, (left + val / 2, 0.25), xytext=(tx, 0.62),
                        ha="center", fontsize=6.0, arrowprops=dict(arrowstyle="-", lw=0.5))
        left += val
    bx.text(total * 0.02, -0.75, f"also {removed} families removed", fontsize=6.0, color=C["removed"])
    bx.annotate("", xy=(unchanged, -0.42), xytext=(total, -0.42),
                arrowprops=dict(arrowstyle="<->", lw=0.6, color=C["new"]))
    bx.text(unchanged - 300, -0.42, "work that must be redone: 13.4%", ha="right", va="center", fontsize=6.2, color=C["new"])
    bx.set_xlim(0, total * 1.02)
    bx.set_ylim(-1.0, 1.0)
    bx.set_yticks([])
    bx.spines["left"].set_visible(False)
    bx.set_xlabel("Pfam 38.2 models, by comparison with 38.1 (strict hash)")
    bx.set_title("(b) What actually changed, 38.1 $\\rightarrow$ 38.2", loc="left")
    fig.tight_layout(w_pad=2.2)
    save(fig, "churn")


# ---------------------------------------------------------------------------
# Figure: exactness evidence (MEASURED)
# ---------------------------------------------------------------------------
def fig_exact():
    rows = []
    e12 = load("exact_replay/e1_e2.json")
    rows.append(("HMMER, 300 proteins", e12["E1"]["check1_R_vs_S"]["tbl"]["lines_a"],
                 e12["E1"]["check1_R_vs_S"]["dom"]["lines_a"],
                 e12["E1"]["check2_Rn_vs_S"]["tbl"]["differing_positions"] / e12["E1"]["check2_Rn_vs_S"]["tbl"]["lines_a"]))
    sc = load("exact_replay/e1scale.json")
    for p in sc["proteomes"]:
        t = p["E2"]["vs_stock"]["tbl"]["lines_stock"]
        d = p["E2"]["vs_stock"]["dom"]["lines_stock"]
        rn = p["Rn"]["vs_stock"]["tbl"]["differing_positions"] / t
        rows.append((f"HMMER, {p['proteome'].split('_protein')[0]}", t, d, rn))
    cp = load("exact_replay/costpass_measured.json")
    for p in cp["proteomes"]:
        rows.append((f"HMMER tool, {p['proteome']}", p["e2"]["tbl"]["lines_stock"], p["e2"]["dom"]["lines_stock"], None))
    ti = load("infernal/test_i.json")
    rows.append(("Infernal oracle, 10 genomes", ti["rows"]["noclan"], 0, None))
    rows.append(("Infernal oracle + clans", ti["rows"]["clan"], 0, None))
    m2 = load("infernal/measured2.json")["summary"]
    rows.append(("Infernal tool, 10 new genomes", m2["noclan"]["body_lines"], 0, None))
    rows.append(("Infernal tool + clans", m2["clan"]["body_lines"], 0, None))

    fig, ax = plt.subplots(figsize=(ONE, 2.7))
    y = list(range(len(rows)))
    for i, (name, t, d, rn) in enumerate(rows):
        ax.barh(i, t, color=C["tare"], height=0.62)
        ax.barh(i, d, left=t, color=C["replay"], height=0.62)
        ax.text(t + d + 250, i, f"{t + d:,}", va="center", fontsize=5.8)
        if rn is not None:
            ax.text(23200, i, f"{100 * rn:.1f}%", va="center", ha="right", fontsize=5.8, color=C["bad"])
    ax.text(23200, -1.05, "unpinned\ndiffers", ha="right", va="center", fontsize=5.6, color=C["bad"])
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=5.8)
    ax.invert_yaxis()
    ax.set_xlim(0, 23500)
    ax.set_xlabel("output lines compared byte for byte (all identical)")
    ax.legend(handles=[Patch(color=C["tare"], label="hit table (tblout)"),
                       Patch(color=C["replay"], label="domain table (domtblout)")],
              loc="lower right", frameon=False)
    ax.grid(axis="x")
    save(fig, "exact")


# ---------------------------------------------------------------------------
# Figure: where the time goes, before vs after (MEASURED, workstation)
# ---------------------------------------------------------------------------
def fig_phases():
    base = load("exact_replay/costpass_baseline.json")
    meas = load("exact_replay/costpass_measured.json")
    order = ["diff", "discovery", "replay", "check", "verify", "parse", "other"]
    names = {"diff": "diff", "discovery": "discovery", "replay": "replay", "check": "safety check",
             "verify": "audit", "parse": "parsing", "other": "other"}
    bp = base["replay_38.2"]["median_phases"]
    before = {"diff": bp["diff_s"], "discovery": bp["discovery_s"], "replay": bp["replay_s"],
              "check": bp["ic2_s"], "verify": bp["verify_s"], "parse": bp["parse_s"]}
    before["other"] = base["replay_38.2"]["median_wall_s"] - sum(before.values())
    rows = [("first version\nGCF_013315695.1", before, base["stock"]["median_s"], None)]
    for p in meas["proteomes"]:
        ph = p["e2"]["phases"]
        check = ph["ic2_neighbor_s"] + sum(v for k, v in ph.items() if k.startswith("ic2_random_") and k.count("_") == 3)
        after = {"diff": ph["diff_s"], "discovery": ph["discovery_s"], "replay": ph["replay_s"],
                 "check": check, "verify": ph["verify_s"], "parse": ph["parse_s"]}
        after["other"] = p["e2"]["wall_s"] - sum(after.values())
        rows.append((f"shipped\n{p['proteome']}", after, p["stock"]["wall_s"], 0.13446605163602576 * p["stock"]["wall_s"]))

    fig, ax = plt.subplots(figsize=(ONE, 2.05))
    for i, (label, ph, stock, pred) in enumerate(rows):
        left = 0.0
        for k in order:
            ax.barh(i, ph[k], left=left, color=C[k], edgecolor="white", linewidth=0.4, height=0.58,
                    label=names[k] if i == 0 else None)
            left += ph[k]
        ax.plot([stock, stock], [i - 0.36, i + 0.36], color=C["stock"], lw=1.3)
        ax.text(stock + 8, i - 0.33, f"stock {stock:.0f}s", fontsize=5.4, va="top")
        ax.text(left + 8, i + 0.05, f"{left:.0f}s = {stock / left:.2f}$\\times$", va="center", fontsize=6.2,
                fontweight="bold", color=C["bad"] if stock < left else C["ok"])
        if pred is not None:
            ax.plot([pred], [i + 0.42], marker="v", ms=3.2, color=C["discovery"])
    ax.text(105, 2.62, "$\\blacktriangledown$ model: discovery = $f_\\Delta \\cdot T_{stock}$", fontsize=5.4, color=C["discovery"])
    ax.annotate("check alone: 668s", xy=(560, 0), xytext=(420, -0.82), fontsize=5.8, color=C["check"],
                arrowprops=dict(arrowstyle="-", lw=0.5, color=C["check"]))
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows], fontsize=6)
    ax.invert_yaxis()
    ax.set_xlim(0, 1060)
    ax.set_ylim(2.75, -1.1)
    ax.set_xlabel("wall-clock seconds (workstation, indicative)")
    ax.legend(ncol=4, loc="lower center", bbox_to_anchor=(0.45, 1.0), frameon=False, columnspacing=0.8, handlelength=1.2)
    ax.grid(axis="x")
    save(fig, "phases")


# ---------------------------------------------------------------------------
# Figure: the cost model across release sizes (MODEL + MEASURED points)
# ---------------------------------------------------------------------------
def fig_model():
    meas = load("exact_replay/costpass_measured.json")
    f_meas = 0.13446605163602576
    a_vals, c_vals, pts = [], [], []
    for p in meas["proteomes"]:
        stock = p["stock"]["wall_s"]
        disc = p["e2"]["phases"]["discovery_s"]
        wall = p["e2"]["wall_s"]
        a_vals.append(disc / stock / f_meas)
        c_vals.append((wall - disc) / stock)
        pts.append(stock / wall)
    a = sum(a_vals) / len(a_vals)
    c = sum(c_vals) / len(c_vals)
    fs = [0.004 + i * 0.001 for i in range(0, 300)]
    model = [1 / (a * f + c) for f in fs]
    bound = [1 / f for f in fs]

    fig, ax = plt.subplots(figsize=(ONE, 2.45))
    ax.plot([100 * f for f in fs], bound, ls="--", color="#999999", lw=0.8, label="upper bound $1/f_\\Delta$ (only discovery)")
    ax.plot([100 * f for f in fs], model, color=C["model"], lw=1.4,
            label=f"model, measured overheads ($a$={a:.2f}, $c$={c:.3f})")
    ax.axhline(1 / c, color=C["model"], lw=0.5, ls=":")
    ax.text(16.5, 1 / c + 0.2, f"overhead ceiling 1/c = {1 / c:.1f}$\\times$", ha="left", fontsize=5.6, color=C["model"])
    ax.axhline(1, color=C["stock"], lw=0.6)
    ax.text(29.5, 1.12, "full rerun (1$\\times$)", ha="right", fontsize=5.6)
    ax.scatter([100 * f_meas] * len(pts), pts, color=C["ok"], zorder=5, s=14, label="measured, Pfam 38.1$\\rightarrow$38.2")
    lb = [("37.1$\\rightarrow$37.2, 37.3$\\rightarrow$37.4", [282 / 24076, 312 / 24736]),
          ("37.4$\\rightarrow$38.0", [809 / 25545]), ("38.0$\\rightarrow$38.1", [1936 / 27481])]
    for name, group in lb:
        for f in group:
            ax.plot([100 * f], [1 / (a * f + c)], marker="^", ms=3.5, color=C["proj"], mec=C["model"], mew=0.4)
        f = max(group)
        ax.text(100 * f + 0.5, 1 / (a * f + c) + 0.15, name, fontsize=5.0, color="#3f6f9f")
    ax.plot([], [], marker="^", ls="", ms=3.5, color=C["proj"], mec=C["model"], mew=0.4,
            label="projected, other releases (net additions only)")
    # INFERNAL_PROTOCOL.md "Measured 2026-10-14 — removing GlmZ_SraJ": update 666.0 s, stock 328.4 s, 1 of 4,227 families.
    ax.scatter([100 * 1 / 4227], [328.4 / 666.0], marker="x", color=C["warn"], s=18, zorder=5, clip_on=False,
               label="Infernal before: one-family removal (check dominates)")
    m2 = load("infernal/measured2.json")["summary"]
    for var, mk in (("noclan", "D"), ("clan", "d")):
        f_inf = m2[var]["f"]
        ax.errorbar([100 * f_inf], [m2[var]["median_s_g"]],
                    yerr=[[m2[var]["median_s_g"] - m2[var]["bootstrap_median"]["p2.5"]],
                          [m2[var]["bootstrap_median"]["p97.5"] - m2[var]["median_s_g"]]],
                    fmt=mk, ms=3.6, color=C["warn"], mec="black", mew=0.3, capsize=1.5, lw=0.7, zorder=6,
                    label=f"Infernal after, {'no clan' if var == 'noclan' else 'clans'}: median, 95% CI (10 genomes)")
    ax.set_xlim(0, 30)
    ax.set_ylim(0, 8)
    ax.set_xlabel("fraction of the reference that changed, $f_\\Delta$ (%)")
    ax.set_ylabel("speedup over a full rerun")
    ax.grid()
    ax.legend(loc="lower center", bbox_to_anchor=(0.45, 1.0), ncol=1, frameon=False, fontsize=5.4)
    save(fig, "model")


# ---------------------------------------------------------------------------
# Figure: prior incremental search vs TARE on DIAMOND (MEASURED)
# ---------------------------------------------------------------------------
def fig_idiamond():
    d = load("reference_diamond/dx.json")["dx_i"]["idiamond"]
    stock_rows = d["stock_rows"]
    ident = d["shared_byte_identical"]
    value = d["same_hsp_different_value"]
    hsp = d["different_hsp"]
    extra = d["row_extra"]
    fig, ax = plt.subplots(figsize=(ONE, 1.15))
    segs = [("byte-identical", ident, C["ok"]), ("same hit, different printed value", value, C["edited"]),
            ("different alignment", hsp, C["bad"]), ("stale: sequence removed from release", extra, C["removed"])]
    left = 0
    for name, v, col in segs:
        ax.barh(1, v, left=left, color=col, height=0.55, label=f"{name} ({v:,})")
        left += v
    ax.barh(0, stock_rows, color=C["ok"], height=0.55)
    ax.text(stock_rows / 2, 0, f"TARE: refuses, returns the full run ({stock_rows:,} rows, 100% identical)",
            ha="center", va="center", fontsize=5.8, color="white", fontweight="bold")
    ax.text(ident + value / 2, 1, f"{100 * ident / stock_rows:.1f}% of shared rows byte-identical",
            ha="center", va="center", fontsize=5.8)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["TARE", "iSeqSearch\n(iDiamond)"], fontsize=6.2)
    ax.set_xlim(0, (stock_rows + extra) * 1.01)
    ax.set_xlabel("output rows, Swiss-Prot 2026_01 $\\rightarrow$ 2026_03, 300 queries")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=2, frameon=False, fontsize=5.4, handlelength=1)
    save(fig, "idiamond")


# ---------------------------------------------------------------------------
# Figure: how often the random half of the check misses unknown coupling (MODEL)
# ---------------------------------------------------------------------------
def p_miss(n, k, s, q):
    h = comb(n - k, s) / comb(n, s)
    return h + (1 - h) * (1 - q) ** 3


def fig_pmiss():
    n, k = 2000, 22
    ss = list(range(1, 401))
    fig, ax = plt.subplots(figsize=(ONE, 1.8))
    for q, col, lab in [(0.3125, C["model"], "coupling entry hit by a pad w.p. q = 0.31 (DX3)"),
                        (0.0488, C["warn"], "q = 0.049 (one specific DIAMOND neighbor)")]:
        ax.plot(ss, [p_miss(n, k, s, q) for s in ss], color=col, lw=1.2, label=lab)
        ax.axhline((1 - q) ** 3, color=col, lw=0.5, ls=":")
    ax.plot([0, 400], [0, 0], color=C["ok"], lw=2.2, solid_capstyle="butt",
            label="neighbor pad, file-order coupling: caught by construction")
    ax.scatter([50], [p_miss(n, k, 50, 0.3125)], color=C["model"], zorder=5, s=14)
    ax.annotate(f"shipped: s = 50, miss = {p_miss(n, k, 50, 0.3125):.2f}", (50, p_miss(n, k, 50, 0.3125)),
                xytext=(95, 0.80), fontsize=5.8, arrowprops=dict(arrowstyle="-", lw=0.5))
    ax.set_xlim(0, 400)
    ax.set_ylim(-0.04, 1.04)
    ax.set_xlabel("records sampled for random pads, $s$  (k = 22 of n = 2,000 affected)")
    ax.set_ylabel("probability the check misses")
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 0.05), frameon=False, fontsize=5.3)
    ax.grid()
    save(fig, "pmiss")


if __name__ == "__main__":
    fig_churn()
    fig_exact()
    fig_phases()
    fig_model()
    fig_idiamond()
    fig_pmiss()
