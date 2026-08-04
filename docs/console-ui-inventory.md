# MineAI Bot Control — UI 按鈕與欄位清單

來源: `static/index.html` + `static/app.js` + `control_api.py` + `tools/*.py`
目的: 提供給設計工具(Claude design / 其他)參考,重新設計這個 Web 控制台的 UI。

整個頁面分三大區塊:
1. **Dashboard**(建立機器人 + 機器人列表 + Activity 即時動態)
2. **Manual Console**(側滑抽屜,裡面是所有可手動呼叫的工具 = 本次重點)
3. 全域元件(語言切換、toast、hover popover)

---

## 1. 頁首(Header)

| 元件 | 類型 | 說明 |
|---|---|---|
| 語言切換 `#lang-toggle` | 按鈕 | 顯示「中」,點擊切換 中文/英文 |
| 伺服器狀態 `#server-dot` + `#server-label` | 狀態指示(非按鈕) | connecting… / up / down,用顏色 dot 表示 |

---

## 2. Dashboard — 「Create a bot」表單(側邊欄卡片)

| 欄位 | 類型 | 必填 | Placeholder / 預設值 |
|---|---|---|---|
| Name | text | ✅ 必填、唯一 | `builder` |
| Account shorthand | text | 選填 | `g_swim`(camp machines 用) |
| **▸ Advanced connection options** | 展開/收合按鈕 | — | 點擊展開下方進階欄位 |
| ├ Host | text | 選填 | 空白時取 `.env` |
| ├ Port | number | 選填 | 空白時取 `.env` / SRV |
| ├ Username | text | 選填 | 空白時取 `.env` |
| ├ Password | password | 選填(online-mode 伺服器用) | 空白時取 `.env` |
| ├ Version | text | 選填 | 空白時取 `.env` |
| ├ Height | number | 選填 | — |
| └ Wait for spawn before returning | checkbox | 選填 | 預設勾選 |
| **Create bot** | 送出按鈕(primary) | — | 送出時文字變 "Creating…" |

## 3. Dashboard — 「Bots」列表卡片

| 元件 | 類型 | 顯示條件 |
|---|---|---|
| Remove closed | 按鈕(ghost, small) | 只在有已關閉的 bot 時顯示,文字含數量 |
| ↻ Refresh | 按鈕(ghost, small) | 一直顯示 |
| 每張 bot 卡片內: | | |
| ├ Set active | 按鈕(small) | active 或 closed 時 disabled |
| └ Close(未關閉)/ Remove(已關閉) | 按鈕(small, danger) | 依 bot 狀態二選一顯示 |

每張 bot 卡片顯示的資訊(非按鈕,設計時可參考):狀態徽章(online/connecting/closed)、name、account/username、position、health、food、pathfinder 是否已載入、關閉/踢出原因。

## 4. Dashboard — 「Activity」卡片

| 元件 | 類型 | 選項 |
|---|---|---|
| Console | 按鈕(small) | 開啟 Manual Console 抽屜 |
| 來源篩選 `#ev-filter` | 下拉選單 | All sources / Model only / Human only / System only |
| 種類篩選 `#ev-kind` | 下拉選單 | All kinds / Tool calls / HTTP / Bot events |
| Clear | 按鈕(ghost, small) | 清空 activity log |
| Map / Calls | 分段按鈕(segmented, 2 選 1) | 切換視覺化面板:地圖視角 / 呼叫路徑視角 |

視覺化面板本身(canvas 地圖、呼叫路徑 chip 流)不是輸入欄位,而是唯讀顯示。

---

## 5. Manual Console(抽屜)— 本次整理重點

抽屜標題:**Manual console**。說明文字:這些就是模型能用的工具,自己手動跑一次也會出現在 Activity(標記 `human`)。

固定元件:

| 元件 | 類型 | 說明 |
|---|---|---|
| ✕ 關閉 `#console-close` | 按鈕 | 關閉抽屜 |
| 工具搜尋 `#tool-search` | text input | Placeholder:「Filter tools… (e.g. move, dig, pathfinder)」,即時過濾 name/description |

每個工具都渲染成一張可展開卡片(`<details>`):
- **Summary**:工具名稱 + 一行描述
- **參數欄位**(依 JSON Schema 自動產生,型別對應):
  - `boolean` → checkbox
  - `number` / `integer` → number input(placeholder 顯示預設值)
  - `string`(含可為 null 的選填) → text input
  - 每個欄位旁有 hint:必填 / 預設值 / 選填
- **Run** 按鈕(primary, small)— 呼叫工具,執行中文字變 "Running…"
- **輸出區塊** — 顯示結果或錯誤(唯讀)

工具依模組分類(category = 檔名),分類與工具總覽如下(共 47 個工具):

### movement(移動,10 個)
| 工具 | 參數(型別,必填/預設) |
|---|---|
| move_forward | blocks(number, 預設 1.0)、bot_name(text, 選填) |
| move_backward | blocks(number, 預設 1.0)、bot_name(text, 選填) |
| move_left | blocks(number, 預設 1.0)、bot_name(text, 選填) |
| move_right | blocks(number, 預設 1.0)、bot_name(text, 選填) |
| jump | bot_name(text, 選填) |
| turn | **degrees(number, 必填)**、bot_name(text, 選填) |
| turn_left | bot_name(text, 選填) |
| turn_right | bot_name(text, 選填) |
| set_turn | **yaw(number, 必填)**、bot_name(text, 選填) |
| look_at | **x, y, z(number, 必填 ×3)**、bot_name(text, 選填) |

### interaction(互動,11 個)
| 工具 | 參數(型別,必填/預設) |
|---|---|
| hold | **name(text, 必填)**、bot_name(text, 選填) |
| dig | bot_name(text, 選填) |
| place | bot_name(text, 選填) |
| unhold | bot_name(text, 選填) |
| drop | item(text, 選填)、count(number, 選填)、bot_name(text, 選填) |
| use | bot_name(text, 選填) |
| use_player | **username(text, 必填)**、bot_name(text, 選填) |
| sneak | **on(boolean, 必填)**、bot_name(text, 選填) |
| action | **name(text, 必填)**、value(number, 選填)、bot_name(text, 選填) |
| chat | **message(text, 必填)**、bot_name(text, 選填) |
| set_height | **level(number, 必填, 1–5)**、bot_name(text, 選填) |

### lifecycle(生命週期,4 個)
| 工具 | 參數(型別,必填/預設) |
|---|---|
| list_bots | 無參數 |
| check_bot_health | **bot_name(text, 必填)** |
| get_active_bot | 無參數 |
| set_active_bot | **bot_name(text, 必填)** |

### sensors(感測,唯讀,10 個)
| 工具 | 參數(型別,必填/預設) |
|---|---|
| get_pos | bot_name(text, 選填) |
| get_block | **x, y, z(number, 必填 ×3)**、bot_name(text, 選填) |
| look_block | bot_name(text, 選填) |
| find_block | **name(text, 必填)**、bot_name(text, 選填) |
| find_blocks | **name(text, 必填)**、max(number, 預設 16)、bot_name(text, 選填) |
| get_block_in_front | bot_name(text, 選填) |
| get_block_property | **x, y, z(number, 必填 ×3)**、**property_name(text, 必填)**、bot_name(text, 選填) |
| get_hand | bot_name(text, 選填) |
| get_height | bot_name(text, 選填) |
| get_orientation | bot_name(text, 選填) |

### pathfinder(路徑規劃,12 個)
| 工具 | 參數(型別,必填/預設) |
|---|---|
| load_pathfinder | bot_name(text, 選填) |
| pathfinder_status | bot_name(text, 選填) |
| pathfinder_stop | bot_name(text, 選填) |
| pathfinder_clear_goal | bot_name(text, 選填) |
| pathfinder_goto | **x, y, z(number, 必填 ×3)**、bot_name(text, 選填) |
| pathfinder_check_path | **x, y, z(number, 必填 ×3)**、timeout_ms(number, 預設 5000)、include_path(boolean, 預設 true)、bot_name(text, 選填) |
| pathfinder_set_goal_near | **x, y, z(number, 必填 ×3)**、radius(number, 預設 1.0)、dynamic(boolean, 預設 false)、bot_name(text, 選填) |
| pathfinder_set_goal_block | **x, y, z(number, 必填 ×3)**、dynamic(boolean, 預設 false)、bot_name(text, 選填) |

---

## 附註:通用互動模式(設計時可參考)

- `bot_name` 幾乎每個工具都有,選填,留空時使用「目前 active 的 bot」。
- 工具卡片是 `<details>` 折疊清單,依分類(movement / interaction / lifecycle / sensors / pathfinder)分組並顯示每組數量。
- 上方有即時搜尋框可用工具名稱或描述關鍵字過濾。
- Run 按鈕點下後 disable + 文字變 "Running…",完成後顯示結果或錯誤(紅色)在卡片下方。
- 目前是深色主題,按鈕樣式分:`btn primary`(主要動作,如 Create bot / Run)、`btn ghost`(次要動作,如 Refresh / Clear)、`btn small`、`btn danger`(Close / Remove)。
