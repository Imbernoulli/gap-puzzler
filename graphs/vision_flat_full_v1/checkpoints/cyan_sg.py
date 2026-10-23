from gap.runtime.verify import Checkpoint

def verified(world):
    v=world.sim_state.get("vision",{})
    a=v.get("assessment",{})
    return a.get("bead_error_m",{}).get('cyan') is not None and a["bead_error_m"]['cyan']<.003

CHECKPOINTS=[Checkpoint(name='cyan_visual_estimate',subgraph='cyan_sg',predicate=verified,validate=True)]
