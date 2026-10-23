"""The prebuilt environment: a Daytona snapshot with RSS + its CPU venv + the GaP siblings.

Layout inside the image (fleet.common.REMOTE_*):

    /opt/gk/robosimstudio       RSS at the THIRD_PARTY.lock commit, .venv synced CPU-only
    /opt/gk/graph-as-policy     sibling clone at its lock commit
    /opt/gk/open-robot-skills   sibling clone at its lock commit ([tool.gap] registries)
    /opt/gk/gap-knot            our code bundle, extracted per job by fleet.pool

The venv is ``UV_NO_GROUP=rtx uv sync --frozen --extra cpu --extra gap --extra superdex``:
``cpu`` is ``robosimstudio[superdex]`` (SuperDex for the rope; MuJoCo's C library for the
arms) and ``rtx`` (the 1.8 GB OVRTX path tracer) is left out. ``--frozen`` installs
exactly uv.lock, which pins torch's CUDA build, so the CUDA wheels torch and cuRobo
name come along (about 6 GB); nothing loads them on a CPU.

The snapshot name is ``gap-knot-rss-<hash>`` where the hash covers THIRD_PARTY.lock and
the Dockerfile text, so a changed pin or recipe is a new snapshot. Snapshots carry the
default sandbox shape; Daytona's API here has no hot resize (``POST .../resize`` 404s)
and takes no resources with a snapshot, so each sandbox shape is its own snapshot
(``gap-knot-rss-<hash>-c<cpu>m<mem>d<disk>``, built from the same image, see
``ensure_shape``).
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fleet.common import REMOTE_ROOT, REMOTE_RSS, ROOT, STATE, describe, ledger

LOCK = ROOT / "THIRD_PARTY.lock"
BASE_IMAGE = "python:3.12.13-slim-bookworm"
UV_VERSION = "0.11.14"
SYNC = "uv sync --frozen --no-cache --extra cpu --extra gap --extra superdex"
DEFAULT_SHAPE = (2, 4, 30)  # cpu, memory GiB, disk GiB: the benchmarked best episodes/h/$ (README)


def pins() -> dict[str, tuple[str, str]]:
    out = {}
    for line in LOCK.read_text().splitlines():
        parts = line.split()
        if len(parts) == 3:
            out[parts[0]] = (parts[1], parts[2])
    for name in ("robosimstudio", "graph-as-policy", "open-robot-skills"):
        if name not in out:
            raise ValueError(f"{LOCK} names no {name}")
    return out


def dockerfile() -> str:
    lines = [
        f"FROM {BASE_IMAGE}",
        "ENV DEBIAN_FRONTEND=noninteractive",
        "RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates curl procps"
        " build-essential libgl1 libegl1 libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*",
        f"RUN pip install --no-cache-dir uv=={UV_VERSION}",
        "ENV UV_NO_GROUP=rtx UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PYTHON=/usr/local/bin/python3.12",
        f"RUN mkdir -p {REMOTE_ROOT}/jobs",
    ]
    for name, (url, sha) in pins().items():
        lines.append(
            f"RUN git clone --quiet {url} {REMOTE_ROOT}/{name} && git -C {REMOTE_ROOT}/{name} checkout --quiet --detach {sha}"
            f" && test \"$(git -C {REMOTE_ROOT}/{name} rev-parse HEAD)\" = {sha}"
        )
    lines += [
        f"RUN cd {REMOTE_RSS} && {SYNC}",
        f"RUN cd {REMOTE_RSS} && .venv/bin/python -m robosimstudio.machine"
        " && .venv/bin/python -c 'import superdex.physics, newton, mujoco, gap, torch, viser; print(\"imports ok\")'",
        # Warm the on-disk caches (Warp's CPU kernels, RSS's convex pieces) with the knot scene: a fresh
        # sandbox otherwise spends ~25 s compiling them in its first episode. Warp keys its cache by CPU
        # target, so a builder CPU unlike the runners' only costs a miss. Never fails the build.
        f"RUN cd {REMOTE_RSS} && (timeout 1800 .venv/bin/python -c \"import os; "
        "from tests.fixtures.examples import _run; from tests.fixtures.grasp import open_session, tick; "
        "sim, kw = _run('03_materials/03_knot.py'); s = open_session(sim, 9785, kw.get('page')); tick(s, 60); "
        "print('warm-up ok', flush=True); os._exit(0)\" || echo 'warm-up failed (non-fatal)') && du -sh /root/.cache/* || true",
        f"WORKDIR {REMOTE_ROOT}",
    ]
    return "\n".join(lines) + "\n"


def image():
    from daytona import Image

    img = Image.base(BASE_IMAGE)
    img._dockerfile = dockerfile()  # the whole recipe, verbatim (Image.base adds only the FROM line)
    return img


def recipe_hash() -> str:
    return hashlib.sha256((LOCK.read_text() + dockerfile()).encode()).hexdigest()[:8]


def base_name() -> str:
    return f"gap-knot-rss-{recipe_hash()}"


def shape_name(cpu: int, memory: int, disk: int) -> str:
    if (cpu, memory, disk) == DEFAULT_SHAPE:
        return base_name()
    return f"{base_name()}-c{cpu}m{memory}d{disk}"


def _get(d, name):
    try:
        return d.snapshot.get(name)
    except Exception as exc:
        if "not found" in str(exc).lower() or type(exc).__name__ in ("DaytonaNotFoundError", "NotFoundException"):
            return None
        raise


def _state(snap) -> str:
    s = getattr(snap, "state", None)
    return str(getattr(s, "value", s) or "").lower()


def build(d=None, *, cpu: int = DEFAULT_SHAPE[0], memory: int = DEFAULT_SHAPE[1], disk: int = DEFAULT_SHAPE[2],
          log=print) -> str:
    """Build (or find) the snapshot for this recipe and shape; returns its name."""
    from daytona import CreateSnapshotParams, Resources

    from fleet.common import client

    d = d or client()
    name = shape_name(cpu, memory, disk)
    snap = _get(d, name)
    if snap is not None and (snap.cpu, snap.mem, snap.disk) != (cpu, memory, disk):
        raise RuntimeError(f"snapshot {name} exists as {snap.cpu} vCPU/{snap.mem} GiB/{snap.disk} GiB, not "
                           f"{cpu}/{memory}/{disk}; delete it (cli.py snapshot delete --name {name}) to rebuild")
    if snap is not None and _state(snap) == "active":
        log(f"snapshot {name} already active")
        return name
    if snap is not None and _state(snap) in ("error", "build_failed"):
        log(f"snapshot {name} is {_state(snap)} ({getattr(snap, 'error_reason', '')}); deleting and rebuilding")
        d.snapshot.delete(snap)
        ledger("snapshot_deleted", name=name, why=_state(snap))
        time.sleep(5)
    elif snap is not None:
        log(f"snapshot {name} is {_state(snap)}; waiting")
    STATE.mkdir(parents=True, exist_ok=True)
    logfile = STATE / f"snapshot-{name}.log"
    t0 = time.time()
    ledger("snapshot_build_started", name=name, cpu=cpu, memory=memory, disk=disk)
    with open(logfile, "a", encoding="utf-8") as fh:
        def on_logs(chunk: str) -> None:
            fh.write(chunk + "\n")
            fh.flush()

        try:
            if snap is None or _state(snap) in ("error", "build_failed"):
                d.snapshot.create(
                    CreateSnapshotParams(name=name, image=image(), resources=Resources(cpu=cpu, memory=memory, disk=disk)),
                    on_logs=on_logs,
                    timeout=0,
                )
            while _state(snap := _get(d, name)) not in ("active", "error", "build_failed"):
                time.sleep(10)
        except Exception as exc:
            ledger("snapshot_build_failed", name=name, error=describe(exc), seconds=time.time() - t0)
            raise RuntimeError(f"snapshot {name} failed after {time.time() - t0:.0f}s: {describe(exc)} (log: {logfile})") from None
    if _state(snap) != "active":
        ledger("snapshot_build_failed", name=name, state=_state(snap), seconds=time.time() - t0)
        raise RuntimeError(f"snapshot {name} ended {_state(snap)}: {getattr(snap, 'error_reason', '')} (log: {logfile})")
    ledger("snapshot_built", name=name, seconds=time.time() - t0, size=getattr(snap, "size", None),
           image_name=getattr(snap, "image_name", None))
    log(f"snapshot {name} active after {time.time() - t0:.0f}s (log: {logfile})")
    return name


def ensure_shape(d, cpu: int, memory: int, disk: int, log=print) -> str:
    """The snapshot for this shape: the base one, or a variant built from the same recipe.

    A variant reuses Daytona's build cache for the identical Dockerfile, so it costs a
    pull rather than a rebuild. Variants count against the org's snapshot quota (20).
    """
    return build(d, cpu=cpu, memory=memory, disk=disk, log=log)


def info(d=None) -> list[dict]:
    """Our snapshots (name prefix gap-knot-rss-) with state and size."""
    from fleet.common import client

    d = d or client()
    out, page = [], 1
    while True:
        res = d.snapshot.list(page=page, limit=100)
        for s in res.items:
            if s.name.startswith("gap-knot-rss-"):
                out.append(dict(name=s.name, state=_state(s), size=getattr(s, "size", None), cpu=s.cpu, mem=s.mem,
                                disk=s.disk, created_at=str(s.created_at), last_used_at=str(getattr(s, "last_used_at", ""))))
        if page >= (res.total_pages or 1):
            break
        page += 1
    return out


def delete(name: str, d=None) -> None:
    """Delete one of our snapshots (refuses any name outside gap-knot-rss-*)."""
    from fleet.common import client

    if not name.startswith("gap-knot-rss-"):
        raise ValueError(f"refusing to delete {name!r}: not a gap-knot-rss-* snapshot")
    d = d or client()
    d.snapshot.delete(name)
    ledger("snapshot_deleted", name=name, why="requested")


if __name__ == "__main__":
    print(dockerfile())
    print(base_name())
