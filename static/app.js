/* MineAI control UI: bot panel, live activity timeline, manual tool console. */

const API = "";
const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]),
  );

async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
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

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("on"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("on"));
    tab.classList.add("on");
    $("panel-" + tab.dataset.tab).classList.add("on");
  });
});

/* ------------------------------- bots ------------------------------- */

const val = (id) => $(id).value.trim();

function botCard(b) {
  const status = b.closed
    ? `<span class="badge offline">closed</span>`
    : b.connected && b.spawned
      ? `<span class="badge online">online</span>`
      : `<span class="badge pending">connecting</span>`;
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
          ${b.active ? '<span class="badge active">active</span>' : ""}
          ${status}
          <span class="user">${b.username ? "@" + esc(b.username) : b.account ? "account: " + esc(b.account) : "—"}</span>
        </div>
        <div class="stats">
          <div class="stat"><span class="k">position</span><span class="v">${esc(pos)}</span></div>
          <div class="stat"><span class="k">health</span><span class="v">${b.health ?? "—"}</span></div>
          <div class="stat"><span class="k">food</span><span class="v">${b.food ?? "—"}</span></div>
          <div class="stat"><span class="k">pathfinder</span><span class="v">${b.pathfinder_loaded ? "yes" : "no"}</span></div>
        </div>
        ${why ? `<div class="why">${esc(why)}</div>` : ""}
      </div>
      <div class="actions">
        <button class="btn small activate-btn" data-name="${esc(b.name)}" ${b.active || b.closed ? "disabled" : ""}>Set active</button>
        ${
          b.closed
            ? `<button class="btn small danger forget-btn" data-name="${esc(b.name)}">Remove</button>`
            : `<button class="btn small danger close-btn" data-name="${esc(b.name)}">Close</button>`
        }
      </div>
    </div>`;
}

async function refreshBots() {
  try {
    const data = await api("/health");
    $("server-dot").className = "dot up";
    $("server-label").textContent = "service up";
    const bots = data.bots || [];
    const host = $("bots");
    $("clear-closed").style.display = "none";
    if (!bots.length) {
      host.innerHTML = `<div class="empty">
        <div class="big">No bots yet</div>
        <div>Create one above. On camp machines use the account shorthand;
        for dev testing leave it blank and the values come from <code>.env</code>.</div>
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
          toast("Could not activate", e.message, true);
        }
      }),
    );
    host.querySelectorAll(".close-btn").forEach((btn) =>
      btn.addEventListener("click", async () => {
        try {
          await api(`/bots/${encodeURIComponent(btn.dataset.name)}`, { method: "DELETE" });
          refreshBots();
        } catch (e) {
          toast("Could not close", e.message, true);
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
          toast("Could not remove", e.message, true);
        }
      }),
    );

    const closed = bots.filter((b) => b.closed).length;
    $("clear-closed").style.display = closed ? "" : "none";
    $("clear-closed").textContent = `Remove ${closed} closed`;
  } catch (e) {
    $("server-dot").className = "dot down";
    $("server-label").textContent = "service down";
  }
}

$("adv-toggle").addEventListener("click", () => {
  const adv = $("adv");
  adv.classList.toggle("open");
  $("adv-toggle").textContent = (adv.classList.contains("open") ? "▾" : "▸") + " Advanced connection options";
});

$("create-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const name = val("f-name");
  if (!name) return toast("Name required", "Give the bot a unique name.", true);

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
  btn.textContent = "Creating…";
  try {
    await api("/bots", { method: "POST", body: JSON.stringify(body) });
    toast("Bot created", `${name} is connected.`);
    $("f-name").value = "";
    $("f-password").value = "";
    refreshBots();
  } catch (e) {
    toast("Could not create bot", e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Create bot";
  }
});

$("refresh-btn").addEventListener("click", refreshBots);

$("clear-closed").addEventListener("click", async () => {
  try {
    const res = await api("/bots/closed", { method: "DELETE" });
    toast("Removed", `${res.removed.length} closed bot(s) removed.`);
    refreshBots();
  } catch (e) {
    toast("Could not remove", e.message, true);
  }
});

/* ----------------------------- activity ----------------------------- */

let events = [];

const fmtTime = (ts) => {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString(undefined, { hour12: false }) + "." + String(d.getMilliseconds()).padStart(3, "0");
};

const preview = (ev) => {
  if (ev.error) return ev.error;
  const args = ev.arguments && Object.keys(ev.arguments).length ? JSON.stringify(ev.arguments) : "";
  const out = ev.result != null ? " → " + JSON.stringify(ev.result) : "";
  return (args + out).slice(0, 220);
};

function renderFeed() {
  const src = $("ev-filter").value;
  const kind = $("ev-kind").value;
  const rows = events.filter((e) => (src === "all" || e.source === src) && (kind === "all" || e.kind === kind));
  $("ev-count").textContent = events.length;

  if (!rows.length) {
    $("feed").innerHTML = `<div class="empty">
      <div class="big">Nothing yet</div>
      <div>Ask the model to do something with a bot, or run a tool from the Console tab.</div>
    </div>`;
    return;
  }

  $("feed").innerHTML = rows
    .slice()
    .reverse()
    .map(
      (ev) => `
      <div class="ev ${ev.error ? "err" : ""}" data-id="${ev.id}">
        <div class="ev-head">
          <span class="src ${ev.source}">${ev.source}</span>
          <span class="kind">${ev.kind}</span>
          <span class="ev-name">${esc(ev.name)}</span>
          ${ev.duration_ms != null ? `<span class="ev-ms">${ev.duration_ms} ms</span>` : ""}
          <span class="ev-time">${fmtTime(ev.timestamp)}</span>
        </div>
        <div class="ev-preview">${esc(preview(ev))}</div>
        <div class="ev-detail">
          <div class="lbl">Arguments</div>
          <pre>${esc(JSON.stringify(ev.arguments ?? null, null, 2))}</pre>
          <div class="lbl">${ev.error ? "Error" : "Result"}</div>
          <pre>${esc(ev.error || JSON.stringify(ev.result ?? null, null, 2))}</pre>
        </div>
      </div>`,
    )
    .join("");

  $("feed")
    .querySelectorAll(".ev")
    .forEach((row) => row.addEventListener("click", () => row.classList.toggle("open")));
}

function startStream() {
  const source = new EventSource("/api/events/stream");
  source.onmessage = (msg) => {
    try {
      const ev = JSON.parse(msg.data);
      events.push(ev);
      if (events.length > 500) events = events.slice(-500);
      renderFeed();
      // Bot lifecycle changes are worth reflecting in the Bots tab immediately.
      if (ev.kind === "bot") refreshBots();
    } catch {
      /* ignore malformed frame */
    }
  };
  source.onerror = () => {
    // EventSource retries on its own; surface the state instead of reconnecting.
    $("server-dot").className = "dot down";
    $("server-label").textContent = "stream lost — retrying";
  };
}

$("ev-filter").addEventListener("change", renderFeed);
$("ev-kind").addEventListener("change", renderFeed);
$("ev-clear").addEventListener("click", async () => {
  await api("/api/events", { method: "DELETE" });
  events = [];
  renderFeed();
});

/* ------------------------------ console ----------------------------- */

let allTools = [];

/** Build one input from a JSON-schema property. */
function fieldFor(toolName, key, spec, required) {
  const id = `arg-${toolName}-${key}`;
  // Optional args are `anyOf: [{type: X}, {type: "null"}]`; unwrap to the real type.
  let type = spec.type;
  if (!type && Array.isArray(spec.anyOf)) {
    const real = spec.anyOf.find((s) => s.type && s.type !== "null");
    type = real?.type;
  }
  const hint = required ? "required" : spec.default !== undefined ? `default ${JSON.stringify(spec.default)}` : "optional";

  let input;
  if (type === "boolean") {
    input = `<div class="row-inline"><input type="checkbox" id="${id}" data-key="${esc(key)}" data-type="boolean" ${spec.default ? "checked" : ""} /></div>`;
  } else if (type === "number" || type === "integer") {
    input = `<input type="number" step="any" id="${id}" data-key="${esc(key)}" data-type="number" placeholder="${spec.default ?? ""}" />`;
  } else {
    input = `<input type="text" id="${id}" data-key="${esc(key)}" data-type="string" placeholder="${spec.default ?? ""}" autocomplete="off" />`;
  }
  return `<div class="field"><label for="${id}">${esc(key)} <span class="hint">· ${hint}</span></label>${input}</div>`;
}

function toolCard(tool) {
  const props = tool.schema?.properties || {};
  const required = tool.schema?.required || [];
  const fields = Object.entries(props)
    .map(([key, spec]) => fieldFor(tool.name, key, spec, required.includes(key)))
    .join("");
  return `
    <details class="tool" data-name="${esc(tool.name)}">
      <summary>
        <span class="tname">${esc(tool.name)}</span>
        <span class="tdesc">${esc(tool.description.split("\n")[0])}</span>
      </summary>
      <div class="tool-body">
        ${fields ? `<div class="tool-args">${fields}</div>` : '<p class="note">No arguments.</p>'}
        <div class="tool-run">
          <button class="btn primary small run-btn" data-name="${esc(tool.name)}">Run</button>
          <span class="muted" style="font-size:12px">runs as <span class="src human">human</span></span>
        </div>
        <div class="tool-out" id="out-${esc(tool.name)}"></div>
      </div>
    </details>`;
}

function renderTools() {
  const q = $("tool-search").value.trim().toLowerCase();
  const shown = allTools.filter((t) => !q || t.name.includes(q) || t.description.toLowerCase().includes(q));
  const groups = {};
  shown.forEach((t) => (groups[t.category] ||= []).push(t));

  $("tools").innerHTML = Object.keys(groups)
    .sort()
    .map(
      (cat) =>
        `<div class="tool-group"><h3>${esc(cat)} · ${groups[cat].length}</h3>${groups[cat].map(toolCard).join("")}</div>`,
    )
    .join("");

  $("tools")
    .querySelectorAll(".run-btn")
    .forEach((btn) => btn.addEventListener("click", () => runTool(btn)));
}

async function runTool(btn) {
  const name = btn.dataset.name;
  const body = btn.closest(".tool-body");
  const out = $("out-" + name);
  const args = {};

  body.querySelectorAll("[data-key]").forEach((input) => {
    const key = input.dataset.key;
    if (input.dataset.type === "boolean") {
      args[key] = input.checked;
    } else if (input.value.trim() !== "") {
      args[key] = input.dataset.type === "number" ? Number(input.value) : input.value;
    }
    // Blank optional fields are omitted so the tool's own default applies.
  });

  btn.disabled = true;
  btn.textContent = "Running…";
  out.className = "tool-out show";
  out.textContent = "…";
  try {
    const res = await api(`/api/tools/${encodeURIComponent(name)}/invoke`, {
      method: "POST",
      body: JSON.stringify(args),
    });
    out.className = "tool-out show";
    out.textContent = typeof res.result === "string" ? res.result : JSON.stringify(res.result, null, 2);
  } catch (e) {
    out.className = "tool-out show err";
    out.textContent = e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Run";
  }
}

$("tool-search").addEventListener("input", renderTools);

async function loadTools() {
  try {
    allTools = (await api("/api/tools")).tools || [];
    renderTools();
  } catch (e) {
    $("tools").innerHTML = `<div class="empty"><div class="big">Could not load tools</div><div>${esc(e.message)}</div></div>`;
  }
}

/* ------------------------------- boot ------------------------------- */

refreshBots();
loadTools();
renderFeed();
startStream();
// Bot changes arrive over SSE and refresh immediately; this is only a slow
// safety net for state the stream can't see (e.g. a bot dying mid-request).
setInterval(refreshBots, 15000);
