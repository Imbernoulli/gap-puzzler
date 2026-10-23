from gap.runtime.verify import Checkpoint

def verified(world):
    v=world.sim_state.get("vision",{})
    a=v.get("assessment",{})
    return a.get("bead_error_m",{}).get('lime') is not None and a["bead_error_m"]['lime']<.003

CHECKPOINTS=[Checkpoint(name='lime_visual_estimate',subgraph='lime_sg',predicate=verified,validate=True)]
