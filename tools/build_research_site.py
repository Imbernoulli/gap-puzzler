"""Export the research page from an executable policy and its recorded evidence.

This exporter does not run a policy. It preserves the distinction between policy
RGB inputs, independent physical checkpoints, and final episode acceptance.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "runs/pyramid_full12_bimanual_layout_c_v13/workspace/runs/full12_original_order_layout_c_v10"
COLORS = {
    "azure": "#0473e8", "orange": "#ff6403", "yellow": "#d5a400",
    "teal": "#06908a", "purple": "#8743b9", "cyan": "#25a9c8",
    "mint": "#46a984", "lime": "#87a91e", "maroon": "#a34360",
    "navy": "#555b9b", "pink": "#d35d99", "red": "#d64e43",
}
LABELS = {
    "perceive_plan": "Observe & plan", "grasp": "Grasp", "transport": "Transport",
    "release": "Release", "receipt_settle": "Observe & settle", "handoff": "Verify & advance",
    "cyan_approach": "Transfer approach", "cyan_receiver_close": "Receiver closes",
    "cyan_donor_release": "Donor releases", "cyan_receiver_bind": "Rebind from RGB",
    "cyan_receiver_transport": "Receiver transports", "red_handoff_prepare": "First transfer",
    "red_receiver_close": "Receiver closes", "red_sender_release": "Sender releases",
    "red_receiver_bind": "Rebind from RGB", "red_return_prepare": "Return transfer",
    "red_return_close": "Receiver closes", "red_return_release": "Sender releases",
    "red_return_bind": "Rebind from RGB", "red_goal_transport": "Apex approach",
    "red_goal_release": "Apex release", "red_goal_verify": "Verify & advance",
    "finish": "Home & final check",
}
CHECKPOINT_PHASES = {
    "receipt_settle": {"release", "conditional_release"},
    "cyan_approach": {"handoff_approach"}, "cyan_receiver_close": {"handoff_dualhold"},
    "cyan_donor_release": {"handoff_receiveronly"}, "cyan_receiver_bind": {"handoff_receiver_hold"},
    "cyan_receiver_transport": {"transport"}, "red_handoff_prepare": {"handoff_prepared"},
    "red_receiver_close": {"handoff_dualhold"}, "red_sender_release": {"handoff_receiver_only"},
    "red_receiver_bind": {"handoff_receiver_bound"}, "red_return_prepare": {"return_handoff_prepared"},
    "red_return_close": {"return_handoff_dualhold"}, "red_return_release": {"return_handoff_receiver_only"},
    "red_return_bind": {"return_handoff_receiver_bound"}, "red_goal_transport": {"transport"},
    "red_goal_release": {"release"}, "red_goal_verify": {"handoff"}, "finish": {"finish"},
}


def read_json(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def source_path(path: Path):
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def read_checkpoints(path: Path):
    records = []
    for line in path.read_text().splitlines(keepends=True):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if line.endswith("\n"):
                raise
            print("Ignoring an incomplete last checkpoint line from the live writer.")
    return records


def public_checkpoint(record, number):
    keys = (
        "piece", "phase", "passed", "native_step", "protected_window_start", "policy_input",
        "functional_postcondition_passed", "prefix_postcondition_passed", "maximum_prefix_bead_error_m",
        "target_max_matched_bead_error_m", "actual_attachment_bead_drift_m", "actual_jaw_width_m",
        "continuous_dual_finger_no_external_support", "continuous_no_foreign_support",
        "visual_receipt_status", "visual_diagnostics_affect_physical_result",
    )
    return {"number": number, **{key: record[key] for key in keys if key in record}}


def build(args):
    run, site = args.run.resolve(), args.site.resolve()
    workflow_path = run / "episode/trace/0000/workflow.json"
    checkpoint_path = run / "independent_verification/checkpoint_results.jsonl"
    workflow = read_json(workflow_path)
    records = read_checkpoints(checkpoint_path)
    audit = read_json(args.audit) if args.audit else None
    content = read_json(args.content) if args.content.exists() else {}
    media_manifest = read_json(args.media) if args.media.exists() else {}
    media = dict(media_manifest.get("media", {}))
    mapping = media.get("mapping", [])
    for index, point in enumerate(mapping):
        assert point["videoTime"] >= 0 and point["simTime"] >= 0
        if index:
            assert point["videoTime"] > mapping[index - 1]["videoTime"], "Video mapping must increase."
            assert point["simTime"] >= mapping[index - 1]["simTime"], "Simulation mapping must increase."
    if mapping:
        assert media_manifest.get("sourceEpisode") == source_path(run / "episode"), "Media belongs to a different policy episode."
    media["partial"] = media_manifest.get("partial", True)
    if media.get("kind") == "native_recorded_state_render":
        media["nativeFrameCount"] = media_manifest.get("nativeFrameCount", len(mapping))
        media["recordedFrameCount"] = media_manifest.get("recordedFrameCount")
        observations_path = run / "episode/rgb/observations.json"
        media["policyRGBObservationCount"] = len(read_json(observations_path)) if observations_path.exists() else None
    else:
        media["observationCount"] = media_manifest.get("observationCount", len(mapping))
    last_sim = mapping[-1]["simTime"] if mapping else 0

    def video_at(sim_time):
        if not mapping or sim_time > last_sim:
            return None
        # Step media holds authentic observations. Seek to the first recorded
        # observation at/after the checkpoint boundary, never to an invented frame.
        index = bisect_left([p["simTime"] for p in mapping], sim_time)
        return mapping[min(index, len(mapping) - 1)]["videoTime"]

    schedule = []
    for piece in workflow["meta"]["ordered_stages"]:
        for phase in workflow["meta"]["phase_schedule"][piece]:
            node_id = f"{piece}_{phase}"
            assert node_id in workflow["nodes"], f"Missing executable node: {node_id}"
            schedule.append({"piece": piece, "phase": phase, "nodeId": node_id})
    finish_id = next((name for name, node in workflow["nodes"].items() if node.get("ref") == "finish_sg"), None)
    assert finish_id, "Workflow has no final finish subgraph."
    schedule.append({"piece": "all12", "phase": "finish", "nodeId": finish_id})
    assert len(records) <= len(schedule), "Repeated or unexpected checkpoints require explicit alignment."

    terminal = None
    result_path = run / "episode/result.json"
    trace_path = run / "episode/trace/0000/dag_trace.json"
    if result_path.exists() and trace_path.exists():
        result = read_json(result_path)
        next_stage = schedule[len(records)] if len(records) < len(schedule) else None
        if next_stage:
            expected_ref = workflow["nodes"][next_stage["nodeId"]].get("ref")
            errors = [event for event in read_json(trace_path).get("events", [])
                      if event.get("event_type") == "error_recorded" and event.get("node_name") == f"{expected_ref}.act"]
            if errors:
                error = errors[-1]
                terminal = {"nodeId": next_stage["nodeId"], "status": "refused" if "StageRefusal" in error.get("detail", {}).get("error", "") else "failed",
                            "reason": error.get("detail", {}).get("error"), "simTime": result["sim_time_s"],
                            "graphSuccess": result.get("graph_success"), "rssSuccess": result.get("rss_success"),
                            "sourceEvent": error}

    timeline = []
    compact_records = []
    for index, record in enumerate(records):
        expected = schedule[index]
        accepted_phases = CHECKPOINT_PHASES.get(expected["phase"], {expected["phase"]})
        assert record["phase"] in accepted_phases, f"CP {index + 1}: expected {expected}, got phase {record['phase']}"
        if expected["phase"] != "finish":
            assert record["piece"] == expected["piece"], f"CP {index + 1}: unexpected piece."
        sim_start = record["protected_window_start"] / 50
        sim_end = record["native_step"] / 50
        assert sim_end >= sim_start
        if timeline:
            assert sim_start >= timeline[-1]["simEnd"], "Checkpoint windows must be sequential."
        checkpoint = public_checkpoint(record, index + 1)
        compact_records.append(checkpoint)
        timeline.append({**expected, "simStart": sim_start, "simEnd": sim_end,
                         "videoStart": video_at(sim_start), "videoEnd": video_at(sim_end),
                         "passed": record["passed"], "checkpoint": checkpoint})
    # Observations can show the next stage before its independent checkpoint is
    # written. Preserve that as an unfinished stage, without granting a pass.
    end = timeline[-1]["simEnd"] if timeline else 0
    if terminal:
        timeline.append({**schedule[len(records)], "simStart": end, "simEnd": terminal["simTime"],
                         "videoStart": video_at(end), "videoEnd": video_at(terminal["simTime"]),
                         "passed": False, "checkpoint": None, "terminalStatus": terminal["status"]})
    elif len(records) < len(schedule) and last_sim > end and (not records or records[-1]["passed"]):
        timeline.append({**schedule[len(records)], "simStart": end, "simEnd": last_sim + .001,
                         "videoStart": video_at(end), "videoEnd": media.get("duration"),
                         "passed": None, "checkpoint": None})

    edges = []
    for start, target in workflow.get("edges", []):
        edges.append({"source": start, "target": target, "conditions": [], "kind": "direct"})
    for start, route in workflow.get("conditional_edges", {}).items():
        targets = {}
        for condition, target in route["mapping"].items():
            targets.setdefault(target, []).append(condition)
        for target, conditions in targets.items():
            edges.append({"source": start, "target": target, "conditions": conditions,
                          "kind": "error" if target == "abort" else "conditional"})
    graph_nodes = []
    for item in schedule:
        node = workflow["nodes"][item["nodeId"]]
        graph_nodes.append({**item, "label": LABELS.get(item["phase"], item["phase"]), "ref": node.get("ref")})
    for node_id in ("abort", "done"):
        if node_id in workflow["nodes"]:
            graph_nodes.append({"nodeId": node_id, "piece": "all12", "phase": node_id,
                                "label": "Abort" if node_id == "abort" else "Complete", "type": "end"})
    pieces = []
    for piece in workflow["meta"]["ordered_stages"]:
        stages = [x for x in schedule if x["piece"] == piece]
        observed = [x for x in timeline if x["piece"] == piece and x["checkpoint"]]
        first = next((x for x in timeline if x["piece"] == piece), None)
        pieces.append({"name": piece, "color": COLORS.get(piece, "#68776d"),
                       "nodeIds": [x["nodeId"] for x in stages],
                       "simStart": first["simStart"] if first else None,
                       "videoStart": first["videoStart"] if first else None,
                       "checkpointCount": len(observed), "expectedCheckpoints": len(stages),
                       "complete": len(observed) == len(stages) and all(x["passed"] for x in observed)})
    all_checkpoints_pass = len(records) == len(schedule) and all(x["passed"] for x in records)
    physical_accepted = bool(audit and audit.get("full12Physical") is True)
    accepted = bool(all_checkpoints_pass and physical_accepted and audit.get("accepted") is True)
    run_info = {
        "id": run.parent.parent.parent.name, "name": workflow["meta"].get("name"),
        "source": source_path(run), "updatedAt": datetime.now(timezone.utc).isoformat(),
        "checkpointCount": len(records), "expectedCheckpoints": len(schedule),
        "passedCheckpoints": sum(x["passed"] is True for x in records),
        "completePieces": sum(x["complete"] for x in pieces), "pieceCount": len(pieces),
        "checkpointComplete": all_checkpoints_pass, "independentAuditAvailable": audit is not None,
        "full12Accepted": accepted, "mediaPartial": media.get("partial", True),
        "physicalAccepted": physical_accepted, "terminal": terminal,
        "timingBasis": "Independent native checkpoint windows at 50 Hz, matched to archived policy RGB timestamps.",
        "checkpointScope": "Independent physical checks; simulator diagnostics are not policy inputs. RGB receipts retain their own status.",
    }
    export = {"schema": "puzzler-research-site-v1", "run": run_info, "media": media,
              "timeline": timeline, "pieces": pieces, "graph": {"nodes": graph_nodes, "edges": edges},
              "refinement": content.get("refinement", []), "generalization": content.get("generalization", []),
              "intro": content.get("intro", {}), "real2sim": content.get("real2sim", {}),
              "methodAlignment": content.get("methodAlignment", {}),
              "evidence": {"workflow": "data/policy_workflow.json", "checkpoints": "data/policy_checkpoints.json",
                           "media": "data/policy_media_manifest.json"}}
    write_json(site / "data/research.json", export)
    write_json(site / "data/policy_checkpoints.json", {"run": run_info, "records": compact_records})
    write_json(site / "data/policy_media_manifest.json", media_manifest)
    shutil.copy2(workflow_path, site / "data/policy_workflow.json")
    for key, summary in content.get("evidenceSummaries", {}).items():
        assert key.replace("-", "").replace("_", "").isalnum(), "Unsafe evidence filename."
        write_json(site / "data/evidence" / f"{key}.json", summary)
    if audit:
        write_json(site / "data/policy_final_audit.json", audit)
        export["evidence"]["audit"] = "data/policy_final_audit.json"
        write_json(site / "data/research.json", export)
    if terminal:
        write_json(site / "data/policy_terminal.json", terminal)
    print(f"Built {site / 'data/research.json'}: {len(records)}/{len(schedule)} physical checkpoints, "
          f"{run_info['completePieces']}/{len(pieces)} completed piece modules, {len(mapping)} recorded timing points.")
    return export


def validate_export(site: Path):
    """Check the frozen deployment without local simulation runs or dependencies."""
    data = read_json(site / "data/research.json")
    workflow = read_json(site / "data/policy_workflow.json")
    checkpoints = read_json(site / "data/policy_checkpoints.json")
    media_manifest = read_json(site / "data/policy_media_manifest.json")
    assert data["schema"] == "puzzler-research-site-v1"
    assert media_manifest["sourceEpisode"] == f"{data['run']['source']}/episode", "Media and trace episode differ."
    assert data["pieces"] and len(checkpoints["records"]) == data["run"]["checkpointCount"]
    assert sum(record["passed"] is True for record in checkpoints["records"]) == data["run"]["passedCheckpoints"]
    node_ids = {node["nodeId"] for node in data["graph"]["nodes"]}
    assert node_ids <= set(workflow["nodes"])
    assert all(stage["nodeId"] in node_ids for stage in data["timeline"])
    assert all(edge["source"] in node_ids | {"START"} and edge["target"] in node_ids for edge in data["graph"]["edges"])
    observed = [stage for stage in data["timeline"] if stage["checkpoint"]]
    assert len(observed) == len(checkpoints["records"])
    assert all(stage["checkpoint"] == record for stage, record in zip(observed, checkpoints["records"]))
    mapping = data["media"]["mapping"]
    assert mapping and mapping[-1]["videoTime"] <= data["media"]["duration"] + .001
    assert all(a["videoTime"] < b["videoTime"] and a["simTime"] <= b["simTime"] for a, b in zip(mapping, mapping[1:]))
    refs = [data["media"]["src"], data["media"]["poster"], *data["evidence"].values()]
    refs.extend(link["href"] for link in data.get("methodAlignment", {}).get("evidence", []))
    for item in data["refinement"] + data["generalization"]:
        refs.extend(link["href"] for link in item.get("evidence", []))
        if item.get("media"):
            refs.append(item["media"]["src"])
    for ref in refs:
        if ref.startswith(("https://", "http://")):
            continue
        path = (site / ref).resolve()
        assert path.is_relative_to(site.resolve()) and path.is_file(), f"Missing or invalid deployment asset: {ref}"
    if data["run"].get("physicalAccepted") or data["run"].get("full12Accepted"):
        audit = read_json(site / "data/policy_final_audit.json")
        assert audit.get("full12Physical") is True
        if data["run"].get("full12Accepted"):
            assert audit.get("accepted") is True and data["run"]["checkpointComplete"]
    print(f"Validated frozen research site: {len(data['pieces'])} pieces, {len(observed)} checkpoints, {len(refs)} asset/evidence links.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    parser.add_argument("--media", type=Path, default=ROOT / "results/site_policy_media/manifest.json")
    parser.add_argument("--content", type=Path, default=ROOT / "site/research-content.json")
    parser.add_argument("--audit", type=Path, help="Final independent acceptance record with accepted:true; never inferred from video.")
    parser.add_argument("--validate", action="store_true", help="Validate the frozen site without reading local runs or rebuilding.")
    args = parser.parse_args()
    if args.validate:
        validate_export(args.site)
    else:
        build(args)


if __name__ == "__main__":
    main()
