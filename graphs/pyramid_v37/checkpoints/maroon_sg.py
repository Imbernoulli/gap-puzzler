from gap.runtime.verify import Checkpoint

def verified(world):
    g=world.sim_state["puzzle_grade"]
    return g['bead_error_m']['maroon'] < .004 and g['speed_mps']['maroon'] < .015

def diagnostics(world):
    return world.sim_state["puzzle_grade"]

CHECKPOINTS=[Checkpoint(name='maroon_physical_state',subgraph='maroon_sg',predicate=verified,validate=True,diagnostics_fn=diagnostics)]
