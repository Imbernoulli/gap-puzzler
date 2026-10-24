"""Fresh, explicitly GPU native entry for the packaged layout-C policy.

Validation and preparation construct no Env or renderer. A prepared manifest
is a launch request, never a cached qualification or a success receipt.
"""
import argparse
from copy import deepcopy
import json
from importlib.metadata import distribution
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / 'graphs/pyramid_full12'
ORDER = ['azure', 'orange', 'yellow', 'teal', 'purple', 'cyan',
         'mint', 'lime', 'maroon', 'navy', 'pink', 'red']
LAYOUT = dict(name='C_Lime_world_y_plus070', piece='lime',
              translation_m=[0., .070, 0.], all12_loose=True)
JOB_SOURCE = ('from pathlib import Path\n'
              'from tools.layout_c_native import jobs\n'
              "JOBS = jobs(Path(__file__).with_name('manifest.json'))\n")


def fresh_graph(graph=GRAPH):
    graph = Path(graph).resolve()
    if not graph.is_relative_to(ROOT):
        raise ValueError('The graph must be inside this delivery bundle')
    document = json.loads((graph / 'workflow.json').read_text())
    params = json.loads((graph / 'params.json').read_text())
    meta = document['meta']
    if (meta.get('ordered_stages') != ORDER or params.get('assembly_order') != ORDER
            or meta.get('initialized_prefix') != []
            or meta.get('full_assembly_eligible') is not True
            or meta.get('required_checkpoint_mode') != 'raise'
            or params.get('diagnostic_subset')
            or params.get('diagnostic_prefix_finish')
            or meta.get('canonical_original_staging') is not False
            or meta.get('public_initial_layout') != LAYOUT):
        raise ValueError('A fresh all12 layout-C graph with raise checkpoints is required')
    literals = [node['inputs']['state'] for node in document['nodes'].values()
                if isinstance(node.get('inputs', {}).get('state'), dict)
                and '$ref' not in node['inputs']['state']]
    if len(literals) != 1:
        raise ValueError('Exactly one initial state is required')
    first, = literals
    for key in ('executed_placements', 'initialized_prefix', 'execution_tokens', 'rgb_history',
                'belief_ledger', 'observation', 'planning_scene', 'history', 'prediction',
                'plan', 'release_execution', 'support_anchor_evidence', 'pending_placement_receipt'):
        if first.get(key):
            raise ValueError('Fresh initial state must have empty ' + key)
    memory = first.get('memory', {})
    if (memory.get('placements') or memory.get('local_prefix_assumptions')
            or memory.get('last_frame_sha256') or memory.get('last_timestamp', -1.) >= 0.):
        raise ValueError('Fresh initial state cannot contain a receipt or cached scene')
    if first.get('piece') != ORDER[0] or first.get('arm') != -1 or first.get('attempt') != 0:
        raise ValueError('Fresh initial state must begin before the first grasp')
    # The builder derives each piece's parameters from the shared assembly
    # fields plus that piece's public profile. It is not the raw params object.
    from puzzler.modular_controller import initial_state
    if first != initial_state(ORDER[0], params):
        raise ValueError('Frozen initial state disagrees with the public profile builder')
    if first.get('assembly_order') not in (None, ORDER):
        raise ValueError('Initial-state order disagrees with graph')
    return document


def validate(graph=GRAPH):
    document = fresh_graph(graph)
    # These adapters load the graph-owned schema, then delegate to the pinned
    # official GaP CLI. They do not invoke any connector tool.
    for command in (['tools/validate_staged_graph.py', str(graph)],
                    ['tools/check_project_skills.py', str(graph),
                     '--registry', 'puzzler-modular-rgb-skills']):
        subprocess.run([sys.executable, *command], cwd=ROOT, check=True)
    from puzzler.assets import manifest
    manifest()  # Local known-CAD files only; never regenerate geometry.
    return document


def prepare(output, *, seed=0, max_steps=60000, graph=GRAPH):
    if seed != 0:
        raise ValueError('This candidate is scoped to the declared seed-0 layout')
    if max_steps <= 0:
        raise ValueError('max_steps must be positive')
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('Use a new output directory: ' + str(output))
    document = validate(graph)
    graph = Path(graph).resolve()
    output.mkdir(parents=True, exist_ok=False)
    path = output / 'manifest.json'
    manifest = dict(schema='puzzler.delivery_fresh_native.v1',
        initialization='fresh_canonical_all12_loose',
        initialization_scope='Fresh all12 loose under explicitly declared public layout C',
        graph=str(graph), episode=str(output / 'episode'),
        native_root=str(output / 'native_pool'), jobfile=str(output / 'native_jobs.py'),
        suite='delivery_' + output.name, seed=seed, max_steps=max_steps,
        device='cuda:0', contact_capacity=4096,
        physical_gpu_mask=None, rgb_renderer='RGBSensor tiled CUDA renderer',
        ordered_stages=ORDER,
        piece_phase_count=sum(len(v) for v in document['meta']['phase_schedule'].values()),
        initial_ledgers_empty=True, initialized_prefix=[], terminate_on_success=False,
        canonical_original_staging=False, public_initial_layout=deepcopy(LAYOUT),
        native_run_started=False, full12_acceptance=False, flat_acceptance=False,
        cached_qualification_used=False,
        complete_native_logs_required_for_capacity_audit=True,
        outcome='Unstarted launch request; physical completion is established only by its own native evidence.')
    path.write_text(json.dumps(manifest, indent=2) + '\n')
    # Resolve from this jobfile, so the prepared output can be reviewed without
    # embedding the old run or innerV10 directory in Python source.
    Path(manifest['jobfile']).write_text(JOB_SOURCE)
    return path


def run_prepared(path):
    path = Path(path).resolve()
    manifest = json.loads(path.read_text())
    expected = dict(schema='puzzler.delivery_fresh_native.v1',
                    initialization='fresh_canonical_all12_loose',
                    graph=str(GRAPH.resolve()), episode=str(path.parent / 'episode'),
                    native_root=str(path.parent / 'native_pool'),
                    jobfile=str(path.parent / 'native_jobs.py'),
                    device='cuda:0', seed=0, contact_capacity=4096,
                    initial_ledgers_empty=True, initialized_prefix=[],
                    ordered_stages=ORDER, terminate_on_success=False,
                    full12_acceptance=False, flat_acceptance=False,
                    canonical_original_staging=False, public_initial_layout=LAYOUT,
                    cached_qualification_used=False)
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError('Prepared launch contract or output paths changed')
    if manifest.get('max_steps', 0) <= 0 or Path(manifest['jobfile']).read_text() != JOB_SOURCE:
        raise ValueError('Prepared step bound or layout-C jobfile changed')
    if manifest.get('native_run_started') or Path(manifest['episode']).exists():
        raise RuntimeError('This output has already started; prepare a new directory')
    selected_gpu_mask()
    validate()
    gpu = gpu_check()
    manifest.update(native_run_started=True, physical_gpu_mask=gpu['physical_gpu_mask'],
                    cuda_runtime=gpu,
                    full12_acceptance=False, flat_acceptance=False,
                    outcome='Running; no completion claim at launch')
    path.write_text(json.dumps(manifest, indent=2) + '\n')
    from tools.unified_native import run
    return run(path)


def selected_gpu_mask():
    mask = os.environ.get('CUDA_VISIBLE_DEVICES', '').strip()
    if not mask or mask in ('-1', 'none', 'None') or ',' in mask:
        raise RuntimeError('Set CUDA_VISIBLE_DEVICES to one explicitly allocated physical GPU')
    return mask


def runtime_warp():
    """Inspect the selected installed wheel without initializing CUDA."""
    version = distribution('warp-lang').version
    if version != '1.18.0+cu12':
        raise RuntimeError('Official Warp 1.18.0+cu12 is required. Set PUZZLER_CUDA_DEPS '
                           'or run tools/install_cuda_deps.py; shared venv is unchanged.')
    import warp as wp
    return wp


def gpu_check():
    """Check only the selected CUDA device, without creating Env or rendering."""
    mask = selected_gpu_mask()
    wp = runtime_warp()
    # This is the first CUDA operation. Validation/preparation stay CPU-only.
    wp.init()
    device = wp.get_device('cuda:0')
    if not device.is_cuda:
        raise RuntimeError('cuda:0 is not available; CPU fallback is forbidden')
    os.environ.update(ROBOSIMSTUDIO_DEVICE='cuda:0', ROBOSIMSTUDIO_RENDERER='tiled')
    return dict(physical_gpu_mask=mask, device=device.alias, device_name=device.name,
                warp_distribution=distribution('warp-lang').version,
                warp_path=wp.__file__, no_Env_or_render=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('validate', 'prepare', 'run', 'run-prepared', 'gpu-check'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--max-steps', type=int, default=60000)
    args = parser.parse_args()
    if args.action == 'gpu-check':
        print(json.dumps(gpu_check(), indent=2))
    elif args.action == 'validate':
        validate()
        print('Fresh graph, official skill contract and local CAD: PASS; native not started')
    elif args.action == 'run-prepared':
        if args.manifest is None:
            parser.error('--manifest is required')
        print(run_prepared(args.manifest))
    else:
        if args.output is None:
            parser.error('--output is required')
        path = prepare(args.output, seed=args.seed, max_steps=args.max_steps)
        print(path, flush=True)
        if args.action == 'run':
            print(run_prepared(path))


if __name__ == '__main__':
    main()
