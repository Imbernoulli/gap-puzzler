from gap.runtime.verify import Checkpoint

def verified(world):
    v=world.sim_state.get("vision",{})
    a=v.get("assessment",{})
    return 'board' in v.get('poses',{})

CHECKPOINTS=[Checkpoint(name='anchor_visual_estimate',subgraph='anchor_sg',predicate=verified,validate=True)]
