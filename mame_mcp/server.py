"""Minimal stdio MCP server for mame_mcp."""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable

from . import __version__
from .mame import (
    MameMcpError,
    audit_romset,
    capture_leaf_io,
    config_check,
    get_ioports,
    run_lua_inline,
    run_lua_script,
    trace_cchip_superman,
    trace_memory_access,
)
from .tools import tool_descriptions


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]

HANDLERS: dict[str, ToolHandler] = {
    "ping": lambda args: {"pong": True, "echo": args.get("echo", args)},
    "config_check": config_check,
    "audit_romset": audit_romset,
    "get_ioports": get_ioports,
    "trace_memory_access": trace_memory_access,
    "trace_cchip_superman": trace_cchip_superman,
    "run_lua_script": run_lua_script,
    "run_lua_inline": run_lua_inline,
    "capture_leaf_io": capture_leaf_io,
}


def _log(message: str) -> None:
    sys.stderr.write(f"[mame-mcp] {message}\n")
    sys.stderr.flush()


def _write(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _result(request_id: Any, result: Any) -> None:
    _write({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id: Any, code: int, message: str, data: Any | None = None) -> None:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    _write({"jsonrpc": "2.0", "id": request_id, "error": err})


def _tool_result(payload: dict[str, Any], is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True)}],
        "isError": is_error,
    }


def _handle_tool_call(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    if not isinstance(name, str):
        return _tool_result({"error": "tools/call requires string param `name`"}, True)
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return _tool_result({"error": "tools/call param `arguments` must be an object"}, True)
    handler = HANDLERS.get(name)
    if handler is None:
        return _tool_result({"error": f"unknown tool: {name}"}, True)
    try:
        return _tool_result(handler(arguments))
    except MameMcpError as exc:
        return _tool_result({"error": str(exc)}, True)
    except Exception as exc:  # Keep stdio transport alive for diagnostics.
        _log(traceback.format_exc())
        return _tool_result({"error": str(exc), "type": type(exc).__name__}, True)


def _handle_request(message: dict[str, Any]) -> bool:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    # Notifications have no id. Ignore the standard initialized notification.
    if request_id is None:
        return True

    if method == "initialize":
        _result(
            request_id,
            {
                "protocolVersion": params.get("protocolVersion") or "2024-11-05",
                "serverInfo": {"name": "mame_mcp", "version": __version__},
                "capabilities": {"tools": {"listChanged": False}},
            },
        )
    elif method == "tools/list":
        _result(request_id, {"tools": tool_descriptions()})
    elif method == "tools/call":
        _result(request_id, _handle_tool_call(params))
    elif method == "shutdown":
        _result(request_id, None)
        return False
    else:
        _error(request_id, -32601, f"method not found: {method}")
    return True


def main() -> int:
    _log("stdio server starting")
    for line in sys.stdin:
        line = line.lstrip("\ufeffï»¿")
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                _error(None, -32600, "invalid request")
                continue
            if not _handle_request(message):
                break
        except json.JSONDecodeError as exc:
            _error(None, -32700, f"parse error: {exc}")
        except Exception as exc:
            _log(traceback.format_exc())
            _error(None, -32603, str(exc))
    _log("stdio server exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
