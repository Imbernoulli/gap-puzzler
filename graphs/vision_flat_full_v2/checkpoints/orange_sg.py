from gap.runtime.verify import Checkpoint

def verified(world):
    v=world.sim_state.get("vision",{})
    a=v.get("assessment",{})
    return a.get("bead_error_m",{}).get('orange') is not None and a["bead_error_m"]['orange']<.003

CHECKPOINTS=[Checkpoint(name='orange_visual_estimate',subgraph='orange_sg',predicate=verified,validate=True)]
