from pathlib import Path


BRIDGE = Path(__file__).resolve().parents[1] / "mame_mcp" / "bridge.lua"


def test_chained_trace_owns_one_deferred_debugger_lifecycle():
    text = BRIDGE.read_text()
    start = text.index('handlers.mame_run_from_reset_until_pc_and_trace')
    end = text.index('-- Handler: cold reset -> run until PC, capture state', start)
    handler = text[start:end]
    chain = text[text.index('elseif ctx.phase == "waiting_for_chain_step"'):text.index('elseif ctx.phase == "waiting_for_step"')]

    assert 'count > 512' in handler
    assert 'phase = "waiting_for_chain_breakpoint"' in handler
    assert 'start_chained_step(ctx, cpu)' in text
    assert 'ctx.rows = { snapshot_debug_state(cpu, ctx.memory) }' in text
    assert 'table.insert(ctx.rows, snapshot)' in text
    assert 'cpu.debug:step(1)' in chain
    assert 'cpu.debug:go()' not in chain
    assert 'emu.unpause()' not in chain


def test_public_catalog_exposes_chained_trace_and_single_steps():
    from mame_mcp.tools import tool_descriptions

    tools = {item["name"]: item for item in tool_descriptions()}
    assert "mame_run_from_reset_until_pc_and_trace" in tools
    assert "mame_run_until_pc_and_step" in tools
    assert "mame_run_from_reset_until_pc_and_step" in tools
    for name in ("mame_run_until_pc_and_step", "mame_run_from_reset_until_pc_and_step"):
        schema = tools[name]["inputSchema"]
        assert schema["required"] == ["targetPc"]
        assert {"targetPc", "expectedSp", "expectedRegs", "preStepRegs", "memory", "cpuTag"} <= set(schema["properties"])


def test_live_single_step_wrappers_translate_generic_filters(monkeypatch):
    import mame_mcp.live as live

    class FakeSession:
        def __init__(self):
            self.calls = []

        def mame_run_until_pc_and_step(self, **kwargs):
            self.calls.append(("until", kwargs))
            return {"ok": True}

        def mame_run_from_reset_until_pc_and_step(self, **kwargs):
            self.calls.append(("reset", kwargs))
            return {"ok": True}

    fake = FakeSession()
    monkeypatch.setattr(live, "_SESSION", fake)
    args = {
        "targetPc": 0x1413,
        "memory": [{"addr": 0xE000, "len": 2}],
        "expectedSp": 0xE480,
        "expectedRegs": {"AF": 0x1234},
        "preStepRegs": {"BC": 0x5678},
        "cpuTag": ":maincpu",
    }
    assert live.mame_run_until_pc_and_step(args) == {"ok": True}
    assert live.mame_run_from_reset_until_pc_and_step(args) == {"ok": True}
    assert fake.calls == [
        ("until", {"target_pc": 0x1413, "memory": [{"addr": 0xE000, "len": 2}],
                    "expected_sp": 0xE480, "expected_regs": {"AF": 0x1234},
                    "pre_step_regs": {"BC": 0x5678}, "cpu_tag": ":maincpu"}),
        ("reset", {"target_pc": 0x1413, "memory": [{"addr": 0xE000, "len": 2}],
                    "expected_sp": 0xE480, "expected_regs": {"AF": 0x1234},
                    "pre_step_regs": {"BC": 0x5678}, "cpu_tag": ":maincpu"}),
    ]
