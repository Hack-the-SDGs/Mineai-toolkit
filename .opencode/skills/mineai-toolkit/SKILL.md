---
name: mineai-toolkit
description: Use when controlling a Minecraft bot through the mine-ai-toolkit MCP server — moving, turning, digging, placing, using items, pathfinding to coordinates, or reading the world (position, blocks, held item). Covers how to drive the tools reliably: sense before acting, verify after, recover when a path is blocked, and pick a reachable target instead of retrying an unreachable one.
---

# mineai-toolkit

## Overview

mineai-toolkit is an MCP server that controls a live Minecraft bot. The tools are
**low-level verbs** — one action each (`move_forward`, `turn`, `dig`, `place`,
`find_block`, `pathfinder_goto_near`, …). They do exactly what they say and
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
- **Load the pathfinder once per bot before any `pathfinder_goto_*`.** Call
  `load_pathfinder()`, then check `pathfinder_status`. The pathfinder **never
  digs** (it routes around obstacles) — a "no path" result means blocked, not
  "try again".
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
2. If you cannot reach or act on it (pathfinder returns no path, or
   `look_block` / `get_block_in_front` never shows the target), **stop retrying
   that block.**
3. `find_blocks(name, max)` for several candidates, closest first.
4. Walk the list in order, **skip the one that already failed**, and take the
   first you can actually reach.
5. Keep a short note of which coords failed this task so you never loop back.

One line to hold onto:

> **On failure: don't repeat — enumerate alternatives, drop the one that failed,
> take the nearest feasible one.**

This is general. It applies to digging, to `place` (needs a valid face), to
`use_player` (player must be in range), and to reaching any quest block.

## When `pathfinder_goto_*` gets stuck

Stuck ≠ dead end. Work **down** this ladder; stop as soon as one step works. Only
after the whole ladder fails do you switch targets (the rule above).

1. **Confirm it's really stuck.** `pathfinder_status` + `get_pos`. If position is
   still changing, it is mid-route — wait, don't interrupt.
2. **Loosen the goal.** The exact cell may not be standable:
   `pathfinder_goto_near(x, y, z, radius=2)`, then `radius=3`. Standing *near* is
   usually enough.
3. **Drop a constraint.** Don't need the exact Y? `pathfinder_goto_near_xz(x, z,
   radius)` or `pathfinder_goto_xz(x, z)`. Height problem? `pathfinder_goto_y(y)`.
4. **Aim to touch, not to occupy.** For a block you'll dig/use,
   `pathfinder_goto_get_to_block(x, y, z)` (reach adjacent) instead of
   `pathfinder_goto_block` (stand on it).
5. **Close the last gap manually.** Once near: `look_at(x, y, z)` / `set_turn`,
   then `move_forward(1)`, and re-check `get_block_in_front`. Pathfinder gets you
   *near*; your own steps get you *exact*.
6. **Still blocked? It's a wall.** No route exists (pathfinder won't dig).
   `pathfinder_clear_goal`, then apply reachability → `find_blocks` and pick the
   nearest reachable alternative.

One line to hold onto:

> **Stuck: loosen the goal, then aim to touch, then step in manually — and only
> then switch targets.**

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
| `load_pathfinder` / `pathfinder_status` | status | Enable / inspect pathfinder |
| `pathfinder_stop` / `pathfinder_clear_goal` | — | Halt / drop current goal |
| `pathfinder_goto_near(x, y, z, radius=?)` | arrival | Stand within radius of a point |
| `pathfinder_goto_near_xz(x, z, radius=?)` / `pathfinder_goto_xz(x, z)` | arrival | Ignore Y |
| `pathfinder_goto_block(x, y, z)` / `pathfinder_goto_get_to_block(x, y, z)` | arrival | Stand on / reach adjacent to a block |
| `pathfinder_goto_y(y)` | arrival | Reach a height |
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
pathfinder_goto_near(10, 64, 20, radius=2)
pathfinder_status                   -> no path    (behind a wall; pathfinder won't dig)
    # DO NOT retry (10,64,20). Mark it failed.
pathfinder_clear_goal()

find_blocks("oak_log", 8)           -> [ (10 64 20), (18 63 5), ... ]  closest first
    # skip (10,64,20) — already failed
pathfinder_goto_get_to_block(18, 63, 5)   -> arrived  (farther, but reachable)
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
| `pathfinder_goto_*` before `load_pathfinder` | Load the pathfinder once per bot first |
| Treating "no path" as "retry" | It's blocked (pathfinder never digs) — loosen the goal or switch target |
| Treating a `timeout` return as a crash | Goal is already cleared and bot stopped — re-sense, then decide |
| `place` with an empty hand | `hold(block)` and confirm with `get_hand` first |
| Ignoring the return string | Every tool tells you what happened — read it before the next step |
| Guessing a `bot_name` | `get_active_bot` / `list_bots`; if none active, stop |
