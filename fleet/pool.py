"""A pool of CPU Daytona sandboxes that runs gap-knot jobs, one job per sandbox at a time.

Library use (the self-learning loop calls this every iteration)::

    from fleet.pool import Pool, Job

    pool = Pool()                             # 2 vCPU / 4 GiB / 30 GiB -> snapshot gap-knot-rss-<hash>
    pool.up(8)                                # parallel create + health check (idempotent)
    results = pool.run([
        Job(id="ep-0001", cmd="python -m knotlab.rollout --seed 1 --out out",
            outputs=["out"], timeout_s=3 * 3600, env={"SEED": "1"}),
    ])                                        # -> list[JobResult]; also <results_dir>/results.jsonl
    pool.down()                               # delete every sandbox of this pool

Each job runs under the RSS venv with ``cwd`` = the code bundle (``/opt/gk/gap-knot``,
a fresh tarball of this checkout without third_party/, runs/, video/, .git) and
``PYTHONPATH=/opt/gk/gap-knot:/opt/gk/robosimstudio``. ``GK_CPUS`` holds the sandbox's
vCPU quota: inside a sandbox ``nproc`` reports the host's cores (48 on the runners
seen), not the quota, so the thread variables are set to the quota and a rope job
should start SuperDex with ``ensure_initialized(int(os.environ["GK_CPUS"]))``.

Files: ``{local: remote}``, a relative remote path is taken under the job's directory
(``$GK_JOB_DIR``). Outputs: remote paths (relative ones under ``cwd``) packed into one
tarball with the job's stdout/stderr, downloaded to ``<results_dir>/<id>/outputs.tar.gz``
and extracted beside it. A job whose sandbox is lost, or which runs past ``timeout_s``,
is retried once on a freshly created sandbox; a job that exits non-zero is not.
"""

from __future__ import annotations

import io
import json
import os
import queue
import re
import shlex
import sys
import tarfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fleet.common import (
    LABELS,
    MAX_ALIVE,
    POOL_LABEL,
    REMOTE_CODE,
    REMOTE_JOBS,
    REMOTE_PY,
    REMOTE_ROOT,
    REMOTE_RSS,
    ROOT,
    STATE,
    alive,
    append_jsonl,
    client,
    describe,
    is_mine,
    labels_of,
    ledger,
    list_mine,
    present,
    price_per_hour,
    state_of,
)

BUNDLE_EXCLUDE_DIRS = {"third_party", "runs", "video", ".git", "__pycache__", ".venv", ".pytest_cache",
                       "node_modules", ".mypy_cache", ".ruff_cache"}
BUNDLE_EXCLUDE_PATHS = {"fleet/state"}
THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
               "VECLIB_MAXIMUM_THREADS", "GK_CPUS")
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


class SandboxLost(Exception):
    """The sandbox stopped answering or left the started state."""


class JobTimeout(Exception):
    pass


@dataclass
class Job:
    id: str
    cmd: str
    files: dict[str, str] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)
    timeout_s: float = 3600.0
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None  # default: the code bundle, /opt/gk/gap-knot

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        known = {k: d[k] for k in ("id", "cmd", "files", "outputs", "timeout_s", "env", "cwd") if k in d}
        unknown = set(d) - set(known)
        if unknown:
            raise ValueError(f"job {d.get('id')!r}: unknown keys {sorted(unknown)}")
        job = cls(**known)
        if not _SAFE_ID.match(job.id):
            raise ValueError(f"job id {job.id!r} must match {_SAFE_ID.pattern}")
        job.env = {str(k): str(v) for k, v in (job.env or {}).items()}
        for k in job.env:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
                raise ValueError(f"job {job.id}: bad env name {k!r}")
        return job


@dataclass
class JobResult:
    id: str
    status: str  # ok | failed (non-zero exit) | timeout | lost | error
    exit_code: int | None = None
    attempts: int = 0
    sandboxes: list[str] = field(default_factory=list)
    run_s: float | None = None  # the command alone, measured in the sandbox
    wall_s: float | None = None  # dispatch to result, including uploads/downloads/retries
    started_at: float | None = None
    ended_at: float | None = None
    cpu: int | None = None
    memory: int | None = None
    outputs_tar: str | None = None
    outputs_dir: str | None = None
    missing_outputs: list[str] = field(default_factory=list)
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: str | None = None
    errors: list[str] = field(default_factory=list)  # one per failed attempt


# ----------------------------------------------------------------------------- bundle

def make_bundle(root: Path = ROOT) -> tuple[bytes, str]:
    """A reproducible .tar.gz of the checkout (sorted, mtime/owner zeroed) and its sha256[:12]."""
    import gzip
    import hashlib

    root = Path(root).resolve()

    def keep(rel: Path) -> bool:
        parts = rel.parts
        if any(p in BUNDLE_EXCLUDE_DIRS for p in parts):
            return False
        s = rel.as_posix()
        if any(s == p or s.startswith(p + "/") for p in BUNDLE_EXCLUDE_PATHS):
            return False
        return not s.endswith((".pyc", ".pyo"))

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for dirpath, dirnames, filenames in os.walk(root):
            rel_dir = Path(dirpath).relative_to(root)
            dirnames[:] = sorted(d for d in dirnames if keep(rel_dir / d))
            for name in sorted(filenames):
                rel = rel_dir / name
                path = Path(dirpath) / name
                if not keep(rel) or not (path.is_file() or path.is_symlink()):
                    continue
                info = tar.gettarinfo(str(path), arcname=rel.as_posix())
                info.mtime, info.uid, info.gid, info.uname, info.gname = 0, 0, 0, "", ""
                if info.isfile():
                    with open(path, "rb") as fh:
                        tar.addfile(info, fh)
                else:
                    tar.addfile(info)
    data = raw.getvalue()
    digest = hashlib.sha256(data).hexdigest()[:12]
    return gzip.compress(data, compresslevel=6, mtime=0), digest


# ----------------------------------------------------------------------------- pool

class Pool:
    """Sandboxes labelled owner=bohan,label=bohan,purpose=gap-knot,gk-pool=<name>."""

    def __init__(self, name: str = "default", *, cpu: int = 2, memory: int = 4, disk: int = 30,
                 snapshot: str | None = None, auto_stop: int = 45, results_root: Path | None = None,
                 poll_s: float = 5.0, create_parallel: int = 6, log=None, d=None):
        if not re.fullmatch(r"[a-z0-9-]{1,24}", name):
            raise ValueError("pool name must match [a-z0-9-]{1,24}")
        self.name = name
        self.cpu, self.memory, self.disk = int(cpu), int(memory), int(disk)
        self._snapshot = snapshot
        self.auto_stop = int(auto_stop)
        self.results_root = Path(results_root or STATE / "results")
        self.poll_s = poll_s
        self.create_parallel = create_parallel
        self._log = log or (lambda msg: print(msg, file=sys.stderr, flush=True))
        self._d = d
        self._lock = threading.Lock()
        self._bundle: tuple[bytes, str] | None = None
        self._known: dict[str, float] = {}  # sandbox ids this object created (listing lags creation)

    # -- plumbing
    @property
    def d(self):
        if self._d is None:
            self._d = client()
        return self._d

    @property
    def snapshot(self) -> str:
        if self._snapshot is None:
            from fleet.snapshot import shape_name

            self._snapshot = shape_name(self.cpu, self.memory, self.disk)
        return self._snapshot

    def log(self, msg: str) -> None:
        self._log(f"[pool {self.name}] {msg}")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.down()

    @property
    def labels(self) -> dict:
        return {**LABELS, POOL_LABEL: self.name}

    def _listed(self, all_pools: bool = False) -> list:
        """Our sandboxes by label listing, plus those this object created that the listing (which
        lags creation by a few seconds) does not show yet, re-read by id."""
        listed = list_mine(self.d) if all_pools else list_mine(self.d, pool=self.name)
        seen = {sb.id for sb in listed}
        with self._lock:
            missing = [i for i in self._known if i not in seen]
        for sid in missing:
            try:
                sb = self.d.get(sid)
            except Exception:
                sb = None
            if sb is None or not is_mine(sb) or not present(sb):
                with self._lock:
                    self._known.pop(sid, None)
                continue
            listed.append(sb)
        return listed

    def sandboxes(self, *, started_only: bool = True) -> list:
        out = [sb for sb in self._listed() if alive(sb)]
        return [sb for sb in out if state_of(sb) == "started"] if started_only else out

    # -- lifecycle
    def _create_one(self, index: int):
        from daytona import CreateSandboxFromSnapshotParams, DaytonaRateLimitError

        name = f"bohan-gk-{self.name}-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        params = CreateSandboxFromSnapshotParams(
            name=name, snapshot=self.snapshot, labels=dict(self.labels), ephemeral=True,
            auto_stop_interval=self.auto_stop, os_user="root",
            env_vars={"GK_CPUS": str(self.cpu)},
        )
        t0 = time.time()
        sb = None
        for attempt in range(4):
            try:
                sb = self.d.create(params, timeout=900)
                break
            except DaytonaRateLimitError as exc:
                self.log(f"create rate limited ({describe(exc)[:120]}); backing off")
                time.sleep(15 * (attempt + 1))
            except Exception as exc:
                ledger("create_failed", name=name, pool=self.name, snapshot=self.snapshot, error=describe(exc))
                self._reap_by_name(name)
                raise
        if sb is None:
            ledger("create_failed", name=name, pool=self.name, snapshot=self.snapshot, error="rate limited")
            self._reap_by_name(name)
            raise RuntimeError("sandbox create rate limited 4 times")
        with self._lock:
            self._known[sb.id] = time.time()
        ledger("created", id=sb.id, name=sb.name, pool=self.name, snapshot=self.snapshot, cpu=sb.cpu,
               memory=sb.memory, disk=sb.disk, seconds=time.time() - t0,
               price_per_hour=price_per_hour(sb.cpu, sb.memory, sb.disk))
        if not is_mine(sb):  # never expected; refuse to use anything unlabelled
            raise RuntimeError(f"created sandbox {sb.id} lacks ownership labels")
        try:
            self.health(sb)
        except Exception as exc:
            ledger("health_failed", id=sb.id, pool=self.name, error=describe(exc))
            self.delete(sb, why="health check failed")
            raise
        self.log(f"up {sb.id} ({sb.cpu} vCPU / {sb.memory} GiB) in {time.time() - t0:.0f}s")
        return sb

    def _reap_by_name(self, name: str) -> None:
        """A create that raised may still have made the sandbox: find it by name and delete it."""
        try:
            sb = self.d.get(name)
        except Exception:
            return
        if is_mine(sb):
            ledger("created", id=sb.id, name=name, pool=self.name, snapshot=self.snapshot, orphan=True)
            self.delete(sb, why="create raised")

    def ensure_snapshot(self) -> str:
        """The pool's snapshot, built if missing (a shape variant of the current recipe is instant)."""
        if getattr(self, "_snapshot_ok", None) == self.snapshot:
            return self.snapshot
        from fleet.snapshot import _get, _state, build, shape_name

        snap = _get(self.d, self.snapshot)
        if snap is not None and (snap.cpu, snap.mem, snap.disk) != (self.cpu, self.memory, self.disk):
            raise RuntimeError(f"snapshot {self.snapshot} is {snap.cpu} vCPU/{snap.mem} GiB/{snap.disk} GiB, "
                               f"not the pool's {self.cpu}/{self.memory}/{self.disk}")
        if snap is None or _state(snap) != "active":
            if self.snapshot != shape_name(self.cpu, self.memory, self.disk):
                raise RuntimeError(f"snapshot {self.snapshot} is {'missing' if snap is None else _state(snap)}")
            self.log(f"snapshot {self.snapshot} missing; building it")
            build(self.d, cpu=self.cpu, memory=self.memory, disk=self.disk, log=self.log)
        self._snapshot_ok = self.snapshot
        return self.snapshot

    def health(self, sb) -> dict:
        cmd = (f"test -x {REMOTE_PY} && cat /sys/fs/cgroup/cpu.max && nproc && "
               f"{REMOTE_PY} -c 'import robosimstudio, superdex.physics; print(\"gk-health-ok\")'")
        r = sb.process.exec(cmd, timeout=180)
        if r.exit_code != 0 or "gk-health-ok" not in (r.result or ""):
            raise RuntimeError(f"health check exit {r.exit_code}: {(r.result or '')[-500:]}")
        quota, nproc = (r.result or "").split("\n")[:2]
        q = quota.split()
        cpus = int(q[0]) / int(q[1]) if q and q[0].isdigit() else None
        ledger("healthy", id=sb.id, cgroup_cpus=cpus, nproc=nproc.strip())
        return {"cgroup_cpus": cpus, "nproc": nproc.strip()}

    def up(self, n: int) -> list:
        """Make this pool hold ``n`` started sandboxes (creating in parallel); returns them."""
        self.ensure_snapshot()
        have = [sb for sb in self._listed() if present(sb)]
        for sb in have:
            if state_of(sb) not in ("started", "starting", "creating", "pending_build", "building_snapshot",
                                    "pulling_snapshot", "restoring"):
                self.delete(sb, why=f"not started ({state_of(sb)})")
        have = [sb for sb in self.sandboxes(started_only=False) if state_of(sb) == "started"]
        need = max(0, n - len(have))
        if need:
            total = len([sb for sb in self._listed(all_pools=True) if present(sb)])
            room = MAX_ALIVE - total
            if need > room:
                self.log(f"cap: {total} gap-knot sandboxes alive, MAX_ALIVE={MAX_ALIVE}; creating {max(room, 0)} not {need}")
                need = max(room, 0)
        if need:
            self.log(f"creating {need} x {self.cpu} vCPU / {self.memory} GiB / {self.disk} GiB from {self.snapshot}")
            with ThreadPoolExecutor(max_workers=min(need, self.create_parallel)) as ex:
                futures = [ex.submit(self._create_one, i) for i in range(need)]
                for f in futures:
                    try:
                        have.append(f.result())
                    except Exception as exc:
                        self.log(f"create failed: {describe(exc)}")
        return have

    def delete(self, sb, why: str = "") -> bool:
        if not is_mine(sb):
            self.log(f"refusing to delete {getattr(sb, 'id', '?')}: not labelled owner=bohan,purpose=gap-knot")
            return False
        try:
            self.d.delete(sb, timeout=180, wait=True)
        except Exception as exc:
            if "not found" not in str(exc).lower():
                ledger("delete_failed", id=sb.id, error=describe(exc))
                self.log(f"delete {sb.id} failed: {describe(exc)}")
                return False
        with self._lock:
            self._known.pop(sb.id, None)
        ledger("deleted", id=sb.id, pool=labels_of(sb).get(POOL_LABEL), why=why)
        return True

    def down(self, *, all_pools: bool = False) -> int:
        """Delete every sandbox of this pool (or of every gap-knot pool); verify by listing."""
        for _ in range(3):
            sbs = [sb for sb in self._listed(all_pools) if present(sb)]
            if not sbs:
                return 0
            self.log(f"deleting {len(sbs)} sandbox(es)")
            with ThreadPoolExecutor(max_workers=8) as ex:
                list(ex.map(lambda sb: self.delete(sb, why="down"), sbs))
            time.sleep(5)  # the label listing lags deletion by a few seconds
        left = [sb for sb in self._listed(all_pools) if present(sb)]
        if left:
            self.log(f"WARNING: {len(left)} sandbox(es) still listed after down: {[sb.id for sb in left]}")
        return len(left)

    def status(self, *, all_pools: bool = False) -> list[dict]:
        rows = []
        now = time.time()
        for sb in self._listed(all_pools):
            created = getattr(sb, "created_at", None)
            try:
                from datetime import datetime

                age = now - datetime.fromisoformat(str(created).replace("Z", "+00:00")).timestamp()
            except Exception:
                age = None
            rows.append(dict(id=sb.id, name=sb.name, pool=labels_of(sb).get(POOL_LABEL), state=state_of(sb),
                             cpu=sb.cpu, memory=sb.memory, disk=sb.disk, snapshot=getattr(sb, "snapshot", None),
                             age_min=None if age is None else round(age / 60, 1),
                             price_per_hour=round(price_per_hour(sb.cpu, sb.memory, sb.disk), 4)))
        return rows

    # -- jobs
    def bundle(self, refresh: bool = False) -> tuple[bytes, str]:
        if self._bundle is None or refresh:
            self._bundle = make_bundle(ROOT)
        return self._bundle

    def _ensure_code(self, sb, data: bytes, digest: str) -> None:
        r = sb.process.exec(f"cat {REMOTE_CODE}/.bundle 2>/dev/null", timeout=30)
        if (r.result or "").strip() == digest:
            return
        tmp = f"{REMOTE_ROOT}/bundle-{digest}.tar.gz"
        sb.fs.upload_file(data, tmp)
        cmd = (f"set -e; rm -rf {REMOTE_CODE}.new; mkdir -p {REMOTE_CODE}.new; tar xzf {tmp} -C {REMOTE_CODE}.new; "
               f"echo {digest} > {REMOTE_CODE}.new/.bundle; rm -rf {REMOTE_CODE}; mv {REMOTE_CODE}.new {REMOTE_CODE}; rm -f {tmp}")
        r = sb.process.exec(cmd, timeout=300)
        if r.exit_code != 0:
            raise RuntimeError(f"bundle extract failed: {(r.result or '')[-500:]}")

    def _script(self, job: Job, jobdir: str, cpu: int) -> str:
        cwd = job.cwd or REMOTE_CODE
        env = {
            "VIRTUAL_ENV": f"{REMOTE_RSS}/.venv",
            "UV_NO_GROUP": "rtx",
            "PYTHONUNBUFFERED": "1",
            "MPLBACKEND": "Agg",
            "GK_JOB_ID": job.id,
            "GK_JOB_DIR": jobdir,
            "GK_CODE": REMOTE_CODE,
            "GK_RSS": REMOTE_RSS,
            **{v: str(cpu) for v in THREAD_VARS},
            "GK_SUPERDEX_THREADS": str(cpu),
            **job.env,
        }
        lines = [
            "#!/bin/bash",
            f"cd {shlex.quote(jobdir)}",
            "echo $$ > pid",
            "date +%s.%N > start",
            *(f"export {k}={shlex.quote(v)}" for k, v in env.items()),
            'export PATH="$VIRTUAL_ENV/bin:$PATH"',
            # fleet/remote holds sitecustomize.py (SuperDex workers = GK_SUPERDEX_THREADS, see there).
            f'export PYTHONPATH="{REMOTE_CODE}:{REMOTE_CODE}/fleet/remote:{REMOTE_RSS}${{PYTHONPATH:+:$PYTHONPATH}}"',
            f"cd {shlex.quote(cwd)} || {{ echo 'no such cwd {cwd}' > {jobdir}/stderr.log; echo 97 > {jobdir}/exit_code; exit 97; }}",
            f"bash -c {shlex.quote(job.cmd)} > {jobdir}/stdout.log 2> {jobdir}/stderr.log < /dev/null",
            "rc=$?",
            f"date +%s.%N > {jobdir}/end",
            f"cat /sys/fs/cgroup/memory.peak > {jobdir}/memory_peak 2>/dev/null || true",
            f"echo $rc > {jobdir}/exit_code.tmp && mv {jobdir}/exit_code.tmp {jobdir}/exit_code",
        ]
        return "\n".join(lines) + "\n"

    def _exec(self, sb, cmd: str, timeout: int = 60):
        """process.exec with a few retries; repeated failure -> SandboxLost if the sandbox is gone."""
        last = None
        for i in range(5):
            try:
                return sb.process.exec(cmd, timeout=timeout)
            except Exception as exc:
                last = exc
                time.sleep(3 * (i + 1))
                try:
                    cur = self.d.get(sb.id)
                    if not alive(cur) or state_of(cur) != "started":
                        raise SandboxLost(f"sandbox {sb.id} is {state_of(cur)}") from None
                except SandboxLost:
                    raise
                except Exception as get_exc:
                    if "not found" in str(get_exc).lower():
                        raise SandboxLost(f"sandbox {sb.id} not found") from None
        raise SandboxLost(f"sandbox {sb.id} unreachable: {describe(last)}")

    def _run_on(self, sb, job: Job, attempt: int, outdir: Path, stream) -> dict:
        """Run one job attempt on ``sb``; returns a partial result dict. Raises SandboxLost/JobTimeout."""
        cpu = int(getattr(sb, "cpu", self.cpu) or self.cpu)
        jobdir = f"{REMOTE_JOBS}/{job.id}.{attempt}"
        data, digest = self.bundle()
        try:
            self._ensure_code(sb, data, digest)
            r = sb.process.exec(f"rm -rf {jobdir} && mkdir -p {jobdir}", timeout=30)
            if r.exit_code != 0:
                raise RuntimeError(f"mkdir {jobdir}: {r.result}")
            for local, remote in job.files.items():
                remote = remote if remote.startswith("/") else f"{jobdir}/{remote}"
                parent = os.path.dirname(remote)
                sb.process.exec(f"mkdir -p {shlex.quote(parent)}", timeout=30)
                sb.fs.upload_file(str(Path(local).expanduser().resolve()), remote)
            sb.fs.upload_file(self._script(job, jobdir, cpu).encode(), f"{jobdir}/run.sh")
            # setsid: the job is its own process group, so a timeout can kill all of it.
            r = sb.process.exec(f"cd {jobdir} && (setsid nohup bash run.sh > launcher.log 2>&1 < /dev/null &) && echo launched",
                                timeout=30)
            if "launched" not in (r.result or ""):
                raise RuntimeError(f"launch failed: {r.result}")
        except (SandboxLost, JobTimeout):
            raise
        except Exception as exc:
            # Upload/launch errors on a dead sandbox are a loss, not a job failure.
            try:
                cur = self.d.get(sb.id)
                gone = not alive(cur) or state_of(cur) != "started"
            except Exception:
                gone = True
            if gone:
                raise SandboxLost(f"setup on {sb.id}: {describe(exc)}") from None
            raise
        t0 = time.time()
        offsets = {"stdout.log": 0, "stderr.log": 0}
        outdir.mkdir(parents=True, exist_ok=True)
        for fname in offsets:  # this attempt's stream starts empty
            (outdir / fname).write_text("")
        last_refresh = time.time()
        vanished = 0
        while True:
            time.sleep(self.poll_s)
            probe = self._exec(sb, f"cd {jobdir} && cat exit_code 2>/dev/null; echo '|'; "
                                   f"stat -c %s stdout.log stderr.log 2>/dev/null | tr '\\n' ' '; echo '|'; "
                                   f"kill -0 $(cat pid 2>/dev/null) 2>/dev/null && echo alive", timeout=30)
            head, _, rest = (probe.result or "").partition("|")
            sizes, _, liveness = rest.partition("|")
            sizes = [int(s) for s in sizes.split() if s.isdigit()]
            for (fname, off), size in zip(list(offsets.items()), sizes, strict=False):
                if size > off:
                    chunk = self._exec(sb, f"tail -c +{off + 1} {jobdir}/{fname} | head -c 1048576", timeout=60).result or ""
                    with open(outdir / fname, "a", encoding="utf-8", errors="replace") as fh:
                        fh.write(chunk)
                    if stream and fname == "stdout.log":
                        for line in chunk.splitlines():
                            stream(f"[{job.id}] {line}")
                    offsets[fname] = off + len(chunk.encode("utf-8", errors="replace"))
            if head.strip():
                exit_code = int(head.strip().splitlines()[-1])
                break
            vanished = 0 if "alive" in liveness else vanished + 1
            if vanished >= 3:  # run.sh is gone and wrote no exit code: the sandbox lost the process
                raise SandboxLost(f"job {job.id}: process vanished on {sb.id} without an exit code")
            if time.time() - t0 > job.timeout_s:
                self._exec(sb, f"kill -TERM -- -$(cat {jobdir}/pid) 2>/dev/null; sleep 5; "
                               f"kill -KILL -- -$(cat {jobdir}/pid) 2>/dev/null; true", timeout=60)
                raise JobTimeout(f"job {job.id} passed timeout_s={job.timeout_s:.0f} on {sb.id}")
            if time.time() - last_refresh > 300:
                try:
                    sb.refresh_activity()
                except Exception:
                    pass
                last_refresh = time.time()
        # Pack outputs (+ logs) into one tarball and bring it home.
        cwd = job.cwd or REMOTE_CODE
        parts = [f"tar cf {jobdir}/out.tar -C {jobdir} run.sh stdout.log stderr.log exit_code start end",
                 f"(tar rf {jobdir}/out.tar -C {jobdir} memory_peak 2>/dev/null || true)"]
        for out in job.outputs:
            base = os.path.dirname(out.rstrip("/")) if out.startswith("/") else cwd
            rel = os.path.basename(out.rstrip("/")) if out.startswith("/") else out
            parts.append(f"(test -e {shlex.quote(base)}/{shlex.quote(rel)} && tar rf {jobdir}/out.tar -C {shlex.quote(base)} "
                         f"{shlex.quote(rel)} || echo MISSING:{shlex.quote(out)})")
        parts.append(f"gzip -f {jobdir}/out.tar && cat {jobdir}/start {jobdir}/end && cat {jobdir}/memory_peak 2>/dev/null")
        r = self._exec(sb, "; ".join(parts), timeout=600)
        text = r.result or ""
        missing = [ln.split("MISSING:", 1)[1] for ln in text.splitlines() if ln.startswith("MISSING:")]
        nums = [ln for ln in text.splitlines() if re.fullmatch(r"\d+(\.\d+)?", ln.strip())]
        run_s = float(nums[1]) - float(nums[0]) if len(nums) >= 2 else None
        mem_peak = int(nums[2]) if len(nums) >= 3 else None
        tar_path = outdir / "outputs.tar.gz"
        try:
            sb.fs.download_file(f"{jobdir}/out.tar.gz", str(tar_path))
        except Exception as exc:
            raise SandboxLost(f"download from {sb.id}: {describe(exc)}") from None
        extracted = outdir / "outputs"
        with tarfile.open(tar_path) as tar:
            tar.extractall(extracted, filter="data")
        self._exec(sb, f"rm -rf {jobdir}", timeout=60)

        def tail(name: str) -> str:
            path = extracted / name
            return path.read_text(errors="replace")[-2000:] if path.exists() else ""

        return dict(exit_code=exit_code, run_s=run_s, memory_peak=mem_peak, outputs_tar=str(tar_path),
                    outputs_dir=str(extracted), missing_outputs=missing, stdout_tail=tail("stdout.log"),
                    stderr_tail=tail("stderr.log"))

    def run(self, jobs, *, results_dir: Path | str | None = None, size: int | None = None, keep: bool = True,
            stream=None) -> list[JobResult]:
        """Run jobs over the pool, one per sandbox at a time; returns a JobResult per job.

        ``size``: bring the pool to this many sandboxes first (default: keep what is up, or
        create min(len(jobs), MAX_ALIVE) if none). ``keep=False`` deletes the pool afterwards.
        """
        jobs = [j if isinstance(j, Job) else Job.from_dict(j) for j in jobs]
        ids = [j.id for j in jobs]
        if len(set(ids)) != len(ids):
            raise ValueError("job ids must be unique")
        results_dir = Path(results_dir or self.results_root / time.strftime(f"%Y%m%d-%H%M%S-{self.name}"))
        results_dir.mkdir(parents=True, exist_ok=True)
        results_file = results_dir / "results.jsonl"
        data, digest = self.bundle(refresh=True)
        self.log(f"code bundle {digest} ({len(data) / 1e6:.1f} MB); {len(jobs)} job(s) -> {results_dir}")
        results: dict[str, JobResult] = {}
        try:
            want = size if size is not None else (len(self.sandboxes()) or min(len(jobs), MAX_ALIVE))
            workers = self.up(min(want, len(jobs))) if jobs else []
            if jobs and not workers:
                raise RuntimeError("no sandboxes could be brought up")
            todo: queue.Queue = queue.Queue()
            for j in jobs:
                todo.put((j, 1))
            pending = {"n": len(jobs)}
            done_ev = threading.Event()
            lock = threading.Lock()

            def finish(res: JobResult) -> None:
                with lock:
                    results[res.id] = res
                    append_jsonl(results_file, asdict(res))
                    pending["n"] -= 1
                    if pending["n"] <= 0:
                        done_ev.set()
                ok = "ok" if res.status == "ok" else res.status.upper()
                self.log(f"{res.id}: {ok} exit={res.exit_code} run={res.run_s and round(res.run_s, 1)}s "
                         f"attempts={res.attempts}" + (f" error={res.error}" if res.error else ""))

            partial: dict[str, JobResult] = {}

            def worker(sb):
                while not done_ev.is_set():
                    try:
                        job, attempt = todo.get(timeout=1)
                    except queue.Empty:
                        if done_ev.is_set():
                            return
                        if not keep and sb is not None:
                            # Nothing left to start and the pool is not kept: stop paying for this one now.
                            self.delete(sb, why="idle at end of run")
                            return
                        continue
                    res = partial.setdefault(job.id, JobResult(id=job.id, status="error", started_at=time.time()))
                    res.attempts = attempt
                    res.sandboxes.append(sb.id if sb is not None else "")
                    res.cpu, res.memory = getattr(sb, "cpu", None), getattr(sb, "memory", None)
                    retry = False
                    try:
                        if sb is None:
                            raise SandboxLost("no sandbox")
                        out = self._run_on(sb, job, attempt, results_dir / job.id, stream)
                        res.exit_code, res.run_s = out["exit_code"], out["run_s"]
                        res.outputs_tar, res.outputs_dir = out["outputs_tar"], out["outputs_dir"]
                        res.missing_outputs = out["missing_outputs"]
                        res.stdout_tail, res.stderr_tail = out["stdout_tail"], out["stderr_tail"]
                        res.status = "ok" if out["exit_code"] == 0 else "failed"
                        res.error = None
                    except (SandboxLost, JobTimeout) as exc:
                        res.status = "timeout" if isinstance(exc, JobTimeout) else "lost"
                        res.error = describe(exc)
                        res.errors.append(res.error)
                        ledger("job_" + res.status, job=job.id, attempt=attempt, id=getattr(sb, "id", None),
                               error=res.error)
                        retry = attempt < 2
                        # Replace the sandbox: delete it (a timed-out one may be wedged) and create anew.
                        if sb is not None:
                            self.delete(sb, why=f"{res.status} on job {job.id}")
                        try:
                            sb = self._fresh()
                        except Exception as up_exc:
                            self.log(f"replacement sandbox failed: {describe(up_exc)}")
                            sb = None
                    except Exception as exc:
                        res.status, res.error = "error", describe(exc)
                        res.errors.append(res.error)
                    if retry:
                        self.log(f"{job.id}: {res.status} ({res.error}); retrying on a fresh sandbox")
                        todo.put((job, attempt + 1))
                        if sb is None:
                            return  # this worker has no sandbox left; others drain the queue
                        continue
                    res.ended_at = time.time()
                    res.wall_s = res.ended_at - res.started_at
                    finish(res)

            threads = [threading.Thread(target=worker, args=(sb,), daemon=True) for sb in workers]
            for t in threads:
                t.start()
            while not done_ev.wait(5):
                if not any(t.is_alive() for t in threads):
                    # Every worker lost its sandbox: fail what is left.
                    while True:
                        try:
                            job, attempt = todo.get_nowait()
                        except queue.Empty:
                            break
                        res = partial.setdefault(job.id, JobResult(id=job.id, status="error"))
                        res.status = res.status if res.status in ("lost", "timeout") else "error"
                        res.error = (res.error or "") + " | no sandbox left to retry on"
                        res.ended_at = time.time()
                        res.wall_s = res.ended_at - (res.started_at or res.ended_at)
                        finish(res)
                    break
            for t in threads:
                t.join(timeout=10)
        finally:
            if not keep:
                self.down()
        return [results[i] for i in ids if i in results]

    def _fresh(self):
        """A newly created sandbox for a retry (respecting MAX_ALIVE)."""
        total = len([sb for sb in self._listed(all_pools=True) if present(sb)])
        if total >= MAX_ALIVE:
            raise RuntimeError(f"MAX_ALIVE={MAX_ALIVE} reached; cannot replace a lost sandbox")
        return self._create_one(0)


def load_jobs(path: Path | str) -> list[Job]:
    raw = json.loads(Path(path).read_text())
    if isinstance(raw, dict) and "jobs" in raw:
        raw = raw["jobs"]
    if not isinstance(raw, list):
        raise ValueError("JOBS.json must be a list of jobs (or {\"jobs\": [...]})")
    return [Job.from_dict(j) for j in raw]
