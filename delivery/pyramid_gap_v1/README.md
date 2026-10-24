This is a runnable delivery **draft**, scoped to a fresh seed-0, all12-loose pyramid under the declared public layout C (Lime starts 70 mm farther along world Y). It preserves the original piece order, typed GaP subgraphs, RGB/proprioception/public CAD policy inputs, and independent physical checkpoints. It has no prefix, restored state, action tape, or cached receipt.

The packaged entry has now completed a fresh native trial: all twelve physical placements and RSS success passed, while the graph stopped at its original terminal-visual rule after 82 of 84 checkpoints. See `RUN_EVIDENCE.json` for the recorded main V13 scope; the clean-entry trial is separately documented in the repository's packaging evidence. This version preserves that original behavior; v2 contains the subsequent terminal repair.

On a clean machine with git and uv, `python3 tools/bootstrap_runtime.py` installs the revisions in `RUNTIME.lock` and numerical dependencies in `requirements-runtime.lock`, including the official **Warp 1.18.0+cu12** wheel used by the native candidates. The default PyPI 1.18.0 wheel uses CUDA 13.4 and fails on the current host's driver. The bootstrap recipe still requires clean-machine validation.

For an existing pinned RSS runtime, set `PUZZLER_PYTHON` to its `bin/python` and either set `PUZZLER_CUDA_DEPS` to the existing official CUDA12 overlay or run `PUZZLER_PYTHON=... ./tools/rss.sh tools/install_cuda_deps.py`. The latter installs only that wheel into this bundle's `.runtime/cu12deps`; the shared venv stays unchanged. `tools/rss.sh` discovers the bundle-local overlay automatically.

CPU-only bundle check:

```bash
./tools/rss.sh -m tools.delivery validate
```

Run with one explicitly allocated physical GPU and a new output directory:

```bash
CUDA_VISIBLE_DEVICES=0 ./run.sh --output /absolute/path/to/new-run > /absolute/path/to/new-run.native.log 2>&1
```

For an existing runtime, the single launch command is:

```bash
PUZZLER_PYTHON=/absolute/path/to/pinned/venv/bin/python PUZZLER_CUDA_DEPS=/absolute/path/to/cu12deps CUDA_VISIBLE_DEVICES=0 ./run.sh --output /absolute/path/to/new-run > /absolute/path/to/new-run.native.log 2>&1
```

`prepare --output PATH` and `run-prepared --manifest PATH/manifest.json` are also available through `tools/rss.sh -m tools.delivery`. Preparation never starts simulation. Each output path is used once. The launcher always selects `cuda:0` inside the chosen physical GPU mask and refuses CPU fallback. Keep complete stdout/stderr outside the policy inputs for capacity auditing.

`tools/rss.sh -m tools.delivery gpu-check` checks the selected CUDA12 wheel and allocated GPU without creating an Env or rendering; it uses the same gate as the native launcher.

The new output contains its manifest/jobfile, native pool captures, policy episode trace and RGB, and independent verification. The launch manifest starts with acceptance false. The final physical result, source integrity, all checkpoints, final all12 stability/home/contact gates, and complete-log capacity check must be reviewed before a completion claim. Historical `integration_status.json` and qualification booleans are not loaded by this entry.

Use the frozen graph included here. `tools/build_unified_graph.py` is retained as authoring provenance because the native source recorder includes it; rebuilding from the older profile sources can lose later candidate-specific graph settings. The packaged entry never rebuilds the graph. Historical paths in profile provenance strings are documentation, not runtime file dependencies.

`puzzler/`, `profiles/`, `assets/`, and the frozen graph contain the selected policy and public geometry. `registry_modular/` declares its official GaP skill contract; `third_party/open-robot-skills/` contains the official registry. `verification/` is a separate evaluator, whose privileged physical state does not enter the policy tool results. Runtime versions are pinned separately from task source.
