# 安裝設定：opencode + mineai-toolkit MCP（SSH 金鑰版）

本文件會帶你**從零開始**，設定好以下這套環境：

1. **opencode**（桌面／終端機版的 AI coding 客戶端）跑在你自己的電腦上。
2. **LLM 模型**跑在實驗室伺服器上，透過 **SSH 通道**（SSH 金鑰 + port 轉發）連線。
   你需要開一個終端機視窗把通道一直掛著。
3. **mineai-toolkit MCP 伺服器**跑在本機，提供模型操控 Minecraft 機器人的工具。

> 本版本假設你**已經拿到** `llm_access@140.118.164.1` 這個帳號的 SSH 金鑰。
> 如果還沒有，請先向營隊工作人員索取。

---

## 0. 最終會長這樣

```
┌─────────────────────────────┐        SSH 通道          ┌───────────────────────┐
│ 你的電腦（桌面）            │   本機 :2222  ───────▶   │ 實驗室伺服器          │
│                             │                          │ 140.118.164.1         │
│  opencode  ──▶ localhost:2222│◀════════════════════════│ 模型 @ 127.0.0.1:57413 │
│      │                      │                          └───────────────────────┘
│      └──▶ mineai-toolkit MCP │
│              │              │
│              └──▶ Minecraft 機器人
└─────────────────────────────┘
```

- opencode 透過 `http://localhost:2222/v1` 跟模型溝通。
- 通道把你本機的 `2222` 對應到伺服器的 `127.0.0.1:57413`（模型實際監聽的位置）。
- MCP 伺服器跑在本機，把 Minecraft 工具提供給 opencode。

---

## 1. 安裝 opencode **桌面版 App**

我們使用**桌面版（圖形介面 GUI）App**，不是終端機版。目前為 beta 版，支援
macOS、Windows、Linux。

**下載頁面：** <https://opencode.ai/download>

挑選符合你電腦的版本：

| 平台 | 下載 |
| --- | --- |
| macOS（Apple Silicon，M1–M4） | <https://opencode.ai/download/stable/darwin-aarch64-dmg>（`.dmg`） |
| macOS（Intel） | <https://opencode.ai/download/stable/darwin-x64-dmg>（`.dmg`） |
| Windows（x64） | <https://opencode.ai/download/stable/windows-x64-nsis>（`.exe` 安裝檔） |
| Linux（`.deb`） | <https://opencode.ai/download/stable/linux-x64-deb> |
| Linux（`.rpm`） | <https://opencode.ai/download/stable/linux-x64-rpm> |

像安裝一般 App 那樣安裝：

- **macOS：** 打開 `.dmg`，把 **opencode** 拖進 `Applications`，然後啟動它。
  （Apple Silicon 的 Mac 用 *Apple Silicon* 版；較舊的 Intel Mac 用 *Intel* 版。
  不確定的話：  → 關於這台 Mac → 看晶片型號。）也可以用 Homebrew 安裝：
  `brew install --cask opencode-desktop`。
- **Windows：** 執行下載的 `.exe` 安裝檔，照著提示安裝，然後從開始功能表啟動
  **opencode**。
- **Linux：** 安裝 `.deb`（`sudo apt install ./opencode*.deb`）或 `.rpm`
  （`sudo rpm -i opencode*.rpm`），然後從應用程式選單啟動。

先打開 App 一次，確認能正常啟動。第 4 步會再回到它加入設定。

---

## 2. 開啟連到模型的 SSH 通道

模型監聽在**伺服器的** `127.0.0.1:57413`，從外部是連不到的。SSH 通道會把一個本機
port 轉發過去，讓 opencode 可以像模型跑在自己電腦上一樣連線。

開一個**專用的終端機視窗**，執行：

```bash
ssh -N -L 2222:127.0.0.1:57413 llm_access@140.118.164.1
```

各參數的意思：

| 部分                      | 意義                                                        |
| ------------------------- | ----------------------------------------------------------- |
| `-N`                      | 不開遠端 shell，只單純把通道掛著。                          |
| `-L 2222:127.0.0.1:57413` | 把**本機** `2222` 轉發到伺服器的 `127.0.0.1:57413`（模型）。 |
| `llm_access@140.118.164.1`| SSH 帳號 + 伺服器位址。                                     |

**這個終端機要一直開著。** 通道只在這個指令持續執行時才存在。
使用 `-N` 時不會有任何輸出——游標一直閃、提示字元沒有跳回來，就代表連線成功、正常運作中。

### 2a. 如果它要你輸入密碼（而不是用金鑰）

代表你的金鑰沒有被送出。明確指定金鑰檔給 SSH：

```bash
ssh -i /path/to/your_private_key -N -L 2222:127.0.0.1:57413 llm_access@140.118.164.1
```

- macOS/Linux 的金鑰通常放在 `~/.ssh/`（例如 `~/.ssh/id_ed25519`）。
- Windows 的金鑰通常放在 `C:\Users\<你>\.ssh\`。

如果 SSH 抱怨金鑰權限「太開放」，把權限收緊：

```bash
chmod 600 /path/to/your_private_key   # macOS / Linux
```

### 2b.（選用）存成命名主機

把下面內容加進 `~/.ssh/config`，之後就能用一行短指令重連：

```ssh-config
Host ntust-llm
    HostName 140.118.164.1
    User llm_access
    IdentityFile ~/.ssh/your_private_key
    LocalForward 2222 127.0.0.1:57413
    RequestTTY no
```

之後開通道就只要：

```bash
ssh -N ntust-llm
```

### 2c. 驗證通道真的通到模型

在**另一個**終端機（讓通道那個視窗繼續掛著）：

```bash
curl http://localhost:2222/v1/models
```

你應該會拿到一串 JSON 的模型清單。如果出現「connection refused」，代表通道沒開起來
——回去檢查跑 `ssh` 那個視窗。

> **關於「reverse（反向）」這個說法：** 上面的指令嚴格來說是 SSH 的**本地（local）**
> port 轉發（`-L`）——它把遠端的模型「拉」到你的電腦上。這對本設定來說是正確的指令；
> 所謂「反向／通道」只是指去連一個原本連不到的服務而已。

---

## 3. 安裝並準備 mineai-toolkit MCP 伺服器

MCP 伺服器就是本專案。它是一個 Python（Poetry）專案，提供 Minecraft 機器人工具，
同時會開啟一個小型的機器人控制網頁介面。

在專案根目錄（`mineai_toolkit/`）下：

```bash
# 1. 如果還沒裝 Poetry：  https://python-poetry.org/docs/#installation
#    （macOS/Linux）
curl -sSL https://install.python-poetry.org | python3 -

# 2. 安裝本專案的相依套件
poetry install
```

確認伺服器指令存在：

```bash
poetry run mineai-mcp --help   # 應該會啟動 MCP 伺服器（按 Ctrl+C 結束）
```

> 啟動時，伺服器也會開啟機器人控制介面：<http://127.0.0.1:8765>。這是正常的——
> 那個面板是給**你**用來建立／選擇／關閉機器人的。opencode／模型只能操控目前
> 選定的那隻機器人（active bot）。

一般情況下你**不需要**自己手動啟動 `mineai-mcp`——opencode 會幫你啟動（見下一步）。
先記下這個專案根目錄的**絕對路徑**，等一下會用到：

```bash
pwd   # 把這個路徑複製起來
```

---

## 4. 設定 opencode

opencode 會讀取一個叫 `opencode.json` 的設定檔。你可以把它放在：

- **專案層級：** 你用 opencode 開啟的那個資料夾裡的 `opencode.json`，或
- **全域：** `~/.config/opencode/opencode.json`（到處都適用）。

本 repo 附了一份可直接改的範本：[`opencode.jsonc`](opencode.jsonc)。
複製它，然後填入要替換的地方即可。

**全域設定（營隊建議這樣做）：**

```bash
mkdir -p ~/.config/opencode
cp opencode.jsonc ~/.config/opencode/opencode.json
```

接著打開 `~/.config/opencode/opencode.json`，改成像這樣：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ntust-llm": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "NTUST LLM (via SSH tunnel)",
      "options": {
        "baseURL": "http://localhost:2222/v1",
        "apiKey": "dummy"
      },
      "models": {
        "Qwen3.6-27B-UD-Q4_K_XL.gguf": {
          "name": "Qwen3.6 27B UD-Q4_K_XL (remote)",
          "limit": { "context": 130816, "output": 16384 }
        }
      }
    }
  },
  "mcp": {
    "mineai-toolkit": {
      "type": "local",
      "command": ["poetry", "run", "mineai-mcp"],
      "cwd": "/你的/mineai_toolkit/絕對路徑",
      "enabled": true,
      "environment": {
        "MINEAI_OPEN_UI": "1"
      }
    }
  }
}
```

要改的地方／要知道的重點：

- **`baseURL`** — `http://localhost:2222/v1`。這是第 2 步 SSH 通道的**本機端**，
  **不是**伺服器位址。除非你改了 `ssh -L` 裡的本機 port，否則就維持 `2222`。
- **`apiKey`** — 本地 llama.cpp 這類伺服器不會檢查它，填 `"dummy"` 即可
  （但 opencode 仍要求這個欄位存在）。
- **`models`** — 這個 key（`Qwen3.6-27B-UD-Q4_K_XL.gguf`）必須跟伺服器在
  `curl http://localhost:2222/v1/models` 回報的模型 id 一致。若伺服器列出的
  是別的 id，就把這個 key 改成一致。
- **`cwd`** — 換成你在第 3 步用 `pwd` 複製的**絕對路徑**。opencode 就是靠它
  才知道要在哪裡執行 `poetry run mineai-mcp`。
- **`command`** — `["poetry", "run", "mineai-mcp"]` 之所以行得通，是因為 `cwd`
  指向這個 Poetry 專案。如果 `poetry` 不在 opencode 的 `PATH` 裡，改成用 venv
  腳本的絕對路徑，例如
  `["/你的/mineai_toolkit/絕對路徑/.venv/bin/mineai-mcp"]`
  （用 `poetry run which mineai-mcp` 找出來）。

---

## 5. 準備 Minecraft 端（開發／內部測試）

第 1～4 步讓模型拿到工具，這一步則是讓它有東西可以登入。

> **營隊當天 vs. 開發測試。** 營隊電腦由工作人員跑一次
> `minethon/pc_setup/setup.sh`，它會寫出 `~/.htsdg.json`（內容就只有
> `{"group": 3, "computer": 24}`）。學員之後在機器人面板只要填 **Name** 和
> **Account shorthand**（例如 `g_swim`），帳號、密碼、主機、認證網址就會自動推導出來。
>
> **內部測試**沒有那個檔案，也不需要它。你改成註冊一個真實帳號，把帳密放進
> `.env`。以下就是在講這條路。

### 5a. 安裝 HMCL（Minecraft 啟動器）

你需要一個真正的 Minecraft 客戶端才能進伺服器**看**機器人——MCP 伺服器只負責
操控機器人，它不會畫出任何畫面。

請用營隊的 fork 版本，已經幫你設定好我們的認證伺服器：

**<https://github.com/Hack-the-SDGs/HMCL>**

到該 repo 的 Releases 下載啟動器、安裝，並確認你能用**自己的帳號**啟動 Minecraft
並連上 `mc.ntust.camp:50213`。請先做完這件事再去弄機器人——如果你自己的客戶端都
進不去，機器人一定也進不去，先確認可以省下找錯層級的時間。

### 5b. 註冊機器人的帳號

機器人是用**它自己的帳號**登入，不是你的。同一個帳號不能同時兩個客戶端登入，
會互相把對方踢掉、無限循環。

到 **<https://drash.ntust.camp/en/login>** 註冊一個給機器人用的帳號
（例如 `devbot01`）。記下帳號與密碼，需要的就只有這兩個。

### 5c. 建立你的 `.env`

這個檔案要放在**跟 `main.py` 同一層**。repo 附了範本，複製後填入兩行帳密即可：

```bash
cp .env.example .env
```

各欄位的來源：

| 欄位 | 從哪裡來 |
| --- | --- |
| `MC_USERNAME` | 5b 註冊的帳號 |
| `MC_PASSWORD` | 同上 |
| `MC_HOST` | `mc.ntust.camp` |
| `MC_PORT` | **`50213`** — 不是預設的 25565 |
| `MC_AUTH` | `mojang`（Drasl 走的是舊版 Yggdrasil 協定） |
| `MC_AUTH_SERVER` | `https://drasl.ntust.camp/auth` |
| `MC_SESSION_SERVER` | `https://drasl.ntust.camp/session` |
| `MC_VERSION` | `1.21.11` |

兩個重點：

- **不需要 `set -a`、不需要 `export`、不需要任何 shell 技巧。** MCP 伺服器啟動時
  會自己讀這個檔（[`main.py`](main.py) 用絕對路徑鎖定 `mineai_toolkit/.env`，
  所以不管 opencode 開的是哪個資料夾都讀得到）。你不用手動 source 它。
- **它只在啟動時讀一次。** 改完 `.env` 之後要重啟 MCP 伺服器——實務上就是關掉
  opencode 再開一次。

> `.env` 裡有帳密，請不要 commit 進 git，只 commit `.env.example`。
> （`minethon/examples/demos/drasl_auth/.env.example` 是獨立腳本那條路的對應範本，
> 欄位一樣，但它少了 `MC_PORT`，用那條路要自己補上。）

### 5d. 建立機器人

打開面板 <http://127.0.0.1:8765>，填入：

- **Name** — 任何不重複的本機標籤（`test`、`devbot`）。這只是給
  `set_active_bot`／關閉用的代號，**不是** Minecraft 使用者名稱。
- **Account shorthand** — **留空**（那是營隊當天用的）。

**Advanced connection options** 底下全部可以留空：只要沒填 shorthand，任何空欄位
都會自動用 `.env` 裡對應的 `MC_*` 值。只有想針對單一機器人覆蓋時才填——例如想再
開第二隻用不同帳號的機器人：

- **Username** / **Password** — 只覆蓋身分，伺服器設定仍沿用 `.env`。

按 **Create bot**。這個請求會等到機器人 spawn 完才回應，接著卡片會顯示
`connected: true` 和座標。密碼在所有 API 回應中都會被移除，不會從 `/bots` 洩漏出去。

---

## 6. 開始執行

1. **終端機 A** — 保持通道開著（第 2 步的指令）：

   ```bash
   ssh -N -L 2222:127.0.0.1:57413 llm_access@140.118.164.1
   ```

2. **啟動 opencode 桌面版 App**，然後在裡面開啟專案資料夾
   （`/你的/mineai_toolkit/絕對路徑`）——用 App 的「開啟資料夾／專案」功能，
   讓它讀到專案和你的設定。

3. 在 opencode 裡：
   - 選擇模型 **NTUST LLM → Qwen3.6 27B UD-Q4_K_XL (remote)**
     （用 App 介面上的模型選擇器）。
   - opencode 會自動啟動 `mineai-toolkit` MCP 伺服器，並開啟機器人面板
     <http://127.0.0.1:8765>。在那裡建立／選擇一隻機器人（第 5d 步）。
   - 請模型對機器人做點事來確認工具接好了（例如「列出所有機器人」或
     「讓目前的機器人走到 100 64 100」）。
   - 用 HMCL 自己進伺服器，就能親眼看到機器人在動。

---

## 7. 疑難排解

| 症狀 | 可能原因與解法 |
| --- | --- |
| opencode：connection refused／模型錯誤 | SSH 通道（終端機 A）沒在跑。重新執行 `ssh -N -L ...`。 |
| `curl http://localhost:2222/v1/models` 失敗 | 同上——通道斷了，或本機 port 填錯。 |
| SSH 要求輸入密碼 | 金鑰沒被送出——用 `ssh -i /path/to/key ...`（第 2a 步）。 |
| SSH 說金鑰「permissions are too open」 | `chmod 600 /path/to/your_private_key`。 |
| opencode 沒列出 MCP 工具 | 檢查 `opencode.json` 的 `cwd` 是真正的專案路徑，且 `poetry install` 有成功。手動跑 `poetry run mineai-mcp` 看錯誤訊息。 |
| opencode 裡出現 `poetry: command not found` | 在 `command` 用 venv 的絕對路徑（第 4 步最後一點）。 |
| 模型 id 不一致 | 讓 `models` 的 key 跟 `/v1/models` 回報的一致。 |
| 機器人面板沒開 | 設定 `MINEAI_OPEN_UI=1`（範本裡已經有）或手動開 <http://127.0.0.1:8765>。 |
| 建立機器人時出現「找不到本機識別檔」 | 你填了 **Account shorthand** 但沒有 `~/.htsdg.json`。開發測試請把該欄留空，改用 `.env`（第 5c 步）。 |
| 建立機器人時出現「找不到此任務」 | 帳號或密碼錯誤，或帳號不存在。到 <https://drash.ntust.camp/en/login> 重新確認。 |
| 機器人連到 `localhost` 而不是營隊伺服器 | `.env` 沒被讀到——它必須放在 `mineai_toolkit/.env`，而且建立後要重啟過 MCP 伺服器。 |
| 機器人一直逾時但沒有登入錯誤 | 幾乎都是 `MC_PORT`。營隊伺服器在 **50213**，預設值是 25565。 |
| `Server version '…' is not supported` | `MC_VERSION` 必須 ≤ `1.21.11`（mineflayer 4.37 支援的最新版本）。 |
| 機器人跟你自己的客戶端互踢 | 兩邊用同一個帳號登入。請幫機器人另外註冊一個帳號（第 5b 步）。 |
| 剛建立的機器人在面板上看不到 | 開了第二個 opencode 視窗、啟動了第二個 MCP 伺服器；面板屬於先搶到 8765 埠的那個行程。只留一個視窗，或其他視窗用 `MINEAI_CONTROL_API=0` 啟動。 |

---

## 參考連結

- opencode 文件：<https://opencode.ai/docs/>
- opencode providers（自訂 OpenAI 相容）：<https://opencode.ai/docs/providers/>
- opencode 設定：<https://opencode.ai/docs/config/>
- opencode MCP 伺服器：<https://opencode.ai/docs/mcp-servers/>
- Poetry 安裝：<https://python-poetry.org/docs/#installation>
- 本 repo 的設定範本：[`opencode.jsonc`](opencode.jsonc)
- 帳密範本：[`.env.example`](.env.example)
- 伺服器／MCP 工具參考：[`README.md`](README.md)
- HMCL 啟動器（營隊 fork）：<https://github.com/Hack-the-SDGs/HMCL>
- 帳號註冊（Drasl）：<https://drash.ntust.camp/en/login>
