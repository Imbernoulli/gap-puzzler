from gap.runtime.verify import Checkpoint

def verified(world):
    g=world.sim_state["puzzle_grade"]
    return g['bead_error_m']['lime'] < .004 and g['speed_mps']['lime'] < .015

def diagnostics(world):
    return world.sim_state["puzzle_grade"]

CHECKPOINTS=[Checkpoint(name='lime_physical_state',subgraph='lime_sg',predicate=verified,validate=True,diagnostics_fn=diagnostics)]
