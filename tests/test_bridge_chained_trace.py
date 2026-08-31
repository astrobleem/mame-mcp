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


def test_existing_one_shot_handlers_remain_present():
    text = BRIDGE.read_text()
    assert 'handlers.mame_run_from_reset_until_pc_and_step = function(p)' in text
    assert 'handlers.mame_step_instruction = function(p)' in text
    assert 'handlers.mame_run_until_pc_and_step = function(p)' in text
