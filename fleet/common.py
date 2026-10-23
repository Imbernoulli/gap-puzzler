"""Shared pieces of the gap-knot Daytona fleet: client, ownership labels, ledger, prices.

The API key is read from KEYFILE into the process environment and nowhere else:
it is never printed, logged, written to a file or passed to a sandbox. Every
string that leaves this package through a log or a JSONL record goes through
``redact`` first, because SDK exceptions can carry request details.
"""

from __future__ import annotations

import fcntl
import getpass
import json
import os
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # the gap-knot checkout
FLEET = ROOT / "fleet"
STATE = FLEET / "state"
LEDGER = STATE / "ledger.jsonl"
KEYFILE = Path(os.environ["DAYTONA_API_KEY_FILE"]) if os.environ.get("DAYTONA_API_KEY_FILE") else None

FLEET_OWNER = os.environ.get("PUZZLER_FLEET_OWNER", getpass.getuser())
LABELS = {"owner": FLEET_OWNER, "label": FLEET_OWNER, "purpose": "gap-puzzler"}
"""Every sandbox this package creates carries these; nothing without them is ever touched."""
POOL_LABEL = "gk-pool"
"""An extra label naming the pool a sandbox belongs to (default pool: "default")."""
MAX_ALIVE = 48
"""Hard cap on owner=bohan,purpose=gap-knot sandboxes alive at once, across all pools."""

# Remote layout (baked into the snapshot, see fleet/snapshot.py).
REMOTE_ROOT = "/opt/gk"
REMOTE_RSS = f"{REMOTE_ROOT}/robosimstudio"
REMOTE_PY = f"{REMOTE_RSS}/.venv/bin/python"
REMOTE_CODE = f"{REMOTE_ROOT}/gap-knot"
REMOTE_JOBS = f"{REMOTE_ROOT}/jobs"

# Daytona on-demand list prices, USD per hour (daytona.io/pricing: $0.000014 /vCPU/s,
# $0.0000045 /GiB RAM/s, $0.00000003 /GiB disk/s with the first 5 GiB free).
PRICE_CPU_H = 0.0504
PRICE_MEM_H = 0.0162
PRICE_DISK_H = 0.000108
FREE_DISK_GIB = 5


def price_per_hour(cpu: float, memory: float, disk: float) -> float:
    return cpu * PRICE_CPU_H + memory * PRICE_MEM_H + max(0.0, disk - FREE_DISK_GIB) * PRICE_DISK_H


_KEY: str | None = None


def _load_key() -> str:
    global _KEY
    if _KEY is None:
        _KEY = os.environ.get("DAYTONA_API_KEY") or (KEYFILE.read_text().strip() if KEYFILE else None)
        if not _KEY:
            raise RuntimeError("Set DAYTONA_API_KEY or DAYTONA_API_KEY_FILE for optional cloud evaluation.")
        os.environ["DAYTONA_API_KEY"] = _KEY
    return _KEY


def redact(value):
    """Strip the API key (whole or any 12+ char slice of it) from strings, recursively."""
    key = _KEY or os.environ.get("DAYTONA_API_KEY")
    if isinstance(value, str):
        if key:
            value = value.replace(key, "[redacted]")
            if len(key) >= 24:
                for i in range(0, len(key) - 12):
                    frag = key[i : i + 12]
                    if frag in value:
                        value = value.replace(frag, "[redacted]")
        return value
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


def describe(exc: BaseException) -> str:
    """An exception as ``Type: message`` with the key redacted and headers dropped."""
    text = str(exc)
    # urllib3/openapi exceptions append response headers; keep only the head.
    text = text.split("HTTP response headers")[0].strip()
    return redact(f"{type(exc).__name__}: {text}"[:2000])


def client():
    """A Daytona client authenticated from KEYFILE (imports the SDK lazily)."""
    _load_key()
    import warnings

    warnings.filterwarnings("ignore", message=".*doesn't match a supported version.*")
    from daytona import Daytona

    return Daytona()


def labels_of(sandbox) -> dict:
    return dict(getattr(sandbox, "labels", None) or {})


def is_mine(sandbox) -> bool:
    """owner=bohan AND purpose=gap-knot (the only sandboxes we may list/stop/delete)."""
    lab = labels_of(sandbox)
    return lab.get("owner") == LABELS["owner"] and lab.get("purpose") == LABELS["purpose"]


def state_of(sandbox) -> str:
    s = getattr(sandbox, "state", None)
    return str(getattr(s, "value", s) or "").lower()


def alive(sandbox) -> bool:
    name = getattr(sandbox, "name", "") or ""
    return state_of(sandbox) not in ("destroyed", "destroying", "error", "build_failed") and not name.startswith(
        "DESTROYED_"
    )


def present(sandbox) -> bool:
    """Not (being) destroyed: anything else -- error states included -- is ours to delete."""
    name = getattr(sandbox, "name", "") or ""
    return state_of(sandbox) not in ("destroyed", "destroying") and not name.startswith("DESTROYED_")


def list_mine(d, pool: str | None = None) -> list:
    """Our sandboxes (server-side label filter, then re-checked here)."""
    from daytona import ListSandboxesQuery

    query = dict(LABELS)
    query.pop("label")  # filter on the two ownership keys; 'label' is set on create
    if pool is not None:
        query[POOL_LABEL] = pool
    out = []
    for sb in d.list(ListSandboxesQuery(labels=query, limit=100)):
        if is_mine(sb) and (pool is None or labels_of(sb).get(POOL_LABEL) == pool):
            out.append(sb)
    return out


_LEDGER_LOCK = threading.Lock()


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(redact(record), default=str, sort_keys=True) + "\n"
    with _LEDGER_LOCK, open(path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.write(line)
        fh.flush()
        fcntl.flock(fh, fcntl.LOCK_UN)


def ledger(event: str, **fields) -> None:
    append_jsonl(LEDGER, {"ts": time.time(), "event": event, **fields})


def read_jsonl(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    out = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out
