---
name: mineai-toolkit
description: Use when controlling a Minecraft bot through the mine-ai-toolkit MCP server — moving, turning, digging, placing, using items, pathfinding to coordinates, or reading the world (position, blocks, held item). Covers how to drive the tools reliably: sense before acting, verify after, check a route is reachable before walking it, recover when a path is blocked, and pick a reachable target instead of retrying an unreachable one.
---

# mineai-toolkit

## Overview

mineai-toolkit is an MCP server that controls a live Minecraft bot. The tools are
**low-level verbs** — one action each (`move_forward`, `turn`, `dig`, `place`,
`find_block`, `pathfinder_goto`, …). They do exactly what they say and
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
- **Load the pathfinder once per bot before any goto.** Call `load_pathfinder()`
  first. The pathfinder **never digs** (it routes around obstacles) — a "no
  path" result means blocked, not "try again".
- **There is one goto: `pathfinder_goto(x, y, z)`.** It plans the route with
  `mineflayer-pathfinder`, then drives to the route's last node — no radius, no
  variants. It adapts to the target and tells you which in `mode`:
  - **Empty target cell** (`mode: "on"`) → stands **on** it. For travel.
  - **Occupied cell** you'll dig/use/place (`mode: "beside"`) → stands **beside**
    it and faces it (`facing_target: true`), ready to act.
  When there is no route at all it returns `arrived: false` with `status`
  (`noPath`/`timeout`) and does **not** move — "unreachable, switch target",
  never "retry".
  - For a stand-on target the planner stops just short of (a fence corner, a
    half-slab step — which `mineflayer-pathfinder` won't plan but the bot *can*
    walk), goto **finishes with plain cardinal steps** (walk → turn → walk,
    routing around fences) and returns `arrived: true, status: "success_manual"`.
    Treat it like any arrival.
  - If even that can't finish, it returns `arrived: false, status:
    "stopped_short"` with where it parked — switch target rather than retry.
- **Check the path — and read the log — to see *why* a goto fails.**
  `pathfinder_check_path(x, y, z)` plans the *same* route without moving and
  returns `reachable`, `mode`, `status`, `end`, and the full `path` array. Every
  plan is also logged (`mineai.pathfinder`): `status: noPath` = walled off,
  `partial` = blocked partway (`end` shows how far), `timeout` = search ran out
  of budget. `reachable: false` means pick a different target, don't launch the
  goto.
- **Know which bot you are driving.** If unsure, `get_active_bot` /
  `list_bots`. If no bot is active, stop and say so — do not guess a `bot_name`.
- **Read the return string.** Tools return `'none'`, `'empty'`, `True`/`False`,
  `'coords, name'`, or `'timeout after Ns: ...'`. Check it before the next step.
- **A timeout is not an error you retry blindly.** `timeout after Ns:` means the
  goal was already cleared and the bot has stopped. Re-sense position, then
  decide — do not immediately re-issue the same goto.
- **Coordinates are integers. Facing is in degrees.** yaw 0 = north (−Z);
  `turn(degrees)` is *relative* (positive = left); `set_turn(yaw)` is absolute.
- **On grid/quest servers, turns snap to cardinal directions** and named quest
  steps go through `action(name, value?)`, not through movement tools.

## Reachability beats proximity — and remember what failed

The **nearest** target is not always the **best** target. When an action toward a
specific target fails, do **not** retry that same target. Broaden your view, mark
it failed, and take the nearest *reachable* alternative — even if it is farther.

The loop:

1. `find_block(name)` gives the single nearest — fine for the first attempt.
2. **Verify before you commit:** `pathfinder_check_path(x, y, z)`. If
   `reachable` is false, the nearest is walled off (the fence case) — skip
   straight to enumerating alternatives, no wasted goto.
3. If you cannot reach or act on it (check_path says unreachable, pathfinder
   returns no path, or `look_block` / `get_block_in_front` never shows the
   target), **stop retrying that block.**
4. `find_blocks(name, max)` for several candidates, closest first.
5. Walk the list in order, **skip the one that already failed**, and — cheaply —
   `pathfinder_check_path` each candidate, taking the first that comes back
   `reachable`. That way you goto only a spot you already know has a route.
6. Keep a short note of which coords failed this task so you never loop back.

One line to hold onto:

> **On failure: don't repeat — enumerate alternatives, drop the one that failed,
> take the nearest feasible one.**

This is general. It applies to digging, to `place` (needs a valid face), to
`use_player` (player must be in range), and to reaching any quest block.

## When a goto gets stuck

Stuck ≠ dead end. Work **down** this ladder; stop as soon as one step works. Only
after the whole ladder fails do you switch targets (the rule above).

1. **Read the goto result.** `pathfinder_goto` returns a dict, not a guess.
   Check `arrived` first.
2. **`arrived: false`?** The target is unreachable — this is not a stuck bot.
   `status` says why: `noPath` = walled off, `partial` = blocked partway,
   `timeout` = search budget spent (never moved), `stopped_short` = it walked
   but the pathfinder parked near without reaching (a fence between / blocked
   final step). The `mineai.pathfinder` log has the full planned path. Skip to
   step 4; do not re-issue the same goto.
3. **`arrived: true` but you still can't act?** Check `mode` and `facing_target`.
   If `mode: "beside"` but `facing_target: false`, line of sight is off —
   re-`look_at(x, y, z)` and re-check `get_block_in_front`. Close any last
   sub-block gap manually: `move_forward(1)`, then re-aim.
4. **It's walled off.** Confirm with `pathfinder_check_path(x, y, z)` —
   `status: partial`/`noPath` proves no route exists (and `end` shows how far a
   route gets). Then apply reachability → `find_blocks` and pick the nearest
   reachable alternative.

One line to hold onto:

> **Stuck: `arrived:false` means switch targets, not retry; `beside` +
> `facing_target:false` means re-aim; the log shows the planned path.**

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
| `get_block_in_front` | `coords, name` or `none` | Solid block one step ahead |
| `find_block(name)` | coords | Nearest block by name |
| `find_blocks(name, max=16)` | list, closest first, or `empty` | N nearest blocks |
| `load_pathfinder` / `pathfinder_status` | status | Enable / inspect pathfinder (call `load_pathfinder` once per bot) |
| `pathfinder_goto(x, y, z)` | `{arrived, mode, status, facing_target, stood_at, stalled_at, …}` | **The goto.** Plans + walks — `on` (stand on an empty target) or `beside` (stand beside+facing a block); doesn't move if no route. Path is logged |
| `pathfinder_check_path(x, y, z, include_path=True)` | `{reachable, status, mode, end, path}` | Plan the goto's route **without moving** — see *why* it would fail; also logged |
| `pathfinder_stop` / `pathfinder_clear_goal` | — | Halt / drop current goal |
| `move_forward(blocks=1)` | position | Walk; also `move_backward/left/right` |
| `jump` | position | Jump once |
| `turn(degrees)` | orientation | Relative turn (+ = left) |
| `turn_left` / `turn_right` | orientation | 90° step |
| `set_turn(yaw)` | orientation | Face absolute yaw |
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
load_pathfinder()
pathfinder_check_path(10, 64, 20)   -> reachable: false, status: noPath   (log shows the planned path)
    # walled off by fences — never even start the goto. Mark (10,64,20) failed.

find_blocks("oak_log", 8)           -> [ (10 64 20), (18 63 5), ... ]  closest first
    # skip (10,64,20) — already failed
pathfinder_check_path(18, 63, 5)    -> reachable: true, mode: beside, end: [18,63,6]
pathfinder_goto(18, 63, 5)          -> arrived: true, mode: beside, facing_target: true
get_block_in_front                  -> 18 63 5, oak_log   (aim confirmed)
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
get_block_in_front                  -> 12 64 8, dirt      (a face to place against)
place                               -> 12 65 8, cobblestone
get_block(12, 65, 8)                -> cobblestone        (verified)
```

## Common mistakes

| Mistake | Fix |
|---------|-----|
| `dig` / `place` without aiming first | `look_block` / `get_block_in_front` to confirm the target, then act |
| Retrying the same unreachable block | `find_blocks`, skip the failed coord, take the nearest reachable one |
| A goto toward a fenced-off block | `pathfinder_check_path` first; only goto when `reachable` is true |
| Retrying `pathfinder_goto` after `arrived: false` | It already found no route and didn't move — switch target, don't retry |
| Guessing why a goto failed | Read `status` / the `mineai.pathfinder` log — `noPath` vs `partial` vs `timeout` tells you the cause |
| Acting after `arrived: true` without checking `facing_target` | For `mode: "beside"`, confirm `facing_target` / `get_block_in_front` before dig/use/place |
| A goto before `load_pathfinder` | Load the pathfinder once per bot first |
| Treating a `timeout` return as a crash | Goal is already cleared and bot stopped — re-sense, then decide |
| `place` with an empty hand | `hold(block)` and confirm with `get_hand` first |
| Ignoring the return string | Every tool tells you what happened — read it before the next step |
| Guessing a `bot_name` | `get_active_bot` / `list_bots`; if none active, stop |
