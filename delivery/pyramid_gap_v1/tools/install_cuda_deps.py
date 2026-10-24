"""Install only the official Warp CUDA12 wheel into an isolated overlay.

For an existing pinned RSS Python, this avoids modifying its shared venv.
No Env, renderer, CUDA context or native policy is started by installation.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WHEEL = 'https://github.com/NVIDIA/warp/releases/download/v1.18.0/warp_lang-1.18.0%2Bcu12-py3-none-manylinux_2_28_x86_64.whl'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, default=ROOT / '.runtime/cu12deps')
    args = parser.parse_args()
    if not shutil.which('uv'):
        parser.error('Install uv first')
    target = args.target.resolve()
    if target.exists():
        parser.error('Use a new target directory; existing dependencies are never overwritten')
    subprocess.run(['uv', 'pip', 'install', '--python', sys.executable,
                    '--target', str(target), '--no-deps', WHEEL], check=True)
    print('Isolated CUDA12 overlay installed at ' + str(target))
    print('tools/rss.sh uses .runtime/cu12deps automatically, or set PUZZLER_CUDA_DEPS.')


if __name__ == '__main__':
    main()
