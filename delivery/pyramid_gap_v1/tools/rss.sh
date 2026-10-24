#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TASK_PYTHON="${PUZZLER_PYTHON:-$TASK_ROOT/.runtime/venv/bin/python}"
TASK_CUDA_DEPS="${PUZZLER_CUDA_DEPS:-$TASK_ROOT/.runtime/cu12deps}"
if [[ ! -x "$TASK_PYTHON" ]]; then
  printf '%s\n' 'Set PUZZLER_PYTHON to the pinned runtime Python, or run tools/bootstrap_runtime.py.' >&2
  exit 1
fi
export PYTHONPATH="$TASK_ROOT${PYTHONPATH:+:$PYTHONPATH}"
if [[ -n "${PUZZLER_CUDA_DEPS:-}" && ! -d "$TASK_CUDA_DEPS/warp" ]]; then
  printf '%s\n' 'PUZZLER_CUDA_DEPS must contain the isolated official warp package.' >&2
  exit 1
fi
if [[ -d "$TASK_CUDA_DEPS/warp" ]]; then
  export PYTHONPATH="$TASK_ROOT:$TASK_CUDA_DEPS${PYTHONPATH:+:$PYTHONPATH}"
fi
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES-}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}" OPENBLAS_NUM_THREADS=1
export OPENCV_FOR_THREADS_NUM="${OPENCV_FOR_THREADS_NUM:-1}"
export NUMPY_MADVISE_HUGEPAGE="${NUMPY_MADVISE_HUGEPAGE:-0}"
export PYTHONUNBUFFERED=1
cd "$TASK_ROOT"
exec "$TASK_PYTHON" "$@"
