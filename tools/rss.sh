#!/bin/bash
set -e
TASK_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$TASK_ROOT${PYTHONPATH:+:$PYTHONPATH}" CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES-}" OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}" OPENBLAS_NUM_THREADS=1
exec "$TASK_ROOT/third_party/robosimstudio/.venv/bin/python" "$@"
