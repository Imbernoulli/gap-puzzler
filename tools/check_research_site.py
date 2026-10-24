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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=Path(__file__).resolve().parents[1] / "site")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    validate(args.site, args.require_complete)
