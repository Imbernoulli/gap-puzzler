from gap.runtime.verify import Checkpoint

def verified(world):
    v=world.sim_state.get("vision",{})
    a=v.get("assessment",{})
    return a.get("bead_error_m",{}).get('purple') is not None and a["bead_error_m"]['purple']<.003

CHECKPOINTS=[Checkpoint(name='purple_visual_estimate',subgraph='purple_sg',predicate=verified,validate=True)]
