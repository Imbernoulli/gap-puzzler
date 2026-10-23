from gap.runtime.verify import Checkpoint

def verified(world):
    g=world.sim_state["puzzle_grade"]
    return g['bead_error_m']['orange'] < .004 and g['speed_mps']['orange'] < .015

def diagnostics(world):
    return world.sim_state["puzzle_grade"]

CHECKPOINTS=[Checkpoint(name='orange_physical_state',subgraph='orange_sg',predicate=verified,validate=True,diagnostics_fn=diagnostics)]
