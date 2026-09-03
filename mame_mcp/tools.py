"""Static catalog for the mame_mcp MCP tool surface."""

from __future__ import annotations

import argparse
import sys
from collections import OrderedDict
from typing import Any


JSON_OBJECT: dict[str, Any] = {"type": "object", "additionalProperties": False}

COMMON_LAUNCH_PROPS: dict[str, Any] = {
    "mameExe": {"type": "string", "description": "MAME executable. Defaults to MAME_EXE or `mame`."},
    "cwd": {"type": "string", "description": "MAME working directory. Defaults to MAME_CWD or current directory."},
    "workdir": {"type": "string", "description": "Generated-script/log directory. Defaults to MAME_WORKDIR or <cwd>/.mame_mcp."},
}

COMMON_MACHINE_PROPS: dict[str, Any] = {
    **COMMON_LAUNCH_PROPS,
    "system": {"type": "string", "description": "MAME machine short name. Defaults to MAME_SYSTEM."},
    "rompath": {"type": "string", "description": "ROM search path. Defaults to MAME_ROMPATH."},
}

SINGLE_STEP_PROPS: dict[str, Any] = {
    "targetPc": {"type": "integer", "description": "CPU program counter at which to stop."},
    "memory": {"type": "array", "items": {"type": "object", "properties": {
        "addr": {"type": "integer"}, "len": {"type": "integer"}},
        "required": ["addr"], "additionalProperties": False}},
    "expectedSp": {"type": "integer"},
    "expectedRegs": {"type": "object", "additionalProperties": {"type": "integer"}},
    "preStepRegs": {"type": "object", "additionalProperties": {"type": "integer"}},
    "cpuTag": {"type": "string", "default": ":maincpu"},
}


TOOLS: "OrderedDict[str, dict[str, Any]]" = OrderedDict(
    [
        (
            "ping",
            {
                "category": "state",
                "summary": "Echo back an optional payload. Use to verify the MCP bridge is alive.",
                "schema": {
                    "type": "object",
                    "properties": {"echo": {"description": "Optional value to echo back."}},
                    "additionalProperties": True,
                },
            },
        ),
        (
            "config_check",
            {
                "category": "state",
                "summary": "Resolve MAME env/config paths and report which required pieces exist.",
                "schema": {
                    "type": "object",
                    "properties": COMMON_MACHINE_PROPS,
                    "additionalProperties": False,
                },
            },
        ),
        (
            "audit_romset",
            {
                "category": "machine",
                "summary": "Run `mame -verifyroms <system>` and return the audit output tail.",
                "schema": {
                    "type": "object",
                    "properties": {
                        **COMMON_MACHINE_PROPS,
                        "timeoutSec": {"type": "integer", "description": "Process timeout in seconds.", "default": 60},
                    },
                    "additionalProperties": False,
                },
            },
        ),
        (
            "get_ioports",
            {
                "category": "machine",
                "summary": "Boot a machine briefly and list MAME Lua IO-port fields for input injection.",
                "schema": {
                    "type": "object",
                    "properties": {
                        **COMMON_MACHINE_PROPS,
                        "logPath": {"type": "string", "description": "Optional output log path."},
                        "timeoutSec": {"type": "integer", "description": "Process timeout in seconds.", "default": 30},
                    },
                    "additionalProperties": False,
                },
            },
        ),
        (
            "trace_memory_access",
            {
                "category": "trace",
                "summary": "Install Lua read/write taps over CPU address ranges and log deduped accesses.",
                "schema": {
                    "type": "object",
                    "properties": {
                        **COMMON_MACHINE_PROPS,
                        "frames": {"type": "integer", "description": "Frame budget before dumping the trace.", "default": 1800},
                        "ranges": {
                            "type": "array",
                            "description": "Address ranges to tap in maincpu program space.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "start": {"type": "integer"},
                                    "end": {"type": "integer"},
                                },
                                "required": ["start", "end"],
                                "additionalProperties": False,
                            },
                        },
                        "trackReads": {
                            "type": "array",
                            "description": "Read addresses whose distinct values should be counted.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "address": {"type": "integer"},
                                },
                                "required": ["address"],
                                "additionalProperties": False,
                            },
                        },
                        "injectPreset": {
                            "type": "string",
                            "description": "`none` or `coin_start`.",
                            "default": "none",
                        },
                        "logPath": {"type": "string", "description": "Optional output log path."},
                        "timeoutSec": {"type": "integer", "description": "Process timeout in seconds."},
                        "dryRun": {"type": "boolean", "description": "Generate the Lua harness but do not launch MAME.", "default": False},
                    },
                    "additionalProperties": False,
                },
            },
        ),
        (
            "trace_cchip_superman",
            {
                "category": "trace",
                "summary": "Superman helper: trace $900000-$900FFF C-Chip accesses and report $900803 status verdict.",
                "schema": {
                    "type": "object",
                    "properties": {
                        **COMMON_MACHINE_PROPS,
                        "frames": {"type": "integer", "description": "Frame budget.", "default": 1800},
                        "injectPreset": {"type": "string", "description": "`none` or `coin_start`.", "default": "none"},
                        "logPath": {"type": "string", "description": "Optional output log path."},
                        "timeoutSec": {"type": "integer", "description": "Process timeout in seconds."},
                        "dryRun": {"type": "boolean", "description": "Generate the Lua harness but do not launch MAME.", "default": False},
                    },
                    "additionalProperties": False,
                },
            },
        ),
        (
            "run_lua_script",
            {
                "category": "lua",
                "summary": "Run a caller-supplied MAME Lua autoboot script headlessly.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "scriptPath": {"type": "string", "description": "Lua script path."},
                        **COMMON_MACHINE_PROPS,
                        "frames": {"type": "integer", "description": "Frame budget used to calculate safety seconds.", "default": 60},
                        "timeoutSec": {"type": "integer", "description": "Process timeout in seconds."},
                    },
                    "required": ["scriptPath"],
                    "additionalProperties": False,
                },
            },
        ),
        (
            "run_lua_inline",
            {
                "category": "lua",
                "summary": "Run caller-supplied MAME Lua source (string, not a path) headlessly; optionally read back an artifact file.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "lua": {"type": "string", "description": "Lua source to run as an autoboot script."},
                        **COMMON_MACHINE_PROPS,
                        "frames": {"type": "integer", "description": "Frame budget for safety seconds.", "default": 60},
                        "artifactPath": {"type": "string", "description": "Optional file the script writes; its text is returned."},
                        "timeoutSec": {"type": "integer", "description": "Process timeout in seconds."},
                    },
                    "required": ["lua"],
                    "additionalProperties": False,
                },
            },
        ),
        (
            "capture_leaf_io",
            {
                "category": "trace",
                "summary": "Golden-vector capture for a pure leaf that transforms one memory word/byte in place (RNG/counter/accumulator). Injects inputs via taps, records output + regs + CCR. Independent oracle for the transpiler differential harness.",
                "schema": {
                    "type": "object",
                    "properties": {
                        **COMMON_MACHINE_PROPS,
                        "entryPc": {"type": "integer", "description": "Function entry address (e.g. 0x412)."},
                        "varAddress": {"type": "integer", "description": "Absolute address of the in/out word the leaf reads then writes (e.g. 0xF0170E)."},
                        "width": {"type": "integer", "description": "Operand width in bytes: 1 or 2.", "default": 2},
                        "pcLow": {"type": "integer", "description": "Low PC bound identifying 'inside this function' (default entryPc-2)."},
                        "pcHigh": {"type": "integer", "description": "High PC bound (default entryPc+0x40)."},
                        "inputs": {
                            "type": "array",
                            "description": "Test input values to inject (integers).",
                            "items": {"type": "integer"},
                        },
                        "regs": {
                            "type": "array",
                            "description": "Register names to capture at write-back (e.g. [\"D7\"]).",
                            "items": {"type": "string"},
                        },
                        "frameCap": {"type": "integer", "description": "Max frames to run before giving up.", "default": 1500},
                        "logPath": {"type": "string", "description": "Optional output log path."},
                        "timeoutSec": {"type": "integer", "description": "Process timeout in seconds."},
                    },
                    "required": ["entryPc", "varAddress", "inputs"],
                    "additionalProperties": False,
                },
            },
        ),
        # ---- persistent live session (Mesen-MCP-style control of one long-lived MAME) ----
        (
            "mame_launch",
            {
                "category": "live",
                "summary": "Launch a PERSISTENT live MAME (headless + bridge) and keep it running across tool calls. Required before any other mame_* live tool.",
                "schema": {
                    "type": "object",
                    "properties": {
                        **COMMON_MACHINE_PROPS,
                        "stateDirectory": {"type": "string", "description": "MAME -state_directory (enables load/save state)."},
                        "bootWait": {"type": "number", "description": "Seconds to wait for the bridge to become ready.", "default": 25},
                    },
                    "additionalProperties": False,
                },
            },
        ),
        ("mame_session_stop", {"category": "live", "summary": "Terminate the live MAME session.",
            "schema": {**JSON_OBJECT, "properties": {}}}),
        ("mame_session_status", {"category": "live", "summary": "Live session status (system, frame, paused).",
            "schema": {**JSON_OBJECT, "properties": {}}}),
        ("mame_pause", {"category": "live", "summary": "Pause the live machine (state stays readable).",
            "schema": {**JSON_OBJECT, "properties": {}}}),
        ("mame_resume", {"category": "live", "summary": "Resume the live machine.",
            "schema": {**JSON_OBJECT, "properties": {}}}),
        ("mame_run_frames", {"category": "live", "summary": "Run N frames then pause; returns the frame number.",
            "schema": {"type": "object", "properties": {"n": {"type": "integer", "description": "Frames to advance."}}, "required": ["n"], "additionalProperties": False}}),
        ("mame_load_state", {"category": "live", "summary": "Load a MAME save state by name (needs stateDirectory). Apply with a run_frames after.",
            "schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False}}),
        ("mame_save_state", {"category": "live", "summary": "Save a MAME save state by name.",
            "schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False}}),
        ("mame_get_regs", {"category": "live", "summary": "Read all CPU state registers (D0-D7,A0-A7,PC,SR,USP,...).",
            "schema": {"type": "object", "properties": {"device": {"type": "string", "default": ":maincpu"}}, "additionalProperties": False}}),
        ("mame_set_reg", {"category": "live", "summary": "Set one CPU register.",
            "schema": {"type": "object", "properties": {"reg": {"type": "string"}, "value": {"type": "integer"}, "device": {"type": "string", "default": ":maincpu"}}, "required": ["reg", "value"], "additionalProperties": False}}),
        ("mame_read_memory", {"category": "live", "summary": "Read a memory block (hex) from a device's program space.",
            "schema": {"type": "object", "properties": {"addr": {"type": "integer"}, "len": {"type": "integer"}, "space": {"type": "string", "default": ":maincpu"}}, "required": ["addr", "len"], "additionalProperties": False}}),
        ("mame_write_memory", {"category": "live", "summary": "Write a hex block to a device's program space.",
            "schema": {"type": "object", "properties": {"addr": {"type": "integer"}, "hex": {"type": "string"}, "space": {"type": "string", "default": ":maincpu"}}, "required": ["addr", "hex"], "additionalProperties": False}}),
        ("mame_send_input", {"category": "live", "summary": "Set an ioport field value (e.g. 'Coin 1', 'P1 Right').",
            "schema": {"type": "object", "properties": {"field": {"type": "string"}, "value": {"type": "integer"}}, "required": ["field", "value"], "additionalProperties": False}}),
        ("mame_capture_game_tick", {"category": "live", "summary": "Run to the Nth GAME_TICK ($3A92) and snapshot regs + a memory region AT the prologue read (lockstep regsA/wramA primitive; entry a7 = SP+60).",
            "schema": {"type": "object", "properties": {"addr": {"type": "integer"}, "len": {"type": "integer"}, "nth": {"type": "integer", "default": 1}, "timeout": {"type": "number", "default": 60}}, "required": ["addr", "len"], "additionalProperties": False}}),
        ("mame_run_until_pc_and_step", {"category": "live", "summary": "Run to a filtered PC, then capture exactly one instruction before and after execution.",
            "schema": {"type": "object", "properties": SINGLE_STEP_PROPS, "required": ["targetPc"], "additionalProperties": False}}),
        ("mame_run_from_reset_until_pc_and_step", {"category": "live", "summary": "Reset organically, run to a filtered PC, then capture exactly one instruction before and after execution.",
            "schema": {"type": "object", "properties": SINGLE_STEP_PROPS, "required": ["targetPc"], "additionalProperties": False}}),
        ("mame_run_from_reset_until_pc_and_trace", {"category": "live", "summary": "Reset organically, stop at a filtered PC, then return a bounded same-lifecycle instruction-boundary transcript with registers and requested memory.",
            "schema": {"type": "object", "properties": {"targetPc": {"type": "integer"}, "count": {"type": "integer", "minimum": 1, "maximum": 512, "default": 1}, "memory": {"type": "array", "items": {"type": "object", "properties": {"addr": {"type": "integer"}, "len": {"type": "integer"}}, "required": ["addr"], "additionalProperties": False}}, "expectedSp": {"type": "integer"}, "expectedRegs": {"type": "object", "additionalProperties": {"type": "integer"}}, "cpuTag": {"type": "string", "default": ":maincpu"}}, "required": ["targetPc"], "additionalProperties": False}}),
        ("mame_drive_to_gameplay", {"category": "live", "summary": "BOOT-AWARE drive to a running game: wait for the $0818 idle (boot done), inject clean coin/start EDGES, confirm GAME_TICK. Replay-robust where a fixed-frame .inp desyncs (the C-Chip boot handshake isn't bit-reproducible).",
            "schema": {"type": "object", "properties": {"coin": {"type": "string", "default": "Coin 1"}, "start": {"type": "string", "default": "1 Player Start"}, "credits": {"type": "integer", "default": 1}}, "additionalProperties": False}}),
        ("mame_exec_lua_live", {"category": "live", "summary": "Run Lua on the live machine (vars M/machine = manager.machine); returns its value.",
            "schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"], "additionalProperties": False}}),
    ]
)


CATEGORY_BLURBS = {
    "state": "Bridge lifecycle and configuration.",
    "machine": "MAME machine metadata and ROM audit helpers.",
    "trace": "Generated Lua trace harnesses for arcade reverse engineering.",
    "lua": "Escape hatch for hand-written MAME Lua scripts.",
    "live": "Persistent live-session control of one long-lived MAME (load state, step, read/write regs+memory, capture).",
}


def tool_descriptions() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": info["summary"],
            "inputSchema": info["schema"],
        }
        for name, info in TOOLS.items()
    ]


def _iter_filtered(category: str | None, needle: str | None) -> list[tuple[str, dict[str, Any]]]:
    rows = []
    for name, info in TOOLS.items():
        if category and info["category"] != category:
            continue
        hay = f"{name} {info['summary']}".lower()
        if needle and needle.lower() not in hay:
            continue
        rows.append((name, info))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List the mame_mcp tool surface.")
    parser.add_argument("--names", action="store_true", help="Print tool names only.")
    parser.add_argument("--category", help="Filter by category.")
    parser.add_argument("--filter", help="Filter by substring.")
    args = parser.parse_args(argv)

    rows = _iter_filtered(args.category, args.filter)
    if args.names:
        for name, _ in rows:
            print(name)
        return 0

    print(f"mame_mcp tool surface ({len(rows)} of {len(TOOLS)} tools)")
    print("=" * 60)
    current = None
    for name, info in rows:
        category = info["category"]
        if category != current:
            current = category
            print()
            print(f"[{category}]  {CATEGORY_BLURBS.get(category, '')}")
        print(f"  {name:22} {info['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
