from gap.runtime.verify import Checkpoint

def verified(world):
    v=world.sim_state.get("vision",{})
    a=v.get("assessment",{})
    return all(a["bead_error_m"].get(n) is not None and a["bead_error_m"][n]<.003 for n in ['yellow', 'purple', 'cyan', 'lime', 'mint', 'maroon', 'teal', 'orange', 'navy', 'pink', 'red', 'azure'])

CHECKPOINTS=[Checkpoint(name='finish_visual_estimate',subgraph='finish_sg',predicate=verified,validate=True)]
