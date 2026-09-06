from pathlib import Path

from mame_mcp.tools import TOOLS

BRIDGE = Path(__file__).resolve().parents[1] / "mame_mcp" / "bridge.lua"
LIVE = Path(__file__).resolve().parents[1] / "mame_mcp" / "live.py"
SESSION = Path(__file__).resolve().parents[1] / "mame_mcp" / "session.py"


def test_sparse_ledger_is_nonblocking_and_has_live_controls():
    text = BRIDGE.read_text()
    assert "handlers.mame_trace_pc_events_start" in text
    assert "handlers.mame_trace_pc_events_status" in text
    assert "handlers.mame_trace_pc_events_stop" in text
    assert "cpu.debug:go()" in text
    assert "sparse_ctx = ctx" in text
    assert "ctx.by_pc[pc]" in text
    assert "ev.event_sequence=#ctx.events+1" in text
    assert "ev.stack=read_memory(cpu, ev.sp" in text
    assert "sparse_cleanup(ctx)" in text
    assert "Continue below so status/stop commands remain serviceable" in text


def test_sparse_ledger_api_is_exposed_end_to_end():
    assert {"mame_trace_pc_events_start", "mame_trace_pc_events_status", "mame_trace_pc_events_stop"} <= TOOLS.keys()
    assert "trace_pc_events_start" in SESSION.read_text()
    live = LIVE.read_text()
    assert "def mame_trace_pc_events_start" in live
    assert '"mame_trace_pc_events_start": mame_trace_pc_events_start' in live


def test_sparse_ledger_schema_bounds_the_capture():
    schema = TOOLS["mame_trace_pc_events_start"]["schema"]
    props = schema["properties"]
    assert props["pcs"]["maxItems"] == 32
    assert props["capacity"]["maximum"] == 10000
    assert props["stackBytes"]["maximum"] == 64
    assert TOOLS["mame_trace_pc_events_status"]["schema"]["additionalProperties"] is False
    assert TOOLS["mame_trace_pc_events_stop"]["schema"]["additionalProperties"] is False


def test_sparse_ledger_validates_payload_and_deadline_in_bridge():
    text = BRIDGE.read_text()
    assert "#memory > 16" in text
    assert "memory_total > 256" in text
    assert "len > 64" in text
    assert "PC must be a 16-bit integer" in text
    assert "deadline must be a nonnegative frame number" in text
    assert "ctx.deadline > 0" in text
    assert "cleanup_errors" in text
