"""gap-knot Daytona fleet CLI.

    python fleet/cli.py snapshot build [--cpu 4 --memory 8 --disk 30]
    python fleet/cli.py snapshot list | name | dockerfile
    python fleet/cli.py snapshot delete --name gap-knot-rss-<hash>-c8m4d30
    python fleet/cli.py up N [--pool NAME --cpu C --memory M --disk D --auto-stop MIN]
    python fleet/cli.py status [--pool NAME | --all] [--json]
    python fleet/cli.py run JOBS.json [--pool NAME --size N --cpu C ... --results DIR --keep --stream]
    python fleet/cli.py down [--pool NAME | --all]
    python fleet/cli.py ledger [--tail 20]

Run with an interpreter that has the optional daytona SDK installed.
``run`` deletes the pool's sandboxes when it finishes unless ``--keep`` is given.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fleet.common import LEDGER, describe, read_jsonl  # noqa: E402


def _pool(args):
    from fleet.pool import Pool

    return Pool(args.pool, cpu=args.cpu, memory=args.memory, disk=args.disk, snapshot=args.snapshot,
                auto_stop=args.auto_stop)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    def shape(sp):
        sp.add_argument("--pool", default="default")
        sp.add_argument("--cpu", type=int, default=2)
        sp.add_argument("--memory", type=int, default=4, help="GiB")
        sp.add_argument("--disk", type=int, default=30)
        sp.add_argument("--snapshot", default=None, help="override the snapshot name for this shape")
        sp.add_argument("--auto-stop", type=int, default=45, help="minutes idle before Daytona stops (and, ephemeral, deletes)")

    sp = sub.add_parser("snapshot")
    sp.add_argument("action", choices=["build", "list", "name", "dockerfile", "delete"])
    sp.add_argument("--name", default=None, help="for delete: a gap-knot-rss-* snapshot")
    sp.add_argument("--cpu", type=int, default=2)
    sp.add_argument("--memory", type=int, default=4)
    sp.add_argument("--disk", type=int, default=30)

    sp = sub.add_parser("up")
    sp.add_argument("n", type=int)
    shape(sp)
    sp = sub.add_parser("down")
    shape(sp)
    sp.add_argument("--all", action="store_true", help="every owner=bohan,purpose=gap-knot sandbox, all pools")
    sp = sub.add_parser("status")
    shape(sp)
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("run")
    sp.add_argument("jobs", type=Path)
    shape(sp)
    sp.add_argument("--size", type=int, default=None, help="sandboxes to bring up (default: min(#jobs, 24))")
    sp.add_argument("--results", type=Path, default=None)
    sp.add_argument("--keep", action="store_true", help="leave the sandboxes up for the next run")
    sp.add_argument("--stream", action="store_true", help="echo each job's stdout as it arrives")
    sp = sub.add_parser("ledger")
    sp.add_argument("--tail", type=int, default=20)
    args = p.parse_args(argv)

    try:
        if args.cmd == "snapshot":
            from fleet import snapshot

            if args.action == "build":
                print(snapshot.build(cpu=args.cpu, memory=args.memory, disk=args.disk))
            elif args.action == "list":
                for row in snapshot.info():
                    print(json.dumps(row))
            elif args.action == "delete":
                snapshot.delete(args.name)
                print(f"deleted {args.name}")
            elif args.action == "name":
                print(snapshot.shape_name(args.cpu, args.memory, args.disk))
            else:
                print(snapshot.dockerfile(), end="")
        elif args.cmd == "up":
            pool = _pool(args)
            sbs = pool.up(args.n)
            print(f"{len(sbs)} sandbox(es) up in pool {args.pool}: " + " ".join(sb.id for sb in sbs))
            return 0 if len(sbs) >= args.n else 1
        elif args.cmd == "down":
            left = _pool(args).down(all_pools=args.all)
            print("down: nothing left" if not left else f"down: {left} still listed")
            return 0 if not left else 1
        elif args.cmd == "status":
            rows = _pool(args).status(all_pools=args.all)
            if args.json:
                print(json.dumps(rows, indent=2))
            else:
                print(f"{'id':38} {'pool':10} {'state':10} cpu mem disk age_min  $/h")
                for r in rows:
                    print(f"{r['id']:38} {str(r['pool']):10} {r['state']:10} {r['cpu']:>3} {r['memory']:>3} {r['disk']:>4} "
                          f"{str(r['age_min']):>7} {r['price_per_hour']:.4f}")
                live = [r for r in rows if r["state"] not in ("destroyed", "destroying")]
                print(f"{len(live)} alive, ${sum(r['price_per_hour'] for r in live):.3f}/h")
        elif args.cmd == "run":
            from fleet.pool import load_jobs

            jobs = load_jobs(args.jobs)
            pool = _pool(args)
            results = pool.run(jobs, results_dir=args.results, size=args.size, keep=args.keep,
                               stream=print if args.stream else None)
            bad = [r for r in results if r.status != "ok"]
            for r in results:
                print(json.dumps({k: v for k, v in asdict(r).items() if k not in ("stdout_tail", "stderr_tail")}))
            print(f"{len(results) - len(bad)}/{len(jobs)} ok" + ("" if args.keep else "; pool deleted"))
            return 0 if not bad and len(results) == len(jobs) else 1
        elif args.cmd == "ledger":
            for row in read_jsonl(LEDGER)[-args.tail:]:
                print(json.dumps(row))
        return 0
    except KeyboardInterrupt:
        print("interrupted; sandboxes are left as they are -- run `down` to delete them", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"{args.cmd} failed: {describe(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
