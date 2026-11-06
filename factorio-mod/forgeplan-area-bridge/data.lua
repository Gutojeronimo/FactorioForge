local selector = {
  type = "selection-tool",
  name = "forgeplan-area-selector",
  icon = "__base__/graphics/icons/blueprint.png",
  icon_size = 64,
  flags = {"only-in-cursor"},
  stack_size = 1,
  subgroup = "tool",
  order = "z[forgeplan-area-selector]",
  select = {
    mode = {"any-entity", "any-tile"},
    cursor_box_type = "copy",
    border_color = {r = 0.2, g = 0.85, b = 1, a = 0.8}
  },
  alt_select = {
    mode = {"any-entity", "any-tile"},
    cursor_box_type = "not-allowed",
    border_color = {r = 1, g = 0.3, b = 0.3, a = 0.8}
  }
}

local shortcut = {
  type = "shortcut",
  name = "forgeplan-select-area",
  action = "spawn-item",
  item_to_spawn = selector.name,
  toggleable = false,
  icon = "__base__/graphics/icons/blueprint.png",
  icon_size = 64,
  small_icon = "__base__/graphics/icons/blueprint.png",
  small_icon_size = 64,
  order = "f[blueprint]-forgeplan-area",
  localised_name = {"shortcut-name.forgeplan-select-area"},
  localised_description = {"shortcut-description.forgeplan-select-area"}
}

data:extend({selector, shortcut})
