"""All data figures for the TARE paper, generated from committed result files.

Run:  python3 make_figures.py      (writes PDF + PNG next to this file)

Sources (relative to pipeline/results/ unless noted):
  exact_replay/costpass_baseline.json, exact_replay/costpass_measured.json
  exact_replay/server_cost_fit.json    (server a, c and the three phase bars)
  exact_replay/headline_carc.json      (server median and its CI)
  exact_replay/e1_e2.json, exact_replay/e1scale.json
  reference_diamond/dx.json            (iSeqSearch / iDiamond comparison)
  infernal/test_i.json
  release_chain/pairs.json             (measured f_delta for each Pfam pair)
  Pfam release table: pipeline/docs/MOTIVATION_EVIDENCE.md (relnotes for 38.2, CITED)
  Pfam 38.1 -> 38.2 strict-hash counts: results/reference_kill_r1.json (MEASURED)
Curves labelled "model" are PROJECTED from T = a f T_stock + c T_stock.
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

HERE = Path(__file__).resolve().parent
RES = HERE.parents[2] / "results"
sys.path.insert(0, str(RES.parent / "scripts"))
from fit_server_cost import stage_split  # noqa: E402

plt.rcParams.update({
    "pdf.fonttype": 42, "ps.fonttype": 42,
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 7.5, "axes.titlesize": 7.5, "axes.labelsize": 7.5,
    "legend.fontsize": 6.8, "xtick.labelsize": 6.8, "ytick.labelsize": 6.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "grid.linewidth": 0.4, "grid.alpha": 0.35,
})
FS = 6.8  # the one annotation size

# One meaning per color across the paper: TARE blue, stock gray, refusal/wrong red, everything else neutral.
C = {
    "tare": "#2171b5", "tare_light": "#9ecae1", "stock": "#636363", "bad": "#cb181d",
    "n1": "#d9d9d9", "n2": "#bdbdbd", "n3": "#969696", "ink": "#252525",
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

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(TWO, 1.9), gridspec_kw={"width_ratios": [1.35, 1]})
    x = list(range(len(releases)))
    prev = [families[0]] + families[:-1]
    ax.bar(x, prev, color=C["n2"], width=0.62, label="carried from the previous release")
    ax.bar(x[1:], [families[i] - prev[i] for i in x[1:]], bottom=prev[1:], color=C["tare"], width=0.62,
           label="net families added")
    for i in (x[0], x[-1]):
        ax.text(i, families[i] + 400, f"{families[i]:,}", ha="center", fontsize=FS)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{r}\n{d}" for r, d in zip(releases, dates)])
    ax.set_ylabel("Pfam families")
    ax.set_ylim(0, 39000)
    ax.grid(axis="y")
    ax.legend(loc="upper left", ncol=2, frameon=False)
    ax.set_title("(a) Eight Pfam releases in 25 months", loc="left")

    total = unchanged + edited + added
    parts = [("identical", unchanged, C["n2"]), ("edited", edited, C["tare_light"]), ("new", added, C["tare"])]
    left = 0
    for name, val, col in parts:
        bx.barh(0, val, left=left, color=col, edgecolor="white", height=0.5)
        label = f"{name}\n{val:,} ({100 * val / total:.1f}%)"
        if val / total > 0.2:
            bx.text(left + val / 2, 0, label, ha="center", va="center", fontsize=FS)
        else:
            tx = left + val / 2 + (-5200 if name == "edited" else -300)
            bx.annotate(label, (left + val / 2, 0.25), xytext=(tx, 0.62),
                        ha="center", fontsize=FS, arrowprops=dict(arrowstyle="-", lw=0.5))
        left += val
    bx.text(total * 0.02, -0.75, f"also {removed} families removed", fontsize=FS, color=C["stock"])
    bx.annotate("", xy=(unchanged, -0.42), xytext=(total, -0.42),
                arrowprops=dict(arrowstyle="<->", lw=0.6, color=C["tare"]))
    bx.text(unchanged - 300, -0.42, "what TARE reruns: 13.4%", ha="right", va="center", fontsize=FS, color=C["tare"])
    bx.set_xlim(0, total * 1.02)
    bx.set_ylim(-1.0, 1.0)
    bx.set_yticks([])
    bx.spines["left"].set_visible(False)
    bx.set_xlabel("Pfam 38.2 models, by comparison with 38.1 (strict hash)")
    bx.set_title("(b) What actually changed, 38.1 $\\rightarrow$ 38.2", loc="left")
    fig.tight_layout(w_pad=2.2)
    save(fig, "churn")


# ---------------------------------------------------------------------------
# Figure: where the time goes (MEASURED). Laptop first version, then the
# server headline. Separate seconds axes: server stock runs are ~2200–2550 s,
# and one shared axis would shrink the laptop bar.
# ---------------------------------------------------------------------------
def _draw_phase_bars(ax, rows, xlim, ylim):
    order = ["discovery", "replay", "check", "other"]
    cols = {"discovery": C["tare"], "replay": C["tare_light"], "check": C["n3"], "other": C["n1"]}
    gap = xlim * 0.012
    for i, (label, ph, stock, pred) in enumerate(rows):
        left = 0.0
        for key in order:
            ax.barh(i, ph[key], left=left, color=cols[key], edgecolor="white", linewidth=0.4, height=0.58)
            left += ph[key]
        ax.plot([stock, stock], [i - 0.36, i + 0.36], color=C["ink"], lw=1.3)
        ax.text(stock + gap, i - 0.30, f"stock {stock:.0f}s", fontsize=FS, va="top")
        ax.text(left + gap, i + 0.06, f"{left:.0f}s = {stock / left:.2f}$\\times$", va="center", fontsize=FS,
                fontweight="bold", color=C["bad"] if stock < left else C["tare"])
        if pred is not None:
            ax.plot([pred, pred], [i - 0.36, i + 0.36], color=C["ink"], lw=1.0, ls=(0, (1.5, 1.2)))
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([row[0] for row in rows])
    ax.set_xlim(0, xlim)
    ax.set_ylim(*ylim)
    ax.set_xlabel("wall-clock seconds")
    ax.grid(axis="x")


def fig_phases():
    fit = load("exact_replay/server_cost_fit.json")
    base = load("exact_replay/costpass_baseline.json")
    # First version: the run whose wall time is the median of three.
    runs = base["replay_38.2"]["runs"]
    walls = [run["wall_s"] for run in runs]
    mid = sorted(range(len(runs)), key=lambda i: walls[i])[len(runs) // 2]
    breakdown = runs[mid]["breakdown"]
    before = {
        "discovery": breakdown["discovery_s"],
        "replay": breakdown["replay_s"],
        "check": breakdown["ic2_s"] + breakdown["verify_s"],
    }
    before["other"] = walls[mid] - sum(before.values())
    stock_mid = sorted(base["stock"]["walls_s"])[1]
    laptop_rows = [(
        "first version\nGCF_013315695.1",
        before,
        stock_mid,
        fit["f"] * stock_mid,
    )]
    measured = load("exact_replay/costpass_measured.json")
    for proteome in measured["proteomes"]:
        wall = proteome["e2"]["wall_s"]
        laptop_rows.append((
            f"shipped\n{proteome['proteome']}",
            stage_split(proteome["e2"]["phases"], wall),
            proteome["stock"]["wall_s"],
            fit["f"] * proteome["stock"]["wall_s"],
        ))

    roles = {
        "lowest_S_g": "lowest $S_g$",
        "median_S_g": "median $S_g$",
        "highest_S_g": "highest $S_g$",
    }
    server_rows = []
    for spec in fit["phase_bars"]["genomes"]:
        payload = json.loads((RES.parent / spec["source_path"]).read_text())
        repeat = payload["repeats"][spec["repeats_index"]]
        if repeat["arm"] != "B" or repeat["repeat"] != spec["repeat"]:
            raise ValueError(f"phase bar does not match {spec['source_path']}")
        stages = stage_split(repeat["phases"], repeat["wall_s"])
        for key, value in stages.items():
            if abs(value - spec["stages_s"][key]) > 1e-6:
                raise ValueError(f"{spec['proteome']} {key} drifted from the fit file")
        server_rows.append((
            f"{roles[spec['role']]}\n{spec['proteome']}",
            stages,
            spec["stock_median_s"],
            fit["f"] * spec["stock_median_s"],
        ))

    fig, (ax, bx) = plt.subplots(
        2, 1, figsize=(ONE, 4.15), gridspec_kw={"height_ratios": [2.15, 2.45]}
    )
    _draw_phase_bars(ax, laptop_rows, 1120, (2.55, -0.62))
    ax.set_title("laptop", loc="left")
    _draw_phase_bars(bx, server_rows, 3600, (3.35, -0.62))
    bx.set_title("server headline, median run", loc="left")
    bx.plot([150, 430], [2.95, 2.95], color=C["ink"], lw=1.0, ls=(0, (1.5, 1.2)))
    bx.text(480, 2.95, "selection $= f_\\Delta T_{stock}$", fontsize=FS, va="center")
    handles = [
        Patch(facecolor=C["tare"], label="selection"),
        Patch(facecolor=C["tare_light"], label="replay"),
        Patch(facecolor=C["n3"], label="check + audit"),
        Patch(facecolor=C["n1"], label="everything else"),
    ]
    fig.legend(handles=handles, ncol=4, loc="upper center", bbox_to_anchor=(0.52, 1.0),
               frameon=False, columnspacing=0.8, handlelength=1.2)
    fig.tight_layout(rect=(0, 0, 1, 0.93), h_pad=1.15)
    save(fig, "phases")


# ---------------------------------------------------------------------------
# Figure: the cost model across release sizes (MODEL + MEASURED points)
# ---------------------------------------------------------------------------
def fig_model():
    # Solid curve and pair ticks use the server fit. The dashed curve is the
    # published laptop fit (same definition, two proteomes), kept so the two
    # machines are not swapped silently. Panel (b) is unchanged and keeps its
    # own y limit: the server ceiling 1/c sits above 8.
    fit = load("exact_replay/server_cost_fit.json")
    f_meas = fit["f"]
    a, c = fit["a"], fit["c"]
    a_l = fit["laptop_reference"]["recomputed_a"]
    c_l = fit["laptop_reference"]["recomputed_c"]
    meas = load("exact_replay/costpass_measured.json")
    pts = [p["stock"]["wall_s"] / p["e2"]["wall_s"] for p in meas["proteomes"]]
    fs = [0.004 + i * 0.001 for i in range(0, 997)]

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(ONE, 2.85), gridspec_kw={"width_ratios": [1.6, 1]})
    ax.plot([100 * f for f in fs], [1 / f for f in fs], ls="--", color=C["n3"], lw=0.8)
    ax.text(15, 7.55, "$1/f_\\Delta$", fontsize=FS, color=C["n3"])
    ax.plot([100 * f for f in fs], [1 / (a_l * f + c_l) for f in fs], color=C["stock"], lw=1.0,
            ls=(0, (4, 1.5)), label="laptop ($a$=1.06, $c$=0.152)")
    ax.plot([100 * f for f in fs], [1 / (a * f + c) for f in fs], color=C["tare"], lw=1.4, label="server fit")
    ax.axhline(1 / c, color=C["tare"], lw=0.5, ls=":")
    ax.text(99, 1 / c + 0.12, f"1/c = {1 / c:.1f}$\\times$", ha="right", va="bottom", fontsize=FS, color=C["tare"])
    ax.axhline(1, color=C["stock"], lw=0.6)
    ax.scatter([100 * f_meas] * len(pts), pts, color=C["stock"], edgecolor=C["ink"], lw=0.4, zorder=5, s=16,
               label="laptop, 38.1$\\rightarrow$38.2")
    pairs = load("release_chain/pairs.json")["pairs"]
    ax.plot([100 * p["f_delta"] for p in pairs], [1 / (a * p["f_delta"] + c) for p in pairs], ls="", marker="|",
            ms=9, mew=1.4, color=C["stock"], zorder=4, label="model at measured $f_\\Delta$")
    for p in pairs:
        speed = 1 / (a * p["f_delta"] + c)
        if p["old_release"] == "37.3":
            ax.annotate(f"{p['old_release']}$\\rightarrow${p['new_release']}", (100 * p["f_delta"], speed),
                        xytext=(5, 1), textcoords="offset points", ha="left", va="bottom", fontsize=FS)
        elif p["f_delta"] > 0.3 and not (p["old_release"] == "38.1"):
            ax.annotate(f"{p['old_release']}$\\rightarrow${p['new_release']}", (100 * p["f_delta"], speed),
                        xytext=(-4, 8), textcoords="offset points", ha="right" if p["f_delta"] > 0.8 else "left", fontsize=FS)
    head = load("exact_replay/headline_carc.json")
    ci = head["bootstrap_ci95"]
    ax.errorbar([100 * f_meas], [head["headline_median"]], yerr=[[head["headline_median"] - ci["low"]], [ci["high"] - head["headline_median"]]],
                fmt="D", ms=3.6, color=C["tare"], mfc="white", mec=C["tare"], mew=0.9, capsize=1.5, lw=0.7, zorder=6,
                label="server, median of 9 (95% CI)")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 11.4)
    ax.set_xlabel("changed fraction $f_\\Delta$ (%)")
    ax.set_ylabel("speedup over a full rerun")
    ax.set_title(f"(a) HMMER, server ($a$={a:.3f}, $c$={c:.3f})", loc="left")
    ax.grid()
    m2 = load("infernal/measured2.json")["summary"]
    ai, ci = m2["noclan"]["a"], m2["noclan"]["c"]
    fi = [0.002 + i * 0.001 for i in range(0, 200)]
    bx.plot([100 * f for f in fi], [1 / (ai * f + ci) for f in fi], color=C["tare"], lw=1.4)
    bx.axhline(1, color=C["stock"], lw=0.6)
    bx.scatter([100 * 1 / 4227], [328.4 / 666.0], marker="x", color=C["bad"], s=18, zorder=5, clip_on=False,
               label="before")
    for var, mk, dx, face in (("noclan", "o", -0.9, C["tare"]), ("clan", "D", 0.9, "white")):
        f_inf = m2[var]["f"]
        bx.errorbar([100 * f_inf + dx], [m2[var]["median_s_g"]],
                    yerr=[[m2[var]["median_s_g"] - m2[var]["bootstrap_median"]["p2.5"]],
                          [m2[var]["bootstrap_median"]["p97.5"] - m2[var]["median_s_g"]]],
                    fmt=mk, ms=3.6, color=C["tare"], mfc=face, mec=C["tare"], mew=0.9, capsize=1.5, lw=0.7, zorder=6,
                    label="after" + ("" if var == "noclan" else ", clans"))
    bx.set_xlim(0, 20)
    bx.set_ylim(0, 8)
    bx.set_xlabel("$f_\\Delta$ (%)")
    bx.set_title(f"(b) Infernal ($c$={ci:.2f})", loc="left")
    bx.grid()
    bx.legend(loc="upper right", frameon=False, handletextpad=0.3, borderaxespad=0.2)
    fig.tight_layout(w_pad=0.8, rect=(0, 0, 1, 0.78))
    h, l = ax.get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 1.0),
               handletextpad=0.4, columnspacing=1.0)
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
    fig, ax = plt.subplots(figsize=(ONE, 1.3))
    segs = [("byte-identical", ident, C["ink"]), ("same hit, different printed value", value, C["n2"]),
            ("different alignment", hsp, C["bad"]), ("stale: entry removed by release", extra, C["bad"])]
    left = 0
    for name, v, col in segs:
        ax.barh(1, v, left=left, color=col, height=0.55, label=f"{name} ({v:,})",
                hatch="////" if name.startswith("stale") else None, edgecolor="white" if name.startswith("stale") else None)
        left += v
    ax.barh(0, stock_rows, color=C["stock"], height=0.55)
    ax.text(stock_rows / 2, 0, "refused: returns the stock run (no speedup, 100% identical)",
            ha="center", va="center", fontsize=FS, color="white")
    ax.text(ident + value / 2, 1, f"{100 * ident / stock_rows:.1f}% byte-identical", ha="center", va="center", fontsize=FS)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["TARE", "iSeqSearch"])
    ax.set_xlim(0, (stock_rows + extra) * 1.01)
    ax.set_xlabel("output rows, Swiss-Prot 2026_01 $\\rightarrow$ 2026_03, 300 queries")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=2, frameon=False, handlelength=1)
    save(fig, "idiamond")


if __name__ == "__main__":
    fig_churn()
    fig_phases()
    fig_model()
    fig_idiamond()
