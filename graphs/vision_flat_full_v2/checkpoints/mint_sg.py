from gap.runtime.verify import Checkpoint

def verified(world):
    v=world.sim_state.get("vision",{})
    a=v.get("assessment",{})
    return a.get("bead_error_m",{}).get('mint') is not None and a["bead_error_m"]['mint']<.003

CHECKPOINTS=[Checkpoint(name='mint_visual_estimate',subgraph='mint_sg',predicate=verified,validate=True)]
