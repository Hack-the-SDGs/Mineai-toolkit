# Mineai-toolkit
MCP Server for interact with minecraft.

## Runtime shape

Starting the MCP server also starts the user-facing bot lifecycle control UI
and opens it in the default browser:

```bash
mineai-mcp
```

The control UI and its JSON API listen on:

```text
http://127.0.0.1:8765
```

The UI is for **the user** to create, select, inspect, and close bots. The
model only drives whichever bot is active — it cannot create or close bots.
Because the MCP server auto-opens the UI on start, students don't need any
extra step: launching the client (e.g. opencode) brings the panel up.

Keep the control server running but stop it from opening a browser tab:

```bash
MINEAI_OPEN_UI=0 mineai-mcp
```

Disable the control server (and UI) entirely:

```bash
MINEAI_CONTROL_API=0 mineai-mcp
```

Change the bind address with:

```bash
MINEAI_CONTROL_HOST=127.0.0.1 MINEAI_CONTROL_PORT=8765 mineai-mcp
```

If the port is already taken (e.g. a second client window on the same
machine), the MCP server logs a note and keeps running without a second UI
instead of crashing.

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

Close one bot:

```bash
curl -X DELETE http://127.0.0.1:8765/bots/builder
```

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
