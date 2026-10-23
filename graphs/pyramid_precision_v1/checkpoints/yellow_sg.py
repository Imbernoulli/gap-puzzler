from gap.runtime.verify import Checkpoint

def verified(world):
    g=world.sim_state["puzzle_grade"]
    return g['bead_error_m']['yellow'] < .004 and g['speed_mps']['yellow'] < .015

def diagnostics(world):
    return world.sim_state["puzzle_grade"]

CHECKPOINTS=[Checkpoint(name='yellow_physical_state',subgraph='yellow_sg',predicate=verified,validate=True,diagnostics_fn=diagnostics)]
