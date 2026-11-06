local selector_name = "forgeplan-area-selector"
local output_name = "forgeplan-area.json"
local max_side = 512

local function write_result(result)
  helpers.write_file(output_name, helpers.table_to_json(result), false)
end

local function clear_previous_result()
  helpers.remove_path(output_name)
end

local function on_selected_area(event)
  if event.item ~= selector_name then return end

  local left = math.floor(event.area.left_top.x + 0.000001)
  local top = math.floor(event.area.left_top.y + 0.000001)
  local right = math.ceil(event.area.right_bottom.x - 0.000001)
  local bottom = math.ceil(event.area.right_bottom.y - 0.000001)
  local width, height = right - left, bottom - top
  local player = game.get_player(event.player_index)
  local result = {
    schema_version = 1,
    valid = width > 0 and height > 0 and width <= max_side and height <= max_side,
    width = width,
    height = height,
    left_top = {x = left, y = top},
    right_bottom = {x = right, y = bottom},
    surface = event.surface and event.surface.name or "",
    player = player and player.name or "",
    tick = event.tick
  }

  if not result.valid then
    result.error = "Área inválida. Cada lado precisa medir entre 1 e 512 tiles."
    write_result(result)
    if player then player.print({"forgeplan.area-invalid", max_side}) end
    return
  end

  write_result(result)
  if player then player.print({"forgeplan.area-exported", width, height, result.surface}) end
end

script.on_event(defines.events.on_player_selected_area, on_selected_area)
script.on_init(clear_previous_result)
script.on_configuration_changed(clear_previous_result)
