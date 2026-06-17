# mame_mcp

`mame_mcp` is a Model Context Protocol bridge for MAME-focused reverse
engineering. It is aimed at arcade-to-SNES porting work: memory access traces,
input injection, ROM audit checks, IO-port discovery, and reproducible
headless harnesses.

This first cut is stock-MAME compatible. It drives MAME with generated
`-autoboot_script` Lua sidecars instead of requiring a custom MAME binary. That
keeps the useful tools available immediately; a deeper MAME source fork can be
added later for live sockets, richer trace buffers, or debugger APIs that Lua
cannot expose cleanly.

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

Current implemented tools:

| Tool | Purpose |
|---|---|
| `ping` | Verify the MCP bridge is alive. |
| `config_check` | Show resolved MAME executable, working directory, system, and ROM path. |
| `audit_romset` | Run `mame -verifyroms <system>`. |
| `get_ioports` | Boot a machine briefly and list MAME Lua IO-port fields. |
| `trace_memory_access` | Generate a Lua read/write tap trace for one or more CPU address ranges. |
| `trace_cchip_superman` | Optional Superman helper built on `trace_memory_access`; no ROM path is baked in. |
| `run_lua_script` | Run a caller-supplied MAME Lua script headlessly. |

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

A true MAME source fork becomes worthwhile when we need:

- a long-lived JSON-RPC socket inside MAME,
- debugger-grade live memory reads/writes without generated scripts,
- instruction trace ring buffers with low overhead,
- tile/sprite/sound device introspection not exposed through Lua,
- stable save/load state and screenshot APIs as one-shot MCP calls.

The MCP tool names and response shapes here are intentionally similar to the
Mesen MCP bridge so agents can learn one mental model and apply it to both
console and arcade sources.
