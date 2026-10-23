from gap.runtime.verify import Checkpoint

def verified(world):
    v=world.sim_state.get("vision",{})
    a=v.get("assessment",{})
    return a.get("bead_error_m",{}).get('pink') is not None and a["bead_error_m"]['pink']<.003

CHECKPOINTS=[Checkpoint(name='pink_visual_estimate',subgraph='pink_sg',predicate=verified,validate=True)]
