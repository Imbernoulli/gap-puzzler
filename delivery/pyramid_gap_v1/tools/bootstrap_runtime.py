"""Install pinned dependency sources into .runtime; never start simulation.

Run explicitly on a clean machine with uv and git installed. Existing source
directories or an existing venv are refused rather than silently overwritten.
"""
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default='3.12')
    args = parser.parse_args()
    if not shutil.which('uv') or not shutil.which('git'):
        parser.error('Install uv and git first')
    runtime = ROOT / '.runtime'
    if runtime.exists():
        parser.error('.runtime already exists; use its Python or choose a new bundle')
    runtime.mkdir()
    sources = runtime / 'sources'
    sources.mkdir()
    pins = []
    for line in (ROOT / 'RUNTIME.lock').read_text().splitlines():
        if line and not line.startswith('#'):
            name, url, revision = line.split()
            if name != 'graph-as-policy':  # Reference-only checkout in the lock.
                pins.append((name, url, revision))
    for name, url, revision in pins:
        destination = sources / name
        subprocess.run(['git', 'clone', '--no-checkout', url, str(destination)], check=True)
        subprocess.run(['git', '-C', str(destination), 'checkout', '--detach', revision], check=True)
    venv = runtime / 'venv'
    subprocess.run(['uv', 'venv', '--python', args.python, str(venv)], check=True)
    python = venv / 'bin/python'
    subprocess.run(['uv', 'pip', 'install', '--python', str(python),
                    '-r', str(ROOT / 'requirements-runtime.lock')], check=True)
    command = ['uv', 'pip', 'install', '--python', str(python), '--no-deps']
    for relative in ('robosimstudio', 'graph-as-policy-runtime/gap-core',
                     'graph-as-policy-runtime', 'open-robot-skills'):
        command.extend(['-e', str(sources / relative)])
    subprocess.run(command, check=True)
    print('Runtime installed. tools/rss.sh -m tools.delivery validate performs CPU-only bundle checks.')


if __name__ == '__main__':
    main()
