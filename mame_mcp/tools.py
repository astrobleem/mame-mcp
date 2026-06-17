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
    ]
)


CATEGORY_BLURBS = {
    "state": "Bridge lifecycle and configuration.",
    "machine": "MAME machine metadata and ROM audit helpers.",
    "trace": "Generated Lua trace harnesses for arcade reverse engineering.",
    "lua": "Escape hatch for hand-written MAME Lua scripts.",
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
