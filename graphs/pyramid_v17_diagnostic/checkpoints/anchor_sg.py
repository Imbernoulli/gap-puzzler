from gap.runtime.verify import Checkpoint

def verified(world):
    g=world.sim_state["puzzle_grade"]
    return g['finite'] and g['board_resting']

def diagnostics(world):
    return world.sim_state["puzzle_grade"]

CHECKPOINTS=[Checkpoint(name='anchor_physical_state',subgraph='anchor_sg',predicate=verified,validate=True,diagnostics_fn=diagnostics)]
