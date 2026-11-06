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
  for _, sink in pairs(case.sinks or {}) do
    local chest = surface.create_entity{name = "infinity-chest", position = shifted(sink.position), force = "player"}
    if chest then chest.remove_unfiltered_items = true
    else add_error("sink não pôde ser criado em " .. serpent.line(sink.position)) end
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
  local machines = {}
  for _, rec in pairs(storage.machines) do machines[#machines + 1] = rec end
  helpers.write_file("result.json", helpers.table_to_json({
    case_id = case.id, factorio_version = helpers.game_version,
    built = count_names(storage.built), rejected = storage.rejected,
    measured = measured, machines = machines, shift = storage.shift,
    ticks_run = game.tick - storage.t0, errors = storage.errors,
  }), false)
end

local function init()
  for _, recipe in pairs(game.forces.player.recipes) do recipe.enabled = true end
  storage.errors, storage.machines, storage.rejected, storage.built = {}, {}, {}, {}
  storage.t0 = game.tick
  local surface = game.surfaces[1]
  local ok, err = pcall(function()
    storage.built, storage.rejected = build_blueprint(surface)
    place_feeds(surface)
    insert_modules(surface)
    insert_beacon_modules(surface)
  end)
  if not ok then add_error(err) end
  storage.started = true
end

script.on_event(defines.events.on_tick, function(event)
  if not storage.started then
    if event.tick >= START_TICK then init() end
    return
  end
  local surface = game.surfaces[1]
  local elapsed = event.tick - storage.t0
  pcall(refill_power, surface)
  if elapsed % 30 == 0 and elapsed > case.ticks_warmup then pcall(sample_status, surface) end
  if elapsed == case.ticks_warmup then storage.baseline = snapshot(surface) end
  if elapsed == case.ticks_warmup + case.ticks_measure and not storage.finished then
    storage.finished = true
    local ok, err = pcall(finish, surface)
    if not ok then add_error(err); helpers.write_file("result.json", helpers.table_to_json({case_id = case.id, errors = storage.errors}), false) end
  end
end)
