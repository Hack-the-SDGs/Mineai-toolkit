---
name: mineai-toolkit
description: Use when controlling a Minecraft bot through the mine-ai-toolkit MCP server — moving, turning, digging, placing, using items, pathfinding to coordinates, or reading the world (position, blocks, held item). Covers how to drive the tools reliably: sense before acting, verify after, check a route is reachable before walking it, recover when a path is blocked, and pick a reachable target instead of retrying an unreachable one.
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
- **Load the pathfinder once per bot before any goto.** Call
  `load_pathfinder()`, then check `pathfinder_status`. The pathfinder **never
  digs** (it routes around obstacles) — a "no path" result means blocked, not
  "try again".
- **There are exactly two gotos — pick by intent, and you can't get it wrong:**
  - **Acting on a block** (dig / use / place) → `pathfinder_goto_look_at_block(x,
    y, z)`. Ends with the bot in reach of **and facing** the block.
  - **Just travelling** to a place → `pathfinder_goto_near(x, y, z, radius)`.
    Gets you *near*; it does **not** face or land on any specific block.
- **Never use `goto_near` to line up on a block you'll act on.** A radius goal is
  satisfied by *any* cell within range, so for a 3x3 with the target at the
  centre the bot stops in a **corner** — not on, not facing — and still reports
  "arrived". That's what `goto_look_at_block` is for.
- **Check the path before you walk it.** `pathfinder_check_path(x, y, z,
  goal_type)` plans the route *without moving the bot* and returns `reachable`.
  Use it before a goto to any target that might be walled off — the classic trap
  is a one-block spot separated by fences: the coords match but no path exists,
  and a blind goto just stalls. `reachable: false` (status `partial`/`noPath`)
  means pick a different target, don't launch the goto. Pass the **same**
  `goal_type` you'll execute — `near` for a `goto_near`, `look_at_block` for a
  `goto_look_at_block` — so the check matches the move.
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

1. **Confirm it's really stuck.** `pathfinder_status` + `get_pos`. If position is
   still changing, it is mid-route — wait, don't interrupt.
2. **Are you using the right goto?** Acting on the block but used `goto_near`?
   Switch to `pathfinder_goto_look_at_block(x, y, z)` — a radius goal parks the
   bot in a corner reporting "arrived" without facing the block.
3. **Just travelling? Loosen it.** If you only need to *be there*,
   `pathfinder_goto_near(x, y, z, radius=2)`, then `radius=3`. Standing near is
   usually enough for a travel goal.
4. **Close the last gap manually.** Once near: `look_at(x, y, z)` / `set_turn`,
   then `move_forward(1)`, and re-check `get_block_in_front`. Pathfinder gets you
   *near*; your own steps get you *exact*.
5. **Still blocked? It's a wall.** No route exists (pathfinder won't dig).
   Confirm with `pathfinder_check_path(x, y, z, goal_type)` — a `partial`/`noPath`
   status proves it's a wall, not a slow route, and its `end` shows how far the
   route gets before the obstacle. Then `pathfinder_clear_goal`, apply
   reachability → `find_blocks` and pick the nearest reachable alternative.

One line to hold onto:

> **Stuck: check you used the right goto, loosen a travel goal, step in manually
> — and only then switch targets.**

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
| `pathfinder_check_path(x, y, z, goal_type='near'\|'look_at_block', radius=1, timeout_ms=5000, include_path=True)` | `{reachable, status, path_length, cost, end, path}` | Plan a route **without moving** — test reachability before a goto; pass the *same* goal_type you'll execute |
| `pathfinder_stop` / `pathfinder_clear_goal` | — | Halt / drop current goal |
| `pathfinder_goto_near(x, y, z, radius=?)` | arrival | **Travel:** get within radius of a point (does not face a block) |
| `pathfinder_goto_look_at_block(x, y, z)` | arrival | **Interact:** get in reach of **and facing** a block — use before dig/use/place |
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
pathfinder_check_path(10, 64, 20)   -> reachable: false, status: partial, end: [9,64,18]
    # walled off by fences — never even start the goto. Mark (10,64,20) failed.

find_blocks("oak_log", 8)           -> [ (10 64 20), (18 63 5), ... ]  closest first
    # skip (10,64,20) — already failed
pathfinder_check_path(18, 63, 5, goal_type="look_at_block")  -> reachable: true
pathfinder_goto_look_at_block(18, 63, 5)  -> arrived  (in reach AND facing it)
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
| A goto toward a fenced-off block that stalls | `pathfinder_check_path` first; only goto when `reachable` is true |
| `goto_near(radius)` stops in a corner, "arrived" but not on/facing the target | Use `goto_look_at_block` for anything you'll dig/use/place; `goto_near` is travel-only |
| A goto before `load_pathfinder` | Load the pathfinder once per bot first |
| Treating "no path" as "retry" | It's blocked (pathfinder never digs) — loosen the goal or switch target |
| Treating a `timeout` return as a crash | Goal is already cleared and bot stopped — re-sense, then decide |
| `place` with an empty hand | `hold(block)` and confirm with `get_hand` first |
| Ignoring the return string | Every tool tells you what happened — read it before the next step |
| Guessing a `bot_name` | `get_active_bot` / `list_bots`; if none active, stop |
