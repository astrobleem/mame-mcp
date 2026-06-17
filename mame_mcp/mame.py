"""MAME process helpers and generated Lua trace harnesses."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


class MameMcpError(RuntimeError):
    """Raised for configuration or MAME execution failures."""


def _tail(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _lua_quote(value: str | Path) -> str:
    text = str(value).replace("\\", "/")
    return json.dumps(text)


def _hex(value: int) -> str:
    return f"0x{value:X}"


def _coerce_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise MameMcpError(f"{name} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise MameMcpError(f"{name} must be an integer")


def resolve_config(args: dict[str, Any] | None = None) -> dict[str, Any]:
    args = args or {}
    mame_exe = str(args.get("mameExe") or os.environ.get("MAME_EXE") or "mame")
    system = args.get("system") or os.environ.get("MAME_SYSTEM")
    rompath = args.get("rompath") or os.environ.get("MAME_ROMPATH")
    cwd = Path(args.get("cwd") or os.environ.get("MAME_CWD") or os.getcwd()).resolve()
    workdir = Path(args.get("workdir") or os.environ.get("MAME_WORKDIR") or cwd / ".mame_mcp").resolve()

    found_exe = shutil.which(mame_exe) if not Path(mame_exe).exists() else str(Path(mame_exe))
    return {
        "mameExe": mame_exe,
        "mameExeResolved": found_exe,
        "mameExeExists": bool(found_exe),
        "system": system,
        "rompath": rompath,
        "rompathExists": bool(rompath and Path(rompath).exists()),
        "cwd": str(cwd),
        "cwdExists": cwd.exists(),
        "workdir": str(workdir),
    }


def config_check(args: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = resolve_config(args)
    cfg["okForMameLaunch"] = bool(cfg["mameExeExists"] and cfg["system"])
    cfg["notes"] = []
    if not cfg["mameExeExists"]:
        cfg["notes"].append("MAME executable not found. Set MAME_EXE or put mame on PATH.")
    if not cfg["system"]:
        cfg["notes"].append("No default system configured. Set MAME_SYSTEM or pass a system argument.")
    if cfg["rompath"] and not cfg["rompathExists"]:
        cfg["notes"].append("MAME_ROMPATH is set but does not exist.")
    return cfg


def _require_launch_config(args: dict[str, Any]) -> tuple[str, str, str | None, Path, Path]:
    cfg = resolve_config(args)
    if not cfg["mameExeExists"]:
        raise MameMcpError(f"MAME executable not found: {cfg['mameExe']}")
    if not cfg["system"]:
        raise MameMcpError("MAME system is required; pass `system` or set MAME_SYSTEM")
    cwd = Path(cfg["cwd"])
    if not cwd.exists():
        raise MameMcpError(f"MAME working directory not found: {cwd}")
    workdir = Path(cfg["workdir"])
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "nvram").mkdir(exist_ok=True)
    (workdir / "cfg").mkdir(exist_ok=True)
    return str(cfg["mameExeResolved"]), str(cfg["system"]), cfg["rompath"], cwd, workdir


def _run(args: list[str], cwd: Path, timeout_sec: int, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
    env = os.environ.copy()
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    if extra_env:
        env.update(extra_env)
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        raise MameMcpError(f"MAME timed out after {timeout_sec}s") from exc
    return {
        "command": args,
        "cwd": str(cwd),
        "returnCode": proc.returncode,
        "stdoutTail": _tail(proc.stdout),
        "stderrTail": _tail(proc.stderr),
    }


def audit_romset(args: dict[str, Any]) -> dict[str, Any]:
    mame, system, rompath, cwd, _workdir = _require_launch_config(args)
    timeout_sec = int(args.get("timeoutSec") or 60)
    cmd = [mame]
    if rompath:
        cmd.extend(["-rompath", str(rompath)])
    cmd.extend(["-verifyroms", system])
    result = _run(cmd, cwd, timeout_sec)
    result["ok"] = result["returnCode"] == 0
    return result


def _safety_seconds(frames: int) -> int:
    return max(5, int(frames / 60) + 5)


def _run_mame_script(
    args: dict[str, Any],
    script_path: Path,
    frames: int,
    timeout_sec: int | None = None,
) -> dict[str, Any]:
    mame, system, rompath, cwd, workdir = _require_launch_config(args)
    seconds = _safety_seconds(frames)
    cmd = [mame, system]
    if rompath:
        cmd.extend(["-rompath", str(rompath)])
    cmd.extend(
        [
            "-video",
            "none",
            "-sound",
            "none",
            "-nothrottle",
            "-skip_gameinfo",
            "-seconds_to_run",
            str(seconds),
            "-autoboot_script",
            str(script_path),
            "-autoboot_delay",
            "0",
            "-nvram_directory",
            str(workdir / "nvram"),
            "-cfg_directory",
            str(workdir / "cfg"),
        ]
    )
    return _run(cmd, cwd, timeout_sec or seconds + 30)


def _lua_range_table(ranges: list[dict[str, Any]]) -> str:
    rows = []
    for i, item in enumerate(ranges):
        start = _coerce_int(item["start"], f"ranges[{i}].start")
        end = _coerce_int(item["end"], f"ranges[{i}].end")
        if end < start:
            raise MameMcpError(f"ranges[{i}].end must be >= start")
        name = item.get("name") or f"range{i}"
        rows.append(f"    {{ name = {_lua_quote(name)}, start = {_hex(start)}, stop = {_hex(end)} }},")
    return "\n".join(rows)


def _lua_track_table(track_reads: list[dict[str, Any]]) -> str:
    rows = []
    for i, item in enumerate(track_reads):
        address = _coerce_int(item["address"], f"trackReads[{i}].address")
        name = item.get("name") or f"track{i}"
        rows.append(f"    {{ name = {_lua_quote(name)}, address = {_hex(address)} }},")
    return "\n".join(rows)


def _build_trace_lua(
    frames: int,
    log_path: Path,
    ranges: list[dict[str, Any]],
    track_reads: list[dict[str, Any]],
    inject_preset: str,
) -> str:
    if inject_preset not in ("none", "coin_start"):
        raise MameMcpError("injectPreset must be `none` or `coin_start`")
    return f"""-- Generated by mame_mcp. Installs read/write taps and dumps a deduped table.
local CONFIG = {{
  frames = {frames},
  log_path = {_lua_quote(log_path)},
  inject_preset = {_lua_quote(inject_preset)},
  ranges = {{
{_lua_range_table(ranges)}
  }},
  track_reads = {{
{_lua_track_table(track_reads)}
  }},
}}

local log = assert(io.open(CONFIG.log_path, "w"))
local function w(s) log:write(s .. "\\n"); log:flush() end

local seen = {{}}
local order = {{}}
local tracked = {{}}
local frame = 0
local cpu = manager.machine.devices[":maincpu"]
local prog = cpu.spaces["program"]
MAME_MCP_TAPS = {{}}

local function pc()
  local ok, v = pcall(function() return cpu.state["PC"].value end)
  return ok and v or 0
end

local function record(rw, range_name, addr, data)
  local curpc = pc()
  local key = string.format("%s:%06X:%06X:%s", rw, curpc, addr, range_name)
  if not seen[key] then
    seen[key] = {{ count = 0, last = data, pc = curpc, addr = addr, rw = rw, range = range_name }}
    order[#order + 1] = key
  end
  seen[key].count = seen[key].count + 1
  seen[key].last = data

  if rw == "R" then
    for _, t in ipairs(CONFIG.track_reads) do
      if addr == t.address then
        local bucket = tracked[t.name] or {{ address = t.address, values = {{}} }}
        bucket.values[data] = (bucket.values[data] or 0) + 1
        tracked[t.name] = bucket
      end
    end
  end
end

for _, r in ipairs(CONFIG.ranges) do
  local range_name = r.name
  MAME_MCP_TAPS[#MAME_MCP_TAPS + 1] = prog:install_read_tap(r.start, r.stop, "mame_mcp_" .. range_name .. "_r",
    function(offset, data, mask) record("R", range_name, offset, data & 0xff); return data end)
  MAME_MCP_TAPS[#MAME_MCP_TAPS + 1] = prog:install_write_tap(r.start, r.stop, "mame_mcp_" .. range_name .. "_w",
    function(offset, data, mask) record("W", range_name, offset, data & 0xff); return data end)
end

local function find_field(namesub)
  for _, port in pairs(manager.machine.ioport.ports) do
    for fname, field in pairs(port.fields) do
      if fname:find(namesub, 1, true) then return field end
    end
  end
end

local function setfield(field, v) if field then field:set_value(v) end end
local coin, start
local schedule = {{
  [240] = function() w("# inject: COIN1 down"); setfield(coin, 1) end,
  [260] = function() setfield(coin, 0); w("# inject: COIN1 up") end,
  [320] = function() w("# inject: COIN1 down 2"); setfield(coin, 1) end,
  [340] = function() setfield(coin, 0) end,
  [460] = function() w("# inject: START1 down"); setfield(start, 1) end,
  [490] = function() setfield(start, 0); w("# inject: START1 up") end,
}}

local function dump_and_exit()
  for _, key in ipairs(order) do
    local e = seen[key]
    w(string.format("%s   %06X   %06X   %-16s %5d   $%02X", e.rw, e.pc, e.addr, e.range, e.count, e.last))
  end

  w("")
  w("# MAME_MCP_SUMMARY_BEGIN")
  w(string.format("# unique_accesses %d", #order))
  for _, t in ipairs(CONFIG.track_reads) do
    local bucket = tracked[t.name]
    w(string.format("# track %s $%06X", t.name, t.address))
    if bucket then
      for value, count in pairs(bucket.values) do
        w(string.format("#   $%02X read %d times", value, count))
      end
    end
  end
  w("# MAME_MCP_SUMMARY_END")
  log:close()
  manager.machine:exit()
end

local function on_frame()
  frame = frame + 1
  if CONFIG.inject_preset == "coin_start" then
    if frame == 1 then
      coin = find_field("Coin 1")
      start = find_field("1 Player Start") or find_field("P1 Start")
      w(string.format("# inject enabled: coin=%s start=%s", tostring(coin ~= nil), tostring(start ~= nil)))
    end
    local act = schedule[frame]
    if act then act() end
  end
  if frame >= CONFIG.frames then dump_and_exit() end
end

w("# mame_mcp memory access trace")
w(string.format("# frames %d", CONFIG.frames))
for _, r in ipairs(CONFIG.ranges) do
  w(string.format("# range %s $%06X-$%06X", r.name, r.start, r.stop))
end

if emu.register_frame_done then emu.register_frame_done(on_frame)
elseif emu.register_frame then emu.register_frame(on_frame)
else error("MAME Lua frame callback API unavailable") end
"""


ACCESS_RE = re.compile(
    r"^(?P<rw>[RW])\s+(?P<pc>[0-9A-F]+)\s+(?P<addr>[0-9A-F]+)\s+"
    r"(?P<range>\S+)\s+(?P<count>\d+)\s+\$(?P<last>[0-9A-F]{2})$"
)
TRACK_RE = re.compile(r"^# track (?P<name>\S+) \$(?P<addr>[0-9A-F]+)$")
VALUE_RE = re.compile(r"^#\s+\$(?P<value>[0-9A-F]{2}) read (?P<count>\d+) times$")


def parse_trace_log(log_path: Path) -> dict[str, Any]:
    if not log_path.exists():
        return {"logExists": False, "uniqueAccesses": 0, "trackReads": {}}
    track_reads: dict[str, Any] = {}
    access_count = 0
    current_track: str | None = None
    for raw in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        access = ACCESS_RE.match(raw)
        if access:
            access_count += 1
            continue
        track = TRACK_RE.match(raw)
        if track:
            current_track = track.group("name")
            track_reads[current_track] = {
                "address": int(track.group("addr"), 16),
                "values": {},
            }
            continue
        value = VALUE_RE.match(raw)
        if value and current_track:
            track_reads[current_track]["values"][value.group("value")] = int(value.group("count"))
    return {
        "logExists": True,
        "uniqueAccesses": access_count,
        "trackReads": track_reads,
    }


def trace_memory_access(args: dict[str, Any]) -> dict[str, Any]:
    frames = _coerce_int(args.get("frames", 1800), "frames")
    if frames <= 0:
        raise MameMcpError("frames must be positive")
    ranges = args.get("ranges") or []
    if not ranges:
        raise MameMcpError("ranges is required for trace_memory_access")
    track_reads = args.get("trackReads") or []
    inject_preset = str(args.get("injectPreset") or "none")

    if bool(args.get("dryRun")):
        cfg = resolve_config(args)
        system = str(cfg["system"] or "mame")
        workdir = Path(cfg["workdir"])
        workdir.mkdir(parents=True, exist_ok=True)
    else:
        _mame, system, _rompath, _cwd, workdir = _require_launch_config(args)

    log_path = Path(args.get("logPath") or workdir / f"{system}_trace_{_stamp()}.log").resolve()
    script_path = workdir / f"{system}_trace_{_stamp()}.lua"
    script_path.write_text(
        _build_trace_lua(frames, log_path, ranges, track_reads, inject_preset),
        encoding="utf-8",
    )
    if bool(args.get("dryRun")):
        return {
            "ok": True,
            "dryRun": True,
            "scriptPath": str(script_path),
            "logPath": str(log_path),
            "frames": frames,
            "injectPreset": inject_preset,
        }
    result = _run_mame_script(args, script_path, frames, args.get("timeoutSec"))
    result.update(
        {
            "scriptPath": str(script_path),
            "logPath": str(log_path),
            "frames": frames,
            "injectPreset": inject_preset,
            "trace": parse_trace_log(log_path),
        }
    )
    result["ok"] = bool(result["trace"]["logExists"])
    return result


def trace_cchip_superman(args: dict[str, Any]) -> dict[str, Any]:
    merged = dict(args)
    merged.setdefault("system", "superman")
    merged.setdefault("ranges", [{"name": "cchip", "start": 0x900000, "end": 0x900FFF}])
    merged.setdefault(
        "trackReads",
        [
            {"name": "status_900802", "address": 0x900802},
            {"name": "status_900803", "address": 0x900803},
        ],
    )
    result = trace_memory_access(merged)
    if result.get("dryRun"):
        result["cchipStatus"] = {
            "values": {},
            "saw01Ok": False,
            "saw05ErrorHang": False,
            "verdict": "dryRun: MAME was not launched; no $900803 values observed",
        }
        return result

    values: dict[str, int] = {}
    for track in result["trace"].get("trackReads", {}).values():
        for value, count in track.get("values", {}).items():
            values[value] = values.get(value, 0) + count
    saw_01 = values.get("01", 0) > 0
    saw_05 = values.get("05", 0) > 0
    result["cchipStatus"] = {
        "values": values,
        "saw01Ok": saw_01,
        "saw05ErrorHang": saw_05,
        "verdict": f"status $01(OK) seen={str(saw_01).lower()} ; status $05(ERROR/hang) seen={str(saw_05).lower()}",
    }
    return result


def _build_ioports_lua(log_path: Path) -> str:
    return f"""local log = assert(io.open({_lua_quote(log_path)}, "w"))
local function w(s) log:write(s .. "\\n"); log:flush() end
w("# mame_mcp ioport list")
for tag, port in pairs(manager.machine.ioport.ports) do
  for fname, field in pairs(port.fields) do
    w(string.format("PORT\\t%s\\tFIELD\\t%s", tostring(tag), tostring(fname)))
  end
end
log:close()
manager.machine:exit()
"""


def get_ioports(args: dict[str, Any]) -> dict[str, Any]:
    _mame, system, _rompath, _cwd, workdir = _require_launch_config(args)
    log_path = Path(args.get("logPath") or workdir / f"{system}_ioports_{_stamp()}.log").resolve()
    script_path = workdir / f"{system}_ioports_{_stamp()}.lua"
    script_path.write_text(_build_ioports_lua(log_path), encoding="utf-8")
    result = _run_mame_script(args, script_path, 1, args.get("timeoutSec") or 30)
    fields = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split("\t")
            if len(parts) == 4 and parts[0] == "PORT" and parts[2] == "FIELD":
                fields.append({"port": parts[1], "field": parts[3]})
    result.update({"scriptPath": str(script_path), "logPath": str(log_path), "fields": fields, "ok": log_path.exists()})
    return result


def run_lua_script(args: dict[str, Any]) -> dict[str, Any]:
    script = Path(str(args.get("scriptPath", ""))).resolve()
    if not script.exists():
        raise MameMcpError(f"Lua script not found: {script}")
    frames = _coerce_int(args.get("frames", 60), "frames")
    result = _run_mame_script(args, script, frames, args.get("timeoutSec"))
    result.update({"scriptPath": str(script), "frames": frames, "ok": result["returnCode"] == 0})
    return result


def run_lua_inline(args: dict[str, Any]) -> dict[str, Any]:
    """Run caller-supplied Lua *source* (not a path) headlessly.

    The universal escape hatch: write `lua` to a temp autoboot script, run MAME,
    and return stdout/stderr tails. If `artifactPath` is given, its text content
    is read back and returned in `artifact`.
    """
    lua = args.get("lua")
    if not isinstance(lua, str) or not lua.strip():
        raise MameMcpError("`lua` (Lua source string) is required")
    _mame, system, _rompath, _cwd, workdir = _require_launch_config(args)
    frames = _coerce_int(args.get("frames", 60), "frames")
    script_path = workdir / f"{system}_inline_{_stamp()}.lua"
    script_path.write_text(lua, encoding="utf-8")
    result = _run_mame_script(args, script_path, frames, args.get("timeoutSec"))
    artifact_path = args.get("artifactPath")
    artifact = None
    if artifact_path and Path(artifact_path).exists():
        artifact = _tail(Path(artifact_path).read_text(encoding="utf-8", errors="replace"), 200000)
    result.update({
        "scriptPath": str(script_path),
        "frames": frames,
        "artifactPath": str(artifact_path) if artifact_path else None,
        "artifact": artifact,
        "ok": result["returnCode"] == 0,
    })
    return result


def _build_leaf_capture_lua(
    log_path: Path,
    entry_pc: int,
    pc_low: int,
    pc_high: int,
    var_addr: int,
    width: int,
    inputs: list[int],
    regs: list[str],
    frame_cap: int,
) -> str:
    mask = (1 << (8 * width)) - 1
    fw = width * 2  # hex digits for the value width
    inputs_lua = ", ".join(_hex(v & mask) for v in inputs)
    regs_lua = ", ".join(_lua_quote(r) for r in regs)
    return f"""-- Generated by mame_mcp capture_leaf_io. Injects test inputs on the leaf's
-- read of the target word and captures the value it writes back, plus selected
-- registers and CCR. No debugger; full speed. Taps/subscriptions kept in a
-- global table so MAME does not GC them.
MAME_MCP_KEEP = {{}}
local cpu  = manager.machine.devices[":maincpu"]
local prog = cpu.spaces["program"]
local VAR   = {_hex(var_addr)}
local WIDTH = {width}
local MASK  = {_hex(mask)}
local PCLO, PCHI = {_hex(pc_low)}, {_hex(pc_high)}
local ENTRY = {_hex(entry_pc)}
local inputs = {{ {inputs_lua} }}
local regs = {{ {regs_lua} }}
local idx, pending, done = 1, inputs[1], false
local nread, nwrite = 0, 0
local log = assert(io.open({_lua_quote(log_path)}, "w"))
log:write(string.format("# entry=%06X var=%06X width=%d\\n", ENTRY, VAR, WIDTH))
log:write("# input output " .. table.concat(regs, " ") .. " ccr\\n")
log:flush()

local function in_func()
  local ok, v = pcall(function() return cpu.state["PC"].value end)
  if not ok then return false end
  v = v & 0xFFFFFF
  return v >= PCLO and v <= PCHI
end

MAME_MCP_KEEP[#MAME_MCP_KEEP+1] = prog:install_read_tap(VAR, VAR + WIDTH - 1, "leaf_in",
  function(offset, data, mask)
    if done then return data end
    if in_func() then nread = nread + 1; return pending & MASK end
    return data
  end)

MAME_MCP_KEEP[#MAME_MCP_KEEP+1] = prog:install_write_tap(VAR, VAR + WIDTH - 1, "leaf_out",
  function(offset, data, mask)
    if done then return data end
    if in_func() then
      nwrite = nwrite + 1
      local parts = {{}}
      for _, rn in ipairs(regs) do
        local ok, rv = pcall(function() return cpu.state[rn].value end)
        parts[#parts+1] = string.format("%08X", (ok and rv or 0) & 0xFFFFFFFF)
      end
      local ok2, sr = pcall(function() return cpu.state["SR"].value end)
      local ccr = (ok2 and sr or 0) & 0x1F
      log:write(string.format("%0{fw}X %0{fw}X %s %02X\\n",
        pending & MASK, data & MASK, table.concat(parts, " "), ccr))
      log:flush()
      idx = idx + 1
      if idx > #inputs then
        done = true
        log:write(string.format("# CAP done captured=%d reads=%d writes=%d\\n", idx-1, nread, nwrite))
        log:close()
      else
        pending = inputs[idx]
      end
    end
    return data
  end)

local fcount = 0
local function on_frame()
  fcount = fcount + 1
  if done or fcount >= {frame_cap} then
    if not done then
      log:write(string.format("# CAP timeout captured=%d reads=%d writes=%d frames=%d\\n",
        idx-1, nread, nwrite, fcount))
      log:close()
    end
    manager.machine:exit()
  end
end
if emu.register_frame_done then MAME_MCP_KEEP[#MAME_MCP_KEEP+1] = emu.register_frame_done(on_frame)
elseif emu.register_frame then MAME_MCP_KEEP[#MAME_MCP_KEEP+1] = emu.register_frame(on_frame)
else error("MAME Lua frame callback API unavailable") end
"""


_LEAF_LINE = re.compile(r"^(?P<input>[0-9A-F]+)\s+(?P<output>[0-9A-F]+)\s+(?P<rest>.*?)\s+(?P<ccr>[0-9A-F]{2})$")


def _parse_leaf_log(log_path: Path, regs: list[str], width: int) -> dict[str, Any]:
    if not log_path.exists():
        return {"logExists": False, "vectors": [], "complete": False}
    vectors: list[dict[str, Any]] = []
    complete = False
    captured = None
    for raw in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if raw.startswith("# CAP done"):
            complete = True
        if raw.startswith("#"):
            continue
        m = _LEAF_LINE.match(raw.strip())
        if not m:
            continue
        rest = m.group("rest").split()
        regvals = {}
        for i, rn in enumerate(regs):
            if i < len(rest):
                regvals[rn] = int(rest[i], 16)
        vectors.append({
            "input": int(m.group("input"), 16),
            "output": int(m.group("output"), 16),
            "regs": regvals,
            "ccr": int(m.group("ccr"), 16),
        })
    return {"logExists": True, "vectors": vectors, "complete": complete, "count": len(vectors)}


def capture_leaf_io(args: dict[str, Any]) -> dict[str, Any]:
    """Capture golden I/O vectors for a PURE LEAF function that transforms one
    memory word/byte in place (RNGs, counters, accumulators).

    Drives the function at full speed via memory taps: on the leaf's read of
    `varAddress` it substitutes the next test input; on the write-back it records
    the output plus selected `regs` and CCR. The leaf's own code runs in MAME, so
    this is an independent oracle for the transpiler differential harness (G2).
    """
    entry_pc = _coerce_int(args["entryPc"], "entryPc")
    var_addr = _coerce_int(args["varAddress"], "varAddress")
    width = _coerce_int(args.get("width", 2), "width")
    if width not in (1, 2):
        raise MameMcpError("width must be 1 or 2")
    pc_low = _coerce_int(args.get("pcLow", entry_pc - 2), "pcLow")
    pc_high = _coerce_int(args.get("pcHigh", entry_pc + 0x40), "pcHigh")
    inputs_raw = args.get("inputs")
    if not isinstance(inputs_raw, list) or not inputs_raw:
        raise MameMcpError("`inputs` (non-empty list of integers) is required")
    inputs = [_coerce_int(v, "inputs[]") for v in inputs_raw]
    regs = [str(r) for r in (args.get("regs") or [])]
    frame_cap = _coerce_int(args.get("frameCap", 1500), "frameCap")

    _mame, system, _rompath, _cwd, workdir = _require_launch_config(args)
    log_path = Path(args.get("logPath") or workdir / f"{system}_leaf_{entry_pc:06X}_{_stamp()}.log").resolve()
    script_path = workdir / f"{system}_leaf_{entry_pc:06X}_{_stamp()}.lua"
    script_path.write_text(
        _build_leaf_capture_lua(log_path, entry_pc, pc_low, pc_high, var_addr, width, inputs, regs, frame_cap),
        encoding="utf-8",
    )
    # frame budget for safety-seconds: cap drives runtime
    result = _run_mame_script(args, script_path, frame_cap, args.get("timeoutSec"))
    parsed = _parse_leaf_log(log_path, regs, width)
    result.update({
        "scriptPath": str(script_path),
        "logPath": str(log_path),
        "entryPc": entry_pc,
        "varAddress": var_addr,
        "width": width,
        "regs": regs,
        "capture": parsed,
        "ok": parsed["complete"],
    })
    return result
