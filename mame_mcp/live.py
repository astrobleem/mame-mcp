"""Persistent live-session MCP handlers — hold ONE MameSession across tool calls so an MCP
client gets Mesen-MCP-style control of a live MAME (load state, step frames, read/write regs
+ memory, inject input, capture_game_tick) instead of one-shot script launches. The session
lives in this module's global and survives between tools/call requests on the stdio server.
"""
from __future__ import annotations

from typing import Any, Callable

from .mame import MameMcpError, resolve_config
from .session import MameError, MameSession

_SESSION: MameSession | None = None


def _require() -> MameSession:
    if _SESSION is None:
        raise MameMcpError("no live MAME session; call mame_launch first")
    return _SESSION


def _wrap(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except MameError as exc:
        raise MameMcpError(str(exc)) from exc


def mame_launch(args: dict[str, Any]) -> dict[str, Any]:
    """Launch a persistent live MAME (headless + bridge) and wait for it to be ready."""
    global _SESSION
    cfg = resolve_config(args)
    if not cfg["mameExeExists"]:
        raise MameMcpError(f"MAME executable not found: {cfg['mameExe']}")
    if not cfg["system"]:
        raise MameMcpError("MAME system required; pass `system` or set MAME_SYSTEM")
    if _SESSION is not None:
        _SESSION.stop()
    _SESSION = MameSession(
        mame=cfg["mameExeResolved"], system=cfg["system"], rompath=cfg["rompath"] or "roms",
        workdir=cfg["workdir"], state_directory=args.get("stateDirectory"),
    )
    _wrap(lambda: _SESSION.launch(boot_wait=float(args.get("bootWait", 25))))
    return {"launched": True, "workdir": cfg["workdir"], **_wrap(lambda: _SESSION.ping())}


def mame_session_stop(args: dict[str, Any]) -> dict[str, Any]:
    global _SESSION
    if _SESSION is not None:
        _SESSION.stop()
        _SESSION = None
    return {"stopped": True}


def mame_session_status(args): return _wrap(lambda: _require().status())
def mame_pause(args): return _wrap(lambda: _require().pause())
def mame_resume(args): return _wrap(lambda: _require().resume())
def mame_run_frames(args): return _wrap(lambda: _require().run_frames(int(args["n"])))
def mame_load_state(args): return _wrap(lambda: _require().load_state(args["name"]))
def mame_save_state(args): return _wrap(lambda: _require().save_state(args["name"]))
def mame_send_input(args): return _wrap(lambda: _require().send_input(args["field"], int(args["value"])))
def mame_exec_lua_live(args): return {"result": _wrap(lambda: _require().exec_lua(args["code"]))}


def mame_get_regs(args):
    return {"registers": _wrap(lambda: _require().get_regs(args.get("device", ":maincpu")))}


def mame_set_reg(args):
    return _wrap(lambda: _require().set_reg(args["reg"], int(args["value"]), args.get("device", ":maincpu")))


def mame_read_memory(args):
    addr, length = int(args["addr"]), int(args["len"])
    data = _wrap(lambda: _require().read_block(addr, length, args.get("space", ":maincpu")))
    return {"addr": addr, "len": length, "hex": data.hex()}


def mame_write_memory(args):
    return _wrap(lambda: _require().write_block(int(args["addr"]), args["hex"], args.get("space", ":maincpu")))


def mame_capture_game_tick(args):
    return _wrap(lambda: _require().cmd(
        "capture_game_tick", addr=int(args["addr"]), len=int(args["len"]),
        nth=int(args.get("nth", 1)), timeout=float(args.get("timeout", 60))))


def mame_drive_to_gameplay(args):
    return _wrap(lambda: _require().drive_to_gameplay(
        coin=args.get("coin", "Coin 1"), start=args.get("start", "1 Player Start"),
        credits=int(args.get("credits", 1))))


LIVE_HANDLERS = {
    "mame_launch": mame_launch,
    "mame_session_stop": mame_session_stop,
    "mame_session_status": mame_session_status,
    "mame_pause": mame_pause,
    "mame_resume": mame_resume,
    "mame_run_frames": mame_run_frames,
    "mame_load_state": mame_load_state,
    "mame_save_state": mame_save_state,
    "mame_get_regs": mame_get_regs,
    "mame_set_reg": mame_set_reg,
    "mame_read_memory": mame_read_memory,
    "mame_write_memory": mame_write_memory,
    "mame_send_input": mame_send_input,
    "mame_capture_game_tick": mame_capture_game_tick,
    "mame_drive_to_gameplay": mame_drive_to_gameplay,
    "mame_exec_lua_live": mame_exec_lua_live,
}
