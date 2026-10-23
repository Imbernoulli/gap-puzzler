# RGB-only GaP prototype

This is a separate executable prototype. The complete flat/pyramid videos and
successes from the original release remain oracle-state baselines.

The runtime program obtains object information from four calibrated RGB cameras,
using colour detection and rigid CAD fitting. It remeasures the piece after
lifting, above the goal, and after release. Work-arm choice follows the detected
source position. GaP checkpoints see only image-derived observations; the native
physical grader and recorded true poses are evaluation outputs only.

See the [observation audit](OBSERVATION_AUDIT.md) for source checks against RSS,
GaP and the user-supplied RAX paper, the original leaks, the exact tool boundary,
and unresolved assumptions.

## Perception experiment

Three reproducible non-overlapping scattered simulated scenes, seeds 201–203,
were rendered through the actual RSS RGB sensor. Every part has an independently
sampled planar position and yaw, across both sides of the board. The estimator
receives no scene seed, initial staging table, target pose, variant, true object
pose, depth or instance ID.

The final estimator reports **36/36** pieces visible, a median maximum-matched
bead error of **0.46 mm** per piece and a maximum of **1.06 mm**. Board positions
are estimated separately from the RGB case outline under the declared support
and yaw priors. Truth is read only after estimation to compute these errors.

These are development perception checks on three scenes, **not a held-out
manipulation success rate**. The initial estimator's 1.45 mm maximum on the same
scenes is retained separately; the refined contour fit is evaluated again with
source hashes. Data: [final perception records](vision_perception.json),
[initial records](vision_perception_initial.json).

## Physical diagnostics and failures

All twelve pieces start loose in every visual manipulation run. The frozen
`vision_flat_v1` workflow operates only on cyan, then releases both hands and
returns home. A subset outcome is never reported as completion of the puzzle:
the top-level result's `success` remains false.

The earlier development attempts below used a scene-wide IK seed. Although
their object detector used RGB, they do not validate the final visual input
contract. This additional audit finding and its correction are retained in the
[observation audit](OBSERVATION_AUDIT.md).

| Earlier attempt (superseded IK boundary) | Outcome | Independent physical finding |
| --- | --- | --- |
| Seed 101, original 3-view attempt | Failure/refusal | Source-arm motion occluded an obstacle; grasp planning refused |
| Seed 101, 4-view attempt | Failure | Placement missed tolerance; retry disturbed the case and then lost its visual board estimate |
| Seed 101, refined fit and lower release | Subset diagnostic pass | 1.24 mm final maximum bead error; 12.2 s released stability |
| Seed 102, same refined program | Subset diagnostic pass | 0.67 mm final maximum bead error; 12.2 s released stability |
| Scattered seed 201, same refined program | Failure | First grasp did not lift cyan; retry could not find a feasible source/goal grasp |
| Full flat seed 301, v1 | Failure | Orange and purple passed visual placement checks; yellow became occluded after lifting, so execution aborted |
| Full flat seed 302, v2, active inspection | Failure | Orange, purple and yellow passed visual placement checks; a later lime move failed full-pose IK at an 11.3 mm residual |

After the correction, IK reads only declared robot encoder slices and initializes
unrelated free objects to neutral transforms. The frozen cyan workflow was
re-run with the corrected helper:

| Corrected boundary attempt | Outcome | Independent physical finding |
| --- | --- | --- |
| Seed 101, `seed101_robot_only_ik` | Subset diagnostic pass | 0.99 mm final maximum bead error; 12.3 s released stability |
| Seed 102, `seed102_robot_only_ik` | Subset diagnostic pass | 0.50 mm final maximum bead error; 12.1 s released stability |
| Full flat seed 303, v3, robot-only IK | Failure | Orange, purple and yellow passed visual checks; retreat after lime release failed IK at a 10.4 mm residual, so the workflow aborted |

The corrected row-layout diagnostics passed **2/2**. They are development
diagnostics, not independent held-out trials. The earlier randomized
manipulation attempt failed **0/1** and has not been repeated with the corrected
IK boundary. An accurate detector does not by itself establish reliable grasping
across arbitrary placements.

The v3 full workflow additionally screens the exact source grasp and lift
endpoints, rather than accepting a reachable source hover alone. It still does
not guarantee that the image-corrected final pose and retreat will be reachable,
or that interpolated joint motions will avoid collisions. The seed 303 failure
is retained as a corrected-input full-task failure, not a partial success.

The [machine-readable execution ledger](vision_execution.json) includes every
completed visual attempt, visual checkpoint results and source hashes.
Per-episode RGB observation records, errors and frozen graph scripts are retained
in `runs/vision*`; raw images and trajectories are provided as evidence artifacts.
The [versioned prototype evidence release](https://github.com/Imbernoulli/gap-puzzler/releases/tag/v1.1.0-vision-prototype)
includes raw RGB frames, full trajectories and RPC traces, perception inputs,
source snapshots and a checked SHA-256 manifest. Rebuild the archive with
`python tools/archive_vision.py dist/vision-evidence.tar.gz` after running the
experiments.

[Single-piece trajectory replay](vision_cyan_seed101.mp4) renders the actual
recorded simulated body/joint poses without re-simulation or altered motions.
This external viewing camera is not an input to the policy. Original sensor
frames are saved separately, and a real sensor fixture is included in the tests.
The video uses `runs/vision_flat_v1/seed101_robot_only_ik`, after the IK correction.

The independent subset audit reconstructs bead locations from recorded rigid
poses, performs Hungarian matching, measures finite-difference bead speeds and
checks open, clear hands and a resting level board. It does not call the runtime
grader. The audits of the first two refined runs were added after execution;
later runs save them automatically. A subset audit does not assess the positions
of the other eleven pieces as if they had been assembled.

## Verification and reproduction

The test suite has 32 passing tests, including:

- Actual RGB replay produces the same grasp plan and tool arguments when the
  hidden task state changes; evaluator readers are patched to raise.
- Missing image evidence cannot fall back to a predicted or previous pose.
- Privileged tools are refused even if registered after the allowlist is built.
- Two calibrated views recover changed position and height on independent
  synthetic sphere images.
- An unobserved piece cannot pass a visual goal check.
- IK initialization refuses whole-scene and non-robot joint readback.
- A reachable hover cannot mask an unreachable source grasp during selection.

```bash
./tools/rss.sh -m unittest discover -s tests -v

./tools/rss.sh -m puzzler.episode \
  --graph graphs/vision_flat_v1 --observation rgb \
  --out runs/my_visual_diagnostic --seed 102 --max-steps 6000

./tools/rss.sh -m tools.check_vision \
  --out dist/my_visual_perception --seeds 401,402,403
```

Full twelve-piece visual assembly and pyramid assembly remain experimental.
Physical flat-to-pyramid extraction/reassembly has not been implemented. The
prototype also assumes known part colours and CAD, fixed calibrated cameras,
stable lighting and a level supported case in a limited yaw range. It has not
been validated on real hardware or overlapping piles. It is a runnable policy
with a bounded sensor interface, not a claim that all perception, control or
generalization problems have been solved.
