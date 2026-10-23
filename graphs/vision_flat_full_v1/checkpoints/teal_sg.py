from gap.runtime.verify import Checkpoint

def verified(world):
    v=world.sim_state.get("vision",{})
    a=v.get("assessment",{})
    return a.get("bead_error_m",{}).get('teal') is not None and a["bead_error_m"]['teal']<.003

CHECKPOINTS=[Checkpoint(name='teal_visual_estimate',subgraph='teal_sg',predicate=verified,validate=True)]
