# Observation-boundary audit

The previously published flat and pyramid runs are **oracle-state physical-control
baselines**. They do not validate a visual policy. That was a substantive design
and acceptance error, not a naming issue.

## Source checks

The following primary-source sections were retrieved and checked on 2026-10-22.
They support the separation below; this is not a claim to reproduce their full
experimental protocols or results.

- [RoboSimStudio, arXiv:2610.18835v2](https://arxiv.org/abs/2610.18835),
  “Robot Interfaces”: privileged simulator state about manipulated objects is
  kept separate from observations available to the robot. Simulator feedback
  used during development is described separately.
- [GaP, arXiv:2607.05369v1](https://arxiv.org/abs/2607.05369), §3,
  “Problem Definition”: execution induces a closed-loop policy mapping
  multi-view images and graph state to actions. Known CAD and task geometry
  are part of the task specification; live object poses are not supplied by CAD.
- [RAX: Scaling Online Exploration for Robot Agents,
  arXiv:2610.22496v1](https://arxiv.org/abs/2610.22496), §§3.1–3.3,
  §5.3.2, Appendix A, C.2 and G.2.1: perception builds geometric estimates
  from sensor measurements; the final program executes with the same tools,
  and evaluation uses fresh scenes. G.2.1 gives a colour-threshold and geometry
  fitting example without a learned detector. The paper also measures a real
  performance cost when depth is removed.

These papers do not collectively require RGB-only sensing in every experiment.
This project's prototype deliberately uses a stricter **RGB-only + fixed camera
calibration + robot encoder/kinematic model** contract, to satisfy the requested
visual observation boundary without renderer depth or segmentation labels.

## Findings in the original controller

| Finding | Consequence | Visual implementation |
|---|---|---|
| `puzzle.observe` returns true object poses | Perception was bypassed | Separate RGB detector/CAD fitter, no simulator argument |
| `grade` returned in policy observation | Lift/retry/finish decisions could use hidden evaluation state | Observable goal residuals computed from RGB estimates |
| Checkpoint `World` includes true bodies, velocities and `puzzle_grade` | Verification could influence execution through privileged state | Empty physical-body world; only last visual estimate |
| Hidden `grasp_bias` returned | A sampled nuisance parameter enters the commanded pick pose directly | Removed; no hidden variant fields accepted |
| Initial staging table selects the work arm | Source-layout dependence was baked into execution | Work arm selected from observed source position |
| Default tool catalog offers alternate observations and privileged tools | Replacing one tool would not close the boundary | `privileged=False` plus explicit invocation whitelist |
| Fixed `board_feedback=False` path can use nominal board pose | A controller option can bypass current visual board localization | Removed from visual controller |
| True velocities, contact recovery and evaluator success gate routing | Hidden information can leak after a nominally visual grasp | Visual remeasurement, visual lift test and repeated-image stability |
| IK initialization copied the scene-wide joint vector, which includes free-object transforms | Hidden object coordinates entered a kinematic helper even though only arm solutions were returned | Neutral free-object transforms; read only declared robot encoder slices before readback |
| Nominal successes previously invited broader generalization claims | No evidence for arbitrary scattering or flat-to-pyramid transfer | Those claims remain unvalidated |

The frozen oracle graphs are retained as historical evidence. Their observations
are not retroactively changed or relabelled as visual observations.

The bias finding also limits the old perturbation benchmark: `grasp_bias` was
added to the controller's pick command after being returned in its observation.
It was not an independent physical actuator/sensor disturbance. Nominal runs use
zero bias, but the randomized runs must not be described as demonstrating
robustness to independently injected hardware bias.

## Visual runtime boundary

`RGBSensor` renders only `rgb`. `estimate(images, cameras, previous)` receives
pixels, fixed camera calibration and previous image-derived estimates. It does
not import the task/evaluator, request object poses, consume contact state, use
depth or instance IDs, or snap detections to goal poses. Motion-derived pose
predictions initialize optimization only; current-image agreement is required
before a pose is exposed as visible. Missing views cannot return a seed as a
measurement.

The policy tool whitelist contains RGB observations, robot end-effector feedback,
grasp-frame geometry, kinematic planning, joint trajectories, gripper commands,
wait and home. Alternate observation, simulator-object, contact and success
tools are excluded, including tools registered later by a skill. Reward and
completion readers on the policy facade return constants. Independent physical
grading and full state logging remain outside the policy for evaluation only.

The IK issue was found during the final audit of the first visual prototype.
Those earlier attempts are retained, but they are **not evidence for the final
input contract**. `vision_planning.robot_seed` now creates a neutral coordinate
vector from static model topology, sets unrelated free-joint quaternions to
identity, and reads only robot arm/gripper coordinate slices. Cartesian planning
also computes its starting end-effector pose from that sanitized vector. A
regression reader raises on a whole-vector or non-robot access. The execution
ledger identifies which IK boundary each recorded attempt actually used;
`*_robot_only_ik` runs re-evaluate the corrected boundary.

This is an enforced interface boundary for the authored program, **not an OS
security sandbox for hostile Python code**. The simulation, sensor adapter and
executor still share a process. The RGB estimator itself is also usable on saved
images without a simulator.

## Assumptions and remaining limitations

- Known colour-coded parts, known bead CAD, fixed calibrated cameras, stable
  simulated illumination and a declared workspace.
- Board localization currently assumes level table support at a calibrated
  height and a board yaw within ±90°. Its rectangular outline alone does not
  resolve a 180° reversal. A height prior is not a measured height; the prototype
  does not certify a lifted or tilted board.
- A model-fit residual is not a calibrated pose uncertainty interval. Subset
  checks and image-fitting tests are not full assembly successes.
- Occlusion, similarly coloured highlights and newly packed pieces can degrade
  detection. Failure/refusal records must remain in the reported denominator.
- Arbitrary overlapping piles, robust full assembly on unseen layouts, and
  physical extraction from a completed flat puzzle followed by pyramid assembly
  have not been established.

Tests exercise replay independence from the hidden evaluator, blocked tool paths,
missing-view refusal and multi-view height recovery. Physical experiments are
reported separately with independent grading; no assertion that all other errors
have been eliminated follows from this audit.
