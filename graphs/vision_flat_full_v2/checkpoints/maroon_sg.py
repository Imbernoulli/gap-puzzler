from gap.runtime.verify import Checkpoint

def verified(world):
    v=world.sim_state.get("vision",{})
    a=v.get("assessment",{})
    return a.get("bead_error_m",{}).get('maroon') is not None and a["bead_error_m"]['maroon']<.003

CHECKPOINTS=[Checkpoint(name='maroon_visual_estimate',subgraph='maroon_sg',predicate=verified,validate=True)]
