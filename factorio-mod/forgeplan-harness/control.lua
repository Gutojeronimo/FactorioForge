-- ForgePlan harness: builds the case blueprint on a throwaway map, feeds/powers it,
-- measures production (flow statistics input_counts = produced) over a window and writes result.json (see harness/LAUNCH.md).
local case = helpers.json_to_table(require("case_data"))
local START_TICK = 10
local STATUS_NAMES = {}
for name, value in pairs(defines.entity_status) do STATUS_NAMES[value] = name end

local function add_error(msg)
  storage.errors[#storage.errors + 1] = tostring(msg)
end

local function count_names(entities)
  local counts = {}
  for _, e in pairs(entities) do
    if e.valid then counts[e.name] = (counts[e.name] or 0) + 1 end
  end
  local list = {}
  for name, n in pairs(counts) do list[#list + 1] = {name = name, count = n} end
  return list
end

-- build_blueprint centres the blueprint's bounding box on `position`, so world coordinates differ from
-- blueprint coordinates by a constant shift. Recover it by matching every blueprint entity to a ghost.
local function find_shift(bp_entities, ghosts)
  if #bp_entities == 0 then return {x = 0, y = 0} end
  local key = function(name, x, y) return name .. "@" .. x .. "," .. y end
  local first = bp_entities[1]
  for _, g in pairs(ghosts) do
    if g.valid and g.ghost_name == first.name then
      local dx, dy = g.position.x - first.position.x, g.position.y - first.position.y
      local present = {}
      for _, other in pairs(ghosts) do
        if other.valid then present[key(other.ghost_name, other.position.x, other.position.y)] = true end
      end
      local ok = true
      for _, e in pairs(bp_entities) do
        if not present[key(e.name, e.position.x + dx, e.position.y + dy)] then ok = false; break end
      end
      if ok then return {x = dx, y = dy} end
    end
  end
  add_error("não foi possível determinar o deslocamento do blueprint")
  return {x = 0, y = 0}
end

local function build_blueprint(surface)
  local inv = game.create_inventory(1)
  local stack = inv[1]
  stack.set_stack{name = "blueprint"}
  local rc = stack.import_stack(case.blueprint_string)
  if rc == 1 then add_error("import_stack falhou") end
  if rc == -1 then add_error("import_stack com erros") end
  local ghosts = stack.build_blueprint{surface = surface, force = "player", position = {0, 0}}
  if #ghosts == 0 then
    local bp = stack.get_blueprint_entities() or {}
    add_error("build_blueprint não criou ghosts: import_rc=" .. rc .. ", entidades_no_blueprint=" .. #bp ..
      ", superfície=" .. surface.name .. ", tile_origem=" .. surface.get_tile(0, 0).name ..
      ", is_blueprint=" .. tostring(stack.is_blueprint) .. ", valid_for_read=" .. tostring(stack.valid_for_read))
  end
  storage.shift = find_shift(stack.get_blueprint_entities() or {}, ghosts)
  local built, rejected = {}, {}
  for _, ghost in pairs(ghosts) do
    if ghost.valid then
      local name, position = ghost.ghost_name, ghost.position
      local _, revived = ghost.revive()
      if revived then
        built[#built + 1] = revived
      else
        rejected[#rejected + 1] = {name = name, position = position, reason = "revive falhou (colisão ou terreno)"}
      end
    end
  end
  inv.destroy()
  return built, rejected
end

local function shifted(position)
  local s = storage.shift or {x = 0, y = 0}
  return {x = position.x + s.x, y = position.y + s.y}
end

local function place_feeds(surface)
  for _, feed in pairs(case.feed or {}) do
    if feed.fluid then
      local pipe = surface.create_entity{name = "infinity-pipe", position = shifted(feed.position), force = "player"}
      if pipe then pipe.set_infinity_pipe_filter{name = feed.fluid, percentage = 1, mode = "at-least"}
      else add_error("infinity-pipe não pôde ser criado em " .. serpent.line(feed.position)) end
    else
      local chest = surface.create_entity{name = "infinity-chest", position = shifted(feed.position), force = "player"}
      if chest then
        chest.set_infinity_container_filter(1, {name = feed.item, count = prototypes.item[feed.item].stack_size, mode = "at-least"})
      else add_error("infinity-chest não pôde ser criado em " .. serpent.line(feed.position)) end
    end
  end
  storage.counted = {}
  for _, sink in pairs(case.sinks or {}) do
    if sink.count then
      local chest = surface.create_entity{name = "steel-chest", position = shifted(sink.position), force = "player"}
      if chest then storage.counted[#storage.counted + 1] = chest
      else add_error("sink contado não pôde ser criado em " .. serpent.line(sink.position)) end
    else
      local chest = surface.create_entity{name = "infinity-chest", position = shifted(sink.position), force = "player"}
      if chest then chest.remove_unfiltered_items = true
      else add_error("sink não pôde ser criado em " .. serpent.line(sink.position)) end
    end
  end
end

local function insert_modules(surface)
  for _, m in pairs(surface.find_entities_filtered{type = {"assembling-machine", "furnace"}}) do
    local inv = m.get_module_inventory()
    if inv then
      for _, mod in pairs(case.machine_modules or {}) do
        local inserted = inv.insert{name = mod.name, count = mod.count}
        if inserted < mod.count then add_error("módulos inseridos " .. inserted .. "/" .. mod.count .. " em " .. m.name) end
      end
    end
  end
end

local function insert_beacon_modules(surface)
  for _, b in pairs(surface.find_entities_filtered{type = "beacon"}) do
    local inv = b.get_module_inventory()
    if inv then
      for _, mod in pairs(case.beacon_modules or {}) do
        local inserted = inv.insert{name = mod.name, count = mod.count}
        if inserted < mod.count then add_error("módulos de beacon inseridos " .. inserted .. "/" .. mod.count) end
      end
    end
  end
end

local function refill_power(surface)
  for _, e in pairs(surface.find_entities_filtered{force = "player"}) do
    local ok, size = pcall(function() return e.electric_buffer_size end)
    if ok and size and size > 0 then e.energy = size end
  end
end

local function sample_status(surface)
  for _, m in pairs(surface.find_entities_filtered{type = {"assembling-machine", "furnace", "inserter", "infinity-container"}}) do
    local key = m.name .. "@" .. m.position.x .. "," .. m.position.y
    local rec = storage.machines[key]
    if not rec then
      rec = {name = m.name, position = m.position, status_counts = {}}
      storage.machines[key] = rec
    end
    local status = STATUS_NAMES[m.status] or "unknown"
    rec.status_counts[status] = (rec.status_counts[status] or 0) + 1
  end
end

-- Lane probes (see harness/LAUNCH.md): every tick of the measurement window, read the items of both transport
-- lines of the probe tile and count an item once when it crosses the line's midpoint (the exit mark) between two
-- consecutive ticks, tracking it by unique_id. In 2.1 `position` runs from line_length at the entry down to 0 at the
-- exit; the test only asks for a sign change around the mark, so it does not depend on that orientation. An item
-- moves far less than half a tile per tick, so it is seen on both sides of the mark and never counted twice.
local function place_probes(surface)
  storage.probes = {}
  for _, p in pairs(case.lane_probes or {}) do
    local found = surface.find_entities_filtered{position = shifted(p.position), type = {"transport-belt", "underground-belt"}}
    if found[1] then
      storage.probes[#storage.probes + 1] = {entity = found[1], x = p.position.x, y = p.position.y, prev = {{}, {}},
                                             counts = {0, 0}, seen = {0, 0}, min = {}, max = {}}
    else add_error("lane_probe sem esteira em " .. serpent.line(p.position)) end
  end
end

local LINES = {defines.transport_line.left_line, defines.transport_line.right_line}

local function sample_probes(counting)
  for _, probe in pairs(storage.probes or {}) do
    if probe.entity.valid then
      for i, index in ipairs(LINES) do
        local line = probe.entity.get_transport_line(index)
        local mark = line.line_length / 2
        probe.mark = mark
        local now = {}
        for _, item in pairs(line.get_detailed_contents()) do
          local position = item.position
          now[item.unique_id] = position
          probe.min[i] = math.min(probe.min[i] or position, position)
          probe.max[i] = math.max(probe.max[i] or position, position)
          local before = probe.prev[i][item.unique_id]
          if counting and before and (before > mark) ~= (position > mark) then
            probe.counts[i] = probe.counts[i] + item.stack.count
          end
        end
        if counting then for _ in pairs(now) do probe.seen[i] = probe.seen[i] + 1 end end
        probe.prev[i] = now
      end
    end
  end
end

local function counted_contents()
  local totals = {}
  for _, chest in pairs(storage.counted or {}) do
    if chest.valid then
      for _, entry in pairs(chest.get_inventory(defines.inventory.chest).get_contents()) do
        totals[entry.name] = (totals[entry.name] or 0) + entry.count
      end
    end
  end
  return totals
end

local function snapshot(surface)
  local force = game.forces.player
  local snap = {}
  for name, n in pairs(force.get_item_production_statistics(surface).input_counts) do snap[name] = n end
  for name, n in pairs(force.get_fluid_production_statistics(surface).input_counts) do snap[name] = n end
  return snap
end

local function finish(surface)
  local measured = {}
  local now = snapshot(surface)
  local seconds = case.ticks_measure / 60
  for name, n in pairs(now) do
    local delta = n - ((storage.baseline or {})[name] or 0)
    if delta > 0 then measured[name] = delta / seconds end
  end
  local sink_counts = {}
  for name, n in pairs(counted_contents()) do
    local delta = n - ((storage.counted_baseline or {})[name] or 0)
    if delta > 0 then sink_counts[name] = delta / seconds end
  end
  local sink_detail = {}
  for _, chest in pairs(storage.counted or {}) do
    if chest.valid then
      for _, entry in pairs(chest.get_inventory(defines.inventory.chest).get_contents()) do
        sink_detail[#sink_detail + 1] = {x = chest.position.x, y = chest.position.y, item = entry.name, total = entry.count}
      end
    end
  end
  local lane_flow = {}
  for _, probe in pairs(storage.probes or {}) do
    lane_flow[#lane_flow + 1] = {x = probe.x, y = probe.y, left = probe.counts[1] / seconds, right = probe.counts[2] / seconds,
                                 mark = probe.mark, position_range = {left = {probe.min[1], probe.max[1]}, right = {probe.min[2], probe.max[2]}},
                                 item_ticks = {left = probe.seen[1], right = probe.seen[2]}}
  end
  local machines = {}
  for _, rec in pairs(storage.machines) do machines[#machines + 1] = rec end
  helpers.write_file("result.json", helpers.table_to_json({
    case_id = case.id, factorio_version = helpers.game_version,
    built = count_names(storage.built), rejected = storage.rejected,
    measured = measured, sink_counts = sink_counts, sink_detail = sink_detail, machines = machines, shift = storage.shift,
    lane_flow = lane_flow,
    ticks_run = game.tick - storage.t0, errors = storage.errors,
  }), false)
end

local SURFACE_NAME = "forgeplan-harness"

-- Own flat surface: independent of the save's spawn planet (modded starts can leave nauvis ungenerated or watery).
local function make_surface()
  local surface = game.create_surface(SURFACE_NAME, {
    default_enable_all_autoplace_controls = false, starting_area = "none",
    property_expression_names = {cliffiness = 0},
  })
  surface.request_to_generate_chunks({0, 0}, 4)
  surface.force_generate_chunk_requests()
  local tiles = {}
  for x = -96, 95 do for y = -96, 95 do tiles[#tiles + 1] = {name = "lab-dark-1", position = {x, y}} end end
  surface.set_tiles(tiles)
  for _, e in pairs(surface.find_entities()) do if e.type ~= "character" then e.destroy() end end
  return surface
end

local function init()
  for _, recipe in pairs(game.forces.player.recipes) do recipe.enabled = true end
  storage.errors, storage.machines, storage.rejected, storage.built = {}, {}, {}, {}
  storage.t0 = game.tick
  local surface = make_surface()
  local ok, err = pcall(function()
    storage.built, storage.rejected = build_blueprint(surface)
    place_feeds(surface)
    insert_modules(surface)
    insert_beacon_modules(surface)
    place_probes(surface)
  end)
  if not ok then add_error(err) end
  if case.ticks_warmup == 0 then storage.baseline = snapshot(surface); storage.counted_baseline = counted_contents() end
  storage.started = true
end

script.on_event(defines.events.on_tick, function(event)
  if not storage.started then
    if event.tick >= START_TICK then init() end
    return
  end
  local surface = game.surfaces[SURFACE_NAME]
  local elapsed = event.tick - storage.t0
  local ok_power, err_power = pcall(refill_power, surface)
  if not ok_power and not storage.power_error then storage.power_error = true; add_error("refill_power: " .. tostring(err_power)) end
  if elapsed % 30 == 0 and elapsed > case.ticks_warmup then
    local ok_status, err_status = pcall(sample_status, surface)
    if not ok_status and not storage.status_error then storage.status_error = true; add_error("sample_status: " .. tostring(err_status)) end
  end
  if elapsed >= case.ticks_warmup and elapsed <= case.ticks_warmup + case.ticks_measure then
    local ok_probe, err_probe = pcall(sample_probes, elapsed > case.ticks_warmup)
    if not ok_probe and not storage.probe_error then storage.probe_error = true; add_error("sample_probes: " .. tostring(err_probe)) end
  end
  if elapsed == case.ticks_warmup then storage.baseline = snapshot(surface); storage.counted_baseline = counted_contents() end
  if elapsed == case.ticks_warmup + case.ticks_measure and not storage.finished then
    storage.finished = true
    local ok, err = pcall(finish, surface)
    if not ok then add_error(err); helpers.write_file("result.json", helpers.table_to_json({case_id = case.id, errors = storage.errors}), false) end
  end
end)
