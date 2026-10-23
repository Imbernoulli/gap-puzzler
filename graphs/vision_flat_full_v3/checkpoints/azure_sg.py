from gap.runtime.verify import Checkpoint

def verified(world):
    v=world.sim_state.get("vision",{})
    a=v.get("assessment",{})
    return a.get("bead_error_m",{}).get('azure') is not None and a["bead_error_m"]['azure']<.003

CHECKPOINTS=[Checkpoint(name='azure_visual_estimate',subgraph='azure_sg',predicate=verified,validate=True)]
