"""Persistent live MAME session for the MCP — launches MAME headless with the
in-process bridge (bridge.lua) and talks to it over file IPC (mame_cmd.json /
mame_rsp.json in the working dir). Gives Mesen-MCP-style control: pause, step
frames, read/write memory & registers, load/save state, inject input — all on a
single long-lived emulator instead of one-shot script launches.
"""
from __future__ import annotations
import json
import os
import subprocess
import time
from pathlib import Path

BRIDGE_LUA = Path(__file__).resolve().parent / "bridge.lua"


class MameError(RuntimeError):
    pass


class MameSession:
    def __init__(self, mame="mame", system="superman", rompath="roms", workdir=".",
                 state_directory=None, extra_args=None):
        self.mame = mame
        self.system = system
        self.rompath = rompath
        self.workdir = Path(workdir).resolve()
        self.state_directory = state_directory
        self.extra_args = extra_args or []
        self.proc = None
        self._seq = 0

    # ---- lifecycle ----
    def launch(self, boot_wait=20.0):
        self.workdir.mkdir(parents=True, exist_ok=True)
        for f in ("mame_cmd.json", "mame_rsp.json", "mame_bridge.ready"):
            (self.workdir / f).unlink(missing_ok=True)
        cmd = [self.mame, self.system, "-rompath", str(self.rompath),
               "-video", "none", "-sound", "none", "-nothrottle", "-skip_gameinfo",
               "-autoboot_script", str(BRIDGE_LUA), "-autoboot_delay", "0",
               "-nvram_directory", str(self.workdir / "nvram"),
               "-cfg_directory", str(self.workdir / "cfg")]
        if self.state_directory:
            cmd += ["-state_directory", str(self.state_directory)]
        cmd += self.extra_args
        env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
        self.proc = subprocess.Popen(cmd, cwd=str(self.workdir), env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ready = self.workdir / "mame_bridge.ready"
        t0 = time.time()
        while time.time() - t0 < boot_wait:
            if ready.exists():
                return self
            if self.proc.poll() is not None:
                raise MameError(f"MAME exited during boot (code {self.proc.returncode})")
            time.sleep(0.05)
        raise MameError("bridge did not become ready within %.0fs" % boot_wait)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def __enter__(self):
        return self.launch()

    def __exit__(self, *exc):
        self.stop()

    # ---- IPC ----
    def cmd(self, command, timeout=30.0, **params):
        self._seq += 1
        req = {"id": self._seq, "command": command, "params": params}
        cmd_file = self.workdir / "mame_cmd.json"
        rsp_file = self.workdir / "mame_rsp.json"
        tmp = self.workdir / "mame_cmd.json.tmp"
        rsp_file.unlink(missing_ok=True)
        tmp.write_text(json.dumps(req))
        os.replace(tmp, cmd_file)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if rsp_file.exists():
                try:
                    data = json.loads(rsp_file.read_text())
                except (json.JSONDecodeError, ValueError):
                    time.sleep(0.005); continue
                rsp_file.unlink(missing_ok=True)
                if data.get("status") != "ok":
                    raise MameError(f"{command}: {data.get('message')}")
                return data.get("result", {})
            if self.proc and self.proc.poll() is not None:
                raise MameError("MAME exited while awaiting response")
            time.sleep(0.005)
        raise MameError(f"timeout waiting for '{command}' response")

    # ---- convenience ----
    def ping(self): return self.cmd("ping")
    def status(self): return self.cmd("status")
    def pause(self): return self.cmd("pause")
    def resume(self): return self.cmd("resume")
    def run_frames(self, n, timeout=120.0): return self.cmd("run_frames", n=n, timeout=timeout)
    def load_state(self, name): return self.cmd("load_state", name=name)
    def save_state(self, name): return self.cmd("save_state", name=name)
    def send_input(self, field, value): return self.cmd("send_input", field=field, value=value)
    def list_inputs(self): return self.cmd("list_inputs")["fields"]
    def get_regs(self, device=":maincpu"): return self.cmd("get_regs", device=device)["registers"]
    def set_reg(self, reg, value, device=":maincpu"): return self.cmd("set_reg", reg=reg, value=value, device=device)
    def exec_lua(self, code): return self.cmd("exec_lua", code=code)["result"]

    def read_block(self, addr, length, space=":maincpu", timeout=30.0):
        return bytes.fromhex(self.cmd("read_block", addr=addr, len=length, space=space, timeout=timeout)["hex"])

    def write_block(self, addr, data, space=":maincpu"):
        hexs = data.hex() if isinstance(data, (bytes, bytearray)) else data
        return self.cmd("write_block", addr=addr, hex=hexs, space=space)
