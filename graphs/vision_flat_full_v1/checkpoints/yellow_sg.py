from gap.runtime.verify import Checkpoint

def verified(world):
    v=world.sim_state.get("vision",{})
    a=v.get("assessment",{})
    return a.get("bead_error_m",{}).get('yellow') is not None and a["bead_error_m"]['yellow']<.003

CHECKPOINTS=[Checkpoint(name='yellow_visual_estimate',subgraph='yellow_sg',predicate=verified,validate=True)]
