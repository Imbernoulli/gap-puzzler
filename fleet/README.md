# Optional Daytona evaluation helpers

These helpers come from [gap-knot](https://github.com/Imbernoulli/gap-knot) at
`cbac9cb771e916e0d85c22d8a9fba95f1972bda3`, with portable authentication and
local imports. No sibling checkout is required.

Install the Daytona SDK separately and provide `DAYTONA_API_KEY` or
`DAYTONA_API_KEY_FILE`. No cloud jobs are launched by installation or the website.
`fleet/state/` is private local state and is excluded from Git.

```bash
python3 fleet/cli.py snapshot dockerfile
python3 fleet/cli.py snapshot build --cpu 8 --memory 16 --disk 30
python3 tools/daytona_batch.py --graph graphs/pyramid_v40 --mode pyramid \
  --nominal --seeds 0,1 --workers 2 --out runs/cloud_repeats
```

Historical tools reference `gap-knot-rss-abed33ba-c8m16d30`. If unavailable in your
account, build the pinned recipe and set `PUZZLER_DAYTONA_SNAPSHOT` to its name.
The historical names and remote `/opt/gk` layout are retained for compatibility.
`PUZZLER_FLEET_OWNER` chooses the ownership label; it defaults to the local OS user.

`Pool.run` deletes sandboxes unless explicitly told to keep them. Evaluation
scripts also call `pool.down()` in `finally` and record remaining sandboxes.
Cloud commands incur account charges. Local reproduction needs no cloud service.
