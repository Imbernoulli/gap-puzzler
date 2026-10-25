"""Validate the frozen research page and its published execution evidence.

The Pages job checks committed assets rather than rebuilding from private runs.
Only the exporter reads those runs; deployment cannot substitute legacy data.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit


class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if attrs.get("id"):
            assert attrs["id"] not in self.ids, f"Duplicate HTML id: {attrs['id']}"
            self.ids.add(attrs["id"])
        for key in ("src", "href", "poster"):
            if attrs.get(key):
                self.links.append(attrs[key])


def validate(site: Path, require_complete=False):
    site = site.resolve()
    checked = set()

    def local_link(value, owner=site / "index.html"):
        url = urlsplit(value)
        if url.scheme or url.netloc:
            return
        if not url.path:
            return
        assert not url.path.startswith("/"), f"Deployment must work under /gap-puzzler/: {value}"
        path = (owner.parent / unquote(url.path)).resolve()
        assert path.is_relative_to(site), f"Asset leaves the site: {value}"
        if path.is_dir():
            path /= "index.html"
        assert path.is_file(), f"Missing published asset: {value}"
        checked.add(path)

    for html in site.glob("*.html"):
        page = PageLinks()
        page.feed(html.read_text())
        for link in page.links:
            local_link(link, html)
            if link.startswith("#"):
                assert link[1:] in page.ids, f"Missing page anchor: {html.name}{link}"

    research = json.loads((site / "data/research.json").read_text())
    workflow = json.loads((site / "data/policy_workflow.json").read_text())
    checkpoints = json.loads((site / "data/policy_checkpoints.json").read_text())
    run, media = research["run"], research["media"]
    records = checkpoints["records"]
    assert checkpoints["run"] == run, "Checkpoint and page snapshots differ"
    assert len(records) == run["checkpointCount"]
    assert sum(r["passed"] is True for r in records) == run["passedCheckpoints"]
    assert run["pieceCount"] == 12 and run["expectedCheckpoints"] == 84
    assert [p["name"] for p in research["pieces"]] == workflow["meta"]["ordered_stages"]
    assert sum(p["complete"] for p in research["pieces"]) == run["completePieces"]
    assert all(n["nodeId"] in workflow["nodes"] for n in research["graph"]["nodes"])
    assert all(t["nodeId"] in workflow["nodes"] for t in research["timeline"])
    for index, record in enumerate(records):
        assert record["number"] == index + 1
        assert research["timeline"][index]["checkpoint"] == record
    for key in ("src", "poster"):
        if media.get(key):
            local_link(media[key])
    mapping = media["mapping"]
    assert len(mapping) > 1 and mapping[0]["videoTime"] == 0
    assert all(a["videoTime"] < b["videoTime"] and a["simTime"] <= b["simTime"]
               for a, b in zip(mapping, mapping[1:]))
    assert abs(mapping[-1]["videoTime"] - media["duration"]) < .1
    for section in ("refinement", "generalization"):
        for item in research[section]:
            for evidence in item.get("evidence", []):
                local_link(evidence["href"])
            for key in ("src", "poster"):
                if item.get("media", {}).get(key):
                    local_link(item["media"][key])
    for link in research.get("evidence", {}).values():
        local_link(link)
    def nested_assets(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ("src", "poster", "shapeSrc", "href") and isinstance(child, str):
                    local_link(child)
                else:
                    nested_assets(child)
        elif isinstance(value, list):
            for child in value:
                nested_assets(child)

    nested_assets(research)
    if run.get("physicalAccepted"):
        audit = json.loads((site / "data/policy_final_audit.json").read_text())
        assert audit["full12Physical"] is True and audit["physicalPlacedPieces"] == 12
    if run["full12Accepted"] or require_complete:
        assert run["full12Accepted"] and run["checkpointComplete"]
        assert run["completePieces"] == 12
        assert len(records) == 84 and all(r["passed"] is True for r in records)
        assert not media["partial"], "Complete assembly needs its complete recording"
        audit = json.loads((site / "data/policy_final_audit.json").read_text())
        assert audit["accepted"] is True
    for asset in checked:
        assert asset.stat().st_size < 100_000_000, f"Asset exceeds GitHub file size: {asset}"
    print(f"Site verified: {len(checked)} local assets, {len(records)}/84 checkpoints, "
          f"{len(research['refinement'])} refinement cases, accepted={run['full12Accepted']}")


class RigPageLinks(PageLinks):
    """Read the dual-camera-rig page without changing the legacy validator."""

    def __init__(self):
        super().__init__()
        self.page_data = []
        self.reading_page_data = False
        self.default_rig = None
        self.tabs = []
        self.players = []
        self.videos = []

    def handle_starttag(self, tag, attributes):
        super().handle_starttag(tag, attributes)
        attrs = dict(attributes)
        if tag == "script":
            self.reading_page_data = attrs.get("id") == "page-data"
        if tag == "body":
            self.default_rig = attrs.get("data-rig")
        if attrs.get("data-rig-tab"):
            self.tabs.append(attrs)
        if "player" in attrs.get("class", "").split() and attrs.get("data-rig"):
            self.players.append(attrs["data-rig"])
        if tag == "video":
            self.videos.append(attrs)

    def handle_data(self, value):
        if self.reading_page_data:
            self.page_data.append(value)

    def handle_endtag(self, tag):
        if tag == "script":
            self.reading_page_data = False


def validate_rig_site(site: Path, payload, main_page):
    """Validate the committed dual-rig snapshot using only the standard library."""
    site = site.resolve()
    checked = set()

    def local_link(value, owner):
        url = urlsplit(value)
        if url.scheme or url.netloc or not url.path:
            return
        assert not url.path.startswith("/"), f"Deployment must work under /gap-puzzler/: {value}"
        path = (owner.parent / unquote(url.path)).resolve()
        assert path.is_relative_to(site), f"Asset leaves the site: {value}"
        if path.is_dir():
            path /= "index.html"
        assert path.is_file(), f"Missing published asset: {value}"
        assert 0 < path.stat().st_size < 100_000_000, f"Empty or oversized published asset: {path}"
        checked.add(path)

    for html in site.glob("*.html"):
        page = RigPageLinks()
        page.feed(html.read_text())
        for link in page.links:
            local_link(link, html)
            if link.startswith("#"):
                assert link[1:] in page.ids, f"Missing page anchor: {html.name}{link}"

    sidecar_path = site / "data/page.json"
    sidecar = json.loads(sidecar_path.read_text())
    assert sidecar == payload, "Inline page-data and data/page.json snapshots differ"
    checked.add(sidecar_path)

    def nested_assets(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ("src", "poster", "shapeSrc", "href") and isinstance(child, str):
                    local_link(child, site / "index.html")
                else:
                    nested_assets(child)
        elif isinstance(value, list):
            for child in value:
                nested_assets(child)

    nested_assets(payload)
    rigs = payload["rigs"]
    assert set(rigs) == {"official", "custom"}, "Both official and custom camera rigs are required"
    assert main_page.default_rig == "official", "The official three-camera rig must be the default"
    tabs = {tab["data-rig-tab"]: tab for tab in main_page.tabs}
    assert len(main_page.tabs) == len(tabs) == 2 and set(tabs) == set(rigs), "Camera tabs differ from the data"
    assert tabs["official"].get("aria-selected") == "true"
    assert tabs["custom"].get("aria-selected") == "false"
    assert sorted(main_page.players) == sorted(rigs), "Expected one graph/video player per camera rig"
    assert main_page.videos, "The execution recordings are missing"
    for video in main_page.videos:
        assert video.get("src"), "A video is missing its published source"
        assert all(key in video for key in ("autoplay", "muted", "playsinline")), \
            f"Video needs muted inline autoplay: {video.get('src')}"

    for name, run in rigs.items():
        assert run["rss_success"] is True and run["graph_success"] is True, f"{name}: execution did not complete"
        assert run["audit_success"] is True, f"{name}: original independent audit did not pass"
        assert run["pieces_placed"] == 12
        assert run["checkpoints_passed"] == run["checkpoints_total"] == 84
        assert run["control_hz"] > 0 and run["steps"] > 0
        assert run["video"]["steps_per_second"] > 0
        pieces = run["pieces"]
        assert len(pieces) == 13 and sum(piece["name"] == "finish" for piece in pieces) == 1
        assert len({piece["name"] for piece in pieces}) == 13
        assert all(piece["placed"] is True for piece in pieces)
        nodes = [node for piece in pieces for node in piece["nodes"]]
        assert len(nodes) == 84 and len({node["id"] for node in nodes}) == 84
        targets = {node["id"] for node in nodes} | {"done", "abort"}
        for node in nodes:
            assert all(target in targets for target in node.get("routes", {}).values()), \
                f"{name}: unknown graph route from {node['id']}"
        previous_end = 0
        for piece in pieces:
            assert piece["nodes"], f"{name}: empty piece graph"
            assert piece["start"] == piece["nodes"][0]["start"]
            assert piece["end"] == piece["nodes"][-1]["end"]
            for node in piece["nodes"]:
                assert node["passed"] is True, f"{name}: unpassed graph node {node['id']}"
                assert node["start"] == previous_end, f"{name}: discontinuous graph clock at {node['id']}"
                assert node["end"] is not None and node["start"] <= node["end"] <= run["steps"]
                previous_end = node["end"]
        print(f"Rig verified: {name}, 12 pieces, 84/84 checkpoints, independent audit passed")
    for case in payload.get("cases", []):
        assert case["rig"] in rigs
        assert case["graph_success"] is True and case["rss_success"] is True, \
            f"Generalization gallery includes an incomplete case: {case.get('run')}"
    print(f"Tabbed research site verified: {len(checked)} local assets; official rig is the default")


def validate_site(site: Path, require_complete=False):
    """Choose the schema from the actual page, never from stale data files."""
    page = RigPageLinks()
    page.feed((site / "index.html").read_text())
    if page.page_data:
        payload = json.loads("".join(page.page_data))
        if isinstance(payload, dict) and "rigs" in payload:
            return validate_rig_site(site, payload, page)
    return validate(site, require_complete)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=Path(__file__).resolve().parents[1] / "site")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    validate_site(args.site, args.require_complete)
