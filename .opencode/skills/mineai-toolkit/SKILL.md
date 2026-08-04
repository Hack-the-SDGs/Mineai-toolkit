---
name: mineai-toolkit
description: Use when controlling a Minecraft bot through the mine-ai-toolkit MCP server — moving, turning, digging, placing, using items, pathfinding to coordinates, or reading the world (position, blocks, held item). Covers how to drive the tools reliably: sense before acting, verify after, check a route is reachable before walking it, recover when a path is blocked, and pick a reachable target instead of retrying an unreachable one.
---

# mineai-toolkit

## Overview

mineai-toolkit is an MCP server that controls a live Minecraft bot. The tools are
**low-level verbs** — one action each (`move_forward`, `turn`, `dig`, `place`,
`find_block`, `goto`, …). They do exactly what they say and
nothing more: `dig` breaks the block you are *already aiming at*, it does not
walk to a block and dig it for you.

Because the tools are atomic, **you** supply the judgement. The whole skill comes
down to one habit:

> **Sense → Act → Verify.** Read the world, do one thing, then check it worked
> before the next step.

Small mistakes compound fast (digging air, walking into a wall, retrying a block
you can never reach), so never assume an action succeeded — read the return value
and the world state.

## CRITICAL rules (this is where the model gets it wrong)

- **Aim before you dig or place.** `dig()` / `place()` / `use()` act on the block
  you are currently looking at. Before calling them, confirm the target is in
  front of you with `look_block` or `get_block_in_front`. Digging without aiming
  breaks the wrong block or air.
- **`place` needs a block in hand AND a face to place against.** `hold(block)`
  first, confirm with `get_hand`, aim at a solid face, then `place()`. `place`
  returns `none` when there is nothing to place against.
- **No setup step — just `find_path` / `goto`.** The navigator is our own grid
  walker driven through minethon; there is nothing to load first. It **never
  digs** (it routes around obstacles) — a "no path" result means blocked, not
  "try again".
- **Two tools, split on purpose:**
  - **`find_path(x, y, z)`** plans a walkable cell route from where the bot
    stands to the target and returns it **without moving** — `reachable`,
    `target_cell` (the feet cell you'd end at), `route` (the `[x, y, z]` cells to
    walk), `length`. Any valid route, not an optimised one.
  - **`goto(x, y, z)`** plans that same route, then **walks it in straight
    runs** — at each corner it faces the new cardinal direction (and verifies the
    turn took) before moving, then walks the whole straight leg in one
    `move_forward(N)`. Always moves forward (never strafes/reverses); only the
    facing changes at a corner.
- **To go from A to B, just call `goto` — don't `find_path` first.** `goto`
  already plans internally and won't move if there's no route, so a normal trip
  is one `goto` call. `find_path` is mainly a **check** — "is there a route / what
  is blocking" — for when you want to look before you leap (verifying candidates,
  see below) or **diagnosing after `goto` has failed repeatedly on a target you
  believe is reachable**. Reach for `find_path` when `goto` keeps failing, not
  before every trip.
- **Walkability = feet air + head air + a _solid_ floor below.** **Fences (and
  walls) are pure obstacles** — never walked into, under, or onto — so the path
  routes **around** them; a fence is 1.5 tall, so the bot can't walk onto a fence
  top. The floor requirement also keeps it on **one level** (it won't drop off an
  edge); multi-level is not enabled yet.
- **`goto` targets a cell precisely — it resolves what you name:**
  - name an **air** cell you'd stand in → stands **in** it (`kind: "in"`);
  - name a **solid block** (a tile) → stands **on top** of it (`kind: "on_top"`).
    A fence is not standable, so naming one returns `not_standable`.
  There is no "beside" mode. To dig/use/place a block, `goto` next to it (or onto
  the adjacent tile) yourself, then aim with `look_at` / `get_block_in_front`.
- **A failed `goto` does not move blindly:**
  - no route → `arrived: false, status: "unreachable"` with a `reason`; the bot
    does **not** move — "switch target", not "retry";
  - a step that misses → `arrived: false, status: "stalled"` with `stalled_at`
    (the cell it could not reach) and `walked` (cells done); it **stops there**
    rather than wander.
- **Use `find_path` to check *whether* a route exists and *why* one fails — and
  read the log.** `find_path(x, y, z)` returns `reachable` + the `route` without
  moving. Every plan (from `find_path` *or* `goto`) is logged
  (`mineai.pathfinder`) with the full route, or the reason on failure (`target is
  not a standable cell` = no floor / blocked overhead; `no valid path found` =
  boxed in or beyond the search budget). `reachable: false` means pick a
  different target. Since `goto` runs this same check itself, use `find_path`
  when you want the route/reason *without* committing to the walk — not as a
  routine pre-step.
- **Know which bot you are driving.** If unsure, `get_active_bot` /
  `list_bots`. If no bot is active, stop and say so — do not guess a `bot_name`.
- **Read the return string.** Tools return `'none'`, `'empty'`, `True`/`False`,
  `'coords, name'`, or `'timeout after Ns: ...'`. Check it before the next step.
- **A timeout is not an error you retry blindly.** `timeout after Ns:` means the
  call was cut off at its backstop deadline (a very long walk or a wedged read).
  Re-sense position first, then decide — do not immediately re-issue the same
  goto.
- **Coordinates are integers. Facing is in degrees.** yaw 0 = north (−Z);
  `turn(degrees)` is *relative* (positive = left); `set_turn(yaw)` is absolute.
- **On grid/quest servers, turns snap to cardinal directions** and named quest
  steps go through `action(name, value?)`, not through movement tools.

## Reachability beats proximity — and remember what failed

The **nearest** target is not always the **best** target. When an action toward a
specific target fails, do **not** retry that same target. Broaden your view, mark
it failed, and take the nearest *reachable* alternative — even if it is farther.

The loop:

1. `find_block(name)` gives the single nearest — **just `goto` it.** `goto` plans
   internally and won't move if there's no route, so no separate check is needed.
2. If that `goto` returns `unreachable` (or you get there but `look_block` /
   `get_block_in_front` never shows the target), the nearest is walled off — the
   fence case. **Stop retrying that block.**
3. `find_blocks(name, max)` for several candidates, closest first.
4. Walk the list in order, **skip the one that already failed**, and `goto` the
   next. If wasted walks are costly, you *may* `find_path` each candidate first
   and `goto` only the one that comes back `reachable` — a good use of the check
   when you have several to sift.
5. Keep a short note of which coords failed this task so you never loop back.

One line to hold onto:

> **On failure: don't repeat — enumerate alternatives, drop the one that failed,
> take the nearest feasible one.**

This is general. It applies to digging, to `place` (needs a valid face), to
`use_player` (player must be in range), and to reaching any quest block.

## When a goto gets stuck

Stuck ≠ dead end. Work **down** this ladder; stop as soon as one step works. Only
after the whole ladder fails do you switch targets (the rule above).

1. **Read the goto result.** `goto` returns a dict, not a guess. Check `arrived`
   first.
2. **`arrived: false, status: "unreachable"`?** No route exists — this is not a
   stuck bot; the bot never moved. The `reason` says why (`target is not a
   standable cell` = no floor / blocked overhead; `no valid path found` = boxed
   in or beyond the search budget). Skip to step 4; do not re-issue the same
   goto.
3. **`arrived: false, status: "stalled"`?** It walked but a forward step did not
   land on the expected cell (`stalled_at`), so it stopped. Re-sense position;
   the terrain likely differs from what was planned (a block changed, or a step
   under/overshot). Re-`find_path` from where you now stand before trying again.
4. **It's walled off.** Confirm with `find_path(x, y, z)` — `reachable: false`
   proves no route exists. Then apply reachability → `find_blocks` and pick the
   nearest reachable alternative.

One line to hold onto:

> **Stuck: `unreachable` means switch targets, not retry; `stalled` means
> re-sense and re-`find_path`; the log shows the planned route.**

## Quick Reference

Optional `bot_name` on every action tool — omit it to use the active bot.

| Tool | Returns | Purpose |
|------|---------|---------|
| `list_bots` | list | All known bots and their state |
| `get_active_bot` / `set_active_bot(name)` | name | Which bot action tools drive |
| `check_bot_health(name)` | status | One bot's connection + end/kick reason |
| `get_pos` | position | Current (x, y, z) |
| `get_orientation` | `yaw, pitch` | Facing, degrees (yaw 0 = north) |
| `get_hand` | `name, count` or `none` | Held item |
| `get_height` / `set_height(level)` | level 1–5 | Bot size level |
| `get_block(x, y, z)` | name or `none` | Block at coords |
| `get_block_property(x, y, z, prop)` | value or `none` | Block state (`lit`, `facing`, …) |
| `look_block` | `coords, name` or `none` | Block I'm aiming at |
| `get_block_in_front` | `name` or `none` | Solid block one step ahead (name only — use `look_block` for coords) |
| `find_block(name)` | coords | Nearest block by name |
| `find_blocks(name, max=16)` | list, closest first, or `empty` | N nearest blocks |
| `find_path(x, y, z)` | `{reachable, target_cell, route, length, reason}` | Plan a walkable cell route **without moving** — see *why* a goto would fail; also logged. No setup needed |
| `goto(x, y, z)` | `{arrived, status, target_cell, route, walked, stalled_at, pos}` | **The goto.** Plans + walks the route, stepping cell by cell (stands `in` an air target or `on_top` of a block); doesn't move if no route. Route is logged |
| `move_forward(blocks=1)` | position | Walk; also `move_backward/left/right` |
| `jump` | position | Jump once |
| `turn(degrees)` | orientation | Relative turn (+ = left) |
| `turn_left` / `turn_right` | orientation | 90° step |
| `set_turn(yaw)` | orientation | Face absolute yaw |
| `face_north` / `face_south` / `face_east` / `face_west` | orientation | Face a cardinal (−Z / +Z / +X / −X); snaps on grid servers |
| `look_at(x, y, z)` | orientation | Aim at a point |
| `hold(name)` / `unhold` | bool | Equip / put away an item |
| `drop(item=None, count=None)` | bool | Toss held stack, or item by name |
| `dig` | `coords, name` or `none` | Break the aimed block |
| `place` | `coords, name` or `none` | Place held block on the aimed face |
| `use` | bool | Right-click / activate held item |
| `use_player(username)` | bool | Right-click a named player (stack/mount) |
| `sneak(on)` | state | Hold / release sneak |
| `action(name, value=None)` | `sent` | Server-authoritative named quest action |
| `chat(message)` | `sent` | Public chat |

## Example 1 — mine a log, with a blocked-target fallback

The canonical shape: sense, travel, verify aim, act, verify result — and switch
targets when the nearest one is walled off.

```
Goal: get one oak_log.

find_block("oak_log")               -> 10 64 20   (nearest)
find_path(10, 64, 20)               -> reachable: false, reason: "no valid path found"   (log shows the plan)
    # walled off by fences — never even start the goto. Mark (10,64,20) failed.

find_blocks("oak_log", 8)           -> [ (10 64 20), (18 63 5), ... ]  closest first
    # skip (10,64,20) — already failed
find_path(18, 63, 6)                -> reachable: true, target_cell: [18,63,6], length: 5
    # (18,63,6) is the empty tile NEXT TO the log at (18,63,5); goto stands there, then we aim at the log
goto(18, 63, 6)                     -> arrived: true, target_cell: [18,63,6]
look_at(18, 63, 5)                  -> aim at the log
get_block_in_front                  -> oak_log            (something solid ahead; look_block for coords)
hold("wooden_axe")                  -> True
get_hand                            -> wooden_axe, 1
dig                                 -> 18 63 5, oak_log
get_block(18, 63, 5)                -> none               (verified: it's gone)
```

## Example 2 — place a block where you're standing

```
Goal: place a cobblestone in front of me.

get_hand                            -> none
hold("cobblestone")                 -> True
get_hand                            -> cobblestone, 63
get_block_in_front                  -> dirt               (something solid ahead to place against)
place                               -> 12 65 8, cobblestone
get_block(12, 65, 8)                -> cobblestone        (verified)
```

## Common mistakes

| Mistake | Fix |
|---------|-----|
| `dig` / `place` without aiming first | `look_block` / `get_block_in_front` to confirm the target, then act |
| Retrying the same unreachable block | `find_blocks`, skip the failed coord, take the nearest reachable one |
| A goto toward a fenced-off block | `find_path` first; only goto when `reachable` is true |
| Retrying `goto` after `arrived: false, status: "unreachable"` | It found no route and didn't move — switch target, don't retry |
| Guessing why a goto failed | Read `status` / `reason` and the `mineai.pathfinder` log — `unreachable` (no route) vs `stalled` (a step missed) |
| Expecting a "beside" mode to aim for you | There is none: `goto` stands `in`/`on_top` of the target; `look_at(x,y,z)` yourself, then `get_block_in_front`, before dig/use/place |
| Re-issuing the same `goto` after `status: "stalled"` | The terrain differs from the plan — re-sense position and `find_path` again from where you now stand |
| `place` with an empty hand | `hold(block)` and confirm with `get_hand` first |
| Ignoring the return string | Every tool tells you what happened — read it before the next step |
| Guessing a `bot_name` | `get_active_bot` / `list_bots`; if none active, stop |
