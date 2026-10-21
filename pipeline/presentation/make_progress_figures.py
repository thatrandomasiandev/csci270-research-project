"""Slide-ready graphs of every measured TARE result, for progress presentations.

Reads only committed result files under pipeline/results/ and writes 16:9 PNGs (and PDFs) to
pipeline/presentation/progress/. Large fonts, one result per figure. Same palette as the paper:
TARE blue, stock gray, wrong/refusal red, everything else neutral.

Run: python3 pipeline/presentation/make_progress_figures.py
"""
import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
RES = HERE.parent / "results"
OUT = HERE / "progress"
OUT.mkdir(exist_ok=True)

TARE, TARE_L, STOCK, BAD, N1, N2, INK = "#2171b5", "#9ecae1", "#636363", "#cb181d", "#d9d9d9", "#bdbdbd", "#252525"
plt.rcParams.update({
    "font.family": "sans-serif", "font.size": 15, "axes.titlesize": 19, "axes.titleweight": "bold",
    "axes.labelsize": 15, "xtick.labelsize": 13, "ytick.labelsize": 13, "legend.fontsize": 13,
    "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 100,
})
W, H = 12.0, 6.75


def load(rel):
    return json.loads((RES / rel).read_text())


def save(fig, name, note):
    # Put the source note just below everything already drawn, so it never overlaps tick labels.
    fig.canvas.draw()
    bb = fig.get_tightbbox(fig.canvas.get_renderer())
    fig.text(bb.x0 / fig.get_figwidth(), bb.y0 / fig.get_figheight() - 0.015, note, fontsize=10, color=STOCK,
             ha="left", va="top", wrap=True)
    fig.savefig(OUT / f"{name}.png", dpi=170, bbox_inches="tight")
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


# 01 headline speedup per genome --------------------------------------------------------------
def fig_headline():
    h = load("exact_replay/headline_carc.json")
    g = sorted([x for x in h["genomes"] if x["outcome"] == "EXACT"], key=lambda x: x["S_g"])
    fig, ax = plt.subplots(figsize=(W, H))
    x = range(len(g))
    ax.bar(x, [r["S_g"] for r in g], color=TARE, width=0.65)
    for i, r in enumerate(g):
        ax.text(i, r["S_g"] - 0.12, f"{r['S_g']:.2f}×", ha="center", va="top", fontsize=13, color="white", fontweight="bold")
    med, ci = h["headline_median"], h["bootstrap_ci95"]
    ax.axhspan(ci["low"], ci["high"], color=TARE_L, alpha=0.35, lw=0)
    ax.axhline(med, color=INK, lw=1.5, ls="--")
    ax.text(-0.4, 5.45, f"median {med:.2f}×  (95% CI {ci['low']:.2f}–{ci['high']:.2f}, shaded)", ha="left", fontsize=14, fontweight="bold")
    ax.axhline(1, color=STOCK, lw=1.2)
    ax.text(1.005, 1, "full rerun\n= 1×", transform=ax.get_yaxis_transform(), fontsize=11, color=STOCK, va="center")
    ax.set_xticks(list(x))
    ax.set_xticklabels([r["proteome"] for r in g], rotation=30, ha="right", fontsize=11)
    ax.set_ylabel("speedup over a full rerun")
    ax.set_ylim(0, 5.8)
    ax.set_title("Headline: Pfam 38.1→38.2 update is 4.24× faster, byte-identical output")
    save(fig, "01_headline_speedup", "HMMER 3.4 hmmscan, 9 bacterial genomes, dedicated AMD EPYC 7542 node, 3 alternating runs per arm. "
         "Source: results/exact_replay/headline_carc.json")


# 02 exactness ----------------------------------------------------------------------------------
def fig_exactness():
    t = load("exact_replay/exactness_totals.json")
    names = {
        "hmmer_replay_300": "HMMER replay, 300 proteins", "hmmer_replay_3_genomes": "HMMER replay, 3 genomes",
        "hmmer_tool_2_laptop": "HMMER tool, 2 genomes (laptop)", "hmmer_tool_server_genomes": "HMMER tool, 9 genomes (server)",
        "hmmer_tool_diverse_genomes": "HMMER tool, 48 diverse genomes", "infernal_replay_10": "Infernal replay, 10 genomes",
        "infernal_tool_family_removal": "Infernal tool, 1 family removed", "infernal_tool_10_genomes": "Infernal tool, 10 genomes",
    }
    rows = list(t["rows"].items())
    fig, ax = plt.subplots(figsize=(W, H))
    y = range(len(rows))
    ax.barh(list(y), [v for _, v in rows], color=TARE, height=0.6)
    for i, (_, v) in enumerate(rows):
        ax.text(v + 4000, i, f"{v:,} lines, 0 differ", va="center", fontsize=12)
    ax.set_yticks(list(y))
    ax.set_yticklabels([names[k] for k, _ in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, max(v for _, v in rows) * 1.35)
    ax.set_xlabel("output lines compared byte for byte with a full rerun")
    ax.set_title(f"Exactness: {t['total_lines']:,} lines, not one different")
    save(fig, "02_exactness", f"Upper bound on the per-line error rate (one-sided 95%): {t['p_up']:.1e}. "
         "Source: results/exact_replay/exactness_totals.json")


# 03 release churn --------------------------------------------------------------------------------
def fig_churn():
    p = load("release_chain/pairs.json")["pairs"]
    fig, ax = plt.subplots(figsize=(W, H))
    x = range(len(p))
    un = [q["unchanged_strict"] / q["z_new"] for q in p]
    ed = [q["edited"] / q["z_new"] for q in p]
    nw = [q["added"] / q["z_new"] for q in p]
    ax.bar(x, un, color=N2, label="unchanged (reused)")
    ax.bar(x, ed, bottom=un, color=TARE_L, label="edited (rerun)")
    ax.bar(x, nw, bottom=[a + b for a, b in zip(un, ed)], color=TARE, label="new (rerun)")
    for i, q in enumerate(p):
        ax.text(i, 1.02, f"{100 * q['f_delta']:.1f}%", ha="center", color=TARE, fontsize=13)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{q['old_release']}→{q['new_release']}" for q in p])
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("fraction of the new release")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.28), ncol=3, frameon=False)
    ax.set_title("How much of Pfam changes per release (median 12.2%)")
    save(fig, "03_release_churn", "Strict hash of every Pfam model, seven consecutive releases 37.0→38.2. 37.4→38.0 was a full rebuild. "
         "Source: results/release_chain/pairs.json")


# 04 cost model (server) ----------------------------------------------------------------------------
def fig_model():
    s = load("exact_replay/server_cost_fit.json")
    h = load("exact_replay/headline_carc.json")
    a, c = s["a"], s["c"]
    fs = [i / 1000 for i in range(5, 1000)]
    fig, ax = plt.subplots(figsize=(W, H))
    ax.plot([100 * f for f in fs], [1 / (a * f + c) for f in fs], color=TARE, lw=2.5, label=f"model: 1/(a·f + c), a={a:.2f}, c={c:.3f}")
    ax.plot([100 * f for f in fs], [min(1 / f, 12) for f in fs], color=N2, ls="--", lw=1.5, label="upper bound 1/f")
    ax.axhline(1 / c, color=TARE, ls=":", lw=1.2)
    ax.text(99, 1 / c + 0.2, f"ceiling 1/c = {1 / c:.1f}×", ha="right", color=TARE, fontsize=12)
    ax.axhline(1, color=STOCK, lw=1.2)
    for pr in s["predictions"]:
        ax.plot(100 * pr["f_delta"], pr["speedup"], "o", color=STOCK, ms=7)
        if pr["f_delta"] > 0.3:
            ax.annotate(f"{pr['old_release']}→{pr['new_release']}", (100 * pr["f_delta"], pr["speedup"]), xytext=(6, 8),
                        textcoords="offset points", fontsize=12, color=STOCK)
    ax.annotate("four small releases\n(2–12% changed): 4.6–8.5×", (4, 7.8), xytext=(14, 8.6), fontsize=12, color=STOCK,
                arrowprops=dict(arrowstyle="-", color=STOCK, lw=0.8))
    ci = h["bootstrap_ci95"]
    ax.errorbar([100 * s["f"]], [h["headline_median"]], yerr=[[h["headline_median"] - ci["low"]], [ci["high"] - h["headline_median"]]],
                fmt="D", color=TARE, mfc="white", mew=2, ms=10, capsize=5, label="measured: 4.24× (median of 9)")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 12)
    ax.set_xlabel("fraction of the database that changed (%)")
    ax.set_ylabel("speedup over a full rerun")
    ax.legend(loc="center right", frameon=False)
    ax.set_title("A two-term cost model predicts the speedup (4.37× predicted, 4.24× measured)")
    save(fig, "04_cost_model", "Gray dots: model at each Pfam release's measured changed fraction. Above ~93% changed, TARE falls back to a full run. "
         "Source: results/exact_replay/server_cost_fit.json")


# 05 where the time goes (server) ---------------------------------------------------------------------
def fig_phases():
    s = load("exact_replay/server_cost_fit.json")["phase_bars"]["genomes"]
    fig, ax = plt.subplots(figsize=(W, H))
    order = [("discovery", TARE, "discovery (search changed families)"), ("replay", TARE_L, "replay (candidates only)"),
             ("check", N2, "safety check"), ("other", N1, "everything else")]
    for i, g in enumerate(s):
        left = 0
        for k, col, lab in order:
            v = g["stages_s"][k]
            ax.barh(i, v, left=left, color=col, height=0.55, label=lab if i == 0 else None)
            left += v
        ax.plot([g["stock_median_s"]] * 2, [i - 0.35, i + 0.35], color=INK, lw=3)
        ax.text(g["stock_median_s"] + 30, i, f"full rerun {g['stock_median_s']:.0f} s", va="center", fontsize=12)
        ax.text(left + 30, i - 0.32, f"TARE {g['tare_wall_s']:.0f} s ({g['S_g']:.2f}×)", fontsize=12, color=TARE, fontweight="bold")
    ax.set_yticks(range(len(s)))
    ax.set_yticklabels([f"{g['role'].replace('_S_g', '').replace('_', ' ')}\n{g['proteome']}" for g in s])
    ax.invert_yaxis()
    ax.set_xlim(0, 3200)
    ax.set_xlabel("wall-clock seconds")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.32), ncol=4, frameon=False, fontsize=12)
    ax.set_title("Where the time goes: discovery dominates an update")
    save(fig, "05_where_time_goes", "Server headline, the update run with the median time for the lowest, median, and highest-speedup genome. "
         "Source: results/exact_replay/server_cost_fit.json")


# 06 Infernal --------------------------------------------------------------------------------------
def fig_infernal():
    m = load("infernal/measured2.json")["summary"]
    bars = [("Full rerun", 1.0, None, STOCK), ("TARE, first version", 328.4 / 666.0, None, BAD),
            ("TARE, no clans", m["noclan"]["median_s_g"], m["noclan"]["bootstrap_median"], TARE),
            ("TARE, with clans", m["clan"]["median_s_g"], m["clan"]["bootstrap_median"], TARE)]
    fig, ax = plt.subplots(figsize=(W, H))
    for i, (lab, v, ci, col) in enumerate(bars):
        err = None if ci is None else [[v - ci["p2.5"]], [ci["p97.5"] - v]]
        ax.bar(i, v, color=col, width=0.6, yerr=err, capsize=6)
        ax.text(i, (ci["p97.5"] if ci else v) + 0.07, f"{v:.2f}×", ha="center", fontsize=15, fontweight="bold")
    ax.axhline(1, color=INK, ls="--", lw=1)
    ax.set_xticks(range(len(bars)))
    ax.set_xticklabels([b[0] for b in bars])
    ax.set_ylabel("speedup over a full rerun")
    ax.set_ylim(0, 2.8)
    ax.set_title("Second program (Infernal, RNA families): about 2× faster, exact")
    save(fig, "06_infernal", "Infernal 1.1.5 cmscan, Rfam 15.0→15.1, median of 10 genomes, 95% bootstrap CI; laptop timings, 3 alternating runs. "
         "First version: one-family removal. Source: results/infernal/measured2.json")


# 07 safety: adversarial before/after --------------------------------------------------------------
def fig_safety():
    v2 = load("adversarial/v2_summary.json")["arms"]
    m = load("adversarial/measured.json")["cells"]
    first = sum(c["UNSAFE"] for k, c in m.items() if k.startswith(("C2", "C3")))
    labels = ["Original check\n(audit off)", "Audit on\n(~50 records)", "Bounded audit\n(299 records, now default)"]
    allv = [first, v2["shipped"]["hidden_unsafe"], v2["bounded"]["hidden_unsafe"]]
    cov = [None, v2["shipped"]["covered_unsafe"], v2["bounded"]["covered_unsafe"]]
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(W, H))
    ax.bar(range(3), [100 * x / 800 for x in allv], color=[BAD, N2, TARE], width=0.6)
    for i, x in enumerate(allv):
        ax.text(i, 100 * x / 800 + 2, f"{x}/800", ha="center", fontsize=14)
    ax.set_xticks(range(3))
    ax.set_xticklabels(labels, fontsize=12)
    ax.set_ylabel("wrong updates that got through (%)")
    ax.set_ylim(0, 105)
    ax.set_title("All hidden couplings", fontsize=16)
    bx.bar(range(2), [100 * cov[1] / 400, 100 * cov[2] / 400], color=[N2, TARE], width=0.55)
    for i, x in enumerate(cov[1:]):
        bx.text(i, 100 * x / 400 + 1, f"{x}/400", ha="center", fontsize=14)
    bx.axhline(5, color=BAD, ls="--", lw=1.5)
    bx.text(1.45, 5.6, "guarantee: ≤ 5%", ha="right", color=BAD, fontsize=13)
    bx.set_xticks(range(2))
    bx.set_xticklabels(labels[1:], fontsize=12)
    bx.set_ylim(0, 40)
    bx.set_title("When ≥ 1% of records are affected", fontsize=16)
    fig.suptitle("Safety: a sized audit turns 'usually caught' into a stated bound", fontsize=19, fontweight="bold")
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    save(fig, "07_safety_audit", "Injected hidden or distant coupling into an HMMER stand-in; 800 trials per check, 2,000 records. No clean trial was refused. "
         "Sources: results/adversarial/measured.json, v2_summary.json")


# 08 DIAMOND order dependence ------------------------------------------------------------------------
def fig_diamond():
    d = load("diamond_order/g1_measured.json")
    sh = d["shuffles"]
    fig, ax = plt.subplots(figsize=(W, H))
    x = range(len(sh))
    miss = [s["comparison"]["missing"] for s in sh]
    extra = [s["comparison"]["extra"] for s in sh]
    ax.bar([i - 0.2 for i in x], miss, width=0.4, color=BAD, label="hits lost")
    ax.bar([i + 0.2 for i in x], extra, width=0.4, color=N2, label="hits gained")
    for i in x:
        ax.text(i - 0.2, miss[i] + 0.6, str(miss[i]), ha="center", fontsize=13)
        ax.text(i + 0.2, extra[i] + 0.6, str(extra[i]), ha="center", fontsize=13)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"shuffle {i + 1}" for i in x])
    ax.set_ylabel("output rows that changed")
    ax.legend(frameon=False)
    ax.set_title("Finding: DIAMOND's results depend on database order")
    save(fig, "08_diamond_order", f"Same 2,000 queries against Swiss-Prot 2026_03 in 5 random orders, out of {d['original_search']['rows']:,} rows. "
         "Root cause: a 16-byte window that crosses entry boundaries. Source: results/diamond_order/g1_measured.json")


# 09 baselines ---------------------------------------------------------------------------------------------
def fig_baselines():
    b = load("baseline_overhead.json")["modes"]["hmmscan"]
    r = [float(x) for x in b["riker"]["paired_ratio_vs_stock"]]
    i = [float(x) for x in b["incr_default"]["paired_ratio_vs_stock"]]
    h = load("exact_replay/headline_carc.json")
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(W, H), gridspec_kw={"width_ratios": [1.2, 1]})
    names = ["Riker", "INCR", "TARE"]
    first = [statistics.mean(r), statistics.mean(i), h["first_run_overhead_median"]]
    ax.bar(range(3), first, color=[N2, N2, TARE], width=0.6)
    for k, v in enumerate(first):
        ax.text(k, v + 0.05, f"{v:.2f}×", ha="center", fontsize=14)
    ax.axhline(1, color=INK, ls="--", lw=1)
    ax.set_xticks(range(3))
    ax.set_xticklabels(names)
    ax.set_ylabel("first run, relative to a plain run")
    ax.set_title("First-run cost", fontsize=16)
    upd = [1.0, 1.0, h["headline_median"]]
    bx.bar(range(3), upd, color=[N2, N2, TARE], width=0.6)
    for k, v in enumerate(upd):
        bx.text(k, v + 0.08, "1× (reruns)" if k < 2 else f"{v:.2f}× faster", ha="center", fontsize=13)
    bx.set_xticks(range(3))
    bx.set_xticklabels(names)
    bx.set_ylabel("speedup on a database release")
    bx.set_ylim(0, 5)
    bx.set_title("After a database release", fontsize=16)
    fig.suptitle("General-purpose caches cannot reuse anything after a release", fontsize=19, fontweight="bold")
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    save(fig, "09_baselines", "Riker and INCR: mean of 4 paired runs in one container (500 proteins). TARE: server median of 9 genomes. "
         "Source: results/baseline_overhead.json, results/exact_replay/headline_carc.json")


# 10 approximate vs exact -----------------------------------------------------------------------------------
def fig_approx():
    r = load("baselines_exact/rescale.json")["pooled"]["tbl"]
    i = load("reference_diamond/dx.json")["dx_i"]["idiamond"]
    vals = [("Rescale old E-values\n(HMMER)", 100 * r["byte_identical_over_stock"], N2),
            ("iSeqSearch\n(incremental DIAMOND)", 100 * i["shared_byte_identical"] / i["shared_rows"], N2),
            ("TARE", 100.0, TARE)]
    fig, ax = plt.subplots(figsize=(W, H))
    for k, (lab, v, col) in enumerate(vals):
        ax.bar(k, v, color=col, width=0.6)
        ax.text(k, v + 2, f"{v:.1f}%", ha="center", fontsize=16, fontweight="bold")
    ax.set_xticks(range(3))
    ax.set_xticklabels([v[0] for v in vals])
    ax.set_ylabel("output lines identical to a full rerun (%)")
    ax.set_ylim(0, 112)
    ax.set_title("Approximate shortcuts are not exact; TARE is")
    save(fig, "10_approximate_vs_exact", f"iSeqSearch also reported {i['row_extra']} hits to sequences the new release deleted. "
         "Sources: results/baselines_exact/rescale.json, results/reference_diamond/dx.json")


# 11 diverse genomes and needless refusals ------------------------------------------------------------------
def fig_diverse():
    d = load("diverse_genomes/measured_score.json")["by_group"]
    groups = ["archaea", "bacteria", "eukaryote", "mag"]
    names = {"archaea": "Archaea", "bacteria": "Bacteria", "eukaryote": "Eukaryotes", "mag": "Metagenome-\nassembled"}
    fig, ax = plt.subplots(figsize=(W, H))
    ship = [d[g]["pass"] for g in groups]
    ref = [d[g]["needless_refusal"] for g in groups]
    ax.bar(range(4), ship, color=TARE, width=0.6, label="shipped, byte-identical")
    ax.bar(range(4), ref, bottom=ship, color=N2, width=0.6, label="refused although exact (both causes since fixed)")
    for k in range(4):
        ax.text(k, ship[k] + ref[k] + 0.4, f"{ship[k]}/{ship[k] + ref[k]}", ha="center", fontsize=14)
    ax.set_xticks(range(4))
    ax.set_xticklabels([names[g] for g in groups])
    ax.set_ylabel("genomes")
    ax.legend(frameon=False, loc="upper right")
    ax.set_title("Diverse genomes: 48 of 53 shipped exact, none wrong")
    save(fig, "11_diverse_genomes", "HMMER, Pfam 38.1→38.2, includes Drosophila (96 proteins with >20 domains). After two parser fixes, all refused genomes ship exact. "
         "Source: results/diverse_genomes/measured_score.json, results/w6_followup/")


# 12 payback ------------------------------------------------------------------------------------------------
def fig_payback():
    h = load("exact_replay/headline_carc.json")
    f = load("infernal/fill_summary.json")["variants"]["noclan"]
    fig, ax = plt.subplots(figsize=(W, H))
    vals = [("HMMER\n(server)", h["first_run_overhead_median"], h["break_even_n_median"]),
            ("Infernal\n(laptop)", f["median_fill_over_stock"], f["payback_releases"])]
    for k, (lab, fill, n) in enumerate(vals):
        ax.bar(k, fill, color=TARE if k == 0 else N2, width=0.5)
        ax.text(k, fill + 0.1, f"first run {fill:.2f}× a full run\npays back after {n:.1f} updates", ha="center", fontsize=13)
    ax.axhline(1, color=INK, ls="--", lw=1)
    ax.set_xticks(range(2))
    ax.set_xticklabels([v[0] for v in vals])
    ax.set_ylabel("first (cache-filling) run, × a full run")
    ax.set_ylim(0, 6)
    ax.set_title("One-time cost: HMMER pays back on the first update")
    save(fig, "12_payback", "Sources: results/exact_replay/headline_carc.json, results/infernal/fill_summary.json")


# 13 unrelated program (PROSITE) --------------------------------------------------------------------------------
def fig_prosite():
    a = load("unrelated_ship/measured.json")["checks"]
    b = load("unrelated_ship/measured_v2.json")["checks"]
    fig, ax = plt.subplots(figsize=(W, H))
    rows = [("Draw 1", a["n_ship"], a["n"] - a["n_ship"]), ("Draw 2 (fresh)", b["n_ship"], b["n"] - b["n_ship"])]
    for k, (lab, s, inc) in enumerate(rows):
        ax.barh(k, s, color=TARE, height=0.5, label="shipped, byte-identical" if k == 0 else None)
        ax.barh(k, inc, left=s, color=N1, height=0.5, label="too few output lines to count" if k == 0 else None)
        ax.text(s + inc + 0.3, k, f"{s} of {s + inc} exact, 0 wrong", va="center", fontsize=14)
    ax.set_yticks(range(2))
    ax.set_yticklabels([r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 28)
    ax.set_xlabel("genomes")
    ax.legend(frameon=False, loc="upper right")
    ax.set_title("A program from another lab (PROSITE pfscanV3): 26 of 30 exact")
    save(fig, "13_prosite_unrelated", "SIB pftools pfscanV3, PROSITE 2026_02→2026_03, no pin needed. Both draws fell just below their power floors, "
         "so they are supporting evidence. Sources: results/unrelated_ship/measured.json, measured_v2.json")


if __name__ == "__main__":
    for fn in (fig_headline, fig_exactness, fig_churn, fig_model, fig_phases, fig_infernal, fig_safety, fig_diamond,
               fig_baselines, fig_approx, fig_diverse, fig_payback, fig_prosite):
        fn()
