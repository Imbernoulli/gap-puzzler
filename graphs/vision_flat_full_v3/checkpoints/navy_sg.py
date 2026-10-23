from gap.runtime.verify import Checkpoint

def verified(world):
    v=world.sim_state.get("vision",{})
    a=v.get("assessment",{})
    return a.get("bead_error_m",{}).get('navy') is not None and a["bead_error_m"]['navy']<.003

CHECKPOINTS=[Checkpoint(name='navy_visual_estimate',subgraph='navy_sg',predicate=verified,validate=True)]
