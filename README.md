# Puzzler — RoboSimStudio × Graph-as-Policy

A real assembly puzzle reconstructed in GPU simulation, controlled by a modular,
observation-conditioned robot skill graph.

[Project website](https://bohanlyu.com/gap-puzzler/) ·
[Runnable policy source](delivery/pyramid_gap_v2/) ·
[Independent recorded-run review](site/data/policy_full_independent_review.json) ·
[Original demonstration](https://www.youtube.com/watch?v=PSgC31TvdxA)

The website presents four parts: real2sim reconstruction, a video synchronized
with the executing graph, visual self-refinement examples, a separate bimanual demonstration,
and measured adaptation experiments. Its video is a GPU replay of recorded native
states, with an explicit time mapping to the actual workflow and checkpoints.

## Current recorded result

The V13 pyramid run starts with all twelve pieces loose and physically assembles
all twelve in the original order. An independent audit checks the complete native
state/contact history: final maximum bead error is **2.53 mm**, with both arms home
and the released assembly stable. This result uses layout C: Lime's loose start is
shifted 70 mm along world Y.

The recorded graph passed **82 of its 84 required checkpoints**; the remaining
terminal verification refused because four historical visual receipts had become
uncertain. Physical completion and graph completion are reported separately.
The original trajectory, refusal, and missing checkpoints are preserved in
[the terminal record](site/data/policy_final_audit.json). The terminal-ledger repair and current-RGB whole-assembly verification have since
passed an isolated native terminal test. The corrected V17 policy and its
packaged v2 entry are now running new, separate, all-twelve-piece trials; their
full-run verdicts are pending.

## Method

- **RSS:** a reconstructed scene, public geometry, robot embodiment, task evaluator,
  and contact simulation.
- **GaP:** an executable typed graph of perception, grasping, handover, transport,
  release, and verification skills, authored with the supported builder and skill
  contracts. Modules and short sequences are rehearsed in parallel, then rejoined.
- **Policy inputs:** RGB images, robot proprioception, known geometry, and its own
  execution history. Online object poses and collision occupancy come from those
  inputs. Simulator object truth, contacts, and evaluator results remain outside
  the policy interface.
- **Evaluation:** separate physical checkpoints check actual manipulation and
  assembly; they do not provide object state for action generation.

[Source-grounded method review](site/data/evidence/method-alignment.json) ·
[Generalization evidence](https://bohanlyu.com/gap-puzzler/#generalization)

The adaptation results include three local source/board variations, sixteen
actual-function causal checks, and shape perception under shuffled/gray materials.
Each experiment retains its own scope in the linked evidence.

## Reproduce and inspect

The [self-contained source bundle](delivery/pyramid_gap_v2/README.md) contains the
reviewed policy, typed graph, public assets, skill registry, separate verifier,
pinned runtime recipe, and GPU-only entry point. Its clean-entry run is still in
progress; the bundle remains a draft. Version 2 contains the V17 policy,
with the corrected terminal logic. The [v1 snapshot](delivery/pyramid_gap_v1/)
preserves the displayed V13 policy and its original terminal refusal.

```bash
cd delivery/pyramid_gap_v2
python3 tools/bootstrap_runtime.py
CUDA_VISIBLE_DEVICES=0 ./run.sh --output /absolute/path/to/new-run
```

For an existing pinned RSS environment, follow the bundle README's runtime and
CUDA12 overlay instructions. No RTX hardware is required for this native renderer.

The committed `site/data/` and `site/media/` are a frozen publication snapshot.
GitHub Pages validates and deploys that snapshot without substituting older run
data. To validate it locally:

```bash
python3 tools/check_research_site.py
```

Earlier oracle-state baselines, flat-puzzle experiments, and their evidence remain
available in [the archived baseline documentation](BASELINE_README.md) and the
[earlier report](results/REPORT.md).
