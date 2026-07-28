/* Lightweight i18n for the control UI.
 *
 * Policy: instructional / UI prose is Traditional Chinese; technical nouns and
 * identifiers stay English — tool names, category names, connection nouns
 * (Host / Port / Username / Password / Version / Height), the source tags
 * (model / human / system), pathfinder, HTTP, yaw, .env, etc. Those English
 * tokens are baked into the zh strings on purpose, so the two languages share
 * the same jargon.
 *
 * Strings live in T[key] = { en, zh }. `t(key, params)` picks the current
 * language and substitutes {name} tokens from params. Static markup is tagged
 * with data-i18n / data-i18n-ph / data-i18n-html and filled by applyStatic().
 */

// Wrapped in an IIFE so nothing here leaks to global scope; the only public
// surface is window.i18n (set below). Without this, top-level names like `t`
// collide with app.js's own `const t`, throwing a SyntaxError that aborts the
// whole page (stuck on "connecting…").
(() => {
const T = {
  /* ---- header ---- */
  "brand.tagline": {
    en: "You own the bots. Watch what the model does — or drive it yourself.",
    zh: "Bot 是你的。看著 model 怎麼操作 —— 或是自己來。",
  },
  "lang.switchTo": { en: "中", zh: "EN" }, // label shows the language you switch TO

  /* ---- server state ---- */
  "server.connecting": { en: "connecting…", zh: "連線中…" },
  "server.up": { en: "service up", zh: "服務正常" },
  "server.down": { en: "service down", zh: "服務中斷" },
  "server.streamLost": { en: "stream lost — retrying", zh: "連線中斷 —— 重試中" },

  /* ---- create bot card ---- */
  "create.title": { en: "Create a bot", zh: "建立 Bot" },
  "label.name": { en: "Name", zh: "名稱" },
  "hint.name": { en: "· required, unique", zh: "· 必填、不可重複" },
  "label.account": { en: "Account shorthand", zh: "帳號代稱" },
  "hint.account": { en: "· camp machines", zh: "· 營隊電腦用" },
  "btn.advOptions": { en: "Advanced connection options", zh: "進階連線設定" },
  "hint.host": { en: "· blank → .env", zh: "· 留空 → .env" },
  "hint.password": { en: "· online-mode servers", zh: "· online-mode 伺服器" },
  "hint.optional": { en: "· optional", zh: "· 選填" },
  "ph.fromEnv": { en: "from .env", zh: "來自 .env" },
  "ph.fromEnvSrv": { en: "from .env / SRV", zh: "來自 .env / SRV" },
  "label.waitSpawn": {
    en: "Wait for spawn before returning",
    zh: "回傳前等待 spawn 完成",
  },
  "btn.createBot": { en: "Create bot", zh: "建立 Bot" },
  "btn.creating": { en: "Creating…", zh: "建立中…" },

  /* ---- bots card ---- */
  "btn.refresh": { en: "↻ Refresh", zh: "↻ 重新整理" },
  "btn.removeClosed": { en: "Remove closed", zh: "移除已關閉" },
  "btn.removeNClosed": { en: "Remove {n} closed", zh: "移除 {n} 個已關閉" },
  "bots.empty.title": { en: "No bots yet", zh: "還沒有 bot" },
  "bots.empty.desc": {
    en: "Create one above. On camp machines use the account shorthand; for dev testing leave it blank and the values come from <code>.env</code>.",
    zh: "在上方建立一個。營隊電腦請填帳號代稱；開發測試時可留空，數值會來自 <code>.env</code>。",
  },

  /* ---- bot card ---- */
  "badge.closed": { en: "closed", zh: "已關閉" },
  "badge.online": { en: "online", zh: "已上線" },
  "badge.connecting": { en: "connecting", zh: "連線中" },
  "badge.active": { en: "active", zh: "使用中" },
  "bot.account": { en: "account: {name}", zh: "帳號：{name}" },
  "stat.position": { en: "position", zh: "position" },
  "stat.health": { en: "health", zh: "health" },
  "stat.food": { en: "food", zh: "food" },
  "stat.pathfinder": { en: "pathfinder", zh: "pathfinder" },
  "val.yes": { en: "yes", zh: "是" },
  "val.no": { en: "no", zh: "否" },
  "btn.setActive": { en: "Set active", zh: "設為使用中" },
  "btn.remove": { en: "Remove", zh: "移除" },
  "btn.close": { en: "Close", zh: "關閉" },

  /* ---- activity card ---- */
  "activity.title": { en: "Activity", zh: "活動記錄" },
  "btn.console": { en: "Console", zh: "Console" },
  "filter.allSources": { en: "All sources", zh: "所有來源" },
  "filter.modelOnly": { en: "Model only", zh: "只看 model" },
  "filter.humanOnly": { en: "Human only", zh: "只看 human" },
  "filter.systemOnly": { en: "System only", zh: "只看 system" },
  "filter.allKinds": { en: "All kinds", zh: "所有類型" },
  "filter.toolCalls": { en: "Tool calls", zh: "Tool 呼叫" },
  "filter.http": { en: "HTTP", zh: "HTTP" },
  "filter.botEvents": { en: "Bot events", zh: "Bot 事件" },
  "btn.clear": { en: "Clear", zh: "清除" },
  "seg.map": { en: "Map", zh: "地圖" },
  "seg.calls": { en: "Calls", zh: "呼叫" },
  "map.empty": {
    en: "A top-down map draws here as bots move — path trails, facing, and dig/place marks.",
    zh: "當 bot 移動時，這裡會畫出俯視地圖 —— 路徑軌跡、面向，以及 dig／place 標記。",
  },
  "legend.move": { en: "move", zh: "移動" },
  "legend.interact": { en: "interact", zh: "互動" },
  "legend.sense": { en: "sense", zh: "感測" },
  "legend.path": { en: "path", zh: "路徑" },
  "calls.empty": {
    en: "The model's calling path draws here in order — repeats collapse to ×N, and a loop is called out when it repeats.",
    zh: "model 的呼叫路徑會依序畫在這裡 —— 重複的會收合成 ×N，出現迴圈時也會標示出來。",
  },
  "note.activity": {
    en: "Every tool the model calls shows up here with its arguments and its return value. Click a row to expand it.",
    zh: "model 呼叫的每個 tool 都會連同參數與回傳值顯示在這裡。點一列即可展開。",
  },
  "feed.empty.title": { en: "Nothing yet", zh: "還沒有記錄" },
  "feed.empty.desc": {
    en: "Ask the model to do something with a bot, or run a tool from the Console tab.",
    zh: "請 model 用 bot 做點什麼，或從 Console 面板自己執行一個 tool。",
  },
  "lbl.arguments": { en: "Arguments", zh: "參數" },
  "lbl.result": { en: "Result", zh: "結果" },
  "lbl.error": { en: "Error", zh: "錯誤" },

  /* ---- stat strip ---- */
  "st.toolCalls": { en: "tool calls", zh: "tool 呼叫數" },
  "st.modelHuman": { en: "model / human", zh: "model / human" },
  "st.calls60": { en: "calls / last 60s", zh: "近 60 秒呼叫數" },
  "st.topTools": { en: "top tools", zh: "常用 tool" },

  /* ---- call path ---- */
  "loop.looping": { en: "Looping · {block} · {reps}×", zh: "迴圈中 · {block} · {reps}×" },
  "loop.repeating": { en: "Repeating · {name} · {count}×", zh: "重複中 · {name} · {count}×" },
  "cp.nCalls": { en: "{n} calls", zh: "{n} 次呼叫" },
  "cp.latest": { en: "latest", zh: "最新" },
  "cp.args": { en: "args", zh: "args" },
  "cp.result": { en: "result", zh: "result" },
  "cp.error": { en: "error", zh: "error" },

  /* ---- console drawer ---- */
  "drawer.title": { en: "Manual console", zh: "手動 Console" },
  "note.console": {
    en: 'These are the exact tools the model has. Run one yourself and it appears in Activity tagged <span class="src human">human</span>, right next to the model\'s own calls — watch it there while this stays open.',
    zh: '這些就是 model 擁有的那些 tool。自己執行一個，它會以 <span class="src human">human</span> 標記出現在活動記錄裡，就在 model 自己的呼叫旁邊 —— 保持開啟就能在那邊即時觀察。',
  },
  "ph.toolSearch": {
    en: "Filter tools… (e.g. move, dig, pathfinder)",
    zh: "篩選 tool…（例如 move、dig、pathfinder）",
  },
  "tool.noArgs": { en: "No arguments.", zh: "沒有參數。" },
  "btn.run": { en: "Run", zh: "執行" },
  "btn.running": { en: "Running…", zh: "執行中…" },
  "tool.runsAs": {
    en: 'runs as <span class="src human">human</span>',
    zh: '以 <span class="src human">human</span> 身分執行',
  },
  "hint.required": { en: "required", zh: "必填" },
  "hint.optionalField": { en: "optional", zh: "選填" },
  "hint.default": { en: "default {value}", zh: "預設 {value}" },
  "tools.loadError.title": { en: "Could not load tools", zh: "無法載入 tools" },

  /* ---- toasts ---- */
  "toast.nameRequired.title": { en: "Name required", zh: "需要名稱" },
  "toast.nameRequired.msg": { en: "Give the bot a unique name.", zh: "請給 bot 一個不重複的名稱。" },
  "toast.botCreated.title": { en: "Bot created", zh: "已建立 bot" },
  "toast.botCreated.msg": { en: "{name} is connected.", zh: "{name} 已連線。" },
  "toast.createFail": { en: "Could not create bot", zh: "無法建立 bot" },
  "toast.activateFail": { en: "Could not activate", zh: "無法設為使用中" },
  "toast.closeFail": { en: "Could not close", zh: "無法關閉" },
  "toast.removeFail": { en: "Could not remove", zh: "無法移除" },
  "toast.removed.title": { en: "Removed", zh: "已移除" },
  "toast.removed.msg": { en: "{n} closed bot(s) removed.", zh: "已移除 {n} 個已關閉的 bot。" },

  /* ---- summary lines (humanized tool calls) ---- */
  "dir.forward": { en: "forward", zh: "前" },
  "dir.backward": { en: "backward", zh: "後" },
  "dir.left": { en: "left", zh: "左" },
  "dir.right": { en: "right", zh: "右" },
  "sum.walk": { en: "walked {dir} {blocks}", zh: "向{dir}走 {blocks} 格" },
  "sum.jump": { en: "jumped", zh: "跳躍" },
  "sum.turn": { en: "turned {deg}°", zh: "轉向 {deg}°" },
  "sum.turnLeft": { en: "turned left 90°", zh: "左轉 90°" },
  "sum.turnRight": { en: "turned right 90°", zh: "右轉 90°" },
  "sum.setTurn": { en: "faced yaw {yaw}°", zh: "面向 yaw {yaw}°" },
  "sum.lookAt": { en: "looked at ({x}, {y}, {z})", zh: "看向 ({x}, {y}, {z})" },
  "sum.dig": { en: "dug the block in front", zh: "挖掉前方的方塊" },
  "sum.place": { en: "placed the held block", zh: "放置手上的方塊" },
  "sum.use": { en: "used the held item", zh: "使用手上的物品" },
  "sum.usePlayer": { en: "right-clicked {who}", zh: "對 {who} 按右鍵" },
  "sum.aPlayer": { en: "a player", zh: "某位玩家" },
  "sum.hold": { en: "equipped {name}", zh: "裝備 {name}" },
  "sum.unhold": { en: "put the held item away", zh: "收起手上的物品" },
  "sum.drop": { en: "dropped {item}{count}", zh: "丟出 {item}{count}" },
  "sum.dropHeld": { en: "dropped the held item", zh: "丟出手上的物品" },
  "sum.sneakOn": { en: "started sneaking", zh: "開始潛行" },
  "sum.sneakOff": { en: "stopped sneaking", zh: "停止潛行" },
  "sum.action": { en: 'action "{name}"{value}', zh: '動作「{name}」{value}' },
  "sum.chat": { en: "“{message}”", zh: "「{message}」" },
  "sum.setHeight": { en: "set size to {level}", zh: "設定體型為 {level}" },
  "sum.getPos": { en: "read position", zh: "讀取 position" },
  "sum.getOrientation": { en: "read facing", zh: "讀取面向" },
  "sum.getBlock": { en: "read block at ({x}, {y}, {z})", zh: "讀取 ({x}, {y}, {z}) 的方塊" },
  "sum.getBlockProperty": {
    en: "read {property} at ({x}, {y}, {z})",
    zh: "讀取 ({x}, {y}, {z}) 的 {property}",
  },
  "sum.findBlock": { en: "searched for {name}", zh: "搜尋 {name}" },
  "sum.findBlocks": { en: "searched for {name} (×{max})", zh: "搜尋 {name}（×{max}）" },
  "sum.lookBlock": { en: "read the block it's aiming at", zh: "讀取瞄準中的方塊" },
  "sum.getBlockInFront": { en: "read the block in front", zh: "讀取前方的方塊" },
  "sum.getHand": { en: "checked its hand", zh: "查看手上物品" },
  "sum.getHeight": { en: "read its size", zh: "讀取體型" },
  "sum.setActiveBot": { en: "made {name} active", zh: "將 {name} 設為使用中" },
  "sum.pathfindTo": { en: "pathfind to ({to})", zh: "尋路前往 ({to})" },
};

const LANG_KEY = "mineai_lang";
const SUPPORTED = ["zh", "en"];

function detectLang() {
  const saved = localStorage.getItem(LANG_KEY);
  if (SUPPORTED.includes(saved)) return saved;
  return "zh"; // camp default: Traditional Chinese
}

let lang = detectLang();
let onChangeCb = null;

/** Translate a key, substituting {token} placeholders from params. */
function t(key, params) {
  const entry = T[key];
  let s = entry ? entry[lang] ?? entry.en : key;
  if (params) {
    s = s.replace(/\{(\w+)\}/g, (m, name) =>
      name in params && params[name] != null ? String(params[name]) : "",
    );
  }
  return s;
}

/** Fill all statically-tagged markup for the current language. */
function applyStatic(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  root.querySelectorAll("[data-i18n-html]").forEach((el) => {
    el.innerHTML = t(el.getAttribute("data-i18n-html"));
  });
  root.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    el.placeholder = t(el.getAttribute("data-i18n-ph"));
  });
}

function updateChrome() {
  document.documentElement.lang = lang === "zh" ? "zh-Hant" : "en";
  const toggle = document.getElementById("lang-toggle");
  if (toggle) toggle.textContent = t("lang.switchTo");
}

function setLang(next) {
  if (!SUPPORTED.includes(next) || next === lang) return;
  lang = next;
  localStorage.setItem(LANG_KEY, lang);
  updateChrome();
  applyStatic();
  if (onChangeCb) onChangeCb();
}

function toggleLang() {
  setLang(lang === "zh" ? "en" : "zh");
}

/** Register a callback that re-renders dynamic content after a language change. */
function onLangChange(cb) {
  onChangeCb = cb;
}

window.i18n = {
  t,
  applyStatic,
  setLang,
  toggleLang,
  onLangChange,
  get lang() {
    return lang;
  },
};

// Apply once at load (scripts are at end of <body>, so the DOM is ready).
updateChrome();
applyStatic();
document.addEventListener("click", (e) => {
  if (e.target.closest("#lang-toggle")) window.i18n.toggleLang();
});
})();
