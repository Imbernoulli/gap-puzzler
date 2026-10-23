from gap.runtime.verify import Checkpoint

def verified(world):
    g=world.sim_state["puzzle_grade"]
    return g['bead_error_m']['teal'] < .004 and g['speed_mps']['teal'] < .015

def diagnostics(world):
    return world.sim_state["puzzle_grade"]

CHECKPOINTS=[Checkpoint(name='teal_physical_state',subgraph='teal_sg',predicate=verified,validate=True,diagnostics_fn=diagnostics)]
