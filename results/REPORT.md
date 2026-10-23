# IQ Puzzler Pro: oracle-state baseline evidence

**The full-assembly baseline controller is not vision-only.** It obtains object positions and
orientations directly from the simulator through `puzzle.observe`. Images support
reconstruction, recording, and comparison; they are not the runtime perception
input. A separate RGB-only prototype now runs perception and single-piece
closed-loop diagnostics; see [visual results](VISION.md) and the
[observation-boundary audit](OBSERVATION_AUDIT.md). Complete visual assembly
has not been established.

The experiments below establish physical execution under privileged object-pose
observations. They must not be presented as visual manipulation or general-policy
successes. Arbitrary scattered starts and flat-to-pyramid disassembly/reassembly
are not demonstrated.

## Physical-control baseline results

Two stock YAM arms physically assemble all twelve loose pieces from accessible
initial rows and an empty dynamic case. Formal baseline episodes require the
native RSS goal, completed GaP execution, and an independent trajectory audit.

| Oracle-state task | Repeat | Simulation time | Max. bead error | Released stability | RSS / GaP / audit |
| --- | --- | --- | --- | --- | --- |
| Flat v10 | 0 | 267.26 s | 0.712 mm | 4.6 s | PASS / PASS / PASS |
| Flat v10 | 1 | 267.06 s | 0.610 mm | 4.6 s | PASS / PASS / PASS |
| Pyramid v40 | 0 | 363.28 s | 2.614 mm | 4.6 s | PASS / PASS / PASS |
| Pyramid v40 | 1 | 344.54 s | 2.788 mm | 4.6 s | PASS / PASS / PASS |

Sources: [flat summary](../runs/flat_v10_nominal/summary.json),
[pyramid evaluation](pyramid_v40_evaluation.json),
[pyramid protocol](pyramid_v40_evaluation_protocol.json), and
[source hashes](../runs/pyramid_v40_nominal/protocol_source_hashes.json).
Both pyramid repeats use identical task-source and workflow hashes, stock
`yam_bimanual`, and `preset_pieces: []`. Mean successful pyramid simulation time
is 353.91 seconds. These are nominal repeats after development, not held-out
randomized robustness tests.

All fourteen distinct checkpoints pass on their final invocation. The pyramid
repeats contain 16 and 15 records, including 2 and 1 failed attempt checks recovered
by explicit graph retries. Not every historical invocation passed.

### What was verified

1. **RSS native goal:** all 55 bead centers lie within 4 mm of assigned targets;
   pieces are still; the dynamic case rests level on the table; hands are open
   and clear; both wrists return home for a two-second physical hold.
2. **GaP execution:** the workflow reaches its success exit and retains measured
   checkpoint diagnostics, failed attempts, and recovery routes. These checks
   share the environment grader with RSS and are not independent of it.
3. **Independent trajectory audit:** a separate implementation reconstructs bead
   centers from recorded rigid poses, applies Hungarian matching in the case
   frame, estimates finite-difference velocities, and requires released stability.
   It shares the geometry but does not call the environment grader.

The [flat independent recomputation](../runs/flat_v10_nominal/iq-s1/outputs/out/seed1/audit_recomputed.json)
and [pyramid recomputation](../runs/pyramid_v40_nominal/iq-s1/outputs/out/seed1/audit_recomputed.json)
reject a piece displaced by 8 mm, closed hands, and the case plus pieces floating
50 mm above their recorded positions. Checkpoint worlds do not export contact
forces, so checkpoint acceptance is not a contact-force proof.

None of these checks establishes a vision-only observation contract. In the
current baseline, simulator ground truth still enters the controller. For a
future visual policy, this information must remain solely with the evaluator.

## Native live recordings

| Baseline recording | Simulation time | Maximum bead error | Recorded outcome |
| --- | --- | --- | --- |
| [Flat live take](flat_live_success.mp4) | 246.24 s | 0.969 mm | RSS/GaP pass; all 14 checkpoint invocations pass |
| [Pyramid v40 live take](pyramid_live_success.mp4) | 339.86 s | 2.759 mm | RSS/GaP pass; all 14 final distinct checkpoints pass |
| [Earlier pyramid v37 formal replay](pyramid_v37_success.mp4) | 355.04 s | 2.601 mm | One successful formal episode; v37 overall 1/2 |

Live takes have no separate exported full-pose independent audit. The formal
baseline episodes supply that check and are reported separately.

The [pyramid live result](pyramid_live_result.json) retains 16 checkpoint records
with two failed attempts recovered. Cyan's first error was approximately 13.18 mm;
a different grasp seated it at approximately 1.15 mm. Navy's retry physically
nudged it into place, opened the hand, waited, and rechecked the original criteria,
ending at approximately 2.08 mm. Failed attempts were not removed.

The pyramid [video check](pyramid_live_video_check.json) confirms H.264, 244 frames
at 1 fps, and 244 seconds of playback. This differs from its 339.86 simulation
seconds because the native recorder samples simulation steps. The
[actual last frame](pyramid_live_success_final.png) and
[completed workcell snapshot](pyramid_live_workcell_final.png) are saved.

The [final native RSS check](pyramid_live_check.json) passes: 0.07 mm worst overlap
between the board and cyan, and 0.0 mm board drift over 60 steps. This particular
rest check selected only `board`; it did not audit every piece's stability.

**RSS `check` resets the scene after its rest test.** A completed snapshot was
captured before this reset. A page showing the initial loose pieces afterward
is the runnable starting state. The subsequent empty-board `live/run/cmp_025`
comparison is excluded from completion evidence and archived as
`pyramid_live_post_reset_*`. Final visual metrics use the recorded last frame.

## Generalization and the requested vision-only policy

The nominal rows are convenient robot-accessible initial arrangements. The
controller reacts to measured simulator poses and updates grasp offsets, but
that capability is not proof of arbitrary-layout generalization.

| Capability | Status |
| --- | --- |
| Known-pose physical grasping and assembly | Demonstrated in the oracle baseline |
| Runtime recognition from camera images alone | Not implemented or validated |
| Reliable arbitrary scattered starts | Not demonstrated |
| Remove a completed flat layout, then build a pyramid | Not implemented or validated |
| Real-robot execution | Not demonstrated |

The visual-policy acceptance contract must separate controller observations
from evaluator state. Object information must come from camera observations;
robot state must come from observable sensors. Ground-truth object poses,
hidden simulator contacts, and evaluator-only state must not enter the policy.
The exact sensor and calibration contract must be specified before claiming
vision-only execution. All baseline outcomes remain labeled separately.

Flat-to-pyramid conversion would additionally require physical extraction,
temporary placement, support-aware disassembly, and regrasping before pyramid
assembly. No recorded trajectory implements that complete task.

## Controlled flat baseline comparison

The comparison archives one task/tool/evaluator bundle and checks identical
source hashes. Selection uses training seeds 20 and 21. Held-out seeds 100 and
101 are not reused for tuning after inspection.

| Oracle-state candidate | Training success | Mean successful training time | Held-out success |
| --- | --- | --- | --- |
| Fixed grasp heading | 0/2 | No successful episode | Not selected |
| Adaptive grasp | 2/2 | 270.25 s | See archived records |
| 20% faster trajectories | 2/2 | 249.60 s | 0/2 |
| Faster, higher grasp | 2/2 | 244.01 s | 1/2 |

The last candidate reduced training mean time by 9.71% relative to the adaptive
candidate, but reliable generalized acceleration was not established. Its one
successful held-out episode took 281.06 seconds. It was proposed from training
failures before inspection of the original held-out results; both selections
and all results are retained.

With two trials, Wilson 95% intervals are wide: approximately 34.2%–100% for 2/2
and 9.45%–90.55% for 1/2. [Recomputed controlled statistics](controlled_benchmark.json)
include failed attempt time in effective throughput. The additional candidate's
held-out rate is 9.60 completed puzzles per simulation hour and 5.09 per serial
wall-clock hour, excluding sandbox creation. Successful-cycle mean time is
separate. Older `success_parts_per_hour` fields actually described puzzles per
hour inferred from successful cycle means and are not effective throughput.

The [cleanup audit](cloud_cleanup_audit.json) records 20 finished pools, each with
`remaining: []`. This is historical recorded cleanup, not a current account-wide
resource scan.

## Pyramid failure exploration

The [development ledger](pyramid_search_ledger.json) distinguishes full loose-piece
episodes from preset-support diagnostics. Static targets, IK preflights, and
successful preset diagnostics never count as complete task successes.

- Early full runs disturbed seated pieces during support-arm transitions and
  exposed purple gripper interference.
- The robot6 packing restricts tilted-piece normals and gives purple a graspable
  base-layer endpoint. Exact cover took 878,948 nodes and 99.13 seconds. All
  55 lattice sites are covered exactly once by the twelve original rigid shapes.
  Static feasibility and reachable wrist poses remained diagnostic preconditions.
- v15 and v21 stalled at ten seated pieces. A navy part slightly beyond 4 mm
  settled below threshold, but immediate regrasping disrupted it. Later logic
  waits and rechecks the unchanged 4 mm and 0.015 m/s criteria before recovery.
- A local cyan test seated cyan at 1.27 mm while displacing yellow by about
  32.91 mm. Later logic checks existing supports, not only the current piece.
- Older handoff poses were unreachable. A robot6 v28 diagnostic physically
  transferred pink and lifted it about 35 mm after the first hand released,
  then failed at an unreachable target. Contact transfer was not full placement.
- A continuous Cartesian path placed pink at about 2.63 mm with stock grippers
  in a preset-support test; extensions were not necessary for that improvement.
- A red v35 trace reached about 1.89 mm, but a narrow 35 mm release trapped
  adjacent beads. Retreat lifted the apex again. A 90 mm release fixed this in
  v36, which remained a preset diagnostic, with `success: false`.
- Optional contact-seated recovery opens a failed grasp, waits, and verifies
  the unchanged error/speed limits and existing supports after physical contact
  has nudged a near-seated piece into place.
- v37 achieved the first complete stock-hardware success in 355.04 seconds, but
  repeated evaluation was [1/2](pyramid_v37_evaluation.json). Its other formal run
  and a live take failed at cyan. The single success remains separate from v40.
- v38 used cyan's proper rigid-shape symmetry for an outward grasp and continuous
  Cartesian carry, achieving about 1.47 mm locally without support damage.
  The same grasp with ordinary joint interpolation in v39 failed at about
  11.9 mm. v40 incorporated the Cartesian motion and passed both full nominal
  repeats and the native live take.
- A steeper local v41 cyan grasp failed to lift and was not promoted.

`puzzle.plan_path` interpolates wrist translation and rotation, solves sequential
full-pose IK, and executes through motors and contacts. It has no object-pose
setters and gives no general collision-free planning guarantee. The original
20 tests cover geometry, hardware preservation, seated rechecks, contact recovery,
and rigid grasp symmetry.

### Extended-finger diagnostics

Separate 20 mm and 40 mm extensions add 20 g and 12 collision geometries while
retaining original gripper geometry and settings. New rails use friction
`2.0 0.1 0.01`. These are additional hardware assumptions, not video hardware;
they are not merged with stock-gripper results. Original robot self-collision
settings remain a model limitation.

The complete 20 mm v4 trial seated only five pieces. A v8 test with ten preset
supports placed pink and dropped red, so the whole diagnostic failed. The slow
extension v9 run was superseded and [cancelled](../runs/pyramid_cartesian_trials/pyramid_precision_v9/cancellation.json);
exit 143 is not a scored completed manipulation failure. Final v40 uses no
finger extensions.

## Visual reconstruction comparison

The [pyramid action strip](pyramid_live_reference_strip.png) and
[recorded-final look sheet](pyramid_live_final_look.png) show visible differences
alongside the empty-to-complete progression. Frame index 243 at 339.86 simulation
seconds supplies the final RGB, which matches the decoded video frame exactly.
The recorded half-resolution segmentation is resized by nearest neighbor to
640×360. [Metrics and provenance](pyramid_live_final_metrics.json) identify inputs.

Final board-mask IoU is **0.377**, center offset approximately (-24, -21) pixels,
and area-derived size ratio 1.466. This measures only the board mask, not all
pieces or photorealism. The native “1 of 1 did what the clip did” verdict also
concerns only board motion. Source mask displacement is approximately (+344, -58)
pixels, versus (-15, -3) in simulation. The white reverse carrier in the first
reference is missed by the black color mask, so this is not reliable full-case
tracking.

The source person lifts and tilts the case; simulation leaves it on the table.
The white reverse carrier, hand-held display motions, and source pyramid color
packing are not reproduced. Piece order and timing differ. The arm occludes the
phone view late in the take before retreating for a clear last frame. Gloss,
sockets, latches, labels, skin, lighting, and background remain approximate.

The flat dynamic final red-mask IoU is 0.643, while a separate static positive
control gives 0.780. These are different images. Color segmentation can include
skin and omit pieces outside the close camera view. Mask overlap is a visual
diagnostic, not a runtime perception system or a physical success criterion.

## Reproduction and provenance

The [main README](../README.md) documents CPU setup, the actual RSS workcell,
local episodes, audits, rendering, optional cloud tools, and website generation.
The [versioned release](https://github.com/Imbernoulli/gap-puzzler/releases/tag/v1.0.0)
contains all original trajectories, RPC traces, frozen protocols, and native
recordings, with a SHA-256 manifest.

The original `THIRD_PARTY.lock` listed upstream GaP `71549e1`, but the installed
RSS execution environment used its compatible fork `09e45f8`. Both source trees
are included as pinned submodules. [RUNTIME.lock](../RUNTIME.lock) and the
[measured package inventory](../environment/measured-packages.json) distinguish
the actual installed runtime from the reference upstream checkout. Original
experimental source hashes and evidence remain unchanged.

The model uses a 25 mm bead pitch and 12.5 mm radius. Mass, stiffness, and friction
are monocular modeling assumptions, not measured calibration. The flat target
comes from about 61 seconds in the demonstration. The pyramid uses a solver-found
robot-accessible packing with different colors. No vision-only policy,
photorealistic twin, robust general policy, or real-hardware execution is claimed.
