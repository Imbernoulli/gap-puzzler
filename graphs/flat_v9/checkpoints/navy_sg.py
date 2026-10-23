from gap.runtime.verify import Checkpoint

def verified(world):
    g=world.sim_state["puzzle_grade"]
    return g['bead_error_m']['navy'] < .004 and g['speed_mps']['navy'] < .015

def diagnostics(world):
    return world.sim_state["puzzle_grade"]

CHECKPOINTS=[Checkpoint(name='navy_physical_state',subgraph='navy_sg',predicate=verified,validate=True,diagnostics_fn=diagnostics)]
