# Mineai-toolkit
MCP Server for interact with minecraft.

## Runtime shape

One process serves everything. Start it yourself:

```bash
mineai-control
```

On `http://127.0.0.1:8765` it exposes:

| Path | What |
| --- | --- |
| `/` | web UI — Bots, Activity, Console |
| `/mcp` | MCP endpoint (HTTP transport) |
| `/health`, `/bots`, `/api/*` | JSON API |

opencode connects as a **remote** MCP client and launches nothing:

```json
"mineai-toolkit": { "type": "remote", "url": "http://127.0.0.1:8765/mcp" }
```

### Why one process

Bots live in a module-global `BotManager`. The previous stdio design let each
opencode window spawn its own server, so a bot created in the web UI was
invisible to the model — it was talking to a different process with an empty bot
list. Tool execution also cannot be split out: `tools/pathfinder.py` manipulates
live JSPyBridge proxy objects that don't cross process boundaries.

Starting a second instance therefore fails fast instead of re-creating the split:

```text
[mineai] 127.0.0.1:8765 is already in use.
```

`mineai-mcp` (the old stdio entry point) now exits with a pointer to this
command.

### Environment

```bash
MINEAI_OPEN_UI=0 mineai-control                       # don't open a browser tab
MINEAI_CONTROL_HOST=127.0.0.1 MINEAI_CONTROL_PORT=8765 mineai-control
```

Bot connection defaults come from `mineai_toolkit/.env` (see `.env.example`),
read once at startup. They apply only when creating a bot **without** an account
shorthand; explicit arguments always win.

## Watching the model work

The **Activity** tab is a live feed of every tool call — source (`model` /
`human`), name, duration, and on click the full arguments and return value. Bot
lifecycle events (spawn, kick, disconnect) appear alongside, so a failed login
shows its reason rather than silently doing nothing.

The **Console** tab renders a form per tool from its JSON schema and runs it via
the same FastMCP instance the model uses, tagged `human`. Same execution path,
same middleware, same timeline — so a student's manual call and the model's call
are directly comparable.

Secrets are redacted from the log, and the ring buffer holds the last 500 events.

## Control API

Health:

```bash
curl http://127.0.0.1:8765/health
```

List bots:

```bash
curl http://127.0.0.1:8765/bots
```

Create a bot with explicit mineflayer/minethon options:

```bash
curl -X POST http://127.0.0.1:8765/bots \
  -H 'content-type: application/json' \
  -d '{"name":"builder","host":"localhost","port":25565,"username":"builder"}'
```

Create a bot with minethon's event shorthand:

```bash
curl -X POST http://127.0.0.1:8765/bots \
  -H 'content-type: application/json' \
  -d '{"name":"swimmer","account":"g_swim"}'
```

Select the active bot:

```bash
curl -X POST http://127.0.0.1:8765/active_bot \
  -H 'content-type: application/json' \
  -d '{"name":"builder"}'
```

Check one bot:

```bash
curl http://127.0.0.1:8765/bots/builder/health
```

Close one bot. It stays in the list, marked `closed`, so you can still read why
it ended (`end_reason` / `kicked_reason`):

```bash
curl -X DELETE http://127.0.0.1:8765/bots/builder
```

Remove it from the list for good (closes it first if still connected):

```bash
curl -X DELETE http://127.0.0.1:8765/bots/builder/record
```

Remove every closed bot at once:

```bash
curl -X DELETE http://127.0.0.1:8765/bots/closed
```

In the web UI these are the **Close** and **Remove** buttons — a live bot offers
Close, a closed one offers Remove — plus a **Remove N closed** button in the
Bots header that appears only when there are closed bots. A removed name is free
to reuse immediately.

## MCP tools

Lifecycle inspection tools:

- `list_bots`
- `check_bot_health(bot_name)`
- `get_active_bot`
- `set_active_bot(bot_name)`

Pathfinder tools:

- `load_pathfinder(bot_name?)`
- `pathfinder_status(bot_name?)`
- `pathfinder_stop(bot_name?)`
- `pathfinder_clear_goal(bot_name?)`
- `pathfinder_goto_near(x, y, z, radius?, bot_name?)`
- `pathfinder_goto_block(x, y, z, bot_name?)`
- `pathfinder_goto_get_to_block(x, y, z, bot_name?)`
- `pathfinder_goto_xz(x, z, bot_name?)`
- `pathfinder_goto_near_xz(x, z, radius?, bot_name?)`
- `pathfinder_goto_y(y, bot_name?)`
- `pathfinder_set_goal_near(x, y, z, radius?, dynamic?, bot_name?)`
- `pathfinder_set_goal_block(x, y, z, dynamic?, bot_name?)`

Minecraft action tools accept an optional `bot_name`. If omitted, they use the
active bot selected by the UI/control API or by `set_active_bot`.
