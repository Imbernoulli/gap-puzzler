from gap.runtime.verify import Checkpoint

def verified(world):
    g=world.sim_state["puzzle_grade"]
    return g['bead_error_m']['pink'] < .004 and g['speed_mps']['pink'] < .015

def diagnostics(world):
    return world.sim_state["puzzle_grade"]

CHECKPOINTS=[Checkpoint(name='pink_physical_state',subgraph='pink_sg',predicate=verified,validate=True,diagnostics_fn=diagnostics)]
