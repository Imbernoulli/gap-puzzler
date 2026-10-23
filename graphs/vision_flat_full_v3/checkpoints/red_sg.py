from gap.runtime.verify import Checkpoint

def verified(world):
    v=world.sim_state.get("vision",{})
    a=v.get("assessment",{})
    return a.get("bead_error_m",{}).get('red') is not None and a["bead_error_m"]['red']<.003

CHECKPOINTS=[Checkpoint(name='red_visual_estimate',subgraph='red_sg',predicate=verified,validate=True)]
