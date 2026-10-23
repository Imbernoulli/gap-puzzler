"""Summarize every completed visual attempt without hiding development failures."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    rows=[]
    for p in sorted((ROOT/'runs').glob('vision*/*/result.json')):
        r=json.loads(p.read_text())
        snapshot=p.parent/'source/vision_planning.py'
        ik_contract=('robot_encoder_slices_only'
                     if snapshot.exists() and 'seed=robot_seed(env)' in snapshot.read_text()
                     else 'legacy_full_scene_ik_seed_not_final_visual_contract')
        rows.append(dict(path=str(p.relative_to(ROOT)),graph=r['graph'],seed=r['seed'],
            ik_input_contract=ik_contract,
            scattered=r['variant'].get('scattered',False),full_task_success=r['success'],
            graph_success=r['graph_success'],diagnostic_subset=r.get('diagnostic_subset',[]),
            subset_diagnostic=r.get('single_piece_physical_diagnostic'),
            subset_audit=r.get('independent_subset_audit'),sim_time_s=r['sim_time_s'],
            observation_count=r.get('rgb_observation_count'),
            failure=r.get('graph_trace',{}).get('graph_error',''),
            visual_checkpoints=r['checkpoint_results'],workflow_sha256=r['workflow_sha256'],source_sha256=r['source_sha256']))
    (ROOT/'results/vision_execution.json').write_text(json.dumps(dict(
        scope='Development attempts. Subset diagnostics are never full puzzle successes.',
        runs=rows),indent=2))
    for r in rows:print(r['path'],r['full_task_success'],r['subset_diagnostic'])


if __name__=='__main__':main()
