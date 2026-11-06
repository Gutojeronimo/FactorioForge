-- SPIKE: minimal proof that a blueprint string can be imported, built and reported.
local BLUEPRINT = require("spike_blueprint")
local function run()
  local inv = game.create_inventory(1)
  local stack = inv[1]
  stack.set_stack{name = "blueprint"}
  local rc = stack.import_stack(BLUEPRINT)
  local surface = game.surfaces[1]
  local ghosts = stack.build_blueprint{surface = surface, force = "player", position = {0, 0}}
  local built, rejected = 0, 0
  for _, g in pairs(ghosts) do
    if g.valid then
      local _, revived = g.revive()
      if revived then built = built + 1 else rejected = rejected + 1 end
    end
  end
  inv.destroy()
  helpers.write_file("result.json", helpers.table_to_json({import_rc = rc, ghosts = #ghosts, built = built, rejected = rejected, version = helpers.game_version}), false)
end
script.on_nth_tick(10, function(e)
  if not storage.done then storage.done = true; run() end
end)
