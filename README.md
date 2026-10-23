# IQ Puzzler Pro — oracle-state physical-control baseline

**The published full-assembly results are oracle-state baselines.** Their
controllers read simulator-provided object poses through `puzzle.observe`.
A separate **RGB-only GaP prototype** now performs image detection, calibrated
multi-view pose fitting and closed-loop single-piece grasp/place diagnostics.
It has not established a complete visual assembly policy.

The retained experiments demonstrate physical grasping and assembly with known
object poses. They are an **oracle-state control baseline**, not evidence of
visual perception, arbitrary-layout generalization, or task completion under
vision-only observations.

[Project website](https://bohanlyu.com/gap-puzzler/) ·
[Evidence report](results/REPORT.md) ·
[Complete experimental archive](https://github.com/Imbernoulli/gap-puzzler/releases/tag/v1.0.0) ·
[RGB prototype evidence](https://github.com/Imbernoulli/gap-puzzler/releases/tag/v1.1.0-vision-prototype) ·
[Source demonstration](https://www.youtube.com/watch?v=PSgC31TvdxA)

## Baseline results

Two simulated YAM arms assemble all twelve initially loose pieces into a flat
puzzle and a five-layer pyramid through motor control and physical contacts.
The final baseline policies use stock grippers and an accessible initial layout.

| Oracle-state baseline | Graph | Formal nominal repeats | Simulation time | Max. bead error |
| --- | --- | --- | --- | --- |
| Flat layout | `flat_v10` | 2/2 physical successes | 267.26 / 267.06 s | 0.71 / 0.61 mm |
| Pyramid | `pyramid_v40` | 2/2 physical successes | 363.28 / 344.54 s | 2.61 / 2.79 mm |

Each formal baseline success passes the RSS goal, a completed GaP workflow,
and an independent released-trajectory audit, with 4.6 seconds of released
stability. Those checks establish physical execution under oracle observations;
they do not establish that the observation contract is vision-only.

[Flat live recording](results/flat_live_success.mp4): 246.24 simulation seconds.
[Pyramid live recording](results/pyramid_live_success.mp4): 339.86 simulation
seconds, maximum bead error 2.759 mm. Both live takes pass RSS and GaP. They have
no separate full-pose independent audit; the formal episodes provide that check.
Failed placement checks and graph retries are retained.

## Capability status

| Requirement | Status |
| --- | --- |
| Contact-driven assembly using known object poses | Demonstrated in the baseline |
| RGB-only runtime observations | Implemented in a separate restricted prototype; single-piece diagnostics only |
| Reliable arbitrary loose-piece arrangements | Not demonstrated |
| Disassemble the flat puzzle, then build the pyramid | Not implemented or validated |
| Real-hardware execution | Not demonstrated |

The controller reacts to current object poses, but success on the fixed nominal
layout does not make it general. A faster candidate passed 0/2 held-out perturbed
flat scenes; an additional candidate passed 1/2. The current trials are insufficient
to establish robust layout generalization.

The vision-only acceptance contract requires that the policy derive object
information from camera observations and use only observable robot sensor state.
Ground-truth object poses and hidden simulator state belong in a separate
evaluator, not in policy inputs. Existing baseline results must not be relabeled
as successes for that future implementation.

## RGB-only prototype

[Observation audit and primary-source checks](results/OBSERVATION_AUDIT.md)
document the original leaks and the new boundary. [Visual experiment notes](results/VISION.md)
separate perception, single-piece diagnostics and complete assembly.

The estimator uses colour detection and known bead CAD with four calibrated RGB
views. It receives no object truth, depth, instance IDs, contact state, hidden
physics parameters or evaluator outcomes. The GaP tool whitelist and visual
checkpoints enforce the same interface during execution. Robot encoders and
kinematic models remain available. Board localization currently assumes level
table support and a limited yaw range; this is a declared geometric prior.

Three randomized non-overlapping simulated scenes yielded 36/36 detected pieces,
with a maximum matched bead error of 1.06 mm. Two development single-cyan runs
passed the visual workflow and independent released-pose diagnostic, with final
maximum bead errors of 0.99 and 0.50 mm after the robot-only IK input fix.
These results do not establish general assembly; earlier attempts and the
full-scene IK seed audit finding are retained with their actual provenance.

```bash
# Frozen single-piece diagnostic; all twelve pieces start loose.
./tools/rss.sh -m puzzler.episode \
  --graph graphs/vision_flat_v1 --observation rgb \
  --out runs/my_rgb_diagnostic --seed 102 --max-steps 6000

# Independent perception evaluation on new scattered scenes.
./tools/rss.sh -m tools.check_vision --out dist/my_rgb_check --seeds 401,402,403
```

`success` remains false for a subset diagnostic because the full puzzle is not
complete. Inspect `single_piece_physical_diagnostic` and
`independent_subset_audit` for that explicitly limited outcome.

## Included source and evidence

- `puzzler/`: geometry, dynamic RSS task, controller, oracle observations, IK tools,
  and independent audit.
- `graphs/`: all frozen baseline and diagnostic GaP workflows, scripts,
  checkpoints, retries, and abort routes.
- `third_party/`: pinned Git submodules for **RSS**, **GaP upstream**, the **actual
  RSS-compatible GaP runtime**, and **Open Robot Skills**.
- `live/`: executable browser workcell, configuration, reference stills, and
  native visual comparisons.
- `results/` and `runs/`: recordings, all episode outcome records, source hashes,
  independent audit reports, frozen-protocol summaries, and the failure ledger.
- `tools/`, `tests/`, `fleet/`: CPU setup, audits, rendering, local evaluation,
  parameter search, 32 tests including the observation-boundary regressions,
  and optional cloud infrastructure.
- `site/`: the English project website and interactive evidence viewer.

The [versioned release](https://github.com/Imbernoulli/gap-puzzler/releases/tag/v1.0.0)
contains the complete original experimental workspace: raw trajectories, RPC
traces, native recordings, frozen protocols, and a per-file SHA-256 manifest.
Extract it into a separate evidence directory; its historical files are preserved
byte for byte and may retain their original language and absolute path metadata.
The full downloaded source video is linked rather than redistributed.

## CPU installation

Use Linux, Python 3.12, and [uv](https://docs.astral.sh/uv/getting-started/installation/).
System libraries include `git`, `build-essential`, `libgl1`, `libegl1`,
`libglib2.0-0`, and `libgomp1`.

```bash
git clone --recurse-submodules https://github.com/Imbernoulli/gap-puzzler.git
cd gap-puzzler
./tools/bootstrap.sh
./tools/rss.sh -m unittest discover -s tests
```

The bootstrap creates `third_party/robosimstudio/.venv` and installs CPU execution
dependencies. Optional learned-policy, LIBERO, cuRobo, and RTX stacks are not
required for this baseline. Full upstream source is available through the
submodules. [RUNTIME.lock](RUNTIME.lock) records execution source revisions;
[environment/measured-packages.json](environment/measured-packages.json) records
the measured package inventory.

`THIRD_PARTY.lock` preserves the original checkout inventory. Its upstream GaP
revision was `71549e1`; the actual installed runtime was RSS's compatible fork at
`09e45f8`. Both source trees are included. Bootstrap installs the latter so that
the published baseline uses the runtime from the recorded experiments.

## Start the actual RSS workcell

```bash
./live/ctl up --scene live/scene.py --port 8081
./live/ctl status
./live/ctl play assemble --record my_take --every 70 --camera phone
```

Open **http://localhost:8081**. The default configuration runs the oracle-state
`pyramid_v40` baseline from twelve loose pieces with stock `yam_bimanual` hardware.
To run the flat baseline, set `mode: "flat"`, `graph: "graphs/flat_v10"`, and a fresh
`trace` name in [live/config.json](live/config.json), then reload.

```bash
./live/ctl snapshot --camera workcell
./live/ctl compare --take my_take --timeline live/ref/timeline_pyramid.json --key board=black
./live/ctl check --camera workcell --key board=black
```

RSS `check` resets the scene after its rest test. Capture the completed snapshot
first. Saved takes remain available. A rest check selecting only `board` measures
board drift; it is not an all-piece audit.

The public project website is a static evidence viewer. GitHub Pages serves
videos, checkpoint exploration, results, and documentation. The actual physics
workcell runs on the included local Python server.

## Run, audit, and render baseline episodes

```bash
./tools/rss.sh -m puzzler.episode --graph graphs/flat_v10 --mode flat \
  --nominal --max-steps 30000 --out runs/my_flat
./tools/rss.sh -m puzzler.episode --graph graphs/pyramid_v40 --mode pyramid \
  --nominal --max-steps 30000 --out runs/my_pyramid
./tools/rss.sh tools/audit_episode.py runs/my_pyramid
./tools/rss.sh tools/render.py runs/my_pyramid results/my_pyramid.mp4 --stride 22
```

Omit `--nominal` and choose `--seed N` for perturbed poses, friction, and grasp bias.
That starts a new baseline experiment, not a validated vision-only evaluation.
Simulation execution time and wall-clock time are separate metrics.

Local batches need no cloud account:

```bash
python3 tools/batch.py --graph graphs/pyramid_v40 --mode pyramid \
  --nominal --seeds 0,1 --workers 2 --out runs/local_repeats
```

The included [fleet helpers](fleet/README.md) support optional Daytona execution.
They use your `DAYTONA_API_KEY` or `DAYTONA_API_KEY_FILE` and a snapshot available
in your account. No cloud job is started by setup or by the website.

## Preview the English website

```bash
uv run --with Markdown==3.9 python tools/build_site.py
python3 -m http.server 8080 --directory site
```

GitHub Actions builds the same site and deploys it to GitHub Pages on pushes
to `main`.

## Assumptions and attribution

The flat packing is transcribed from the demonstration around 61 seconds. The
pyramid uses a robot-accessible exact-cover packing of the same twelve shapes,
with a different color arrangement. The source's white reverse carrier and
hand-held case motions are not modeled. Bead pitch, mass, friction, visual
materials, sockets, latches, and background are assumptions or approximations.

[RoboSimStudio](https://github.com/robosimstudio/robosimstudio),
[Graph-as-Policy](https://github.com/graph-robots/graph-as-policy), and
[Open Robot Skills](https://github.com/graph-robots/open-robot-skills) retain their
original licenses and notices. Reference stills are attributed to the
[original demonstration](https://www.youtube.com/watch?v=PSgC31TvdxA) and are
included for reconstruction comparisons. No photorealistic twin is claimed.
