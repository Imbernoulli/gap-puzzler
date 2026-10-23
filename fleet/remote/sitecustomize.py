"""Loaded by every Python process a fleet job starts (fleet/remote is on the job's PYTHONPATH).

Inside a Daytona sandbox the CPU quota is a cgroup limit, while the hardware SuperDex
sizes its default worker pool from is the whole host (48 logical CPUs on the runners
seen): RSS's default ``threads=-1`` then starts ~22 workers on, say, 4 vCPUs, and the
knot pull ran 2-5x slower than with workers = quota. When ``GK_SUPERDEX_THREADS`` is set
(fleet.pool sets it to the sandbox's vCPUs), this turns RSS's ``-1`` into that number.
An explicit thread count (``ensure_initialized(n)`` with n >= 0) is left alone; set
``GK_SUPERDEX_THREADS=-1`` in a job's env to keep SuperDex's own choice. Nothing is
imported here beyond the standard library, and only when the bridge module is.
"""

import os
import sys

_THREADS = os.environ.get("GK_SUPERDEX_THREADS", "").strip()
_TARGET = "robosimstudio.engines.superdex.bridge"

if _THREADS.lstrip("-").isdigit() and int(_THREADS) >= 0:
    import importlib.abc
    import importlib.machinery

    class _SuperdexThreads(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name != _TARGET:
                return None
            sys.meta_path.remove(self)
            spec = importlib.machinery.PathFinder.find_spec(name, path)
            if spec is None or spec.loader is None:
                return spec
            exec_module = spec.loader.exec_module

            def patched_exec(module):
                exec_module(module)
                real = module.ensure_initialized

                def ensure_initialized(threads: int = -1):
                    return real(int(_THREADS) if int(threads) < 0 else threads)

                ensure_initialized.__doc__ = real.__doc__
                module.ensure_initialized = ensure_initialized

            spec.loader.exec_module = patched_exec
            return spec

    sys.meta_path.insert(0, _SuperdexThreads())
