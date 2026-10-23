#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$TASK_ROOT"
command -v uv >/dev/null || { printf '%s\n' 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/'; exit 1; }
git submodule update --init
uv venv --python 3.12 third_party/robosimstudio/.venv
uv pip install --python third_party/robosimstudio/.venv/bin/python -r requirements-cpu.lock
# Install the exact source versions without optional GPU/ML bundle dependencies.
# Their CPU execution dependencies are listed and pinned in requirements-cpu.lock.
uv pip install --python third_party/robosimstudio/.venv/bin/python --no-deps \
  -e third_party/robosimstudio \
  -e third_party/graph-as-policy-runtime/gap-core \
  -e third_party/graph-as-policy-runtime \
  -e third_party/open-robot-skills
./tools/rss.sh -c 'import robosimstudio, gap, gap_core, mujoco, newton; print("RSS, GaP and CPU physics imports OK")'
printf '%s\n' 'Ready. Run: ./tools/rss.sh -m unittest discover -s tests' \
  'Open the workcell: ./live/ctl up --scene live/scene.py --port 8081'
