"""Refresh a transparent development ledger from recorded physical episodes."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    rows = []
    for result in sorted((ROOT/'runs').rglob('result.json'), key=lambda p:p.stat().st_mtime):
        if not any(p.startswith(('pyramid_', 'full_pyramid')) for p in result.relative_to(ROOT).parts):
            continue
        data = json.loads(result.read_text())
        variant = data.get('variant', {})
        preset = variant.get('preset_pieces', [])
        errors = data.get('final', {}).get('bead_error_m', {})
        failures = []
        for output in sorted((result.parent/'trace/0000/node_data').glob('*/iters/*/output.json')):
            value = json.loads(output.read_text())
            if value.get('failure') or value.get('route') == 'retry':
                failures.append(dict(node=output.parent.parent.parent.name,
                    iteration=output.parent.name,
                    **{k:value[k] for k in ['failure','piece','error_m','rise','grasp_index',
                       'grasp_heading','grasp_lean','handoff','disturbed_pieces'] if k in value}))
        rows.append(dict(result=str(result.relative_to(ROOT)), graph=data.get('graph'),
            embodiment=variant.get('embodiment','yam_bimanual'),
            full_task_success=bool(data.get('success') and not preset),
            diagnostic_success=data.get('diagnostic_success',False),
            diagnostic_preset=bool(preset),initial_preset_count=len(preset),
            final_seated_count=sum(e<.004 for e in errors.values()),
            new_seated_count=sum(e<.004 for name,e in errors.items() if name not in preset),
            sim_time_s=data.get('sim_time_s'),failures=failures))
    report=dict(scope='Development exploration, not a controlled benchmark. Preset diagnostics '
        'can never count as full-task success. Static targets and IK are excluded.',runs=rows)
    (ROOT/'results/pyramid_search_ledger.json').write_text(json.dumps(report,indent=2))
    print(f'Recorded {len(rows)} physical episodes; custom hardware is marked separately.')


if __name__=='__main__':
    main()
