/* TARE console. Every number on screen comes from the local engine (/api/*). */

const ICONS = {
  logo: "M12 2 2 7l10 5 10-5-10-5z M2 17l10 5 10-5 M2 12l10 5 10-5",
  newrun: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M12 18v-6 M9 15h6",
  folderOpen: "M6 14l1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2",
  folder: "M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2z",
  save: "M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z M17 21v-8H7v8 M7 3v5h8",
  addInputs: "M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7 M18 2v6 M15 5h6 M8 12h8 M8 16h5",
  tool: "M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z",
  checks: "M18 6 7 17l-5-5 M22 10l-7.5 7.5L13 16",
  diff: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M9 11h6 M12 8v6 M9 18h6",
  play: "M6 3l14 9-14 9z",
  cancel: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z M15 9l-6 6 M9 9l6 6",
  retry: "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8 M21 3v5h-5 M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16 M8 16H3v5",
  logs: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8",
  compare: "M18 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M13 6h3a2 2 0 0 1 2 2v7 M11 18H8a2 2 0 0 1-2-2V9",
  cpu: "M5 5h14v14H5z M9 9h6v6H9z M9 1v3 M15 1v3 M9 20v3 M15 20v3 M20 9h3 M20 14h3 M1 9h3 M1 14h3",
  download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M7 10l5 5 5-5 M12 15V3",
  report: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M8 18v-2 M12 18v-4 M16 18v-6",
  bundle: "M16.5 9.4 7.55 4.24 M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z M3.27 6.96 12 12.01l8.73-5.05 M12 22.08V12",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z M21 21l-4.35-4.35",
  right: "M9 18l6-6-6-6",
  down: "M6 9l6 6 6-6",
  db: "M12 8c4.97 0 9-1.34 9-3s-4.03-3-9-3-9 1.34-9 3 4.03 3 9 3z M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5 M3 12c0 1.66 4 3 9 3s9-1.34 9-3",
  layers: "M12 2 2 7l10 5 10-5-10-5z M2 17l10 5 10-5 M2 12l10 5 10-5",
  ok: "M22 11.08V12a10 10 0 1 1-5.93-9.14 M22 4 12 14.01l-3-3",
  check: "M20 6 9 17l-5-5",
  clock: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z M12 6v6l4 2",
  warn: "M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z M12 9v4 M12 17h.01",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z M12 16v-4 M12 8h.01",
  x: "M18 6 6 18 M6 6l12 12",
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M17 8l-5-5-5 5 M12 3v12",
  build: "M2 20h20 M5 20V9l7-5 7 5v11 M9 20v-6h6v6",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z M9 12l2 2 4-4",
  trash: "M3 6h18 M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6 M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2",
  users: "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M23 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75",
  history: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8 M3 3v5h5 M12 7v5l4 2",
  term: "M4 17l6-6-6-6 M12 19h8",
  plug: "M12 22v-5 M9 8V2 M15 8V2 M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8z",
  sliders: "M4 21v-7 M4 10V3 M12 21v-9 M12 8V3 M20 21v-5 M20 12V3 M1 14h6 M9 8h6 M17 16h6",
  scale: "M16 16l3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1z M2 16l3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1z M7 21h10 M12 3v18 M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2",
  copy: "M20 9h-9a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2z M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1",
  export: "M14 3h7v7 M10 14 21 3 M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6",
  dna: "M2 15c6.667-6 13.333 0 20-6 M9 22c1.8-2 2.52-4 2.81-6 M15 2c-1.8 2-2.52 4-2.81 6 M17 6l-2.5-2.5 M14 8l-1-1 M7 18l2.5 2.5 M10 16l1.5 1.5",
  doc: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6",
  more: "M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2z M12 6a1 1 0 1 0 0-2 1 1 0 0 0 0 2z M12 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  spin: "M21 12a9 9 0 1 1-6.22-8.56",
  memory: "M6 19v-3 M10 19v-3 M14 19v-3 M18 19v-3 M8 11V9 M16 11V9 M12 11V9 M2 15h20 M2 7a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v1.1a2 2 0 0 0 0 3.84V17a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-5.1a2 2 0 0 0 0-3.84z",
  disk: "M22 12H2 M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z M6 16h.01 M10 16h.01",
  activity: "M22 12h-4l-3 9L9 3l-3 9H2",
  home: "M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M9 22V12h6v10",
};

const ic = (name, cls = "") => `<svg class="i ${cls}" viewBox="0 0 24 24"><path d="${ICONS[name] || ICONS.info}"/></svg>`;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const $ = (sel) => document.querySelector(sel);
const n0 = (x) => (x == null ? "–" : Number(x).toLocaleString());
const fx = (x, d = 2) => (x == null ? "–" : Number(x).toFixed(d));

function dur(s) {
  if (s == null || isNaN(s)) return "—";
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const p = (v) => String(v).padStart(2, "0");
  return h ? `${h}:${p(m)}:${p(sec)}` : `${p(m)}:${p(sec)}`;
}
function bytes(b) {
  if (b == null) return "–";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return `${b.toFixed(b >= 100 || i === 0 ? 0 : 1)} ${u[i]}`;
}
const since = (iso) => (iso ? (Date.now() - Date.parse(iso)) / 1000 : null);
const clock = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour12: false }) : "");
const stamp = (iso) => (iso ? new Date(iso).toLocaleString([], { hour12: false, year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(path, opt);
  const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
  if (!res.ok || (data && data.error && res.status >= 400)) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function toast(msg, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = `${ic(kind === "bad" ? "warn" : kind === "ok" ? "ok" : "info")}<div>${esc(msg)}</div>`;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), kind === "bad" ? 7000 : 3800);
}

async function act(fn, okMsg) {
  try {
    const r = await fn();
    if (okMsg) toast(typeof okMsg === "function" ? okMsg(r) : okMsg, "ok");
    await refresh(true);
    return r;
  } catch (e) {
    toast(e.message, "bad");
    return null;
  }
}

/* ---------------------------------------------------------------- state */

const S = {
  app: null, pid: null, P: null, rid: null, run: null,
  log: [], logRid: null, files: null,
  tab: "live", itab: "config", ltab: "activity",
  sel: null, filter: "", board: null, preflight: null, cmd: null,
  open: { inputs: false, runs: true, presets: false, project: true },
  advOpen: true, limits: null, timer: null,
};

const TABS = [
  ["overview", "Overview"], ["setup", "Run Setup"], ["plan", "Plan & Preflight"], ["live", "Live Runs"],
  ["results", "Results"], ["verify", "Verification"], ["cache", "Cache & References"], ["compute", "Compute & Settings"],
];
const STAGES = [["prepare", "Prepare"], ["check", "Check reuse"], ["replay", "Replay"], ["verify", "Verify"], ["complete", "Complete"]];
const KIND_TITLE = { update: "Updating annotations", cache: "Building cache", full: "Full computation" };

const activeRun = () => S.run && ["running", "queued"].includes(S.run.status);
const projectBusy = () => (S.P?.runs || []).some((r) => ["running", "queued"].includes(r.status));
const tool = () => S.P?.tool || {};
const refLabel = (side) => S.P?.references?.[side]?.label || "—";

async function refresh(force = false) {
  clearTimeout(S.timer);
  try {
    S.app = await api("/api/app");
    if (!S.pid && S.app.setup.ready) S.pid = S.app.recent[0]?.id || S.app.demo_id;
    if (S.pid) {
      S.P = await api(`/api/projects/${encodeURIComponent(S.pid)}`);
      if (!S.rid || !S.P.runs.some((r) => r.id === S.rid)) S.rid = S.P.runs[0]?.id || null;
    }
    if (S.rid) {
      S.run = await api(`/api/runs/${encodeURIComponent(S.rid)}`);
      if (S.logRid !== S.rid) { S.log = []; S.logRid = S.rid; S.files = null; }
      const lg = await api(`/api/runs/${encodeURIComponent(S.rid)}/log?after=${S.log.length}`);
      S.log.push(...lg.rows);
      if (S.ltab === "files" && (force || !S.files || activeRun())) S.files = (await api(`/api/runs/${encodeURIComponent(S.rid)}/files`)).files;
    } else {
      S.run = null; S.log = []; S.logRid = null;
    }
  } catch (e) {
    console.error(e);
  }
  render();
  const busy = !S.app?.setup?.ready || projectBusy() || S.run?.comparing;
  S.timer = setTimeout(refresh, busy ? 1000 : 4000);
}

/* ---------------------------------------------------------------- render */

function keepFocus(el, html) {
  const a = document.activeElement;
  if (a && el.contains(a) && /INPUT|SELECT|TEXTAREA/.test(a.tagName)) return false;
  el.innerHTML = html;
  return true;
}

function render() {
  $("#logo").innerHTML = ic("logo");
  const proj = S.P?.project;
  $("#window-title").innerHTML = proj ? `${esc(proj.name)} · TARE` : "TARE";
  document.title = proj ? `${proj.name} · TARE` : "TARE";
  $("#menutabs").innerHTML = TABS.map(([id, label]) => `<button class="${S.tab === id ? "on" : ""}" data-act="tab" data-tab="${id}">${label}</button>`).join("");
  renderRibbon();
  renderLeft();
  const center = $("#center");
  const logScroll = center.querySelector(".logbody");
  const atBottom = logScroll ? logScroll.scrollTop + logScroll.clientHeight >= logScroll.scrollHeight - 4 : true;
  const prevTop = logScroll ? logScroll.scrollTop : 0;
  keepFocus(center, renderCenter());
  const lb = center.querySelector(".logbody");
  if (lb) lb.scrollTop = atBottom ? lb.scrollHeight : prevTop;
  keepFocus($("#right"), renderRight());
  renderStatus();
}

function rbtn(icon, label, actName, { disabled = false, cls = "", title = "" } = {}) {
  return `<button class="rbtn ${cls}" data-act="${actName}" ${disabled ? "disabled" : ""} title="${esc(title || label)}">${ic(icon)}<span>${label}</span></button>`;
}

function renderRibbon() {
  const has = !!S.P;
  const r = S.run;
  const canStart = has && !projectBusy() && S.P.project.settings.compute === "local";
  const retryable = r && !activeRun() && r.items.some((i) => ["failed", "cancelled", "refused"].includes(i.status));
  const finished = r && !activeRun();
  const groups = [
    ["Project", [rbtn("newrun", "New Run", "newRun", { disabled: !has }), rbtn("folderOpen", "Open Project", "openProject"), rbtn("save", "Save Preset", "savePreset", { disabled: !has })]],
    ["Prepare", [rbtn("addInputs", "Add Inputs", "addInputs", { disabled: !has }), rbtn("tool", "Select Tool", "selectTool", { disabled: !has }), rbtn("checks", "Check Setup", "checkSetup", { disabled: !has }), rbtn("diff", "Preview Changes", "previewChanges", { disabled: !has })]],
    ["Execute", [rbtn("play", "Start Run", "startRun", { disabled: !canStart, cls: "go", title: canStart ? "Start an update run on all inputs" : "A run is already active, or compute is not This Mac" }), rbtn("cancel", "Cancel", "cancelRun", { disabled: !activeRun(), cls: "danger" }), rbtn("retry", "Retry Failed", "retryFailed", { disabled: !retryable })]],
    ["Inspect", [rbtn("logs", "View Logs", "viewLogs", { disabled: !r }), rbtn("compare", "Compare Runs", "compareRuns", { disabled: (S.P?.runs || []).length < 2 }), rbtn("cpu", "Run Full Computation", "runFull", { disabled: !canStart })]],
    ["Export", [rbtn("folderOpen", "Open Output", "openOutput", { disabled: !r }), rbtn("download", "Download Results", "downloadResults", { disabled: !finished }), rbtn("report", "Export Report", "exportReport", { disabled: !finished }), rbtn("bundle", "Reproducibility Bundle", "exportBundle", { disabled: !finished })]],
  ];
  $("#ribbon").innerHTML = groups.map(([label, btns]) => `<div class="rgroup"><div class="rbtns">${btns.join("")}</div><div class="rlabel">${label}</div></div>`).join("");
}

/* ---- left */

function tnode({ icon, label, act: a, data = {}, sel = false, twisty = null, iconCls = "", depth = 0 }) {
  const attrs = Object.entries(data).map(([k, v]) => `data-${k}="${esc(v)}"`).join(" ");
  const tw = twisty == null ? `<span class="tw"></span>` : `<span class="tw" data-act="toggle" data-key="${twisty[0]}">${ic(twisty[1] ? "down" : "right", "sm")}</span>`;
  return `<li><div class="tnode ${sel ? "sel" : ""}" ${a ? `data-act="${a}"` : ""} ${attrs} style="padding-left:${6 + depth * 14}px" title="${esc(label)}">${tw}<span class="${iconCls}">${ic(icon)}</span><span class="lbl">${esc(label)}</span></div></li>`;
}

function runIcon(status) {
  return { running: ["spin", "run spin"], queued: ["clock", ""], completed: ["ok", "ok"], failed: ["cancel", "bad"], cancelled: ["cancel", "bad"] }[status] || ["doc", ""];
}

function renderTree() {
  if (!S.P) return `<div class="muted small" style="padding:8px 14px">${S.app?.setup?.state === "running" ? esc(S.app.setup.message) + "…" : "No project open"}</div>`;
  const p = S.P.project;
  const f = S.filter.toLowerCase();
  const match = (s) => !f || String(s).toLowerCase().includes(f);
  const o = S.open;
  const rows = [];
  rows.push(tnode({ icon: "folder", label: p.name, act: "tab", data: { tab: "overview" }, twisty: ["project", o.project] }));
  if (o.project) {
    const ins = p.inputs;
    if (match(`inputs ${ins.length} proteomes`) || ins.some((i) => match(i.label))) {
      rows.push(tnode({ icon: "dna", label: `Inputs / ${ins.length} proteomes`, act: "tab", data: { tab: "setup" }, twisty: ["inputs", o.inputs || !!f], depth: 1 }));
      if (o.inputs || f) ins.filter((i) => match(i.label) || match("inputs")).forEach((i) => rows.push(tnode({ icon: "doc", label: `${i.id} · ${i.label}`, act: "tab", data: { tab: "setup" }, depth: 2 })));
    }
    const t = tool();
    if (match(`tool ${t.label} ${t.program}`)) rows.push(tnode({ icon: "tool", label: `Tool / ${t.label} - ${t.program}`, act: "selectTool", depth: 1 }));
    if (match(`references ${refLabel("old")} ${refLabel("new")}`)) rows.push(tnode({ icon: "layers", label: `References / ${refLabel("old")} → ${refLabel("new").replace(/^Pfam /, "")}`, act: "tab", data: { tab: "cache" }, depth: 1 }));
    const pre = S.app.presets || [];
    if (match("saved presets") || pre.some((x) => match(x.name))) {
      rows.push(tnode({ icon: "save", label: `Saved presets${pre.length ? ` (${pre.length})` : ""}`, act: "toggle", data: { key: "presets" }, twisty: ["presets", o.presets || !!f], depth: 1 }));
      if (o.presets || f) pre.filter((x) => match(x.name) || match("saved presets")).forEach((x) => rows.push(tnode({ icon: "sliders", label: x.name, act: "applyPreset", data: { name: x.name }, depth: 2 })));
    }
    const runs = S.P.runs;
    if (match("runs") || runs.some((r) => match(r.name))) {
      rows.push(tnode({ icon: "folder", label: "Runs", act: "toggle", data: { key: "runs" }, twisty: ["runs", o.runs || !!f], depth: 1 }));
      if (o.runs || f) runs.filter((r) => match(r.name) || match("runs")).forEach((r) => {
        const [icn, cls] = runIcon(r.status);
        const suffix = { running: " - Running", queued: " - Queued", completed: " - Completed", failed: " - Failed", cancelled: " - Cancelled" }[r.status] || "";
        rows.push(tnode({ icon: icn, iconCls: cls, label: `${r.name}${suffix}`, act: "selectRun", data: { rid: r.id }, sel: r.id === S.rid, depth: 2 }));
      });
    }
    if (match("outputs")) rows.push(tnode({ icon: "folder", label: "Outputs", act: "tab", data: { tab: "results" }, depth: 1 }));
    if (match("verification reports")) rows.push(tnode({ icon: "folder", label: "Verification reports", act: "tab", data: { tab: "verify" }, depth: 1 }));
    if (match("cache")) rows.push(tnode({ icon: "db", label: "Cache", act: "tab", data: { tab: "cache" }, depth: 1 }));
  }
  return `<ul class="tree">${rows.join("")}</ul>`;
}

function renderLeft() {
  const left = $("#left");
  if (!left.dataset.built) {
    left.innerHTML = `
      <div class="phead">Project Browser <span class="more" data-act="openProject">${ic("more", "sm")}</span></div>
      <div class="search">${ic("search", "sm")}<input id="treefilter" placeholder="Search project items..." /></div>
      <div id="tree"></div>
      <div class="phead">Project Management</div>
      <div class="mgmt">
        <button class="mbtn" data-act="importRelease">${ic("upload")}Import Release...</button>
        <button class="mbtn" data-act="buildCache">${ic("build")}Build Cache...</button>
        <button class="mbtn" data-act="validateCache">${ic("shield")}Validate Cache...</button>
        <button class="mbtn warn" data-act="invalidateCache">${ic("warn")}Invalidate...</button>
        <button class="mbtn danger" data-act="cleanUp">${ic("trash")}Clean Up...</button>
      </div>
      <div class="phead">Recent Projects</div>
      <ul class="recent" id="recent"></ul>`;
    left.dataset.built = "1";
    $("#treefilter").addEventListener("input", (e) => { S.filter = e.target.value; $("#tree").innerHTML = renderTree(); });
  }
  $("#tree").innerHTML = renderTree();
  const rec = S.app?.recent || [];
  $("#recent").innerHTML = rec.length
    ? rec.map((p) => `<li class="${p.id === S.pid ? "sel" : ""}" data-act="switchProject" data-pid="${esc(p.id)}">${ic("clock", "sm")}${esc(p.name)}</li>`).join("")
    : `<li class="muted">None yet</li>`;
}

/* ---- center */

function renderCenter() {
  if (!S.app) return `<div class="empty">Connecting to the TARE engine…</div>`;
  if (!S.P) {
    const s = S.app.setup;
    if (s.state === "error") return `<div class="empty"><h2>Demo setup failed</h2><p>${esc(s.error)}</p><button class="btn" data-act="setupDemo">${ic("retry")}Try again</button></div>`;
    return `<div class="empty"><h2>${ic("spin", "spin")} Setting up the demo project</h2><p>${esc(s.message || "Starting")}…</p><p class="small">Reads the local Pfam 38.1 and 38.2 files once and slices the E. coli proteomes. About 10 seconds.</p></div>`;
  }
  return ({ overview: viewOverview, setup: viewSetup, plan: viewPlan, live: viewLive, results: viewResults, verify: viewVerify, cache: viewCache, compute: viewCompute }[S.tab] || viewLive)();
}

function statusPill(run) {
  const m = {
    running: `<span class="pill">${ic("spin", "sm spin")}Running</span>`,
    queued: `<span class="pill mute">${ic("clock", "sm")}Queued</span>`,
    completed: `<span class="pill ok">${ic("check", "sm")}Completed</span>`,
    failed: `<span class="pill bad">${ic("cancel", "sm")}Failed</span>`,
    cancelled: `<span class="pill warn">${ic("cancel", "sm")}Cancelled</span>`,
  };
  return m[run.status] || "";
}

function stepper(run) {
  const idx = STAGES.findIndex(([k]) => k === run.stage);
  const doneAll = run.status === "completed";
  const parts = STAGES.map(([k, label], i) => {
    let cls = "";
    if (doneAll || i < idx) cls = "done";
    else if (i === idx) cls = ["failed", "cancelled"].includes(run.status) ? "fail" : run.status === "queued" ? "" : "cur";
    const dot = cls === "done" ? ic("check") : cls === "fail" ? ic("x", "sm") : "";
    const line = i < STAGES.length - 1 ? `<div class="sline ${doneAll || i < idx ? "done" : ""}"></div>` : "";
    return `<div class="step ${cls}"><span class="dot">${dot}</span>${label}</div>${line}`;
  });
  return `<div class="stepper">${parts.join("")}</div>`;
}

function itemElapsed(i) {
  if (i.status === "running" && i.started_at) return since(i.started_at);
  return i.elapsed_s;
}

function runProgress(run) {
  const total = run.items.length;
  const fin = run.items.filter((i) => ["done", "refused", "failed", "cancelled"].includes(i.status)).length;
  const done = run.items.filter((i) => ["done", "refused"].includes(i.status));
  const elapsed = run.finished_at ? run.wall_s ?? (Date.parse(run.finished_at) - Date.parse(run.started_at)) / 1000 : run.started_at ? since(run.started_at) : 0;
  const avg = done.length ? done.reduce((a, i) => a + (i.elapsed_s || 0), 0) / done.length : null;
  const left = total - fin;
  const running = run.items.find((i) => i.status === "running");
  let remaining = null;
  if (avg != null && left > 0) remaining = Math.max(0, avg * left - (running ? since(running.started_at) || 0 : 0));
  return { total, fin, done: done.length, pct: total ? Math.round((100 * fin) / total) : 0, elapsed, remaining };
}

function remainingText(s) {
  if (s == null) return "";
  if (s < 60) return ` · About ${Math.max(1, Math.round(s))} s remaining`;
  return ` · About ${Math.round(s / 60)} min remaining`;
}

function itemRow(i, run) {
  const sel = S.sel === i.id;
  const e = itemElapsed(i);
  const st = {
    done: [`<span class="st ok">${ic("ok")}</span>`, `<div class="cellbar"><div class="bar ok"><i style="width:100%"></i></div><span>100%</span></div>`, `<span class="outc">${i.outcome === "Check failed" ? `<span class="st bad">${ic("warn", "sm")}</span>` : `<span class="st ok">${ic("ok", "sm")}</span>`}${esc(i.outcome || "Done")}</span>`],
    running: [`<span class="st run">${ic("spin", "spin")}</span>`, `<div class="cellbar"><div class="bar indet"><i></i></div><span>…</span></div>`, `<span class="outc"><span class="st run">${ic("clock", "sm")}</span>Running…</span>`],
    queued: [`<span class="st">${ic("clock")}</span>`, `<div class="cellbar"><div class="bar"><i style="width:0"></i></div><span>0%</span></div>`, `<span class="outc"><span class="st">${ic("clock", "sm")}</span>Waiting…</span>`],
    failed: [`<span class="st bad">${ic("cancel")}</span>`, `<div class="cellbar"><div class="bar bad"><i style="width:100%"></i></div><span>—</span></div>`, `<span class="outc" title="${esc(i.error)}"><span class="st bad">${ic("cancel", "sm")}</span>Failed</span>`],
    refused: [`<span class="st warn">${ic("warn")}</span>`, `<div class="cellbar"><div class="bar"><i style="width:100%;background:var(--warn)"></i></div><span>100%</span></div>`, `<span class="outc" title="${esc(i.error)}"><span class="st warn">${ic("warn", "sm")}</span>Reuse declined</span>`],
    cancelled: [`<span class="st warn">${ic("cancel")}</span>`, `<div class="cellbar"><div class="bar"><i style="width:0"></i></div><span>—</span></div>`, `<span class="outc"><span class="st warn">${ic("cancel", "sm")}</span>Cancelled</span>`],
  }[i.status] || ["", "", ""];
  return `<tr class="click ${sel ? "sel" : ""}" data-act="selItem" data-id="${esc(i.id)}">
    <td><span class="outc">${st[0]}${esc(i.label)} <span class="muted">(${esc(i.id)})</span></span></td>
    <td>${esc(i.stage_label)}</td><td>${st[1]}</td><td>${e == null ? "—" : dur(e)}</td><td>${st[2]}</td></tr>`;
}

function verificationCard(run) {
  const v = run.verification;
  const done = run.items.filter((i) => i.status === "done").length;
  const refused = run.items.filter((i) => i.status === "refused").length;
  let icon = "ok", cls = "", text;
  if (run.comparing) {
    icon = "spin"; cls = "mute";
    text = "Running the stock tool on completed inputs to compare full output…";
  } else if (!done) {
    icon = "shield"; cls = "mute";
    text = activeRun() ? "Checks are reported as each input completes." : "No completed inputs to verify.";
  } else if (v && v.full_compared) {
    if (v.full_equal === v.full_compared) text = `Full-output comparison: ${v.full_equal} of ${v.full_compared} inputs byte-identical to a stock run.${v.full_compared < done ? ` ${done - v.full_compared} not compared yet.` : ""}`;
    else { icon = "warn"; cls = "bad"; text = `Full-output comparison: ${v.full_compared - v.full_equal} of ${v.full_compared} inputs differ from a stock run. Inspect the checks.`; }
  } else {
    const audited = run.items.reduce((a, i) => a + ((i.decision || {}).audit_checked || 0), 0);
    const bad = run.items.some((i) => i.outcome === "Check failed");
    if (bad) { icon = "warn"; cls = "bad"; text = "A sampled check failed on a completed item."; }
    else text = `Sampled checks passed on completed items${audited ? ` (${n0(audited)} records audited)` : ""}.<br>Full-output comparison has not been run.`;
  }
  const note = refused
    ? `<div class="vnote">${ic("warn", "sm")}Reuse declined on ${refused} input${refused > 1 ? "s" : ""}. <a data-act="runFullRefused">TARE can complete an ordinary full run.</a></div>`
    : `<div class="vnote">${ic("warn", "sm")}Reuse declined? <a data-act="runFull">TARE can complete an ordinary full run.</a></div>`;
  return `<div class="card verify">
    <div class="vicon ${cls}">${ic(icon, icon === "spin" ? "spin" : "")}</div>
    <div style="min-width:120px"><h3>Verification</h3></div>
    <div style="flex:1"><div class="vtext">${text}</div>${note}</div>
    <div class="btnrow"><button class="btn" data-act="inspectChecks">${ic("search")}Inspect Checks</button>
    <button class="btn" data-act="compareFull" ${!done || activeRun() || run.comparing ? "disabled" : ""}>${ic("scale")}Compare With Full Run</button></div></div>`;
}

function logLevelIcon(r) {
  if (r.level === "error") return ic("cancel", "sm");
  if (r.level === "warn") return ic("warn", "sm");
  if (/passed|completed|identical|filled|ready/i.test(r.message)) return `<span style="color:var(--ok)">${ic("ok", "sm")}</span>`;
  return ic("info", "sm");
}

function logPanel(run) {
  const warns = S.log.filter((r) => r.level !== "info");
  let body;
  if (S.ltab === "files") {
    const files = S.files || [];
    body = files.length
      ? `<table class="grid"><thead><tr><th>File</th><th>Size</th></tr></thead><tbody>${files.map((f) => `<tr><td class="mono">${esc(f.path)}</td><td>${bytes(f.bytes)}</td></tr>`).join("")}</tbody></table>`
      : `<div class="muted" style="padding:10px">No files yet.</div>`;
  } else {
    const rows = S.ltab === "warnings" ? warns : S.log;
    body = rows.length
      ? `<table class="grid"><thead><tr><th>Time</th><th></th><th>Message</th></tr></thead><tbody>${rows.map((r) => `<tr><td class="time">${clock(r.t)}</td><td class="lv ${r.level}">${logLevelIcon(r)}</td><td class="msg">${esc(r.message)}</td></tr>`).join("")}</tbody></table>`
      : `<div class="muted" style="padding:10px">${S.ltab === "warnings" ? "No warnings." : "No activity yet."}</div>`;
  }
  return `<div class="card logpanel">
    <div class="logtabs"><span class="ttl">ACTIVITY LOG</span>
      <button class="t ${S.ltab === "activity" ? "on" : ""}" data-act="ltab" data-t="activity">Activity</button>
      <button class="t ${S.ltab === "warnings" ? "on" : ""}" data-act="ltab" data-t="warnings">${warns.length ? ic("warn", "sm") : ""}Warnings (${warns.length})</button>
      <button class="t ${S.ltab === "files" ? "on" : ""}" data-act="ltab" data-t="files">Files</button>
      <span class="sp"></span>
      <button class="btn sm" data-act="copyLog">${ic("copy", "sm")}Copy Log</button>
      <button class="btn sm" data-act="exportLog">${ic("export", "sm")}Export Log</button>
    </div>
    <div class="logbody">${body}</div></div>`;
}

function viewLive() {
  const run = S.run;
  const p = S.P.project;
  if (!run) {
    const cache = S.P.cache;
    return `<div class="crumbs"><a data-act="tab" data-tab="results">Runs</a></div>
      <div class="card empty"><h2>No runs yet</h2>
      <p>${esc(tool().label)} · ${esc(refLabel("old"))} → ${esc(refLabel("new"))} · ${p.inputs.length} proteomes</p>
      <p class="small">${esc(cache.detail)}</p>
      <div class="btnrow" style="justify-content:center">
        <button class="btn" data-act="buildCache">${ic("build")}Build Cache against ${esc(refLabel("old"))}</button>
        <button class="btn primary" data-act="startRun">${ic("play")}Start Update to ${esc(refLabel("new"))}</button></div></div>`;
  }
  const pr = runProgress(run);
  const labels = run.reference_labels || {};
  const refs = run.kind === "cache" ? labels.old : `${labels.old} → ${(labels.new || "").replace(/^Pfam /, "")}`;
  const d = run.diff;
  const strip = d
    ? `${n0(d.unchanged)} unchanged <span class="sep">|</span> ${n0(d.rerun)} changed or new <span class="sep">|</span> ${n0(d.removed)} removed`
    : run.kind === "cache" ? `Filling the cache against ${esc(labels.old)}: every entry is scanned once`
    : run.kind === "full" ? `Ordinary full run with stock ${esc(tool().program)} against ${esc(labels.new)}` : "Comparing releases…";
  const anyFailed = run.items.some((i) => ["failed", "cancelled", "refused"].includes(i.status));
  const anyDone = run.items.some((i) => i.status === "done");
  return `<div class="crumbs"><a data-act="tab" data-tab="results">Runs</a> / ${esc(run.name)}</div>
    <div class="runhead"><h1>${KIND_TITLE[run.kind]}</h1>${statusPill(run)}</div>
    <div class="sub">${esc(TOOLS_LABEL(run.tool))} · ${esc(refs)} · ${run.items.length} proteomes${run.error ? ` · <span style="color:var(--bad)">${esc(run.error)}</span>` : ""}</div>
    ${stepper(run)}
    <div class="bigbar"><div class="bar big"><i style="width:${pr.pct}%"></i></div><span class="pct">${pr.pct}%</span></div>
    <div class="progressline">${pr.fin} of ${pr.total} proteomes completed · ${dur(pr.elapsed)} elapsed${activeRun() ? remainingText(pr.remaining) : ""}</div>
    <div class="refstrip">${ic("db")}<span>Reference entries: ${strip}</span></div>
    <div class="card" style="overflow:auto"><table class="grid"><thead><tr><th>Input</th><th>Stage</th><th>Progress</th><th>Elapsed</th><th>Outcome</th></tr></thead>
      <tbody>${run.items.map((i) => itemRow(i, run)).join("")}</tbody></table></div>
    <div class="btnrow">
      <button class="btn" data-act="inspectSelected" ${S.sel ? "" : "disabled"}>${ic("search")}Inspect Selected</button>
      <button class="btn" data-act="openCompleted" ${anyDone ? "" : "disabled"}>${ic("folderOpen")}Open Completed Outputs</button>
      <button class="btn" data-act="retryFailed" ${anyFailed && !activeRun() ? "" : "disabled"}>${ic("retry")}Retry Failed Items</button>
      <button class="btn" data-act="runAgain" ${!activeRun() && !projectBusy() ? "" : "disabled"}>${ic("play")}Run Again</button>
    </div>
    ${verificationCard(run)}
    ${logPanel(run)}`;
}

const TOOLS_LABEL = (id) => {
  const t = (S.app?.tools || []).find((x) => x.id === id);
  return t ? t.label : id;
};

function viewOverview() {
  const p = S.P.project;
  const runs = S.P.runs;
  const last = runs.find((r) => r.kind === "update" && r.status === "completed");
  const cache = S.P.cache;
  const nProt = p.inputs.reduce((a, i) => a + i.records, 0);
  if (!S.board) api("/api/board").then((b) => { S.board = b; render(); }).catch(() => {});
  const b = S.board;
  const cases = b ? b.cases.map((c) => {
    const h = c.headline || {};
    const ship = c.verdict === "ship";
    const big = ship ? `${fx(h.median_speedup)}×` : "Refuses";
    const sub = ship
      ? `median over ${h.n_speedups} genomes · 95% CI ${fx(h.ci95?.low)}–${fx(h.ci95?.high)}${h.walls_indicative ? " · indicative walls" : ""}`
      : esc(h.refuse_reason || h.outcome || "");
    return `<div class="card casecard"><div class="top"><b>${esc(c.tool)}</b><span class="pill ${ship ? "ok" : "warn"}">${ship ? "Ships" : "Refuses"}</span></div>
      <div class="muted small">${esc(c.program)} · ${esc(c.release?.pair || "")}</div><div class="big">${big}</div><div class="small">${sub}</div></div>`;
  }).join("") : `<div class="muted">Loading committed results…</div>`;
  return `<div class="page"><h2>${esc(p.name)}</h2><div class="sub">${esc(tool().label)} ${esc(tool().version || "")} ${esc(tool().program)} · ${esc(refLabel("old"))} → ${esc(refLabel("new"))}</div></div>
    <div class="cols">
      <div class="card stat"><div class="k">Inputs</div><div class="v">${p.inputs.length} proteomes</div><div class="s">${n0(nProt)} proteins</div></div>
      <div class="card stat"><div class="k">New release</div><div class="v">${n0(S.P.references.new?.entries)} entries</div><div class="s">${esc(refLabel("new"))} · previous ${n0(S.P.references.old?.entries)}</div></div>
      <div class="card stat"><div class="k">Cache</div><div class="v">${cache.exists ? bytes(cache.bytes) : "Not built"}</div><div class="s">${esc(cache.built_against.length ? "Holds " + cache.built_against.join(", ") : cache.detail)}</div></div>
      <div class="card stat"><div class="k">Last completed update</div><div class="v">${last ? dur(last.wall_s) : "—"}</div><div class="s">${last ? `${esc(last.name)} · ${last.n_done} of ${last.n_items} inputs` : "No update yet"}</div></div>
    </div>
    ${S.P.references.new?.note ? `<div class="refstrip">${ic("info")}<span>${esc(S.P.references.new.note)} This keeps local runs to seconds; the measured server headline below uses full Pfam.</span></div>` : ""}
    <div class="page"><h3>Research evidence (committed results)</h3></div>
    <div class="cols">${cases}</div>
    ${b?.exactness ? `<div class="card pad"><b>${n0(b.exactness.total_lines)}</b> output lines checked byte-identical across HMMER and Infernal runs. <span class="muted">${esc(b.exactness.scope)}</span></div>` : ""}`;
}

function settingsForm(s, disabled) {
  const dis = disabled ? "disabled" : "";
  return `<div class="formgrid">
    <label>Compute</label><select class="in" data-set="compute" ${dis}><option value="local" ${s.compute === "local" ? "selected" : ""}>This Mac (local)</option><option value="carc" ${s.compute === "carc" ? "selected" : ""}>CARC · discovery (not wired)</option></select>
    <label>Threads</label><input class="in" type="number" min="1" max="256" data-set="threads" value="${s.threads}" ${dis} />
    <label>Memory limit</label><select class="in" data-set="memory_gb" ${dis}>${[8, 16, 32, 64, 128].map((g) => `<option value="${g}" ${s.memory_gb == g ? "selected" : ""}>${g} GB</option>`).join("")}</select>
    <label>Time limit</label><input class="in" data-set="time_limit" value="${esc(s.time_limit)}" placeholder="HH:MM:SS" ${dis} />
    <label>Arguments</label><input class="in mono" data-set="arguments" value="${esc(s.arguments)}" ${dis} />
    <label>Pin settings</label><select class="in" data-set="pin" ${dis}>
      <option value="default" ${s.pin === "default" ? "selected" : ""}>Use project default (recommended)</option>
      <option value="infer" ${s.pin === "infer" ? "selected" : ""}>Infer from a probe</option>
      <option value="custom" ${s.pin === "custom" ? "selected" : ""}>Custom template</option></select>
    ${s.pin === "custom" ? `<label>Pin template</label><input class="in mono" data-set="pin_template" value="${esc(s.pin_template)}" ${dis} />` : ""}
    <label>Verification policy</label><select class="in" data-set="verify" ${dis}>
      <option value="audit" ${s.verify === "audit" ? "selected" : ""}>Sampled checks (default)</option>
      <option value="full" ${s.verify === "full" ? "selected" : ""}>Full comparison (runs stock tool too)</option></select>
  </div>`;
}

function viewSetup() {
  const p = S.P.project;
  const tools = S.app.tools;
  const refs = S.app.references;
  const refOpts = (side) => refs.map((r) => `<option value="${esc(r.id)}" ${p.references[side] === r.id ? "selected" : ""}>${esc(r.label)} · ${n0(r.entries)} entries</option>`).join("");
  return `<div class="page"><h2>Run Setup</h2><div class="sub">Choose the tool, the two releases and the inputs. Settings apply to the next run.</div></div>
    <div class="card pad"><h3>Tool</h3><div class="toolcards">${tools.map((t) => `<button class="toolcard ${p.tool === t.id ? "on" : ""}" data-act="setTool" data-tool="${t.id}" ${t.runnable ? "" : "disabled"}>
      <b>${esc(t.label)}</b> <span class="muted">${esc(t.program)}</span><div class="small muted">${t.runnable ? `v${esc(t.version || "?")} · ready` : t.installed ? "installed · not wired yet" : "not installed here"}</div></button>`).join("")}</div></div>
    <div class="card pad"><h3>References</h3><div class="formgrid">
      <label>Previous release</label><select class="in" id="ref-old">${refOpts("old")}</select>
      <label>New release</label><select class="in" id="ref-new">${refOpts("new")}</select>
      <span></span><div class="btnrow"><button class="btn" data-act="saveRefs">${ic("save")}Use these releases</button><button class="btn" data-act="importRelease">${ic("upload")}Import Release...</button></div></div></div>
    <div class="card pad"><h3>Inputs · ${p.inputs.length} proteomes</h3>
      <table class="grid"><thead><tr><th>ID</th><th>Input</th><th>Proteins</th><th>Residues</th><th>Path</th><th></th></tr></thead><tbody>
      ${p.inputs.map((i) => `<tr><td>${esc(i.id)}</td><td>${esc(i.label)}</td><td>${n0(i.records)}</td><td>${n0(i.residues)}</td><td class="mono small">${esc(i.path)}</td><td><button class="btn sm danger" data-act="removeInput" data-id="${esc(i.id)}" ${projectBusy() ? "disabled" : ""}>${ic("trash", "sm")}</button></td></tr>`).join("")}
      </tbody></table><div class="btnrow" style="margin-top:8px"><button class="btn" data-act="addInputs">${ic("addInputs")}Add Inputs</button></div></div>
    <div class="card pad"><h3>Settings</h3>${settingsForm(p.settings, false)}
      <div class="btnrow" style="margin-top:10px"><button class="btn" data-act="savePreset">${ic("save")}Save Preset</button>
      <button class="btn" data-act="checkSetup">${ic("checks")}Check Setup</button>
      <button class="btn primary" data-act="startRun" ${projectBusy() ? "disabled" : ""}>${ic("play")}Start Run</button></div></div>`;
}

function diffBlock(d) {
  if (!d) return `<div class="muted">Set both releases to compare them.</div>`;
  const tot = d.n_new || 1;
  const seg = (n, c) => `<i style="width:${(100 * n) / tot}%;background:${c}"></i>`;
  return `<div class="diffbar">${seg(d.unchanged, "#9fc3ef")}${seg(d.changed, "#f0b13c")}${seg(d.added, "#2e9b4c")}</div>
    <div class="legend"><span style="--c:#9fc3ef">${n0(d.unchanged)} unchanged (reused)</span><span style="--c:#f0b13c">${n0(d.changed)} changed</span><span style="--c:#2e9b4c">${n0(d.added)} new</span><span style="--c:#c9372c">${n0(d.removed)} removed</span></div>
    <p class="small">${esc(d.old)} has ${n0(d.n_old)} entries, ${esc(d.new)} has ${n0(d.n_new)}. Entries scanned again: ${n0(d.rerun)}, which is ${(100 * d.rerun_fraction_length).toFixed(1)}% of the new release by model length (the share of the scan that cannot be reused).</p>
    ${["changed", "added", "removed"].map((k) => d.examples[k].length ? `<div class="small"><b>${k}:</b> <span class="chips">${d.examples[k].map((x) => `<span class="chip">${esc(x)}</span>`).join("")}${d[k] > d.examples[k].length ? `<span class="muted">+${n0(d[k] - d.examples[k].length)} more</span>` : ""}</span></div>` : "").join("")}`;
}

function checkList(checks) {
  const icon = { pass: `<span class="st ok">${ic("ok")}</span>`, warn: `<span class="st warn">${ic("warn")}</span>`, fail: `<span class="st bad">${ic("cancel")}</span>` };
  return `<ul class="checklist">${checks.map((c) => `<li>${icon[c.status] || ""}<div><div class="t">${esc(c.title)}</div><div class="d">${esc(c.detail)}</div></div></li>`).join("")}</ul>`;
}

function viewPlan() {
  if (!S.preflight || S.preflight.pid !== S.pid) {
    api(`/api/projects/${S.pid}/preflight`).then((r) => { S.preflight = { ...r, pid: S.pid }; render(); }).catch((e) => toast(e.message, "bad"));
    api(`/api/projects/${S.pid}/command`).then((r) => { S.cmd = r; render(); }).catch(() => {});
    return `<div class="empty">${ic("spin", "spin")} Checking setup…</div>`;
  }
  const pf = S.preflight;
  return `<div class="page"><h2>Plan & Preflight</h2><div class="sub">Checked ${stamp(pf.checked_at)} · ${pf.ok ? "ready to run" : "fix the failed checks before running"}</div></div>
    <div class="cols" style="grid-template-columns: 1fr 1.3fr">
      <div class="card"><div class="phead">Setup checks <a data-act="recheck">${ic("retry", "sm")} Re-check</a></div>${checkList(pf.checks)}</div>
      <div class="card pad"><h3>What changes between releases</h3>${diffBlock(pf.diff)}</div></div>
    <div class="card pad"><h3>Exact command (per input)</h3><pre class="cmd">${esc(S.cmd?.shell || "…")}</pre>
      <p class="small muted">Runs from <code>${esc(S.cmd?.cwd || "")}</code>. Stock equivalent: <code>${esc(S.cmd?.stock || "")}</code></p></div>
    <div class="btnrow"><button class="btn" data-act="buildCache">${ic("build")}Build Cache against ${esc(refLabel("old"))}</button>
      <button class="btn primary" data-act="startRun" ${pf.ok && !projectBusy() ? "" : "disabled"}>${ic("play")}Start Update</button></div>`;
}

function runPicker() {
  return `<select class="in" style="max-width:280px" data-act-change="pickRun">${S.P.runs.map((r) => `<option value="${esc(r.id)}" ${r.id === S.rid ? "selected" : ""}>${esc(r.name)} · ${esc(r.status)}</option>`).join("")}</select>`;
}

function viewResults() {
  const run = S.run;
  const runs = S.P.runs;
  const hist = `<div class="card"><table class="grid"><thead><tr><th>Run</th><th>Status</th><th>Inputs</th><th>Wall</th><th>Started</th></tr></thead><tbody>
    ${runs.map((r) => `<tr class="click ${r.id === S.rid ? "sel" : ""}" data-act="selectRun" data-rid="${esc(r.id)}"><td>${esc(r.name)}</td><td>${esc(r.status)}</td><td>${r.n_done}/${r.n_items}${r.n_failed ? ` · ${r.n_failed} failed` : ""}</td><td>${dur(r.wall_s)}</td><td>${stamp(r.started_at)}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">No runs yet.</td></tr>`}</tbody></table></div>`;
  if (!run) return `<div class="page"><h2>Results</h2></div>${hist}`;
  const rows = run.items.map((i) => {
    const d = i.decision || {};
    const fc = i.full_compare || {};
    return `<tr class="click ${S.sel === i.id ? "sel" : ""}" data-act="selItem" data-id="${esc(i.id)}"><td>${esc(i.label)}</td><td>${esc(i.status)}</td><td>${esc(d.decision || "—")}</td><td>${d.n_entries != null ? `${n0(d.n_stable)} / ${n0(d.n_entries)}` : "—"}</td><td>${n0(d.reused_rows)}</td><td>${dur(i.elapsed_s)}</td><td>${fc.stock_wall_s != null ? dur(fc.stock_wall_s) : "—"}</td><td>${fc.speedup != null ? fx(fc.speedup) + "×" : "—"}</td></tr>`;
  }).join("");
  const timed = run.items.filter((i) => i.full_compare?.stock_wall_s != null);
  const tare = timed.reduce((a, i) => a + i.elapsed_s, 0), stock = timed.reduce((a, i) => a + i.full_compare.stock_wall_s, 0);
  return `<div class="page"><h2>Results</h2><div class="sub">Pick a run: ${runPicker()}</div></div>
    ${timed.length ? `<div class="refstrip">${ic("activity")}<span>Measured on this Mac for ${timed.length} inputs: TARE ${dur(tare)} vs stock ${dur(stock)} (${fx(stock / tare)}×). Each TARE time includes its checks; one run each, not repeated.</span></div>` : ""}
    <div class="card" style="overflow:auto"><table class="grid"><thead><tr><th>Input</th><th>Status</th><th>Decision</th><th>Entries reused</th><th>Rows reused</th><th>TARE time</th><th>Stock time</th><th>Speedup</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="btnrow"><button class="btn" data-act="openOutput">${ic("folderOpen")}Open Output</button><button class="btn" data-act="downloadResults" ${activeRun() ? "disabled" : ""}>${ic("download")}Download Results</button><button class="btn" data-act="compareFull" ${activeRun() || run.comparing ? "disabled" : ""}>${ic("scale")}Measure stock time (compare with full run)</button></div>
    <div class="page"><h3>All runs</h3></div>${hist}`;
}

function viewVerify() {
  const run = S.run;
  if (!run) return `<div class="page"><h2>Verification</h2></div><div class="card empty">No runs yet.</div>`;
  const v = run.verification || {};
  const rows = run.items.map((i) => {
    const d = i.decision || {};
    const fc = i.full_compare;
    let full = "not run";
    if (fc?.error) full = `<span style="color:var(--bad)">stock run failed</span>`;
    else if (fc) full = fc.byte_equal ? `<span style="color:var(--ok)">byte-identical · ${n0(Object.values(fc.tables).reduce((a, t) => a + t.lines, 0))} lines</span>` : `<span style="color:var(--bad)">differs: ${esc([...new Set(Object.values(fc.tables).flatMap((t) => t.classes))].join(", "))}</span>`;
    return `<tr><td>${esc(i.label)}</td><td>${esc(d.decision || i.status)}</td><td>${esc(d.ic2 || "—")}</td><td>${esc(d.random_pads || "—")}</td><td>${n0(d.audit_checked)}</td><td>${esc(d.match || "—")}</td><td>${full}</td></tr>`;
  }).join("");
  return `<div class="page"><h2>Verification</h2><div class="sub">${runPicker()} · policy: ${esc(v.policy === "full" ? "full comparison" : "sampled checks")}</div></div>
    <div class="cols">
      <div class="card stat"><div class="k">Inputs with checks</div><div class="v">${n0(v.items_checked)}</div><div class="s">neighbor checks passed on ${n0(v.neighbor_checks_passed)}</div></div>
      <div class="card stat"><div class="k">Records audited</div><div class="v">${n0(v.records_audited)}</div><div class="s">re-scanned in full and compared</div></div>
      <div class="card stat"><div class="k">Full comparison</div><div class="v">${n0(v.full_equal)} / ${n0(v.full_compared)}</div><div class="s">byte-identical to stock</div></div>
      <div class="card stat"><div class="k">Reuse declined</div><div class="v">${n0(v.refused)}</div><div class="s">inputs TARE refused to replay</div></div></div>
    <div class="card" style="overflow:auto"><table class="grid"><thead><tr><th>Input</th><th>Decision</th><th>Neighbor check</th><th>Random pads</th><th>Audited</th><th>Match rule</th><th>Full run</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="btnrow"><button class="btn primary" data-act="compareFull" ${activeRun() || run.comparing ? "disabled" : ""}>${ic("scale")}Compare With Full Run</button><button class="btn" data-act="exportReport" ${activeRun() ? "disabled" : ""}>${ic("report")}Export Report</button></div>`;
}

function viewCache() {
  const c = S.P.cache;
  const refs = S.app.references;
  const p = S.P.project;
  return `<div class="page"><h2>Cache & References</h2></div>
    <div class="cols">
      <div class="card stat"><div class="k">Cache file</div><div class="v">${c.exists ? bytes(c.bytes) : "None"}</div><div class="s mono">${esc(c.path)}</div></div>
      <div class="card stat"><div class="k">Cached result rows</div><div class="v">${n0(c.counts?.rows)}</div><div class="s">${n0(c.counts?.records)} records · ${n0(c.counts?.namespaces)} namespaces · ${n0(c.counts?.contracts)} contracts</div></div>
      <div class="card stat"><div class="k">Compatibility</div><div class="v" style="font-size:16px">${{ compatible: "Compatible", missing: "Not built", stale: "Partial" }[c.status]}</div><div class="s">${esc(c.detail)}</div></div>
      <div class="card stat"><div class="k">Last built</div><div class="v" style="font-size:16px">${stamp(c.built_at)}</div><div class="s">${esc(c.built_against.join(", ") || "—")}</div></div></div>
    <div class="btnrow"><button class="btn" data-act="buildCache">${ic("build")}Build Cache...</button><button class="btn" data-act="validateCache">${ic("shield")}Validate Cache...</button><button class="btn danger" data-act="invalidateCache">${ic("warn")}Invalidate...</button><button class="btn" data-act="openProjectDir">${ic("folderOpen")}Open Folder</button></div>
    <div class="card"><div class="phead">References</div><table class="grid"><thead><tr><th>Release</th><th>Entries</th><th>Model length</th><th>Size</th><th>SHA-256</th><th>Use</th></tr></thead><tbody>
      ${refs.map((r) => `<tr><td><b>${esc(r.label)}</b><div class="small muted">${esc(r.note || r.path)}</div></td><td>${n0(r.entries)}</td><td>${n0(r.length)}</td><td>${bytes(r.bytes)}</td><td class="mono small">${esc(r.sha256.slice(0, 12))}…</td>
      <td>${p.references.old === r.id ? `<span class="pill mute">previous</span>` : p.references.new === r.id ? `<span class="pill">new</span>` : `<button class="btn sm" data-act="useRef" data-side="old" data-id="${esc(r.id)}">as previous</button> <button class="btn sm" data-act="useRef" data-side="new" data-id="${esc(r.id)}">as new</button>`}</td></tr>`).join("")}
    </tbody></table><div style="padding:8px 12px"><button class="btn" data-act="importRelease">${ic("upload")}Import Release...</button></div></div>
    <div class="card pad"><h3>${esc(refLabel("old"))} → ${esc(refLabel("new"))}</h3>${S.preflight?.pid === S.pid && S.preflight.diff ? diffBlock(S.preflight.diff) : `<a data-act="loadDiff">Compare the two releases</a>`}</div>`;
}

function viewCompute() {
  const sys = S.app.system;
  const s = S.P.project.settings;
  const conn = S.app.connection || {};
  const connRow = (k, label) => {
    const c = conn[k];
    return `<tr><td>${label}</td><td>${c ? `<span class="dotline"><span class="dot ${c.ok ? "ok" : "bad"}"></span>${c.ok ? "Connected" : "Failed"}</span>` : `<span class="muted">Not tested</span>`}</td><td class="small">${esc(c?.detail || "")}</td><td>${c ? stamp(c.checked_at) : ""}</td><td><button class="btn sm" data-act="testConn" data-compute="${k}">${ic("plug", "sm")}Test</button></td></tr>`;
  };
  return `<div class="page"><h2>Compute & Settings</h2></div>
    <div class="cols">
      <div class="card stat"><div class="k">This Mac</div><div class="v" style="font-size:16px">${esc(sys.host)}</div><div class="s">${sys.ncpu} cores · ${bytes(sys.mem_total)} memory</div></div>
      <div class="card stat"><div class="k">CPU</div><div class="v">${sys.cpu_percent == null ? "–" : Math.round(sys.cpu_percent) + "%"}</div><div class="s">all processes</div></div>
      <div class="card stat"><div class="k">Memory in use</div><div class="v">${bytes(sys.mem_used)}</div><div class="s">of ${bytes(sys.mem_total)}</div></div>
      <div class="card stat"><div class="k">Disk free</div><div class="v">${bytes(sys.disk_free)}</div><div class="s">cache ${bytes(sys.cache_bytes)}</div></div></div>
    <div class="card"><div class="phead">Compute targets</div><table class="grid"><thead><tr><th>Target</th><th>Status</th><th>Detail</th><th>Checked</th><th></th></tr></thead><tbody>${connRow("local", "This Mac")}${connRow("carc", "CARC · discovery")}</tbody></table>
      <p class="small muted" style="padding:0 12px">Runs execute on this Mac. CARC can be tested over SSH, but submitting runs there is not wired into the console yet. Memory limit is recorded with each run; it is enforced only by a scheduler.</p></div>
    <div class="card pad"><h3>Run settings</h3>${settingsForm(s, false)}</div>
    <div class="card"><div class="phead">Tools on this machine</div><table class="grid"><thead><tr><th>Tool</th><th>Program</th><th>Version</th><th>Path</th><th>Console</th></tr></thead><tbody>
      ${S.app.tools.map((t) => `<tr><td>${esc(t.label)}</td><td>${esc(t.program)}</td><td>${esc(t.version || "—")}</td><td class="mono small">${esc(t.binary || "not found")}</td><td>${t.runnable ? `<span class="pill ok">ready</span>` : `<span class="pill mute">${t.installed ? "not wired" : "not installed"}</span>`}</td></tr>`).join("")}</tbody></table></div>`;
}

/* ---- right inspector */

function renderRight() {
  if (!S.P) return `<div class="phead">Run Inspector</div>`;
  const tabs = [["config", "Configuration"], ["checks", "Checks"], ["history", "History"]];
  const head = `<div class="phead">Run Inspector <span class="more">${ic("more", "sm")}</span></div>
    <div class="itabs">${tabs.map(([k, l]) => `<button class="${S.itab === k ? "on" : ""}" data-act="itab" data-t="${k}">${l}</button>`).join("")}</div>`;
  let body = "";
  if (S.itab === "config") body = inspectorConfig();
  if (S.itab === "checks") {
    const run = S.run;
    const sel = run?.items.find((i) => i.id === S.sel);
    const checks = run?.checks?.length ? run.checks : S.preflight?.pid === S.pid ? S.preflight.checks : null;
    body = checks ? `<div class="small muted" style="padding:8px 12px 0">${run ? `Preflight recorded with ${esc(run.name)}` : "Current setup"}</div>${checkList(checks)}` : `<div style="padding:12px"><a data-act="recheck">Run setup checks</a></div>`;
    if (sel) {
      const d = sel.decision || {};
      body += `<div class="phead">Selected · ${esc(sel.id)}</div>${checkList([
        { title: "Decision", status: d.decision === "SHIP" ? "pass" : d.decision ? "warn" : "warn", detail: `${d.decision || sel.status} · ${d.why || sel.error || ""}` },
        { title: "Neighbor and random-pad checks", status: d.ic2 === "pass" ? "pass" : d.ic2 ? "fail" : "warn", detail: d.random_pads || "not reported" },
        { title: "Sampled audit", status: d.audit_checked ? "pass" : "warn", detail: d.audit || "not run on this item" },
        { title: "Full comparison", status: sel.full_compare ? (sel.full_compare.byte_equal ? "pass" : "fail") : "warn", detail: sel.full_compare ? (sel.full_compare.byte_equal ? "byte-identical to stock" : "differs from stock") : "not run" },
      ])}`;
    }
  }
  if (S.itab === "history") {
    body = `<ul class="hist">${S.P.runs.map((r) => {
      const [icn, cls] = runIcon(r.status);
      return `<li class="${r.id === S.rid ? "sel" : ""}" data-act="selectRun" data-rid="${esc(r.id)}"><span class="st ${cls === "ok" ? "ok" : cls === "bad" ? "bad" : "run"}">${ic(icn, icn === "spin" ? "spin" : "")}</span><div><div>${esc(r.name)}</div><div class="m">${stamp(r.created_at)} · ${r.n_done}/${r.n_items} · ${dur(r.wall_s)}</div></div></li>`;
    }).join("") || `<li class="muted">No runs yet.</li>`}</ul>`;
  }
  return head + body;
}

function inspectorConfig() {
  const p = S.P.project;
  const s = p.settings;
  const t = tool();
  const out = S.run ? `tools/tare-console/state/projects/${p.id}/runs/${S.run.id}` : `tools/tare-console/state/projects/${p.id}`;
  const conn = (S.app.connection || {})[s.compute];
  const connTxt = s.compute === "local" ? (conn ? (conn.ok ? "Connected" : "Failed") : "Local") : conn ? (conn.ok ? "Connected" : "Failed") : "Not tested";
  const dotCls = s.compute === "local" ? (conn && !conn.ok ? "bad" : "ok") : conn ? (conn.ok ? "ok" : "bad") : "warn";
  const L = S.limits || { threads: s.threads, memory_gb: s.memory_gb, time_limit: s.time_limit };
  const cache = S.P.cache;
  const building = S.P.runs.some((r) => r.kind === "cache" && ["running", "queued"].includes(r.status));
  const cacheTxt = building ? ["warn", "Building…"] : { compatible: ["ok", "Compatible"], missing: ["warn", "Not built"], stale: ["warn", "Partial"] }[cache.status];
  return `<div class="kv">
      <label>Tool:</label><div class="val">${esc(t.label)} ${esc(t.version || "")}</div>
      <label>Reference:</label><div class="val">${esc(refLabel("old"))} → ${esc(refLabel("new").replace(/^Pfam /, ""))}</div>
      <label>Input:</label><div class="val">${p.inputs.length} proteomes</div>
      <label>Output:</label><div class="field"><input value="${esc(out)}" readonly title="${esc(out)}" /><button class="ib" data-act="openOutput" title="Open folder">${ic("folder", "sm")}</button></div>
      <label>Compute:</label><div class="dotline"><span class="dot ${dotCls}"></span><select class="in" data-set="compute"><option value="local" ${s.compute === "local" ? "selected" : ""}>This Mac</option><option value="carc" ${s.compute === "carc" ? "selected" : ""}>CARC</option></select><span class="small">${esc(connTxt)}</span></div>
      <label>Threads:</label><div class="field"><input type="number" min="1" max="256" data-limit="threads" value="${esc(L.threads)}" /></div>
      <label>Memory limit:</label><div class="field"><select data-limit="memory_gb">${[8, 16, 32, 64, 128].map((g) => `<option value="${g}" ${L.memory_gb == g ? "selected" : ""}>${g} GB</option>`).join("")}</select></div>
      <label>Time limit:</label><div class="field"><input data-limit="time_limit" value="${esc(L.time_limit)}" placeholder="HH:MM:SS" /></div>
      <label>Cache:</label><div class="dotline"><span class="dot ${cacheTxt[0]}"></span>${cacheTxt[1]}</div>
    </div>
    <div class="ibtns"><button class="btn" data-act="testConn" data-compute="${esc(s.compute)}">${ic("plug")}Test Connection</button><button class="btn" data-act="setLimits" ${S.limits ? "" : "disabled"}>${ic("sliders")}Set Limits</button></div>
    <div class="adv"><div class="ah" data-act="toggleAdv">${ic(S.advOpen ? "down" : "right", "sm")}Advanced Settings</div>
    ${S.advOpen ? `<div class="kv">
      <label>Arguments:</label><div class="field"><input class="mono" data-set="arguments" value="${esc(s.arguments)}" /></div>
      <label>Pin settings:</label><div class="field"><select data-set="pin"><option value="default" ${s.pin === "default" ? "selected" : ""}>Use project default (recommended)</option><option value="infer" ${s.pin === "infer" ? "selected" : ""}>Infer from a probe</option><option value="custom" ${s.pin === "custom" ? "selected" : ""}>Custom template</option></select></div>
      ${s.pin === "custom" ? `<label>Template:</label><div class="field"><input class="mono" data-set="pin_template" value="${esc(s.pin_template)}" /></div>` : ""}
      <label>Verification policy:</label><div class="field"><select data-set="verify"><option value="audit" ${s.verify === "audit" ? "selected" : ""}>Sampled checks (default)</option><option value="full" ${s.verify === "full" ? "selected" : ""}>Full comparison</option></select><span class="help" title="Sampled checks re-scan a random sample of records in full and compare. Full comparison also runs the stock tool on every input.">?</span></div>
    </div>
    <div class="cmdlink">${ic("term", "sm")}<a data-act="viewCommand">View exact command...</a></div>
    <div class="rec">${ic("info", "sm")}Configuration recorded ${S.run ? `with run (${stamp(S.run.created_at)})` : `(${stamp(p.settings_recorded_at)})`}.</div>` : ""}</div>
    <div class="ilinks"><a data-act="manageAccess">${ic("users", "sm")}Manage Access...</a><a data-act="auditHistory">${ic("history", "sm")}Audit History...</a></div>`;
}

/* ---- status bar */

function renderStatus() {
  const sys = S.app?.system;
  if (!sys) { $("#statusbar").innerHTML = ""; return; }
  const s = S.P?.project.settings;
  const target = s?.compute === "carc" ? "CARC" : "This Mac";
  const conn = (S.app.connection || {})[s?.compute || "local"];
  const cls = s?.compute === "carc" ? (conn ? (conn.ok ? "ok" : "bad") : "warn") : conn && !conn.ok ? "bad" : "ok";
  const state = s?.compute === "carc" ? (conn ? (conn.ok ? "connected" : "unreachable") : "not tested") : "ready";
  const q = sys.queue;
  $("#statusbar").innerHTML = `
    <div class="sb"><span class="dot ${cls}"></span>${target} ${state}</div>
    <div class="sb">${ic("cpu", "sm")}CPU ${sys.cpu_percent == null ? "–" : Math.round(sys.cpu_percent) + "%"}</div>
    <div class="sb">${ic("memory", "sm")}Memory ${bytes(sys.mem_used)} / ${bytes(sys.mem_total)}</div>
    <div class="sb">${ic("db", "sm")}Cache ${bytes(sys.cache_bytes)}</div>
    <div class="sb">${ic("disk", "sm")}${bytes(sys.disk_free)} free</div>
    <div class="sb grow"></div>
    <div class="sb" style="border:0">${ic(q.active ? "spin" : "activity", q.active ? "sm spin" : "sm")}${q.active ? 1 : 0} active · ${q.queued.length} queued</div>`;
}

/* ---------------------------------------------------------------- modals */

function modal({ title, body, actions = [], wide = false }) {
  const root = $("#modal-root");
  root.innerHTML = `<div class="overlay"><div class="modal ${wide ? "wide" : ""}"><header>${esc(title)}<button data-close>${ic("x")}</button></header><div class="mb">${body}</div>
    <footer>${actions.map((a, i) => `<button class="btn ${a.primary ? "primary" : ""} ${a.danger ? "danger" : ""}" data-mi="${i}">${a.label}</button>`).join("")}<button class="btn" data-close>${actions.length ? "Cancel" : "Close"}</button></footer></div></div>`;
  const close = () => (root.innerHTML = "");
  root.querySelectorAll("[data-close]").forEach((b) => (b.onclick = close));
  root.querySelector(".overlay").onclick = (e) => { if (e.target.classList.contains("overlay")) close(); };
  actions.forEach((a, i) => (root.querySelector(`[data-mi="${i}"]`).onclick = async () => { const keep = await a.onClick(root); if (keep !== true) close(); }));
  const first = root.querySelector("input, textarea, select");
  if (first) first.focus();
  return root;
}

function confirmBox(title, html, label, fn, danger = false) {
  modal({ title, body: html, actions: [{ label, primary: !danger, danger, onClick: fn }] });
}

function download(url) {
  const a = document.createElement("a");
  a.href = url;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

const rid = () => encodeURIComponent(S.rid);
const pidq = () => encodeURIComponent(S.pid);

const ACT = {
  tab: (d) => { S.tab = d.tab; if (d.tab === "plan" || d.tab === "cache") S.preflight = null; render(); },
  itab: (d) => { S.itab = d.t; render(); },
  ltab: async (d) => { S.ltab = d.t; if (d.t === "files" && S.rid) S.files = (await api(`/api/runs/${rid()}/files`)).files; render(); },
  toggle: (d) => { S.open[d.key] = !S.open[d.key]; renderLeft(); },
  toggleAdv: () => { S.advOpen = !S.advOpen; render(); },
  selectRun: (d) => { S.rid = d.rid; S.sel = null; if (!["results", "verify"].includes(S.tab)) S.tab = "live"; refresh(true); },
  selItem: (d) => { S.sel = S.sel === d.id ? null : d.id; render(); },
  switchProject: (d) => { S.pid = d.pid; S.rid = null; S.run = null; S.preflight = null; S.limits = null; refresh(true); },
  setupDemo: () => act(() => api("/api/setup-demo", {})),
  recheck: () => { S.preflight = null; if (S.tab !== "plan" && S.tab !== "cache") { api(`/api/projects/${pidq()}/preflight`).then((r) => { S.preflight = { ...r, pid: S.pid }; render(); }); } render(); },
  loadDiff: () => { S.preflight = null; api(`/api/projects/${pidq()}/preflight`).then((r) => { S.preflight = { ...r, pid: S.pid }; render(); }); },

  newRun: () => {
    const p = S.P.project;
    modal({
      title: "New Run",
      body: `<div class="formgrid"><label>Kind</label><select class="in" id="nr-kind">
        <option value="update">Update: reuse the cache for ${esc(refLabel("new"))}</option>
        <option value="cache">Cache build: scan ${esc(refLabel("old"))} once</option>
        <option value="full">Full computation: stock ${esc(tool().program)} on ${esc(refLabel("new"))}</option></select></div>
        <div><label><input type="checkbox" id="nr-all" checked /> All inputs</label></div>
        <div style="max-height:260px;overflow:auto;border:1px solid var(--line);border-radius:4px;padding:6px">${p.inputs.map((i) => `<div><label><input type="checkbox" class="nr-in" value="${esc(i.id)}" checked /> ${esc(i.id)} · ${esc(i.label)}</label></div>`).join("")}</div>`,
      actions: [{ label: "Start", primary: true, onClick: async (root) => {
        const ids = [...root.querySelectorAll(".nr-in:checked")].map((x) => x.value);
        const r = await act(() => api(`/api/projects/${pidq()}/runs`, { kind: root.querySelector("#nr-kind").value, inputs: ids }), (x) => `${x.name} queued`);
        if (r) { S.rid = r.id; S.tab = "live"; }
      } }],
    });
    $("#nr-all").onchange = (e) => document.querySelectorAll(".nr-in").forEach((x) => (x.checked = e.target.checked));
  },
  startRun: async () => {
    const r = await act(() => api(`/api/projects/${pidq()}/runs`, { kind: "update" }), (x) => `${x.name} queued`);
    if (r) { S.rid = r.id; S.sel = null; S.tab = "live"; render(); }
  },
  runFull: async () => {
    const r = await act(() => api(`/api/projects/${pidq()}/runs`, { kind: "full", inputs: S.sel ? [S.sel] : undefined }), (x) => `${x.name} queued`);
    if (r) { S.rid = r.id; S.tab = "live"; }
  },
  runFullRefused: async () => {
    const ids = S.run.items.filter((i) => i.status === "refused").map((i) => i.id);
    const r = await act(() => api(`/api/projects/${pidq()}/runs`, { kind: "full", inputs: ids }), (x) => `${x.name} queued for ${ids.length} inputs`);
    if (r) { S.rid = r.id; S.tab = "live"; }
  },
  cancelRun: () => confirmBox("Cancel run", `Stop <b>${esc(S.run.name)}</b>? The input in progress is killed; finished inputs keep their outputs.`, "Stop run", () => act(() => api(`/api/runs/${rid()}/cancel`, {}), "Cancelling"), true),
  retryFailed: async () => { const r = await act(() => api(`/api/runs/${rid()}/retry`, {}), (x) => `${x.name} queued`); if (r) { S.rid = r.id; S.tab = "live"; } },
  runAgain: async () => { const r = await act(() => api(`/api/runs/${rid()}/again`, {}), (x) => `${x.name} queued`); if (r) { S.rid = r.id; S.tab = "live"; } },
  compareFull: () => {
    const ids = S.sel ? [S.sel] : null;
    const n = ids ? 1 : S.run.items.filter((i) => i.status === "done").length;
    confirmBox("Compare with full run", `Run stock <code>${esc(tool().program)}</code> on ${n} completed input${n > 1 ? "s" : ""} against ${esc(S.run.reference_labels?.new || "")} and compare the output body byte for byte. This also measures the stock time.`, "Run comparison",
      () => act(() => api(`/api/runs/${rid()}/compare-full`, { inputs: ids }), (r) => `Comparing ${r.started} inputs`));
  },
  inspectChecks: () => { S.itab = "checks"; render(); },
  inspectSelected: () => {
    const i = S.run.items.find((x) => x.id === S.sel);
    if (!i) return;
    const d = i.decision || {};
    const ph = i.phases || {};
    const top = Object.entries(ph).filter(([k]) => k.endsWith("_s") && !/_build_s|_scan_s/.test(k) && k !== "total_s").sort((a, b) => b[1] - a[1]).slice(0, 8);
    modal({
      title: `${i.id} · ${i.label}`, wide: true,
      body: `<div class="cols"><div class="card stat"><div class="k">Status</div><div class="v" style="font-size:16px">${esc(i.outcome || i.status)}</div><div class="s">${esc(i.stage_label)}</div></div>
        <div class="card stat"><div class="k">Entries reused</div><div class="v">${n0(d.n_stable)} / ${n0(d.n_entries)}</div><div class="s">${n0(d.n_fresh)} scanned fresh</div></div>
        <div class="card stat"><div class="k">Elapsed</div><div class="v">${dur(i.elapsed_s)}</div><div class="s">${n0(i.records)} proteins</div></div></div>
        ${i.error ? `<div class="refstrip">${ic("warn")}${esc(i.error)}</div>` : ""}
        <h3 style="margin:4px 0 0">Decision</h3><pre class="cmd">${esc(Object.entries(d).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join("\n") || "none")}</pre>
        ${top.length ? `<h3 style="margin:4px 0 0">Where the time went</h3><table class="grid"><tbody>${top.map(([k, v]) => `<tr><td class="mono">${esc(k)}</td><td>${fx(v, 2)} s</td><td style="width:50%"><div class="bar"><i style="width:${(100 * v) / (ph.total_s || 1)}%"></i></div></td></tr>`).join("")}</tbody></table>` : ""}
        ${i.argv ? `<h3 style="margin:4px 0 0">Command</h3><pre class="cmd">${esc(i.argv.join(" "))}</pre>` : ""}`,
      actions: [{ label: `${ic("folderOpen")}Open folder`, onClick: () => act(() => api(`/api/projects/${pidq()}/open`, { run: S.rid, sub: `items/${i.id}` })) }],
    });
  },
  openCompleted: () => act(() => api(`/api/projects/${pidq()}/open`, { run: S.rid, sub: "items" }), "Opened in Finder"),
  openOutput: () => act(() => api(`/api/projects/${pidq()}/open`, S.rid ? { run: S.rid } : {}), "Opened in Finder"),
  openProjectDir: () => act(() => api(`/api/projects/${pidq()}/open`, {}), "Opened in Finder"),
  downloadResults: () => download(`/api/runs/${rid()}/download`),
  exportReport: () => download(`/api/runs/${rid()}/report`),
  exportBundle: () => download(`/api/runs/${rid()}/bundle`),
  viewLogs: async () => {
    const lg = await api(`/api/runs/${rid()}/log`);
    modal({ title: `Log · ${S.run.name}`, wide: true, body: `<pre class="cmd" style="max-height:60vh;overflow:auto">${esc(lg.rows.map((r) => `${r.t}  ${r.level.toUpperCase().padEnd(5)}  ${r.message}`).join("\n"))}</pre>` });
  },
  copyLog: async () => {
    const text = S.log.map((r) => `${clock(r.t)}\t${r.level}\t${r.message}`).join("\n");
    try { await navigator.clipboard.writeText(text); toast("Log copied", "ok"); } catch { toast("Clipboard not available", "bad"); }
  },
  exportLog: () => {
    const blob = new Blob([S.log.map((r) => `${r.t}\t${r.level}\t${r.message}`).join("\n") + "\n"], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `${S.rid}-log.txt`; a.click(); URL.revokeObjectURL(url);
  },
  compareRuns: () => {
    const runs = S.P.runs;
    const opts = (sel) => runs.map((r) => `<option value="${esc(r.id)}" ${r.id === sel ? "selected" : ""}>${esc(r.name)} · ${esc(r.status)}</option>`).join("");
    const root = modal({
      title: "Compare Runs", wide: true,
      body: `<div class="formgrid"><label>Run A</label><select class="in" id="cr-a">${opts(runs[1]?.id)}</select><label>Run B</label><select class="in" id="cr-b">${opts(runs[0]?.id)}</select></div><div id="cr-out"></div>`,
      actions: [{ label: "Compare", primary: true, onClick: async (root) => {
        try {
          const r = await api(`/api/runs/compare?a=${encodeURIComponent(root.querySelector("#cr-a").value)}&b=${encodeURIComponent(root.querySelector("#cr-b").value)}`);
          const cell = (x) => (x ? `${esc(x.status)} · ${dur(x.elapsed_s)}${x.reused != null ? ` · ${n0(x.reused)} reused` : ""}` : "—");
          root.querySelector("#cr-out").innerHTML = `<table class="grid"><thead><tr><th>Input</th><th>${esc(r.a.name)}</th><th>${esc(r.b.name)}</th><th>Same output</th></tr></thead><tbody>${r.rows.map((x) => `<tr><td>${esc(x.label)}</td><td>${cell(x.a)}</td><td>${cell(x.b)}</td><td>${x.same_output == null ? "—" : x.same_output ? `<span style="color:var(--ok)">identical</span>` : `<span style="color:var(--bad)">differs</span>`}</td></tr>`).join("")}</tbody></table>
            <p class="small">Wall: ${dur(r.a.wall_s)} vs ${dur(r.b.wall_s)}. ${Object.keys(r.settings_diff).length ? "Settings differ: " + Object.entries(r.settings_diff).map(([k, v]) => `${k} ${esc(v[0])} → ${esc(v[1])}`).join("; ") : "Same settings."}</p>`;
        } catch (e) { toast(e.message, "bad"); }
        return true;
      } }],
    });
    return root;
  },
  openProject: () => {
    const rows = S.app.projects.map((p) => `<tr class="click ${p.id === S.pid ? "sel" : ""}" data-pick="${esc(p.id)}"><td>${esc(p.name)}</td><td>${esc(TOOLS_LABEL(p.tool))}</td><td class="mono small">${esc(p.id)}</td></tr>`).join("");
    const root = modal({
      title: "Open Project",
      body: `<table class="grid"><thead><tr><th>Project</th><th>Tool</th><th>ID</th></tr></thead><tbody>${rows}</tbody></table>
        <h3 style="margin:8px 0 0">New project</h3><div class="formgrid"><label>Name</label><input class="in" id="np-name" placeholder="e.g. Bacterial pangenome" />
        <label>Start from</label><select class="in" id="np-copy"><option value="">Empty project</option>${S.app.projects.map((p) => `<option value="${esc(p.id)}">Copy inputs and releases of ${esc(p.name)}</option>`).join("")}</select></div>`,
      actions: [{ label: "Create project", primary: true, onClick: async (root) => {
        const name = root.querySelector("#np-name").value.trim();
        if (!name) { toast("Name the project", "bad"); return true; }
        const p = await act(() => api("/api/projects", { name, copy_from: root.querySelector("#np-copy").value || null }), (x) => `Created ${x.name}`);
        if (p) { S.pid = p.id; S.rid = null; S.tab = "setup"; refresh(true); }
      } }],
    });
    root.querySelectorAll("[data-pick]").forEach((tr) => (tr.onclick = () => { ACT.switchProject({ pid: tr.dataset.pick }); root.innerHTML = ""; }));
  },
  savePreset: () => modal({
    title: "Save Preset", body: `<div class="formgrid"><label>Preset name</label><input class="in" id="ps-name" value="${esc(TOOLS_LABEL(S.P.project.tool))} ${esc(S.P.project.settings.verify === "full" ? "full check" : "sampled")} · ${S.P.project.settings.threads} threads" /></div><p class="small muted">Saves compute, threads, limits, arguments, pin and verification policy.</p>`,
    actions: [{ label: "Save", primary: true, onClick: (root) => act(() => api(`/api/projects/${pidq()}/presets`, { name: root.querySelector("#ps-name").value.trim() }), (r) => `Saved preset ${r.name}`) }],
  }),
  applyPreset: (d) => confirmBox("Apply preset", `Replace the project's run settings with preset <b>${esc(d.name)}</b>?`, "Apply", () => act(() => api(`/api/projects/${pidq()}/apply-preset`, { name: d.name }), `Applied ${d.name}`)),
  addInputs: () => modal({
    title: "Add Inputs",
    body: `<p class="small">One FASTA path per line (absolute, or relative to the repository). Gzipped FASTA is accepted.</p><textarea class="in mono" id="ai-paths" rows="6" placeholder="/path/to/proteome.faa"></textarea>
      <p class="small muted">Current: ${S.P.project.inputs.map((i) => esc(i.id)).join(", ") || "none"}</p>`,
    actions: [{ label: "Add", primary: true, onClick: (root) => act(() => api(`/api/projects/${pidq()}/inputs`, { paths: root.querySelector("#ai-paths").value.split("\n").map((s) => s.trim()).filter(Boolean) }), "Inputs added") }],
  }),
  removeInput: (d) => confirmBox("Remove input", `Remove <b>${esc(d.id)}</b> from this project? The file on disk is kept.`, "Remove", () => act(() => api(`/api/projects/${pidq()}/inputs-remove`, { id: d.id }), "Input removed"), true),
  selectTool: () => modal({
    title: "Select Tool",
    body: `<div class="toolcards" style="grid-template-columns:1fr 1fr">${S.app.tools.map((t) => `<button class="toolcard ${S.P.project.tool === t.id ? "on" : ""}" data-tool="${t.id}" ${t.runnable ? "" : "disabled"}><b>${esc(t.label)}</b> <span class="muted">${esc(t.program)}</span><div class="small muted">${t.runnable ? `v${esc(t.version || "?")} · ${esc(t.binary)}` : t.installed ? "installed; not wired into the console yet" : `${esc(t.program)} not installed on this machine`}</div></button>`).join("")}</div>`,
  }).querySelectorAll("[data-tool]").forEach((b) => (b.onclick = () => { ACT.setTool({ tool: b.dataset.tool }); $("#modal-root").innerHTML = ""; })),
  setTool: (d) => act(() => api(`/api/projects/${pidq()}/tool`, { tool: d.tool }), "Tool selected"),
  checkSetup: () => { S.tab = "plan"; S.preflight = null; render(); },
  previewChanges: async () => {
    try {
      const d = await api(`/api/projects/${pidq()}/diff`);
      modal({ title: `Preview Changes · ${d.old} → ${d.new}`, wide: true, body: diffBlock(d) });
    } catch (e) { toast(e.message, "bad"); }
  },
  saveRefs: () => act(() => api(`/api/projects/${pidq()}/references`, { old: $("#ref-old").value, new: $("#ref-new").value }), "Releases set"),
  useRef: (d) => {
    const refs = { ...S.P.project.references, [d.side]: d.id };
    act(() => api(`/api/projects/${pidq()}/references`, refs), "Releases set").then(() => (S.preflight = null));
  },
  importRelease: () => modal({
    title: "Import Release",
    body: `<div class="formgrid"><label>File</label><input class="in mono" id="ir-path" placeholder="/path/to/Pfam-A.hmm" />
      <label>Label</label><input class="in" id="ir-label" placeholder="Pfam 38.3" />
      <label>Use as</label><select class="in" id="ir-use"><option value="new">New release (current new becomes previous)</option><option value="old">Previous release</option><option value="">Just import</option></select></div>
      <p class="small muted">The file is parsed into entries and copied into the console's reference store. Large profile libraries take a while.</p>`,
    actions: [{ label: "Import", primary: true, onClick: (root) => act(() => api(`/api/projects/${pidq()}/import-release`, { path: root.querySelector("#ir-path").value.trim(), label: root.querySelector("#ir-label").value.trim(), use_as: root.querySelector("#ir-use").value }), (m) => `Imported ${m.label}: ${n0(m.entries)} entries`) }],
  }),
  buildCache: () => {
    const n = S.P.project.inputs.length;
    confirmBox("Build Cache", `Scan ${n} inputs against <b>${esc(refLabel("old"))}</b> once and store every result. Later updates reuse it for unchanged entries.`, "Build cache", async () => {
      const r = await act(() => api(`/api/projects/${pidq()}/runs`, { kind: "cache" }), (x) => `${x.name} queued`);
      if (r) { S.rid = r.id; S.tab = "live"; }
    });
  },
  validateCache: async () => {
    try {
      const r = await api(`/api/projects/${pidq()}/cache-validate`, {});
      modal({ title: "Validate Cache", body: `${checkList([
        { title: "SQLite integrity", status: r.ok ? "pass" : "fail", detail: r.integrity || r.detail },
        { title: "Compatibility", status: r.compatibility === "compatible" ? "pass" : "warn", detail: r.detail },
        { title: "Contents", status: "pass", detail: Object.entries(r.counts || {}).map(([k, v]) => `${n0(v)} ${k}`).join(" · ") || "empty" },
      ])}` });
      refresh(true);
    } catch (e) { toast(e.message, "bad"); }
  },
  invalidateCache: () => confirmBox("Invalidate cache", `Delete the cache for <b>${esc(S.P.project.name)}</b> (${bytes(S.P.cache.bytes)})? The next update scans every entry until the cache is rebuilt. This cannot be undone.`, "Delete cache", () => act(() => api(`/api/projects/${pidq()}/cache-invalidate`, {}), (r) => `Cache removed (${bytes(r.removed_bytes)})`), true),
  cleanUp: () => confirmBox("Clean Up", `Delete the outputs of finished runs except the 3 most recent? Logs and tables of the deleted runs are removed. This cannot be undone.`, "Delete old runs", () => act(() => api(`/api/projects/${pidq()}/cleanup`, { keep: 3 }), (r) => `Removed ${r.removed.length} runs (${bytes(r.freed_bytes)})`), true),
  testConn: (d) => { toast(`Testing ${d.compute === "carc" ? "CARC" : "This Mac"}…`); act(() => api("/api/connection/test", { compute: d.compute }), (r) => `${r.target}: ${r.ok ? "connected" : "failed"} · ${r.detail}`); },
  setLimits: () => {
    const L = S.limits;
    S.limits = null;
    act(() => api(`/api/projects/${pidq()}/settings`, { threads: Number(L.threads), memory_gb: Number(L.memory_gb), time_limit: L.time_limit }), "Limits saved; they apply to the next run");
  },
  viewCommand: async () => {
    try {
      const c = await api(`/api/projects/${pidq()}/command`);
      modal({ title: "Exact command", wide: true, body: `<p class="small">Run once per input from <code>${esc(c.cwd)}</code>:</p><pre class="cmd">${esc(c.shell)}</pre><p class="small">Stock equivalent:</p><pre class="cmd">${esc(c.stock)}</pre>`,
        actions: [{ label: `${ic("copy")}Copy`, onClick: async () => { await navigator.clipboard.writeText(c.shell); toast("Command copied", "ok"); return true; } }] });
    } catch (e) { toast(e.message, "bad"); }
  },
  manageAccess: () => modal({
    title: "Manage Access",
    body: `<p>The console is a single-user local app. It listens on <code>127.0.0.1</code> only, so it is reachable from this Mac and nowhere else.</p>
      <p>Project files: <code>tools/tare-console/state/projects/${esc(S.pid)}</code>. Anyone with your macOS login can read them. To share a run, export a report or a reproducibility bundle.</p>`,
  }),
  auditHistory: async () => {
    const r = await api(`/api/events?project=${pidq()}`);
    modal({ title: "Audit History", wide: true, body: `<table class="grid"><thead><tr><th>Time</th><th>Kind</th><th>Event</th></tr></thead><tbody>${r.events.map((e) => `<tr><td style="white-space:nowrap">${stamp(e.t)}</td><td>${esc(e.kind)}</td><td>${esc(e.message)}</td></tr>`).join("") || `<tr><td colspan="3" class="muted">No events.</td></tr>`}</tbody></table>` });
  },
};

document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-act]");
  if (!el || el.disabled) return;
  const fn = ACT[el.dataset.act];
  if (fn) { e.preventDefault(); e.stopPropagation(); fn({ ...el.dataset }); }
});

document.addEventListener("change", (e) => {
  const el = e.target;
  if (el.dataset.set) {
    act(() => api(`/api/projects/${pidq()}/settings`, { [el.dataset.set]: el.value }), "Setting saved");
  } else if (el.dataset.limit) {
    const s = S.P.project.settings;
    S.limits = S.limits || { threads: s.threads, memory_gb: s.memory_gb, time_limit: s.time_limit };
    S.limits[el.dataset.limit] = el.value;
    el.blur();
    render();
  } else if (el.dataset.actChange === "pickRun") {
    ACT.selectRun({ rid: el.value });
  }
});

refresh(true);
