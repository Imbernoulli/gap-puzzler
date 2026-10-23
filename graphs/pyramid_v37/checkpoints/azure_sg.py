from gap.runtime.verify import Checkpoint

def verified(world):
    g=world.sim_state["puzzle_grade"]
    return g['bead_error_m']['azure'] < .004 and g['speed_mps']['azure'] < .015

def diagnostics(world):
    return world.sim_state["puzzle_grade"]

CHECKPOINTS=[Checkpoint(name='azure_physical_state',subgraph='azure_sg',predicate=verified,validate=True,diagnostics_fn=diagnostics)]
