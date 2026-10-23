"""Build the static English evidence viewer from the original measured results."""
from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
REPOSITORY = "https://github.com/Imbernoulli/gap-puzzler"


def read(path):
    return json.loads((ROOT / path).read_text())


def main():
    import markdown

    media = SITE / "media"
    data = SITE / "data"
    media.mkdir(exist_ok=True)
    data.mkdir(exist_ok=True)
    for name in (
        "flat_live_success.mp4", "flat_live_success_final.png",
        "pyramid_live_success.mp4", "pyramid_live_success_final.png",
        "pyramid_live_workcell_final.png", "pyramid_live_reference_strip.png",
        "pyramid_live_final_look.png", "pyramid_live_final_beside.png",
    ):
        shutil.copy2(ROOT / "results" / name, media / name)
    for name in (
        "flat_live_result.json", "pyramid_live_result.json", "pyramid_live_summary.json",
        "pyramid_v40_evaluation.json", "pyramid_live_final_metrics.json",
        "pyramid_live_check.json", "controlled_benchmark.json", "pyramid_search_ledger.json",
    ):
        shutil.copy2(ROOT / "results" / name, data / name)
    workflow = read("graphs/pyramid_v40/workflow.json")
    shutil.copy2(ROOT / "graphs/pyramid_v40/workflow.json", data / "pyramid_v40_workflow.json")
    live = read("results/pyramid_live_result.json")
    # The list is derived from the executable top-level success edges.
    order, name = [], workflow["conditional_edges"]["anchor"]["mapping"]["ready"]
    while name != "finish":
        order.append(name)
        name = workflow["conditional_edges"][name]["mapping"]["placed"]
    colors = {"azure":"#0473e8","orange":"#ff6403","yellow":"#ffbd08","teal":"#06908a","purple":"#8743b9","cyan":"#30c7ec","mint":"#65dfaf","lime":"#98cb16","maroon":"#d84462","navy":"#7772ef","pink":"#f265ac","red":"#f35345"}
    notes = {
        "cyan": "The first placement failed its check. A graph retry used a different grasp and seated the piece without disturbing its supports.",
        "navy": "The retry's physical contact nudged the piece into place. The gripper opened, waited, and rechecked the original placement and speed thresholds.",
        "pink": "A full-pose continuous Cartesian carry placed the tilted piece with the original YAM gripper.",
        "red": "The apex is released with a 90 mm jaw command to clear its neighboring beads before retreating.",
    }
    pieces = []
    for name in order:
        checks = [c for c in live["checkpoints"] if c["name"] == f"{name}_physical_state"]
        pieces.append({"name":name,"color":colors[name],"attempts":[{"passed":c["passed"],"error_mm":1000*c["diagnostics"]["bead_error_m"][name]} for c in checks],"note":notes.get(name,"Placement passed its measured checkpoint. The next subgraph can proceed while preserving previously seated pieces.")})
    flat = read("runs/flat_v10_nominal/summary.json")
    pyramid = read("results/pyramid_v40_evaluation.json")
    project = {"pieces":pieces,"formal":[
        {"label":"Flat layout","graph":"flat_v10","successes":sum(r["success"] for r in flat),"evidence":"runs/flat_v10_nominal/summary.json","runs":[{"sim_time_s":r["sim_time_s"],"max_error_mm":1000*r["independent_audit"]["final_max_bead_error_m"]} for r in flat]},
        {"label":"Pyramid","graph":"pyramid_v40","successes":pyramid["successes"],"evidence":"results/pyramid_v40_evaluation.json","runs":[{"sim_time_s":r["sim_time_s"],"max_error_mm":1000*r["independent_audit"]["final_max_bead_error_m"]} for r in pyramid["runs"]]},
    ]}
    assert len(order) == 12 and all(p["attempts"][-1]["passed"] for p in pieces)
    (data / "project.json").write_text(json.dumps(project,indent=2)+"\n")
    report = markdown.markdown((ROOT / "results/REPORT.md").read_text(),extensions=["tables","fenced_code","toc"])
    def link(match):
        target = html.unescape(match.group(1))
        if re.match(r"(?:[a-z]+:|#)",target):
            return match.group(0)
        path = (ROOT / "results" / target).resolve()
        relative = path.relative_to(ROOT).as_posix()
        return f'href="{REPOSITORY}/blob/main/{relative}"'
    report = re.sub(r'href="([^"]+)"',link,report)
    (SITE / "report.html").write_text(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Evidence report — Puzzler</title><link rel="icon" href="favicon.svg"><link rel="stylesheet" href="style.css"></head><body><header class="header wrap"><a class="brand" href="./">PUZZLER<span class="brand-sub">EVIDENCE REPORT</span></a><a class="repo-link" href="./">Back to project ↗</a></header><main class="wrap report-main">{report}</main><footer class="wrap footer"><p>RoboSimStudio × Graph-as-Policy</p><a href="{REPOSITORY}">Source repository ↗</a></footer></body></html>''')
    (SITE / ".nojekyll").touch()
    print(f"Built {SITE}: {len(pieces)} measured placements; {len(project['formal'])} formal task summaries.")


if __name__ == "__main__":
    main()
