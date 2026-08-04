/* Lightweight i18n for the control UI.
 *
 * Policy: instructional / UI prose is Traditional Chinese; technical nouns
 * stay English — category names, connection nouns (Host / Port / Username /
 * Password / Version / Height), the source tags (model / human / system),
 * pathfinder, HTTP, yaw, .env, etc. Those English tokens are baked into the
 * zh strings on purpose, so the two languages share the same jargon.
 *
 * Tool *names* are the one exception: in zh mode every place a tool name is
 * shown as a label (console cards/dock, activity feed, call path, top-tools
 * stat) is fully replaced by its Chinese label via TOOL_NAME / toolLabel().
 * The raw English name is kept wherever it's used as an identifier rather
 * than a label (data-name attributes, category/color lookups, filter args).
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

  /* ---- left panel tabs ---- */
  "tab.tool": { en: "Tools", zh: "工具 Tool" },
  "tab.model": { en: "Model History", zh: "模型紀錄" },

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
  "hint.advOptionsShort": { en: "Advanced", zh: "進階" },
  "label.presetNumber": { en: "No.", zh: "編號" },
  "btn.quickCreate": { en: "+ Create ", zh: "＋ 創建 " },

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
  "activity.title2": { en: "Activity Log", zh: "活動紀錄 Log" },
  "col.source": { en: "Source", zh: "來源" },
  "col.tool": { en: "Function", zh: "函式名" },
  "col.args": { en: "Arguments", zh: "參數" },
  "col.result": { en: "Result", zh: "結果" },
  "col.time": { en: "Time / duration", zh: "時間 / 耗時" },
  "src.model": { en: "MODEL", zh: "模型" },
  "src.human": { en: "HUMAN", zh: "人類" },
  "src.system": { en: "SYSTEM", zh: "系統" },
  "btn.console": { en: "Console", zh: "控制台" },
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
  "drawer.title": { en: "Manual console", zh: "手動控制台" },
  "ph.toolSearch": {
    en: "Filter tools… (e.g. move, dig, pathfinder)",
    zh: "篩選 tool…（例如 move、dig、pathfinder）",
  },
  "tool.noArgs": { en: "No arguments.", zh: "沒有參數。" },
  "btn.run": { en: "Run", zh: "執行" },
  "btn.running": { en: "Running…", zh: "執行中…" },
  "dock.asHuman": { en: "runs as HUMAN", zh: "以 HUMAN 身分執行" },
  "hint.required": { en: "required", zh: "必填" },
  "hint.optionalField": { en: "optional", zh: "選填" },
  "hint.default": { en: "default {value}", zh: "預設 {value}" },
  "tools.loadError.title": { en: "Could not load tools", zh: "無法載入 tools" },
  "tools.empty": { en: "No matching tools", zh: "找不到符合的工具" },
  "console.noActiveBot": { en: "no active bot", zh: "尚無使用中 bot" },
  "cat.movement": { en: "Movement", zh: "移動" },
  "cat.interaction": { en: "Interaction", zh: "互動" },
  "cat.lifecycle": { en: "Lifecycle", zh: "Bot 管理" },
  "cat.sensors": { en: "Sensors", zh: "感測" },
  "cat.pathfinder": { en: "Pathfinder", zh: "導航" },
  "cat.other": { en: "Other", zh: "其他" },

  /* ---- toasts ---- */
  "toast.nameRequired.title": { en: "Name required", zh: "需要名稱" },
  "toast.nameRequired.msg": { en: "Give the bot a unique name.", zh: "請給 bot 一個不重複的名稱。" },
  "toast.botCreated.title": { en: "Bot created", zh: "已建立 bot" },
  "toast.botCreated.msg": { en: "{name} is connected.", zh: "{name} 已連線。" },
  "toast.createFail": { en: "Could not create bot", zh: "無法建立 bot" },
  "toast.presetNumberRequired.title": { en: "No. required", zh: "需要編號" },
  "toast.presetNumberRequired.msg": {
    en: "Type a number in the \"No.\" field first.",
    zh: "請先在「編號」欄位輸入數字。",
  },
  "toast.createTimeout": {
    en: "Bot did not spawn in time — it may have been kicked before the stage started. Check the bot card for the reason.",
    zh: "bot 沒有及時進入世界——可能在關卡開始前就被踢出。請看 bot 卡片上的原因。",
  },
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

/* Traditional-Chinese overlay for the console tool list, keyed by tool name.
 * These are shown to the *student* on the web page only — the backend keeps
 * serving the English docstrings, which are what the *model* actually reads.
 * A tool with no entry here falls back to the English description from the API.
 * Identifiers stay English on purpose: yaw / pitch, block & item names, X/Z,
 * bot_name, pathfinder, the literal return strings ('coords, name', 'none', …). */
const TOOL_DESC = {
  // movement
  move_forward: "向前走 ``blocks`` 格；回傳新的 position。",
  move_backward: "向後走 ``blocks`` 格；回傳新的 position。",
  move_left: "向左平移 ``blocks`` 格；回傳新的 position。",
  move_right: "向右平移 ``blocks`` 格；回傳新的 position。",
  jump: "跳一次；回傳新的 position。",
  turn: "以目前面向為基準轉 ``degrees`` 度（正值 = 向左）。",
  turn_left: "向左轉 90 度；回傳新的 (yaw, pitch)。",
  turn_right: "向右轉 90 度；回傳新的 (yaw, pitch)。",
  set_turn: "面向絕對的 ``yaw``（度）；回傳新的 (yaw, pitch)。",
  look_at: "面向指定的世界座標；回傳新的 (yaw, pitch)。",
  // pathfinder
  load_pathfinder: "確保選定的 bot 已載入 mineflayer-pathfinder。",
  pathfinder_status: "回傳 pathfinder 的移動／挖掘／建造狀態。",
  pathfinder_stop: "取消目前的 pathfinder 任務並停止移動。",
  pathfinder_clear_goal: "清除目前的 pathfinder 目標。",
  pathfinder_goto: "沿真實路徑抵達 (x, y, z)：目標是空氣就站上去，是方塊就走到旁邊並面向它以便挖掘／使用／放置。無路徑則不移動並回報卡住位置。不使用半徑。",
  pathfinder_check_path: "只規劃路徑但不移動，回報目標是否可抵達（reachable、status、mode、path 等）；在 goto 前先用它驗證。",
  pathfinder_set_goal_near: "設定一個在 ``(x, y, z)`` 附近的背景 pathfinder 目標。",
  pathfinder_set_goal_block: "為某個精確方塊設定背景 pathfinder 目標。",
  // interaction
  hold: "從物品欄裝備名為 ``name`` 的物品；成功回傳 True。",
  dig: "挖掉瞄準的方塊；回傳 'coords, name' 或 'none'。",
  place: "把手上的方塊放到瞄準的面上；回傳 'coords, name' 或 'none'。",
  unhold: "把手上的物品放回物品欄；手是空的則回傳 False。",
  drop: "把物品丟到地上。",
  use: "使用／啟動手上的物品；成功回傳 True。",
  use_player: "對指定玩家的實體按右鍵（例如騎乘／堆疊）；成功回傳 True。",
  sneak: "按住（``on=True``）或放開（``on=False``）潛行；回傳新的狀態。",
  action: "請 quest server 執行某個具名動作（例如 'put out'）。",
  chat: "向伺服器發送一則聊天訊息。",
  set_height: "設定 bot 體型等級，1 到 5。",
  // sensors
  get_pos: "bot 目前的 (x, y, z) position。",
  get_block: "指定世界座標的方塊名稱，或 'none'。",
  look_block: "bot 目前看著的方塊，格式為 'coords, name'。",
  find_block: "最近的 ``name`` 方塊座標（例如 'oak_log'）。",
  find_blocks: "最多 ``max`` 個最近的 ``name`` 方塊，由近到遠；沒有則回傳 'empty'。",
  get_block_in_front: "前方一步的實心方塊，格式為 'coords, name'；若只有空氣則回傳 'none'。",
  get_block_property: "指定座標的方塊狀態屬性（例如 'lit'、'facing'、'powered'）。",
  get_hand: "目前手上拿的物品，格式為 'name, count'，或 'none'。",
  get_height: "bot 目前的體型等級，1 到 5。",
  get_orientation: "目前面向，格式為 'yaw, pitch'（度）（yaw 0 = 北／-Z）。",
  // lifecycle
  list_bots: "列出 bot 名稱與 health 快照。用這裡的名稱作為 bot_name。",
  check_bot_health: "查詢 list_bots 回傳的某個 bot 名稱的 health。",
  get_active_bot: "回傳當 action tool 省略 bot_name 時目前使用的 bot。",
  set_active_bot: "選擇 action tool 預設要使用哪個現有的 bot。",
};

/* Traditional-Chinese label for each tool *name*, shown in zh mode anywhere
 * a tool name is rendered as a label (console cards/dock, activity feed,
 * call path, top-tools stat). Unlike TOOL_DESC this fully replaces the
 * English name in the UI — the backend/model still only ever see the
 * English name, this is display-only. A tool with no entry here falls back
 * to its raw English name. */
const TOOL_NAME = {
  // movement
  move_forward: "向前走",
  move_backward: "向後走",
  move_left: "向左移動",
  move_right: "向右移動",
  jump: "跳躍",
  turn: "轉向",
  turn_left: "向左轉",
  turn_right: "向右轉",
  set_turn: "設定朝向",
  look_at: "看向座標",
  // pathfinder
  load_pathfinder: "載入導航",
  pathfinder_status: "導航狀態",
  pathfinder_stop: "停止導航",
  pathfinder_clear_goal: "清除導航目標",
  pathfinder_goto: "前往座標",
  pathfinder_check_path: "檢查路徑",
  pathfinder_set_goal_near: "設定背景目標（座標）",
  pathfinder_set_goal_block: "設定背景目標（方塊）",
  // interaction
  hold: "手持物品",
  dig: "挖掘",
  place: "放置方塊",
  unhold: "收起物品",
  drop: "丟棄物品",
  use: "使用物品",
  use_player: "對玩家使用",
  sneak: "潛行",
  action: "執行動作",
  put_out: "撲滅",
  chat: "發送訊息",
  set_height: "設定體型",
  // sensors
  get_pos: "取得座標",
  get_block: "取得方塊",
  look_block: "取得瞄準方塊",
  find_block: "搜尋方塊",
  find_blocks: "搜尋多個方塊",
  get_block_in_front: "取得前方方塊",
  get_block_property: "取得方塊屬性",
  get_hand: "取得手持物品",
  get_height: "取得體型",
  get_orientation: "取得朝向",
  // lifecycle
  list_bots: "列出 bot",
  check_bot_health: "查詢 bot 生命值",
  get_active_bot: "取得使用中 bot",
  set_active_bot: "設定使用中 bot",
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
  root.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.title = t(el.getAttribute("data-i18n-title"));
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

/** Console tool description: zh overlay when available, else the English one
 *  the backend served (which is also what the model reads). */
function toolDesc(name, fallbackEn) {
  if (lang === "zh" && TOOL_DESC[name]) return TOOL_DESC[name];
  return fallbackEn;
}

/** Display label for a tool name: zh label when available and in zh mode,
 *  else the raw (English) tool name — never touches the identifier itself,
 *  only what's rendered on screen. */
function toolLabel(name) {
  if (lang === "zh" && TOOL_NAME[name]) return TOOL_NAME[name];
  return name;
}

window.i18n = {
  t,
  applyStatic,
  setLang,
  toggleLang,
  onLangChange,
  toolDesc,
  toolLabel,
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
