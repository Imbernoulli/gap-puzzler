from gap.runtime.verify import Checkpoint

def verified(world):
    g=world.sim_state["puzzle_grade"]
    return g['success']

def diagnostics(world):
    return world.sim_state["puzzle_grade"]

CHECKPOINTS=[Checkpoint(name='finish_physical_state',subgraph='finish_sg',predicate=verified,validate=True,diagnostics_fn=diagnostics)]
