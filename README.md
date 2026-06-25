# mame_mcp

`mame_mcp` is a Model Context Protocol bridge for MAME-focused reverse
engineering. It is aimed at arcade-to-SNES porting work: memory access traces,
input injection, ROM audit checks, IO-port discovery, and reproducible
headless harnesses.

Stock-MAME compatible — no custom MAME binary required. Two modes, both on stock MAME:
the **stateless** tools drive MAME with generated `-autoboot_script` Lua sidecars (spawn,
run, exit); the **live session** suite keeps a persistent MAME alive behind a bridge and
exposes debugger-style live memory read/write, register access, run/pause, save/load
state, and input injection across calls. A deeper MAME source fork is still only needed
for the harder stuff (low-overhead instruction-trace ring buffers; device introspection
Lua can't reach) — see [Fork Roadmap](#fork-roadmap).

## Quick Start

```powershell
python -m pip install -e .

$env:MAME_EXE = "/path/to/mame"      # or leave unset if mame is on PATH

mame-mcp-tools --names
mame-mcp-tools --category trace
```

Wire it into Codex or another MCP client:

```json
{
  "mcpServers": {
    "mame": {
      "command": "mame-mcp-bridge",
      "env": {
        "MAME_EXE": "/path/to/mame"
      }
    }
  }
}
```

Restart the MCP client after editing its config.

This repo includes a generic `.mcp.json` that only starts the bridge. Pass
`system` and `rompath` in each tool call, or set `MAME_SYSTEM` and
`MAME_ROMPATH` in your local MCP config for the project you are inspecting.

## Tools

Two families: **stateless** one-shot tools (each spawns MAME, does its job, exits) and a
**live session** suite (one persistent MAME kept alive across calls — read/write/run/inject like
a debugger). **25 tools** total.

### Stateless (one-shot)

| Tool | Purpose |
|---|---|
| `ping` | Echo back an optional payload; verify the MCP bridge is alive. |
| `config_check` | Resolve MAME env/config paths and report which required pieces exist. |
| `audit_romset` | Run `mame -verifyroms <system>` and return the audit tail. |
| `get_ioports` | Boot a machine briefly and list MAME Lua IO-port fields (for input injection). |
| `trace_memory_access` | Install Lua read/write taps over CPU address ranges; log deduped accesses. |
| `trace_cchip_superman` | Superman helper: trace `$900000-$900FFF` C-Chip accesses + the `$900803` status verdict. |
| `run_lua_script` | Run a caller-supplied MAME Lua autoboot script (by path), headlessly. |
| `run_lua_inline` | Run caller-supplied MAME Lua source (string, not a path); optional artifact read-back. |
| `capture_leaf_io` | Golden-vector capture for a pure leaf that transforms one word/byte in place — inject inputs via taps, record output+regs+CCR. Independent oracle for a transpiler differential harness. |

### Live session (persistent MAME, debugger-style)

Call `mame_launch` first (keeps MAME running across calls); the rest operate on that session.

| Tool | Purpose |
|---|---|
| `mame_launch` | Launch a PERSISTENT live MAME (headless + bridge). Required before any other `mame_*` tool. |
| `mame_session_status` | Live session status (system, frame, paused). |
| `mame_session_stop` | Terminate the live session. |
| `mame_pause` / `mame_resume` | Pause / resume the machine (state stays readable while paused). |
| `mame_run_frames` | Run N frames then pause; returns the frame number. |
| `mame_read_memory` / `mame_write_memory` | Read / write a hex block in a device's program space. |
| `mame_get_regs` / `mame_set_reg` | Read all CPU registers (D0-D7/A0-A7/PC/SR/USP/…) / set one. |
| `mame_save_state` / `mame_load_state` | Save / load a MAME save state by name (needs `stateDirectory`). |
| `mame_send_input` | Set an ioport field value (e.g. `Coin 1`, `P1 Right`). |
| `mame_exec_lua_live` | Run Lua on the live machine (`M`/`machine` = `manager.machine`); returns its value. |
| `mame_capture_game_tick` | Run to the Nth GAME_TICK and snapshot regs + a memory region at the prologue read (lockstep primitive). |
| `mame_drive_to_gameplay` | Boot-aware drive to a running game: wait for idle, inject clean coin/start edges, confirm GAME_TICK (replay-robust where a fixed `.inp` desyncs). |

The MCP responses return JSON text with command lines, log paths, return codes,
stderr/stdout tails, and parsed trace summaries where applicable.

## Environment

| Env var | Default | Purpose |
|---|---|---|
| `MAME_EXE` | `mame` | MAME executable or command on PATH. |
| `MAME_SYSTEM` | none | Default machine short name, e.g. `driver_short_name`. |
| `MAME_ROMPATH` | none | ROM search path. |
| `MAME_CWD` | current directory | Working directory for generated scripts/logs and MAME state. |
| `MAME_WORKDIR` | `<MAME_CWD>/.mame_mcp` | Generated Lua, logs, nvram, cfg, etc. |

## Generic Trace Example

```json
{
  "system": "driver_short_name",
  "rompath": "/path/to/roms",
  "frames": 1800,
  "ranges": [
    { "name": "device_window", "start": 9437184, "end": 9441279 }
  ],
  "trackReads": [
    { "name": "status", "address": 9439234 }
  ],
  "injectPreset": "none",
  "dryRun": true
}
```

`trace_memory_access` installs read/write taps over each range, dedupes by
`(R/W, PC, address, range)`, optionally counts values read from selected
addresses, and writes a human-readable log plus a parsed JSON summary.

Use `"dryRun": true` to generate the Lua harness without launching MAME.

## Superman C-Chip Helper

`trace_cchip_superman` is a convenience wrapper for the known Superman C-Chip
window. It still requires the caller or environment to provide the ROM path.

```json
{
  "rompath": "/path/to/roms",
  "frames": 1800,
  "injectPreset": "none"
}
```

It expands to a `trace_memory_access` call over `$900000-$900FFF`, tracking
reads from `$900802/$900803` and reporting whether status `$01` and `$05` were
seen.

## Fork Roadmap

The stock-MAME Lua layer can cover a lot:

- address read/write taps,
- frame callbacks,
- input-field injection,
- ROM audit and machine metadata,
- screenshots via MAME command-line/video options,
- reproducible generated scripts and logs.

Already delivered **without** a fork, via the live-session bridge (stock MAME + a persistent
process): a long-lived session, debugger-grade live memory reads/writes, register get/set,
run/pause, and save/load state (the `mame_*` tools above).

A true MAME source fork becomes worthwhile only for what Lua/the bridge can't do well:

- instruction trace ring buffers with low overhead,
- tile/sprite/sound device introspection not exposed through Lua,
- screenshot APIs as one-shot MCP calls.

The MCP tool names and response shapes here are intentionally similar to the
Mesen MCP bridge so agents can learn one mental model and apply it to both
console and arcade sources.
