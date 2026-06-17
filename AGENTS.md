# Agent Notes for mame_mcp

This repository is the MAME-side sibling of the Mesen MCP workflow. Prefer
small, inspectable harnesses that expose arcade runtime truth to an MCP client.

## Operating Rules

- Keep stock-MAME compatibility until a specific API gap justifies a source
  fork.
- Generated Lua scripts and logs belong under `.mame_mcp/` or a caller-provided
  work directory.
- Tool responses should include paths to durable artifacts, not only inline
  summaries.
- For trace tools, return both machine-readable summaries and human-readable
  logs.
- Preserve exact address ranges, frame counts, command lines, and verdict text
  in responses.

## Common Setup

```powershell
python -m pip install -e .
$env:MAME_EXE = "/path/to/mame"
mame-mcp-tools --names
```

## First-Call Protocol

When this is loaded as an MCP server, start with:

1. `ping`
2. `config_check`
3. `audit_romset` for the target machine, if a ROM path is configured

Then use generic tools such as `trace_memory_access`, passing the machine,
ROM path, address ranges, and tracked read addresses for the target at hand.
Use `trace_cchip_superman` only when the target is Superman and the caller has
provided a ROM path through arguments or local environment.
