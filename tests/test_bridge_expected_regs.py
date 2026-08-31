from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "mame_mcp" / "bridge.lua"


def test_run_until_pc_carries_expected_register_filter_and_rejects_mismatch():
    text = BRIDGE.read_text()
    assert "expected_regs = p.expected_regs" in text
    assert "pre_step_regs = p.pre_step_regs" in text
    assert "for name, expected in pairs(ctx.expected_regs) do" in text
    assert "for name, value in pairs(ctx.pre_step_regs) do" in text
    assert "entry.value = value" in text
    assert "ctx.before = snapshot_debug_state(cpu, ctx.memory)" in text
    assert "cpu.debug:step(1)" in text
    assert "cpu.debug:go()" in text
