/* MineAI control UI: bot panel, live activity timeline, manual tool console. */

const API = "";
const t = (key, params) => window.i18n.t(key, params);
const toolLabel = (name) => window.i18n.toolLabel(name);
const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]),
  );

async function api(path, options = {}) {
  // Optional client-side timeout so a request that never returns (e.g. a bot
  // that joins and is kicked before it ever spawns) can't leave a button stuck
  // in its "…" state forever. `timeoutMs` is stripped before hitting fetch.
  const { timeoutMs, ...fetchOptions } = options;
  let controller = null;
  let timer = null;
  if (timeoutMs) {
    controller = new AbortController();
    timer = setTimeout(() => controller.abort(), timeoutMs);
    fetchOptions.signal = controller.signal;
  }
  let res;
  try {
    res = await fetch(API + path, {
      headers: { "content-type": "application/json" },
      ...fetchOptions,
    });
  } catch (e) {
    if (controller && e.name === "AbortError") {
      throw new Error(t("toast.createTimeout"));
    }
    throw e;
  } finally {
    if (timer) clearTimeout(timer);
  }
  const text = await res.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = { message: text };
  }
  if (!res.ok) throw new Error(body?.message || `HTTP ${res.status}`);
  return body;
}

function toast(title, message, isError = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isError ? " err" : "");
  el.innerHTML = `<div class="t">${esc(title)}</div><div class="m">${esc(message || "")}</div>`;
  $("toasts").appendChild(el);
  setTimeout(() => el.remove(), isError ? 8000 : 4000);
}

/* ------------------------------- tabs ------------------------------- */

/* Manual console docks as a 3rd column beside Activity on desktop (collapsing
   it hands that space back to the feed), and falls back to a slide-over
   overlay on narrow screens where there's no room for 3 columns side by side. */
const drawer = $("console-drawer");
const scrim = $("drawer-scrim");
const isNarrowScreen = () => window.matchMedia("(max-width: 900px)").matches;

const setConsoleOpen = (open, opts = {}) => {
  drawer.classList.toggle("open", open);
  drawer.setAttribute("aria-hidden", open ? "false" : "true");
  scrim.hidden = !(open && isNarrowScreen());
  if (open && opts.focus) $("tool-search").focus();
};
const openConsole = () => setConsoleOpen(true, { focus: true });
const closeConsole = () => setConsoleOpen(false);
const toggleConsole = () => setConsoleOpen(!drawer.classList.contains("open"));

$("console-toggle").addEventListener("click", toggleConsole);
$("console-close").addEventListener("click", closeConsole);
scrim.addEventListener("click", closeConsole);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && drawer.classList.contains("open")) closeConsole();
});

// Desktop: docked open by default. Narrow screens: starts closed, since
// opening it there covers the page as a slide-over overlay instead.
setConsoleOpen(!isNarrowScreen());

/* The docked console's sticky `top` (and thus its `height: calc(100vh - top -
   20px)`, see style.css) needs to match where .layout actually starts, which
   moves whenever the header above it changes height — it wraps at some
   widths, and the zh/en taglines are different lengths. A hardcoded px value
   drifts out of sync and the panel overflows past the viewport bottom, so
   this is measured from the live layout instead and kept current via a
   ResizeObserver on the header plus a window resize listener. */
function syncConsoleDockTop() {
  const layout = document.querySelector(".layout");
  if (!layout) return;
  const top = layout.getBoundingClientRect().top + window.scrollY;
  document.documentElement.style.setProperty("--dock-top", `${Math.round(top)}px`);
}
syncConsoleDockTop();
window.addEventListener("resize", syncConsoleDockTop);
const headerEl = document.querySelector("header.top");
if (headerEl && window.ResizeObserver) {
  new ResizeObserver(syncConsoleDockTop).observe(headerEl);
}

/* Map | Calls toggle for the big visualization panel. */
document.querySelectorAll(".viz-toggle .seg").forEach((btn) => {
  btn.addEventListener("click", () => {
    currentView = btn.dataset.view;
    document.querySelectorAll(".viz-toggle .seg").forEach((b) => b.classList.toggle("on", b === btn));
    $("view-map").classList.toggle("on", currentView === "map");
    $("view-calls").classList.toggle("on", currentView === "calls");
    requestAnimationFrame(renderViz); // canvases size only once their view is shown
  });
});

/* Hover a call-path chip (node) to see that call's real args/result. */
(() => {
  const cp = $("call-path");
  if (!cp) return;
  cp.addEventListener("mouseover", (e) => {
    const chipEl = e.target.closest(".chip");
    if (chipEl && cp.contains(chipEl)) showCallPop(chipEl);
  });
  cp.addEventListener("mouseout", (e) => {
    if (!e.target.closest(".chip")) return;
    const to = e.relatedTarget;
    if (!to || !to.closest || !to.closest(".chip")) hideCallPop();
  });
})();

window.addEventListener("resize", () => requestAnimationFrame(renderViz));

/* ------------------------------- bots ------------------------------- */

const val = (id) => $(id).value.trim();

function botCard(b) {
  const status = b.closed
    ? `<span class="badge offline">${t("badge.closed")}</span>`
    : b.connected && b.spawned
      ? `<span class="badge online">${t("badge.online")}</span>`
      : `<span class="badge pending">${t("badge.connecting")}</span>`;
  // Bridge errors arrive with a full JS stack trace and absolute paths. The
  // first line carries the actual reason; the rest is noise on a student's
  // screen. The Activity tab still has the untruncated text.
  const whyRaw = b.kicked_reason || b.end_reason || b.last_error;
  const why = whyRaw ? String(whyRaw).split(/\n|\s+at\s/)[0].slice(0, 180) : "";
  const pos = b.position ? `${b.position}` : "—";
  return `
    <div class="bot ${b.active ? "is-active" : ""}">
      <div class="id">
        <div class="name-row">
          <span class="name">${esc(b.name)}</span>
          ${b.active ? `<span class="badge active">${t("badge.active")}</span>` : ""}
          ${status}
          <span class="user">${b.username ? "@" + esc(b.username) : b.account ? t("bot.account", { name: esc(b.account) }) : "—"}</span>
        </div>
        <div class="stats">
          <div class="stat"><span class="k">${t("stat.position")}</span><span class="v">${esc(pos)}</span></div>
          <div class="stat"><span class="k">${t("stat.health")}</span><span class="v">${b.health ?? "—"}</span></div>
          <div class="stat"><span class="k">${t("stat.food")}</span><span class="v">${b.food ?? "—"}</span></div>
          <div class="stat"><span class="k">${t("stat.pathfinder")}</span><span class="v">${b.pathfinder_loaded ? t("val.yes") : t("val.no")}</span></div>
        </div>
        ${why ? `<div class="why">${esc(why)}</div>` : ""}
      </div>
      <div class="actions">
        <button class="btn small activate-btn" data-name="${esc(b.name)}" ${b.active || b.closed ? "disabled" : ""}>${t("btn.setActive")}</button>
        ${
          b.closed
            ? `<button class="btn small danger forget-btn" data-name="${esc(b.name)}">${t("btn.remove")}</button>`
            : `<button class="btn small danger close-btn" data-name="${esc(b.name)}">${t("btn.close")}</button>`
        }
      </div>
    </div>`;
}

async function refreshBots() {
  try {
    const data = await api("/health");
    $("server-dot").className = "dot up";
    $("server-label").textContent = t("server.up");
    const bots = data.bots || [];
    ingestHealth(bots);
    renderViz();
    updateDrawerBotChip();
    const host = $("bots");
    $("clear-closed").style.display = "none";
    if (!bots.length) {
      host.innerHTML = `<div class="empty">
        <div class="big">${t("bots.empty.title")}</div>
        <div>${t("bots.empty.desc")}</div>
      </div>`;
      return;
    }
    host.innerHTML = bots.map(botCard).join("");
    host.querySelectorAll(".activate-btn").forEach((btn) =>
      btn.addEventListener("click", async () => {
        try {
          await api(`/bots/${encodeURIComponent(btn.dataset.name)}/activate`, { method: "POST" });
          refreshBots();
        } catch (e) {
          toast(t("toast.activateFail"), e.message, true);
        }
      }),
    );
    host.querySelectorAll(".close-btn").forEach((btn) =>
      btn.addEventListener("click", async () => {
        try {
          await api(`/bots/${encodeURIComponent(btn.dataset.name)}`, { method: "DELETE" });
          refreshBots();
        } catch (e) {
          toast(t("toast.closeFail"), e.message, true);
        }
      }),
    );
    // Closed bots stay listed so the kick/disconnect reason is still readable.
    // Removing is the explicit second step.
    host.querySelectorAll(".forget-btn").forEach((btn) =>
      btn.addEventListener("click", async () => {
        try {
          await api(`/bots/${encodeURIComponent(btn.dataset.name)}/record`, { method: "DELETE" });
          refreshBots();
        } catch (e) {
          toast(t("toast.removeFail"), e.message, true);
        }
      }),
    );

    const closed = bots.filter((b) => b.closed).length;
    $("clear-closed").style.display = closed ? "" : "none";
    $("clear-closed").textContent = t("btn.removeNClosed", { n: closed });
  } catch (e) {
    $("server-dot").className = "dot down";
    $("server-label").textContent = t("server.down");
  }
}

function updateAdvToggle() {
  const adv = $("adv");
  $("adv-toggle").textContent = (adv.classList.contains("open") ? "▾" : "▸") + " " + t("btn.advOptions");
}
$("adv-toggle").addEventListener("click", () => {
  $("adv").classList.toggle("open");
  updateAdvToggle();
});

$("create-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const name = val("f-name");
  if (!name) return toast(t("toast.nameRequired.title"), t("toast.nameRequired.msg"), true);

  const body = { name, wait_spawn: $("f-wait").checked };
  if (val("f-account")) body.account = val("f-account");

  const options = {};
  if (val("f-host")) options.host = val("f-host");
  if (val("f-port")) options.port = Number(val("f-port"));
  if (val("f-username")) options.username = val("f-username");
  if (val("f-password")) options.password = val("f-password");
  if (val("f-version")) options.version = val("f-version");
  if (Object.keys(options).length) body.options = options;
  if (val("f-height")) body.height = Number(val("f-height"));

  const btn = $("create-btn");
  btn.disabled = true;
  btn.textContent = t("btn.creating");
  try {
    // Timeout sits just above the server's spawn wait (MINEAI_SPAWN_TIMEOUT,
    // 30s) so a legitimately slow spawn still lands, but a truly wedged request
    // still releases the button instead of leaving it on "Creating…".
    await api("/bots", { method: "POST", body: JSON.stringify(body), timeoutMs: 45000 });
    toast(t("toast.botCreated.title"), t("toast.botCreated.msg", { name }));
    $("f-name").value = "";
    $("f-password").value = "";
    refreshBots();
  } catch (e) {
    toast(t("toast.createFail"), e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = t("btn.createBot");
  }
});

$("refresh-btn").addEventListener("click", refreshBots);

$("clear-closed").addEventListener("click", async () => {
  try {
    const res = await api("/bots/closed", { method: "DELETE" });
    toast(t("toast.removed.title"), t("toast.removed.msg", { n: res.removed.length }));
    refreshBots();
  } catch (e) {
    toast(t("toast.removeFail"), e.message, true);
  }
});

/* ----------------------------- activity ----------------------------- */

let events = [];

const fmtTime = (ts) => {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString(undefined, { hour12: false }) + "." + String(d.getMilliseconds()).padStart(3, "0");
};

/* Canvas colours (mirror the CSS tokens — a canvas can't read CSS variables). */
const C = {
  accent: "#4ea1ff", green: "#3fb950", amber: "#d29922", purple: "#bc8cff",
  red: "#f85149", muted: "#8b95a3", grid: "#212a33",
};
const BOT_PALETTE = ["#4ea1ff", "#3fb950", "#d29922", "#bc8cff", "#f472b6", "#2dd4bf", "#f85149", "#a3e635"];
const CAT_COLOR = {
  movement: "var(--accent)", pathfinder: "var(--purple)",
  interaction: "var(--amber)", sensors: "var(--green)", lifecycle: "var(--muted)",
};

/* Short verb used to phrase the summary line for the directional move tools. */
const MOVE_VERB = { move_forward: "forward", move_backward: "backward", move_left: "left", move_right: "right" };
const POS_TOOLS = new Set([
  "move_forward", "move_backward", "move_left", "move_right", "jump", "get_pos",
  "pathfinder_goto_near", "pathfinder_goto_look_at_block",
]);
const FACE_TOOLS = new Set(["turn", "turn_left", "turn_right", "set_turn", "look_at", "get_orientation"]);
const DIG_TOOLS = new Set(["dig", "place"]);

const toolCat = {}; // name -> category, filled by loadTools()
let activeBot = null;
let currentView = "map"; // "map" | "calls" — which big-panel view is shown
const botState = {}; // name -> { color, x, y, z, yaw, trail[], marks[], closed, ... }
let colorIdx = 0;
const seenIds = new Set(); // rows already animated in

const catColorFor = (name) => CAT_COLOR[toolCat[name]] || "var(--border)";
const PATH_WINDOW = 40; // last N model calls shown in the call-path timeline
// The calling graph is about the *model* looping, so human console runs are excluded.
const modelCalls = (n) => {
  const c = events.filter((e) => e.kind === "tool_call" && e.source === "model");
  return n ? c.slice(-n) : c;
};
const round = (n) => Math.round(n);

// A tool that returns a string surfaces either as a bare string or, when
// FastMCP wraps it in structured output, as { result: "..." }. Unwrap to text.
const resultText = (r) =>
  typeof r === "string" ? r : r && typeof r === "object" && typeof r.result === "string" ? r.result : "";
const nums = (s) => ((typeof s === "string" ? s : resultText(s)).match(/-?\d+(?:\.\d+)?/g) || []).map(Number);

function ensureBot(name) {
  if (!botState[name]) {
    botState[name] = { color: BOT_PALETTE[colorIdx++ % BOT_PALETTE.length], x: null, y: null, z: null, yaw: 0, trail: [], marks: [] };
  }
  return botState[name];
}

function setPos(st, x, y, z, t) {
  st.x = x; st.y = y; st.z = z;
  const last = st.trail[st.trail.length - 1];
  if (!last || Math.abs(last[0] - x) > 0.01 || Math.abs(last[1] - z) > 0.01) {
    st.trail.push([x, z, t || Date.now() / 1000]);
    if (st.trail.length > 250) st.trail = st.trail.slice(-250);
  }
}

/* Fold one streamed event into per-bot map state. */
function ingest(ev) {
  if (ev.kind !== "tool_call") return;
  const name = (ev.arguments && ev.arguments.bot_name) || activeBot;
  if (!name) return;
  const st = ensureBot(name);
  const n = nums(ev.result);
  if (POS_TOOLS.has(ev.name) && n.length >= 3) {
    setPos(st, n[0], n[1], n[2], ev.timestamp);
  } else if (FACE_TOOLS.has(ev.name) && n.length >= 1) {
    st.yaw = n[0];
  } else if (DIG_TOOLS.has(ev.name) && n.length >= 3) {
    st.marks.push({ x: n[0], z: n[2], kind: ev.name });
    if (st.marks.length > 40) st.marks = st.marks.slice(-40);
  }
}

/* Fold /health snapshots in: current position, liveness, active bot. */
function ingestHealth(bots) {
  const active = bots.find((b) => b.active);
  if (active) activeBot = active.name;
  bots.forEach((b) => {
    const st = ensureBot(b.name);
    st.closed = b.closed;
    st.active = b.active;
    // /health returns position as a [x, y, z] array (get_pos' tuple), while tool
    // results are "x, y, z" strings — handle both so a bot shows on the map the
    // moment it spawns, before it has moved.
    const n = Array.isArray(b.position) ? b.position.map(Number) : nums(b.position);
    if (n.length >= 3 && n.every((v) => !Number.isNaN(v))) setPos(st, n[0], n[1], n[2]);
  });
}

/* ---- humanized feed ---- */

function prettyResult(ev) {
  if (ev.error) return { txt: String(ev.error).split(/\n|\s+at\s/)[0].slice(0, 80), err: true };
  if (ev.result == null || ev.result === "") return null;
  const r = resultText(ev.result) || ev.result;
  if (typeof r === "string") {
    if (r === "") return null;
    const n = nums(r);
    if (n.length === 3 && /^-?[\d.]+,\s*-?[\d.]+,\s*-?[\d.]+$/.test(r.trim())) {
      return { txt: `(${n.map(round).join(", ")})` };
    }
    return { txt: r.length > 64 ? r.slice(0, 64) + "…" : r };
  }
  return { txt: JSON.stringify(r).slice(0, 64) };
}

function summaryText(ev) {
  const a = ev.arguments || {};
  switch (ev.name) {
    case "move_forward": case "move_backward": case "move_left": case "move_right":
      return t("sum.walk", { dir: t("dir." + MOVE_VERB[ev.name]), blocks: a.blocks ?? 1 });
    case "jump": return t("sum.jump");
    case "turn": return t("sum.turn", { deg: a.degrees ?? "?" });
    case "turn_left": return t("sum.turnLeft");
    case "turn_right": return t("sum.turnRight");
    case "set_turn": return t("sum.setTurn", { yaw: a.yaw ?? "?" });
    case "look_at": return t("sum.lookAt", { x: a.x, y: a.y, z: a.z });
    case "dig": return t("sum.dig");
    case "place": return t("sum.place");
    case "use": return t("sum.use");
    case "use_player": return t("sum.usePlayer", { who: a.username ?? t("sum.aPlayer") });
    case "hold": return t("sum.hold", { name: a.name ?? "?" });
    case "unhold": return t("sum.unhold");
    case "drop":
      return a.item
        ? t("sum.drop", { item: a.item, count: a.count ? ` ×${a.count}` : "" })
        : t("sum.dropHeld");
    case "sneak": return a.on ? t("sum.sneakOn") : t("sum.sneakOff");
    case "action": return t("sum.action", { name: a.name ?? "?", value: a.value != null ? ` (${a.value})` : "" });
    case "chat": return t("sum.chat", { message: a.message ?? "" });
    case "set_height": return t("sum.setHeight", { level: a.level ?? "?" });
    case "get_pos": return t("sum.getPos");
    case "get_orientation": return t("sum.getOrientation");
    case "get_block": return t("sum.getBlock", { x: a.x, y: a.y, z: a.z });
    case "get_block_property": return t("sum.getBlockProperty", { property: a.property_name ?? "property", x: a.x, y: a.y, z: a.z });
    case "find_block": return t("sum.findBlock", { name: a.name ?? "?" });
    case "find_blocks": return t("sum.findBlocks", { name: a.name ?? "?", max: a.max ?? 16 });
    case "look_block": return t("sum.lookBlock");
    case "get_block_in_front": return t("sum.getBlockInFront");
    case "get_hand": return t("sum.getHand");
    case "get_height": return t("sum.getHeight");
    case "set_active_bot": return t("sum.setActiveBot", { name: a.bot_name ?? "?" });
    default:
      if (ev.name.startsWith("pathfinder_goto")) {
        const to = [a.x, a.y, a.z].filter((v) => v != null).join(", ");
        return t("sum.pathfindTo", { to });
      }
      return toolLabel(ev.name).replace(/_/g, " ");
  }
}

function renderFeed() {
  const src = $("ev-filter").value;
  const kind = $("ev-kind").value;
  const rows = events.filter((e) => (src === "all" || e.source === src) && (kind === "all" || e.kind === kind));
  $("ev-count").textContent = events.length;

  if (!rows.length) {
    $("feed").innerHTML = `<div class="empty">
      <div class="big">${t("feed.empty.title")}</div>
      <div>${t("feed.empty.desc")}</div>
    </div>`;
    return;
  }

  const fresh = [];
  $("feed").innerHTML = rows
    .slice()
    .reverse()
    .map((ev) => {
      const isNew = !seenIds.has(ev.id);
      if (isNew) fresh.push(ev.id);
      const r = prettyResult(ev);
      const accent = ev.error ? "var(--red)" : catColorFor(ev.name);
      return `
      <div class="ev ${ev.source} ${ev.error ? "err" : ""} ${isNew ? "new" : ""}" data-id="${ev.id}" style="border-left:3px solid ${accent}">
        <div class="ev-head">
          <span class="src ${ev.source}">${ev.source}</span>
          <span class="ev-name">${esc(toolLabel(ev.name))}</span>
          ${ev.duration_ms != null ? `<span class="ev-ms">${ev.duration_ms} ms</span>` : ""}
          <span class="ev-time">${fmtTime(ev.timestamp)}</span>
        </div>
        <div class="ev-summary">${esc(summaryText(ev))}${r ? ` <span class="r ${r.err ? "err" : ""}">${r.err ? "" : "→ "}${esc(r.txt)}</span>` : ""}</div>
        <div class="ev-detail">
          <div class="lbl">${t("lbl.arguments")}</div>
          <pre>${esc(JSON.stringify(ev.arguments ?? null, null, 2))}</pre>
          <div class="lbl">${ev.error ? t("lbl.error") : t("lbl.result")}</div>
          <pre>${esc(ev.error || JSON.stringify(ev.result ?? null, null, 2))}</pre>
        </div>
      </div>`;
    })
    .join("");
  fresh.forEach((id) => seenIds.add(id));

  $("feed")
    .querySelectorAll(".ev")
    .forEach((row) => row.addEventListener("click", () => row.classList.toggle("open")));
}

/* ---- stat strip + sparkline ---- */

function renderStats() {
  const el = $("viz-stats");
  if (!el) return;
  const total = events.length;
  const model = events.filter((e) => e.source === "model").length;
  const human = events.filter((e) => e.source === "human").length;
  const counts = {};
  events.filter((e) => e.kind === "tool_call").forEach((e) => (counts[e.name] = (counts[e.name] || 0) + 1));
  const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 4);
  const maxc = top.length ? top[0][1] : 1;

  el.innerHTML = `
    <div class="stat-tile"><div class="st-k">${t("st.toolCalls")}</div><div class="st-v">${total}</div></div>
    <div class="stat-tile">
      <div class="st-k">${t("st.modelHuman")}</div>
      <div class="st-v"><span style="color:var(--purple)">${model}</span> <span class="muted">/</span> <span style="color:var(--green)">${human}</span></div>
    </div>
    <div class="stat-tile spark"><div class="st-k">${t("st.calls60")}</div><canvas id="spark-canvas"></canvas></div>
    <div class="stat-tile">
      <div class="st-k">${t("st.topTools")}</div>
      <div class="toplist">${
        top.length
          ? top.map(([n, c]) => `<div class="tl"><span class="tl-n">${esc(toolLabel(n))}</span><span class="tl-bar"><i style="width:${round((c / maxc) * 100)}%"></i></span><span class="tl-c">${c}</span></div>`).join("")
          : '<span class="muted">—</span>'
      }</div>
    </div>`;
  drawSpark();
}

function sizeCanvas(cv) {
  const w = cv.clientWidth;
  const h = cv.clientHeight;
  if (!w || !h) return null;
  const dpr = window.devicePixelRatio || 1;
  cv.width = w * dpr;
  cv.height = h * dpr;
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}

function drawSpark() {
  const cv = $("spark-canvas");
  if (!cv) return;
  const s = sizeCanvas(cv);
  if (!s) return;
  const { ctx, w, h } = s;
  const now = Date.now() / 1000;
  const span = 60;
  const buckets = 20;
  const bw = span / buckets;
  const counts = new Array(buckets).fill(0);
  events.forEach((e) => {
    const age = now - e.timestamp;
    if (age >= 0 && age < span) counts[Math.min(buckets - 1, Math.floor((span - age) / bw))]++;
  });
  const max = Math.max(1, ...counts);
  const gap = 2;
  const colW = (w - (buckets - 1) * gap) / buckets;
  counts.forEach((c, i) => {
    if (!c) return;
    const bh = Math.max(2, (c / max) * (h - 2));
    ctx.fillStyle = C.accent;
    ctx.fillRect(i * (colW + gap), h - bh, colW, bh);
  });
}

/* ---- live minimap ---- */

function drawMap() {
  const cv = $("map-canvas");
  if (!cv) return;
  const s = sizeCanvas(cv);
  if (!s) return;
  const { ctx, w, h } = s;

  const names = Object.keys(botState);
  const pts = [];
  names.forEach((n) => {
    const st = botState[n];
    if (st.x != null) pts.push([st.x, st.z]);
    st.trail.forEach((p) => pts.push([p[0], p[1]]));
    st.marks.forEach((m) => pts.push([m.x, m.z]));
  });

  const empty = $("map-empty");
  if (empty) empty.classList.toggle("hide", pts.length > 0);
  renderLegend(names);
  if (!pts.length) return;

  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
  pts.forEach(([x, z]) => {
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minZ = Math.min(minZ, z); maxZ = Math.max(maxZ, z);
  });
  const spanX = Math.max(maxX - minX, 8);
  const spanZ = Math.max(maxZ - minZ, 8);
  const pad = 26;
  const scale = Math.min((w - 2 * pad) / spanX, (h - 2 * pad) / spanZ);
  const cx = (minX + maxX) / 2;
  const cz = (minZ + maxZ) / 2;
  const toPx = (x, z) => [w / 2 + (x - cx) * scale, h / 2 + (z - cz) * scale];

  // faint grid every 8 world blocks
  ctx.strokeStyle = C.grid;
  ctx.lineWidth = 1;
  const step = 8;
  for (let gx = Math.ceil(minX / step) * step; gx <= maxX; gx += step) {
    const [px] = toPx(gx, 0);
    ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, h); ctx.stroke();
  }
  for (let gz = Math.ceil(minZ / step) * step; gz <= maxZ; gz += step) {
    const [, py] = toPx(0, gz);
    ctx.beginPath(); ctx.moveTo(0, py); ctx.lineTo(w, py); ctx.stroke();
  }

  names.forEach((n) => {
    const st = botState[n];
    // trail
    if (st.trail.length > 1) {
      ctx.strokeStyle = st.color;
      ctx.globalAlpha = st.closed ? 0.25 : 0.55;
      ctx.lineWidth = 2;
      ctx.lineJoin = "round";
      ctx.beginPath();
      st.trail.forEach((p, i) => {
        const [px, py] = toPx(p[0], p[1]);
        i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
      });
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    // dig/place marks
    st.marks.forEach((mk) => {
      const [px, py] = toPx(mk.x, mk.z);
      ctx.fillStyle = mk.kind === "dig" ? C.red : C.green;
      ctx.globalAlpha = 0.65;
      ctx.fillRect(px - 2.5, py - 2.5, 5, 5);
    });
    ctx.globalAlpha = 1;
    // bot marker + facing
    if (st.x != null) drawBot(ctx, toPx(st.x, st.z), st);
  });
}

function drawBot(ctx, [px, py], st) {
  if (st.active) {
    ctx.fillStyle = st.color;
    ctx.globalAlpha = 0.18;
    ctx.beginPath(); ctx.arc(px, py, 11, 0, Math.PI * 2); ctx.fill();
    ctx.globalAlpha = 1;
  }
  // facing arrow: world yaw 0 = north(-Z); forward = (-sin, -cos) in (x, z)
  const yaw = (st.yaw || 0) * Math.PI / 180;
  const fx = -Math.sin(yaw);
  const fz = -Math.cos(yaw);
  ctx.strokeStyle = st.color;
  ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(px + fx * 13, py + fz * 13); ctx.stroke();
  // body
  ctx.fillStyle = st.closed ? C.muted : st.color;
  ctx.beginPath(); ctx.arc(px, py, 5, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = "#0b0e12";
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

function renderLegend(names) {
  const el = $("map-legend");
  if (!el) return;
  el.innerHTML = names
    .filter((n) => botState[n].x != null)
    .map((n) => `<span class="lg ${botState[n].closed ? "off" : ""}"><i style="background:${botState[n].color}"></i>${esc(n)}</span>`)
    .join("");
}

/* ---- calls view: ordered call-path timeline ---- */

// True when the p-length blocks starting at `a` and `b` are identical.
function blockEq(names, a, b, p) {
  for (let k = 0; k < p; k++) if (names[a + k] !== names[b + k]) return false;
  return true;
}

// Greedily fold a call sequence into segments, collapsing runs and short cycles:
//   dig,dig,dig               -> { single, dig, x3 }
//   get_pos,move,get_pos,move -> { loop, [get_pos, move], x2 }
function parseSegments(names) {
  const segs = [];
  const n = names.length;
  const MAXP = 5;
  let i = 0;
  while (i < n) {
    let best = { p: 1, reps: 1 };
    for (let p = 1; p <= Math.min(MAXP, n - i); p++) {
      let reps = 1;
      while (i + p * (reps + 1) <= n && blockEq(names, i, i + p * reps, p)) reps++;
      if (reps >= 2) {
        const cover = p * reps;
        const bestCover = best.reps >= 2 ? best.p * best.reps : 0;
        if (cover > bestCover || (cover === bestCover && p < best.p)) best = { p, reps };
      }
    }
    if (best.reps >= 2) {
      const len = best.p * best.reps;
      if (best.p === 1) segs.push({ kind: "single", name: names[i], count: best.reps, start: i, len });
      else segs.push({ kind: "loop", block: names.slice(i, i + best.p), reps: best.reps, start: i, len });
      i += len;
    } else {
      segs.push({ kind: "single", name: names[i], count: 1, start: i, len: 1 });
      i += 1;
    }
  }
  return segs;
}

// Each rendered chip registers the call(s) it stands for; the hover popover
// reads this by index (data-ci) to show the real arguments/result.
let pathChipData = [];
let lastPathId = 0; // id of the newest call last drawn — so only real additions animate
function registerChip(name, evs) {
  return pathChipData.push({ name, evs }) - 1;
}

function chip(name, count, cur, ci) {
  const badge = count > 1 ? `<span class="count">×${count}</span>` : "";
  return `<span class="chip${cur ? " cur" : ""}" data-ci="${ci}"><i class="dot" style="background:${catColorFor(name)}"></i>${esc(toolLabel(name))}${badge}</span>`;
}

function showCallPop(chipEl) {
  const d = pathChipData[+chipEl.dataset.ci];
  const pop = $("call-pop");
  if (!d || !pop) return;
  const last = d.evs[d.evs.length - 1];
  let html = `<div class="cp-head"><span class="cp-name">${esc(toolLabel(d.name))}</span>${d.evs.length > 1 ? `<span class="cp-n">${t("cp.nCalls", { n: d.evs.length })}</span>` : ""}</div>`;
  if (last) {
    html += `<div class="cp-time">${fmtTime(last.timestamp)}${last.duration_ms != null ? ` · ${last.duration_ms} ms` : ""}${d.evs.length > 1 ? " · " + t("cp.latest") : ""}</div>`;
    const a = last.arguments && Object.keys(last.arguments).length ? JSON.stringify(last.arguments) : "—";
    html += `<div class="cp-lbl">${t("cp.args")}</div><div class="cp-val">${esc(a)}</div>`;
    const res = last.error
      ? String(last.error).split(/\n/)[0]
      : resultText(last.result) || (last.result != null ? JSON.stringify(last.result) : "—");
    html += `<div class="cp-lbl">${last.error ? t("cp.error") : t("cp.result")}</div><div class="cp-val${last.error ? " err" : ""}">${esc(String(res).slice(0, 240))}</div>`;
  }
  pop.innerHTML = html;
  pop.hidden = false;
  const r = chipEl.getBoundingClientRect();
  pop.style.left = Math.max(8, Math.min(window.innerWidth - pop.offsetWidth - 8, r.left)) + "px";
  pop.style.top = r.bottom + 6 + "px";
}
function hideCallPop() {
  const pop = $("call-pop");
  if (pop) pop.hidden = true;
}

function renderLoopBanner(tail) {
  const b = $("loop-banner");
  if (!b) return;
  const looping = tail && (tail.kind === "loop" || (tail.kind === "single" && tail.count >= 3));
  if (!looping) { b.hidden = true; return; }
  b.textContent =
    tail.kind === "loop"
      ? t("loop.looping", { block: tail.block.join(" → "), reps: tail.reps })
      : t("loop.repeating", { name: toolLabel(tail.name), count: tail.count });
  b.hidden = false;
}

function renderPath() {
  const el = $("call-path");
  if (!el) return;
  const calls = modelCalls(PATH_WINDOW);
  const names = calls.map((e) => e.name);
  const empty = $("calls-empty");
  const legend = $("calls-legend");
  if (empty) empty.classList.toggle("hide", names.length > 0);
  if (legend) legend.classList.toggle("hide", names.length === 0);
  if (!names.length) {
    el.innerHTML = "";
    renderLoopBanner(null);
    return;
  }

  const segs = parseSegments(names);
  pathChipData = [];
  el.innerHTML = segs
    .map((s, idx) => {
      const last = idx === segs.length - 1;
      const arrow = idx > 0 ? `<span class="arrow">→</span>` : "";
      const evs = calls.slice(s.start, s.start + s.len);
      if (s.kind === "single") return arrow + chip(s.name, s.count, last, registerChip(s.name, evs));
      const inner = s.block
        .map((nm, k) => {
          const chipEvs = [];
          for (let r = 0; r < s.reps; r++) chipEvs.push(evs[r * s.block.length + k]);
          return (k ? `<span class="arrow sm">→</span>` : "") + chip(nm, 1, false, registerChip(nm, chipEvs));
        })
        .join("");
      return `${arrow}<span class="loop-group${last ? " cur" : ""}">${inner}<span class="count">×${s.reps}</span></span>`;
    })
    .join("");

  // Animate only the current chip, and only when a new call actually arrived
  // (skip re-renders from health polls / view toggles).
  const newestId = calls.length ? calls[calls.length - 1].id : 0;
  if (newestId && newestId !== lastPathId) {
    const cur = el.querySelector(".cur");
    if (cur) cur.classList.add("pop-in");
  }
  lastPathId = newestId;

  const wrap = el.parentElement;
  if (wrap) wrap.scrollTop = wrap.scrollHeight; // keep the newest call in view
  renderLoopBanner(segs[segs.length - 1]);
}

function renderViz() {
  renderStats();
  if (currentView === "calls") renderPath();
  else drawMap();
}

function startStream() {
  const source = new EventSource("/api/events/stream");
  source.onmessage = (msg) => {
    try {
      const ev = JSON.parse(msg.data);
      events.push(ev);
      if (events.length > 500) events = events.slice(-500);
      ingest(ev);
      renderFeed();
      renderViz();
      // Bot lifecycle changes are worth reflecting in the Bots tab immediately.
      if (ev.kind === "bot") refreshBots();
    } catch {
      /* ignore malformed frame */
    }
  };
  source.onerror = () => {
    // EventSource retries on its own; surface the state instead of reconnecting.
    $("server-dot").className = "dot down";
    $("server-label").textContent = t("server.streamLost");
  };
}

$("ev-filter").addEventListener("change", renderFeed);
$("ev-kind").addEventListener("change", renderFeed);
$("ev-clear").addEventListener("click", async () => {
  await api("/api/events", { method: "DELETE" });
  events = [];
  renderFeed();
  renderViz();
});

/* ------------------------------ console ----------------------------- */

let allTools = [];
let selectedTool = null; // tool name currently shown in the bottom dock, or null
const CAT_ORDER = ["movement", "interaction", "lifecycle", "sensors", "pathfinder", "other"];

const findTool = (name) => allTools.find((tl) => tl.name === name) || null;
const catLabel = (cat) => t("cat." + cat);
// The zh tool descriptions carry RST-style ``param`` markup meant for docs;
// strip it for the compact card/dock UI, which already shows the param names
// as field labels.
const toolDesc = (tool) => window.i18n.toolDesc(tool.name, tool.description.split("\n")[0]).replace(/``/g, "");

function updateDrawerBotChip() {
  const dot = $("drawer-bot-dot");
  const label = $("drawer-bot-name");
  if (!dot || !label) return;
  dot.className = "dot" + (activeBot ? " up" : "");
  label.textContent = activeBot || t("console.noActiveBot");
}

/** One small grid card in the tool list; click selects/deselects it. */
function toolCard(tool) {
  const desc = toolDesc(tool);
  return `
    <div class="tool-card${selectedTool === tool.name ? " selected" : ""}" data-name="${esc(tool.name)}">
      <div class="tc-name">${esc(toolLabel(tool.name))}</div>
      <div class="tc-desc">${esc(desc)}</div>
    </div>`;
}

function renderTools() {
  const q = $("tool-search").value.trim().toLowerCase();
  const shown = allTools.filter((tl) => !q || tl.name.includes(q) || tl.description.toLowerCase().includes(q));
  const groups = {};
  shown.forEach((tl) => (groups[tl.category] ||= []).push(tl));
  const cats = CAT_ORDER.filter((c) => groups[c]?.length);
  Object.keys(groups).forEach((c) => { if (!cats.includes(c)) cats.push(c); });

  $("tools").innerHTML = cats.length
    ? cats
        .map(
          (cat) => `
        <div class="tool-group" data-cat="${esc(cat)}">
          <h3>${esc(catLabel(cat))}(${groups[cat].length})</h3>
          <div class="tool-grid">${groups[cat].map(toolCard).join("")}</div>
        </div>`,
        )
        .join("")
    : `<div class="empty"><div class="big">${t("tools.empty")}</div></div>`;

  $("drawer-cats").innerHTML = cats
    .map((cat) => `<button type="button" class="cat" data-cat="${esc(cat)}">${esc(catLabel(cat))}(${groups[cat].length})</button>`)
    .join("");

  $("tools")
    .querySelectorAll(".tool-card")
    .forEach((card) => card.addEventListener("click", () => selectTool(card.dataset.name)));
  $("drawer-cats")
    .querySelectorAll(".cat")
    .forEach((btn) => btn.addEventListener("click", () => scrollToCat(btn.dataset.cat)));
  highlightActiveCat();
}

function scrollToCat(cat) {
  const container = $("drawer-scroll");
  const section = $("tools").querySelector(`.tool-group[data-cat="${cat}"]`);
  if (!container || !section) return;
  container.scrollTo({ top: section.offsetTop - 8, behavior: "smooth" });
}

/** Highlight the nav pill for whichever category section sits at the scroll top. */
function highlightActiveCat() {
  const container = $("drawer-scroll");
  const nav = $("drawer-cats");
  const sections = [...$("tools").querySelectorAll(".tool-group")];
  if (!container || !nav || !sections.length) return;
  const top = container.getBoundingClientRect().top;
  let active = sections[0].dataset.cat;
  sections.forEach((sec) => {
    if (sec.getBoundingClientRect().top <= top + 60) active = sec.dataset.cat;
  });
  nav.querySelectorAll(".cat").forEach((btn) => btn.classList.toggle("on", btn.dataset.cat === active));
}

/** Build one param input for the bottom dock. `coord` narrows x/y/z into a row. */
function dockField(key, spec, required, coord) {
  const id = `arg-${key}`;
  // Optional args are `anyOf: [{type: X}, {type: "null"}]`; unwrap to the real type.
  let type = spec.type;
  if (!type && Array.isArray(spec.anyOf)) {
    const real = spec.anyOf.find((s) => s.type && s.type !== "null");
    type = real?.type;
  }
  if (type === "boolean") {
    return `<div class="dock-field"><label class="dock-bool"><input type="checkbox" id="${id}" data-key="${esc(key)}" data-type="boolean" ${spec.default ? "checked" : ""} /><span>${esc(key)}</span></label></div>`;
  }
  const hint = required
    ? t("hint.required")
    : spec.default !== undefined
      ? t("hint.default", { value: JSON.stringify(spec.default) })
      : t("hint.optionalField");
  const input =
    type === "number" || type === "integer"
      ? `<input type="number" step="any" id="${id}" data-key="${esc(key)}" data-type="number" placeholder="${spec.default ?? ""}" />`
      : `<input type="text" id="${id}" data-key="${esc(key)}" data-type="string" placeholder="${spec.default ?? ""}" autocomplete="off" />`;
  return `<div class="dock-field${coord ? " coord" : ""}"><label for="${id}">${esc(key)} <span class="hint">· ${hint}</span></label>${input}</div>`;
}

/** Select (or deselect, on repeat click) a tool and (re)draw the bottom dock.
 *  bot_name is left out of the dock — the header's active-bot chip covers it,
 *  and every tool already falls back to the active bot when it's omitted. */
function selectTool(name) {
  selectedTool = selectedTool === name ? null : name;
  renderTools();
  renderDock();
}

function renderDock() {
  const dock = $("drawer-dock");
  const tool = selectedTool ? findTool(selectedTool) : null;
  if (!tool) {
    dock.hidden = true;
    dock.innerHTML = "";
    return;
  }

  const props = tool.schema?.properties || {};
  const required = tool.schema?.required || [];
  const keys = Object.keys(props).filter((k) => k !== "bot_name");
  const coordKeys = new Set(["x", "y", "z"].filter((k) => keys.includes(k)));
  const isCoordGroup = coordKeys.size >= 2;
  const fields = keys.map((key) => dockField(key, props[key], required.includes(key), isCoordGroup && coordKeys.has(key))).join("");
  const desc = toolDesc(tool);

  dock.hidden = false;
  dock.innerHTML = `
    <div class="dock-head">
      <span class="dk-name">${esc(toolLabel(tool.name))}</span>
      <span class="dk-desc">${esc(desc)}</span>
      <span class="dk-close" id="dock-close">✕</span>
    </div>
    ${fields ? `<div class="dock-fields">${fields}</div>` : `<div class="dock-noargs">${t("tool.noArgs")}</div>`}
    <div class="dock-run">
      <button class="btn primary small" id="dock-run-btn">${t("btn.run")}</button>
      <span class="as-human">${t("dock.asHuman")}</span>
    </div>
    <div class="dock-out" id="dock-out"></div>`;

  $("dock-close").addEventListener("click", () => selectTool(null));
  $("dock-run-btn").addEventListener("click", runSelectedTool);
}

async function runSelectedTool() {
  const tool = selectedTool ? findTool(selectedTool) : null;
  if (!tool) return;
  const btn = $("dock-run-btn");
  const out = $("dock-out");
  const args = {};

  $("drawer-dock")
    .querySelectorAll("[data-key]")
    .forEach((input) => {
      const key = input.dataset.key;
      if (input.dataset.type === "boolean") {
        args[key] = input.checked;
      } else if (input.value.trim() !== "") {
        args[key] = input.dataset.type === "number" ? Number(input.value) : input.value;
      }
      // Blank optional fields are omitted so the tool's own default applies.
    });

  btn.disabled = true;
  btn.textContent = t("btn.running");
  out.className = "dock-out show";
  out.textContent = "…";
  try {
    const res = await api(`/api/tools/${encodeURIComponent(tool.name)}/invoke`, {
      method: "POST",
      body: JSON.stringify(args),
    });
    out.className = "dock-out show";
    out.textContent = typeof res.result === "string" ? res.result : JSON.stringify(res.result, null, 2);
  } catch (e) {
    out.className = "dock-out show err";
    out.textContent = e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = t("btn.run");
  }
}

$("tool-search").addEventListener("input", renderTools);
$("drawer-scroll").addEventListener("scroll", highlightActiveCat, { passive: true });

async function loadTools() {
  try {
    allTools = (await api("/api/tools")).tools || [];
    allTools.forEach((tl) => (toolCat[tl.name] = tl.category));
    renderTools();
  } catch (e) {
    $("tools").innerHTML = `<div class="empty"><div class="big">${t("tools.loadError.title")}</div><div>${esc(e.message)}</div></div>`;
  }
}

/* ------------------------------- boot ------------------------------- */

updateAdvToggle();

// Re-render every dynamic surface when the language changes. Static markup is
// handled by i18n.applyStatic(); these are the JS-built pieces.
window.i18n.onLangChange(() => {
  updateAdvToggle();
  refreshBots();
  renderFeed();
  renderViz();
  renderTools();
  renderDock();
  updateDrawerBotChip();
  syncConsoleDockTop();
});

refreshBots();
loadTools();
renderFeed();
renderViz();
startStream();
// Bot changes arrive over SSE and refresh immediately; this is only a slow
// safety net for state the stream can't see (e.g. a bot dying mid-request).
setInterval(refreshBots, 15000);
