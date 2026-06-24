-- bridge.lua — persistent live-session bridge for the MAME MCP (MAME 0.227+).
-- File IPC: the client writes <cwd>/mame_cmd.json, the bridge executes it on the live
-- machine and writes <cwd>/mame_rsp.json (both deleted after use). Polled by BOTH
-- register_frame_done AND register_periodic — the latter fires even while PAUSED, so the
-- session can read/write a frozen machine. No LuaSocket needed.
--
-- Commands (JSON {id, command, params}): ping, status, pause, resume, run_frames{n},
-- read_block{space,addr,len}, write_block{space,addr,hex}, get_regs{device}, set_reg{...},
-- get_reg{device,reg}, load_state{name}, save_state{name}, send_input{field,value}, exec_lua{code}.
-- minimal pure-Lua JSON (MAME's bundled `json` module is absent in some builds, e.g. the
-- 0.287 snap). Handles the subset the bridge needs: objects, arrays, strings, ints, bool, null.
local json = {}
local function jesc(s)
  return (s:gsub('[%c"\\]', function(c)
    local m = {['"']='\\"', ['\\']='\\\\', ['\n']='\\n', ['\r']='\\r', ['\t']='\\t'}
    return m[c] or string.format('\\u%04x', c:byte())
  end))
end
local function jenc(v)
  local t = type(v)
  if t == "nil" then return "null"
  elseif t == "boolean" then return tostring(v)
  elseif t == "number" then return (math.type(v) == "integer") and string.format("%d", v) or string.format("%.17g", v)
  elseif t == "string" then return '"' .. jesc(v) .. '"'
  elseif t == "table" then
    local n = 0; for _ in pairs(v) do n = n + 1 end
    if n > 0 and #v == n then
      local p = {}; for i = 1, #v do p[i] = jenc(v[i]) end; return "[" .. table.concat(p, ",") .. "]"
    end
    local p = {}; for k, val in pairs(v) do p[#p+1] = '"' .. jesc(tostring(k)) .. '":' .. jenc(val) end
    return "{" .. table.concat(p, ",") .. "}"
  end
  return "null"
end
json.stringify = jenc
function json.parse(s)
  local pos = 1
  local function ws() pos = s:find("[^ \t\r\n]", pos) or (#s + 1) end
  local parse_val
  local function parse_str()
    pos = pos + 1; local buf = {}
    while true do
      local c = s:sub(pos, pos)
      if c == '"' then pos = pos + 1; break
      elseif c == "\\" then
        local e = s:sub(pos + 1, pos + 1)
        local m = {['"']='"', ["\\"]="\\", ["/"]="/", n="\n", t="\t", r="\r", b="\b", f="\f"}
        if e == "u" then buf[#buf+1] = utf8.char(tonumber(s:sub(pos+2, pos+5), 16)); pos = pos + 6
        else buf[#buf+1] = m[e] or e; pos = pos + 2 end
      else buf[#buf+1] = c; pos = pos + 1 end
    end
    return table.concat(buf)
  end
  function parse_val()
    ws(); local c = s:sub(pos, pos)
    if c == "{" then
      pos = pos + 1; local o = {}; ws()
      if s:sub(pos, pos) == "}" then pos = pos + 1; return o end
      while true do
        ws(); local k = parse_str(); ws(); pos = pos + 1; o[k] = parse_val(); ws()
        local d = s:sub(pos, pos); pos = pos + 1; if d == "}" then break end
      end
      return o
    elseif c == "[" then
      pos = pos + 1; local a = {}; ws()
      if s:sub(pos, pos) == "]" then pos = pos + 1; return a end
      while true do
        a[#a+1] = parse_val(); ws(); local d = s:sub(pos, pos); pos = pos + 1; if d == "]" then break end
      end
      return a
    elseif c == '"' then return parse_str()
    elseif c == "t" then pos = pos + 4; return true
    elseif c == "f" then pos = pos + 5; return false
    elseif c == "n" then pos = pos + 4; return nil
    else local e = s:find("[^%-+0-9.eE]", pos) or (#s + 1); local num = s:sub(pos, e - 1); pos = e; return tonumber(num) end
  end
  return parse_val()
end
local CMD, RSP, READY = "mame_cmd.json", "mame_rsp.json", "mame_bridge.ready"
local M = manager.machine

local function read_file(p) local f=io.open(p,"r"); if not f then return nil end local c=f:read("*a"); f:close(); return c end
local function write_file(p,c) local f=io.open(p,"w"); if not f then return false end f:write(c); f:close(); return true end
-- atomic: write to a temp then rename, so the client never reads a partial response
local function write_atomic(p,c) write_file(p..".tmp", c); os.remove(p); os.rename(p..".tmp", p) end
local function ok(d) return { status="ok", result=d } end
local function err(m) return { status="error", message=tostring(m) } end

local function maincpu() return M.devices[":maincpu"] end
local function space_of(tag) local d=M.devices[tag or ":maincpu"]; return d and d.spaces["program"] or nil end

local handlers = {}
handlers.ping = function() return ok({ pong=true, gamename=emu.gamename() }) end
handlers.status = function()
  local s = M.screens:at(1)
  return ok({ system=emu.gamename(), paused=M.paused, frame=(s and s:frame_number() or 0) })
end
handlers.pause = function() emu.pause(); return ok({ paused=true }) end
handlers.resume = function() emu.unpause(); return ok({ paused=false }) end
handlers.reset = function() M:soft_reset(); return ok({ reset="soft" }) end

handlers.read_block = function(p)
  local sp = space_of(p.space); if not sp then return err("no space "..tostring(p.space)) end
  local a, n = p.addr, p.len
  local t = {}
  for i=0,n-1 do t[i+1] = string.format("%02x", sp:read_u8(a+i) & 0xFF) end
  return ok({ addr=a, len=n, hex=table.concat(t) })
end
handlers.write_block = function(p)
  local sp = space_of(p.space); if not sp then return err("no space") end
  local a, hex = p.addr, p.hex
  for i=0,(#hex//2)-1 do sp:write_u8(a+i, tonumber(hex:sub(i*2+1,i*2+2),16)) end
  return ok({ addr=a, len=#hex//2 })
end
handlers.read_u = function(p)
  local sp = space_of(p.space); if not sp then return err("no space") end
  local v = ({[1]=sp.read_u8,[2]=sp.read_u16,[4]=sp.read_u32})[p.size or 2](sp, p.addr)
  return ok({ addr=p.addr, value=v })
end
handlers.write_u = function(p)
  local sp = space_of(p.space); if not sp then return err("no space") end
  ;({[1]=sp.write_u8,[2]=sp.write_u16,[4]=sp.write_u32})[p.size or 2](sp, p.addr, p.value)
  return ok({ addr=p.addr })
end

handlers.get_regs = function(p)
  local cpu = M.devices[p.device or ":maincpu"]
  local regs = {}
  for name, entry in pairs(cpu.state) do regs[name] = entry.value & 0xFFFFFFFF end
  return ok({ device=(p.device or ":maincpu"), registers=regs })
end
handlers.get_reg = function(p)
  local cpu = M.devices[p.device or ":maincpu"]
  local e = cpu.state[p.reg]; if not e then return err("no reg "..tostring(p.reg)) end
  return ok({ reg=p.reg, value=e.value & 0xFFFFFFFF })
end
handlers.set_reg = function(p)
  local cpu = M.devices[p.device or ":maincpu"]
  local e = cpu.state[p.reg]; if not e then return err("no reg "..tostring(p.reg)) end
  e.value = p.value
  return ok({ reg=p.reg, value=p.value })
end

handlers.load_state = function(p) M:load(p.name); return ok({ loaded=p.name }) end
handlers.save_state = function(p) M:save(p.name); return ok({ saved=p.name }) end

handlers.send_input = function(p)
  for _, port in pairs(M.ioport.ports) do
    for n, f in pairs(port.fields) do
      if n == p.field then f:set_value(p.value); return ok({ field=p.field, value=p.value }) end
    end
  end
  return err("field not found: "..tostring(p.field))
end
handlers.list_inputs = function()
  local names = {}
  for _, port in pairs(M.ioport.ports) do for n,_ in pairs(port.fields) do names[#names+1]=n end end
  return ok({ fields=names })
end
handlers.exec_lua = function(p)
  local fn, e = load("return function(M, machine) " .. p.code .. " end")
  if not fn then return err("compile: "..tostring(e)) end
  local okc, res = pcall(fn(), M, M)
  if not okc then return err("run: "..tostring(res)) end
  return ok({ result = res })
end

-- run_frames is DEFERRED: set a target, resume, and let poll() finish it when reached.
local run_target = nil
handlers.run_frames = function(p)
  local s = M.screens:at(1)
  run_target = (s and s:frame_number() or 0) + (p.n or 1)
  emu.unpause()
  return nil   -- deferred: poll() writes the response when run_target is hit
end

-- capture_game_tick: run until the Nth GAME_TICK ($3A92 prologue reads $F00000 @ ~$3AA4) and,
-- AT that read (mid-instruction -- emu.pause only stops at frame boundaries), snapshot the 68K
-- regs + a memory region into the response. The lockstep regsA/wramA/wramB primitive. movem.l
-- at $3A92 has already pushed 60 bytes when $F00000 is read, so entry a7 = captured a7 + 60
-- (the client reconstructs). `busy` guards the in-tap region read (which re-touches $F00000).
local cap = { arm=false, done=false, busy=false, count=0, nth=1, addr=0, len=0, tap=nil, result=nil, deadline=0 }
handlers.capture_game_tick = function(p)
  if not cap.tap then
    local sp = space_of(":maincpu")
    cap.tap = sp:install_read_tap(0xF00000, 0xF00001, "mcp_cap", function(off, data, mask)
      if cap.busy or not cap.arm then return data end
      local cpu = M.devices[":maincpu"]
      local pc = cpu.state["PC"].value & 0xFFFFFF
      if pc < 0x3A92 or pc > 0x3AB0 then return data end
      cap.count = cap.count + 1
      if cap.count < cap.nth then return data end
      cap.busy = true
      local regs = {}; for n, e in pairs(cpu.state) do regs[n] = e.value & 0xFFFFFFFF end
      local sp2 = cpu.spaces["program"]; local hb = {}
      for i = 0, cap.len - 1 do hb[i+1] = string.format("%02x", sp2:read_u8(cap.addr + i) & 0xFF) end
      local s = M.screens:at(1)
      cap.result = { registers = regs, hex = table.concat(hb), frame = (s and s:frame_number() or 0), pc = pc }
      cap.arm = false; cap.done = true; cap.busy = false; emu.pause()
      return data
    end)
  end
  cap.addr = p.addr; cap.len = p.len; cap.nth = p.nth or 1; cap.count = 0; cap.done = false; cap.arm = true
  local s = M.screens:at(1); cap.deadline = (s and s:frame_number() or 0) + (p.maxFrames or 1200)
  emu.unpause()
  return nil
end

local function dispatch(req)
  local h = handlers[req.command]
  if not h then return err("unknown command: "..tostring(req.command)) end
  local okc, res = pcall(h, req.params or {})
  if not okc then return err(tostring(res)) end
  return res   -- may be nil for deferred (run_frames)
end

local function poll()
  -- finish a deferred capture_game_tick
  if cap.arm or cap.done then
    if cap.done then
      cap.done = false
      write_atomic(RSP, json.stringify({ status = "ok", result = cap.result }))
    else
      local s = M.screens:at(1)
      if (s and s:frame_number() or 0) >= cap.deadline then
        cap.arm = false; emu.pause()
        write_atomic(RSP, json.stringify({ status = "ok", result = { hit = false } }))
      end
    end
    return
  end
  -- finish a deferred run_frames
  if run_target ~= nil then
    local s = M.screens:at(1)
    if (s and s:frame_number() or 0) >= run_target then
      emu.pause(); local f = s and s:frame_number() or 0; run_target = nil
      write_atomic(RSP, json.stringify({ status="ok", result={ frame=f, paused=true } }))
    end
    return
  end
  local content = read_file(CMD)
  if not content then return end
  os.remove(CMD)
  local okp, req = pcall(json.parse, content)
  local resp
  if not okp or type(req) ~= "table" then resp = err("bad json")
  else resp = dispatch(req) end
  if resp ~= nil then   -- nil = deferred, written later by poll()
    if type(req)=="table" and req.id then resp.id = req.id end
    write_atomic(RSP, json.stringify(resp))
  end
end

os.remove(CMD); os.remove(RSP)
emu.register_frame_done(poll, "mcp_bridge_frame")
if emu.register_periodic then emu.register_periodic(poll, "mcp_bridge_periodic") end
write_file(READY, "1")
print("[MCP-BRIDGE] live session ready (cmd="..CMD..")")
