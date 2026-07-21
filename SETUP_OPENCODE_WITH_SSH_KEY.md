# Setup: opencode + mineai-toolkit MCP (SSH-key edition)

This guide walks you **from zero** to a working setup where:

1. **opencode** (the desktop/terminal AI coding client) runs on your own machine.
2. The **LLM** runs on the lab server and is reached through an **SSH tunnel**
   (SSH key + port forwarding). You keep the tunnel open in one terminal.
3. The **mineai-toolkit MCP server** runs locally and gives the model tools to
   drive a Minecraft bot.

> This edition assumes **you already have the SSH key** for the account
> `llm_access@140.118.164.1`. If you don't, ask the camp staff for it first.

---

## 0. What you'll end up with

```
┌─────────────────────────────┐        SSH tunnel        ┌───────────────────────┐
│ Your machine (desktop)      │   local :2222  ───────▶  │ Lab server            │
│                             │                          │ 140.118.164.1         │
│  opencode  ──▶ localhost:2222│◀════════════════════════│ model @ 127.0.0.1:57413│
│      │                      │                          └───────────────────────┘
│      └──▶ mineai-toolkit MCP │
│              │              │
│              └──▶ Minecraft bot
└─────────────────────────────┘
```

- opencode talks to the model at `http://localhost:2222/v1`.
- The tunnel maps your local `2222` → the server's `127.0.0.1:57413`
  (where the model actually listens).
- The MCP server runs locally and exposes Minecraft tools to opencode.

---

## 1. Install the opencode **desktop app**

We use the **desktop (GUI) app**, not the terminal version. It's currently in
beta and available for macOS, Windows, and Linux.

**Download page:** <https://opencode.ai/download>

Pick the build for your machine:

| Platform | Download |
| --- | --- |
| macOS (Apple Silicon, M1–M4) | <https://opencode.ai/download/stable/darwin-aarch64-dmg> (`.dmg`) |
| macOS (Intel) | <https://opencode.ai/download/stable/darwin-x64-dmg> (`.dmg`) |
| Windows (x64) | <https://opencode.ai/download/stable/windows-x64-nsis> (`.exe` installer) |
| Linux (`.deb`) | <https://opencode.ai/download/stable/linux-x64-deb> |
| Linux (`.rpm`) | <https://opencode.ai/download/stable/linux-x64-rpm> |

Install it like a normal app:

- **macOS:** open the `.dmg`, drag **opencode** into `Applications`, then launch it.
  (Apple Silicon Macs use the *Apple Silicon* build; older Intel Macs use *Intel*.
  If unsure:  → About This Mac → check the chip.) You can also install via
  Homebrew: `brew install --cask opencode-desktop`.
- **Windows:** run the downloaded `.exe` installer and follow the prompts, then
  launch **opencode** from the Start menu.
- **Linux:** install the `.deb` (`sudo apt install ./opencode*.deb`) or `.rpm`
  (`sudo rpm -i opencode*.rpm`), then launch it from your app menu.

Open the app once to confirm it launches. We'll come back to it in Step 4 to add
the config.

---

## 2. Open the SSH tunnel to the model

The model listens on the **server's** `127.0.0.1:57413`, which is not reachable
from outside. The SSH tunnel forwards a local port to it so opencode can connect
as if the model were running on your own machine.

Open a **dedicated terminal** and run:

```bash
ssh -N -L 2222:127.0.0.1:57413 llm_access@140.118.164.1
```

What each flag means:

| Part                      | Meaning                                                             |
| ------------------------- | ------------------------------------------------------------------ |
| `-N`                      | Don't run a remote shell — just hold the tunnel open.              |
| `-L 2222:127.0.0.1:57413` | Forward **local** `2222` → the server's `127.0.0.1:57413` (model). |
| `llm_access@140.118.164.1`| The SSH account + server address.                                  |

**Keep this terminal open.** The tunnel only lives as long as this command runs.
There is no visible output with `-N` — a blinking cursor / no prompt returning
means it's connected and working.

### 2a. If it asks for a password instead of using your key

Your key isn't being offered. Point SSH at the key file explicitly:

```bash
ssh -i /path/to/your_private_key -N -L 2222:127.0.0.1:57413 llm_access@140.118.164.1
```

- macOS/Linux keys usually live in `~/.ssh/` (e.g. `~/.ssh/id_ed25519`).
- Windows keys usually live in `C:\Users\<you>\.ssh\`.

Make the permissions strict if SSH complains the key is "too open":

```bash
chmod 600 /path/to/your_private_key   # macOS / Linux
```

### 2b. (Optional) Save it as a named host

Add this to `~/.ssh/config` so you can reconnect with one short command:

```ssh-config
Host ntust-llm
    HostName 140.118.164.1
    User llm_access
    IdentityFile ~/.ssh/your_private_key
    LocalForward 2222 127.0.0.1:57413
    RequestTTY no
```

Then the tunnel is just:

```bash
ssh -N ntust-llm
```

### 2c. Verify the tunnel actually reaches the model

In **another** terminal (leave the tunnel running):

```bash
curl http://localhost:2222/v1/models
```

You should get a JSON list of models. If you get "connection refused", the
tunnel isn't up — recheck the terminal running the `ssh` command.

> **Note on the term "reverse":** the command above is technically SSH **local**
> port forwarding (`-L`) — it pulls the remote model down to your machine. It's
> the correct command for this setup; the "reverse/tunnel" naming just refers to
> reaching a service that would otherwise be unreachable.

---

## 3. Install & prepare the mineai-toolkit MCP server

The MCP server is this project. It's a Python (Poetry) project that exposes the
Minecraft bot tools and also opens a small bot-control web UI.

From the project root (`mineai_toolkit/`):

```bash
# 1. Install Poetry if you don't have it:  https://python-poetry.org/docs/#installation
#    (macOS/Linux)
curl -sSL https://install.python-poetry.org | python3 -

# 2. Install dependencies for this project
poetry install
```

Sanity-check that the server command exists:

```bash
poetry run mineai-mcp --help   # should start the MCP server (Ctrl+C to stop)
```

> On start, the server also opens the bot-control UI at
> <http://127.0.0.1:8765>. That's expected — that panel is for **you** to
> create/select/close bots. opencode/the model only drives the active bot.

You normally **don't** start `mineai-mcp` by hand — opencode launches it for you
(next step). Note the **absolute path** of this project root, you'll need it:

```bash
pwd   # copy this path
```

---

## 4. Configure opencode

opencode reads a config file named `opencode.json`. You can put it either:

- **Per project:** `opencode.json` in the folder you open with opencode, or
- **Global:** `~/.config/opencode/opencode.json` (applies everywhere).

A ready-to-edit template ships with this repo: [`opencode.jsonc`](opencode.jsonc).
Copy it and replace its placeholders.

**Global setup (recommended for the camp):**

```bash
mkdir -p ~/.config/opencode
cp opencode.jsonc ~/.config/opencode/opencode.json
```

Then open `~/.config/opencode/opencode.json` and edit it to look like this:

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
      "cwd": "/ABSOLUTE/PATH/TO/mineai_toolkit",
      "enabled": true,
      "environment": {
        "MINEAI_OPEN_UI": "1"
      }
    }
  }
}
```

What to change / know:

- **`baseURL`** — `http://localhost:2222/v1`. This is the **local** end of the
  SSH tunnel from step 2, **not** the server address. Leave it as `2222` unless
  you changed the local port in the `ssh -L` command.
- **`apiKey`** — a local llama.cpp-style server doesn't check it; `"dummy"` is
  fine (opencode still requires the field to be present).
- **`models`** — the key (`Qwen3.6-27B-UD-Q4_K_XL.gguf`) must match the model id
  the server reports at `curl http://localhost:2222/v1/models`. If the server
  lists a different id, change this key to match.
- **`cwd`** — replace with the **absolute path** you copied in step 3 (`pwd`).
  This is how opencode knows where to run `poetry run mineai-mcp`.
- **`command`** — `["poetry", "run", "mineai-mcp"]` works because `cwd` points at
  the Poetry project. If `poetry` isn't on opencode's `PATH`, use the absolute
  path to the venv script instead, e.g.
  `["/ABSOLUTE/PATH/TO/mineai_toolkit/.venv/bin/mineai-mcp"]`
  (find it with `poetry run which mineai-mcp`).

---

## 5. Prepare the Minecraft side (dev / internal test)

Steps 1–4 give the model its tools. This step gives it something to log into.

> **Camp day vs. dev test.** On camp machines, staff run
> `minethon/pc_setup/setup.sh` once, which writes `~/.htsdg.json` (just
> `{"group": 3, "computer": 24}`). Students then type only a **Name** and an
> **Account shorthand** like `g_swim` in the bot panel, and the username,
> password, host, and auth URLs are all derived for them.
>
> For **internal testing** you don't have that file and don't need it. You
> register a real account and put its credentials in a `.env` instead. That's
> what the rest of this section covers.

### 5a. Install HMCL (the Minecraft launcher)

You need an actual Minecraft client to join the server and *watch* the bot —
the MCP server only drives the bot, it doesn't render anything.

Use the camp's fork, which is preconfigured for our auth server:

**<https://github.com/Hack-the-SDGs/HMCL>**

Download the launcher from that repo's Releases, install it, and confirm you can
launch Minecraft and connect to `mc.ntust.camp:50213` as **yourself**. Do this
before touching the bot — if your own client can't get in, the bot won't either,
and you'll waste time debugging the wrong layer.

### 5b. Register the bot's account

The bot logs in as its **own account**, not yours. Two clients cannot share one
username — they'll kick each other in a loop.

Register at **<https://drash.ntust.camp/en/login>** and create an account for the
bot (e.g. `devbot01`). Note the username and password; that's all you need.

### 5c. Create your `.env`

The file lives **next to `main.py`** in this project. A template ships with the
repo — copy it and fill in the two credential lines:

```bash
cp .env.example .env
```

Where the values come from:

| Key | Where it comes from |
| --- | --- |
| `MC_USERNAME` | the account you registered in 5b |
| `MC_PASSWORD` | same |
| `MC_HOST` | `mc.ntust.camp` |
| `MC_PORT` | **`50213`** — not the default 25565 |
| `MC_AUTH` | `mojang` (Drasl speaks the legacy Yggdrasil protocol) |
| `MC_AUTH_SERVER` | `https://drasl.ntust.camp/auth` |
| `MC_SESSION_SERVER` | `https://drasl.ntust.camp/session` |
| `MC_VERSION` | `1.21.11` |

Two things to know:

- **No `set -a`, no `export`, no shell tricks.** The MCP server loads this file
  itself at startup ([`main.py`](main.py) pins it to `mineai_toolkit/.env` by
  absolute path, so it works no matter which folder opencode opened). You never
  source it by hand.
- **It's read once, at startup.** After editing `.env`, restart the MCP server —
  in practice, quit and reopen opencode.

> `.env` holds credentials. Keep it out of git; commit only `.env.example`.
> (`minethon/examples/demos/drasl_auth/.env.example` is the equivalent template
> for the standalone script path — same keys, except it's missing `MC_PORT`, so
> add that one yourself if you use it.)

### 5d. Create the bot

Open the panel at <http://127.0.0.1:8765> and fill in:

- **Name** — any unique local label (`test`, `devbot`). This is just a handle for
  `set_active_bot` / close; it is **not** the Minecraft username.
- **Account shorthand** — leave **blank** (that's the camp-day path).

Everything under **Advanced connection options** can stay blank: with no
shorthand, any field you leave empty falls back to the matching `MC_*` value
from `.env`. Fill one in only to override for a single bot — handy when you want
a second bot on a different account:

- **Username** / **Password** — override just the identity, keep the server
  settings from `.env`.

Click **Create bot**. The request blocks until the bot has spawned, then the card
appears with `connected: true` and a position. The password is stripped from all
API responses, so it won't leak back through `/bots`.

---

## 6. Run it

1. **Terminal A** — keep the tunnel open (from step 2):

   ```bash
   ssh -N -L 2222:127.0.0.1:57413 llm_access@140.118.164.1
   ```

2. **Launch the opencode desktop app**, then open the project folder in it
   (`/ABSOLUTE/PATH/TO/mineai_toolkit`) — use the app's "Open folder / project"
   option so it picks up the project and your config.

3. In opencode:
   - Select the model **NTUST LLM → Qwen3.6 27B UD-Q4_K_XL (remote)**
     (use the model picker in the app's UI).
   - opencode auto-launches the `mineai-toolkit` MCP server, which opens the bot
     panel at <http://127.0.0.1:8765>. Create/select a bot there (step 5d).
   - Ask the model to do something with the bot to confirm the tools are wired
     up (e.g. "list the bots" or "walk the active bot to 100 64 100").
   - Join the server yourself with HMCL to watch the bot move.

---

## 7. Troubleshooting

| Symptom | Likely cause & fix |
| --- | --- |
| opencode: connection refused / model errors | The SSH tunnel (Terminal A) isn't running. Restart the `ssh -N -L ...` command. |
| `curl http://localhost:2222/v1/models` fails | Same as above — tunnel down, or wrong local port. |
| SSH asks for a password | Key not offered — use `ssh -i /path/to/key ...` (step 2a). |
| SSH: "permissions are too open" for the key | `chmod 600 /path/to/your_private_key`. |
| opencode doesn't list the MCP tools | Check `cwd` in `opencode.json` is the real project path, and `poetry install` succeeded. Run `poetry run mineai-mcp` by hand to see errors. |
| `poetry: command not found` inside opencode | Use the absolute venv path in `command` (step 4, last bullet). |
| Model id mismatch | Make the `models` key match what `/v1/models` returns. |
| Bot panel didn't open | Set `MINEAI_OPEN_UI=1` (already in the template) or open <http://127.0.0.1:8765> manually. |
| Bot creation: 「找不到本機識別檔」 | You used an **Account shorthand** without `~/.htsdg.json`. For dev test, leave that field blank and use `.env` (step 5c). |
| Bot creation: 「找不到此任務」 | Wrong username/password, or the account doesn't exist. Re-check it at <https://drash.ntust.camp/en/login>. |
| Bot connects to `localhost` instead of the camp server | `.env` isn't being read — it must be `mineai_toolkit/.env`, and the MCP server must have been restarted since you created it. |
| Bot times out with no login error | Almost always `MC_PORT`. The camp server is on **50213**; the default is 25565. |
| `Server version '…' is not supported` | `MC_VERSION` must be ≤ `1.21.11` (the newest version mineflayer 4.37 supports). |
| Bot and your own client keep kicking each other | You're logged into both with the same account. Register a separate account for the bot (step 5b). |
| Panel shows no bots although you just made one | A second opencode window spawned a second MCP server; the UI belongs to whichever process grabbed port 8765 first. Keep one window, or start extras with `MINEAI_CONTROL_API=0`. |

---

## Reference links

- opencode docs: <https://opencode.ai/docs/>
- opencode providers (custom OpenAI-compatible): <https://opencode.ai/docs/providers/>
- opencode config: <https://opencode.ai/docs/config/>
- opencode MCP servers: <https://opencode.ai/docs/mcp-servers/>
- Poetry install: <https://python-poetry.org/docs/#installation>
- This repo's config template: [`opencode.jsonc`](opencode.jsonc)
- Credentials template: [`.env.example`](.env.example)
- Server / MCP tool reference: [`README.md`](README.md)
- HMCL launcher (camp fork): <https://github.com/Hack-the-SDGs/HMCL>
- Account registration (Drasl): <https://drash.ntust.camp/en/login>
