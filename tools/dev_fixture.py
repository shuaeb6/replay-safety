#!/usr/bin/env python3
"""Run the live/ board against local stand-ins for layout work on a laptop.

NOT REAL DATA. Feeds are the offline factory clips, person boxes are a generated
walking path, captions are placeholders, and the rule compiler is a keyword stub.
The UI shows a "Development fixture" banner and lights no sponsor services.
This file is never deployed (the deployment bundle is the live/ folder only).

Usage: python3 tools/dev_fixture.py   then open http://127.0.0.1:8770
"""
import io
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "live"))
os.environ.setdefault("HOST", "127.0.0.1")
os.environ.setdefault("PORT", "8770")
import main  # noqa: E402

CLIPS = ["0_te21", "3_te7", "2_te12", "4_te5", "1_te10", "5_te12"]
FOOTAGE = REPO / "demo-footage" / "factory-cctv"


def fake_source(name, n):
    return f"s3://vss-chunks-segments/segments/devfixture_{name}_segment_{n:03d}_of_002.mp4"


class FixtureArchive:
    configured = True

    def sites(self):
        cameras = [
            {"id": "sdg_warehouse_cam-2", "name": "Warehouse aisle", "place": "Warehouse 3 · synthetic",
             "tone": "warehouse", "synthetic": True, "segments": 6},
            {"id": "smartspace_cam-1", "name": "Indoor floor", "place": "Facility · synthetic",
             "tone": "warehouse", "synthetic": True, "segments": 0},
        ]
        return {"cameras": cameras, "indexed_clips": 6, "sets": main.build_sets(cameras)}

    def feeds(self, camera_id, limit=6):
        feeds = []
        for i, name in enumerate(CLIPS):
            if not (FOOTAGE / f"{name}.mp4").exists():
                continue
            segs = [{"n": 1, "start": 0.0, "end": 5.0, "source": fake_source(name, 1), "caption": "", "objects": ""},
                    {"n": 2, "start": 5.0, "end": 10.0, "source": fake_source(name, 2), "caption": "", "objects": ""}]
            feeds.append({"id": f"dev:{name}", "name": f"Fixture {i + 1}", "subtitle": name, "camera_id": camera_id,
                          "location": "warehouse3", "synthetic": True, "duration": 10.0, "segments": segs,
                          "filename": f"{name}.mp4"})
        return {"camera_id": camera_id, "feeds": feeds[:limit], "available": len(feeds)}

    def segment(self, source):
        n = 1 if source.endswith("001_of_002.mp4") else 2
        return {"source": source, "caption": f"Development fixture caption for segment {n}. A real deployment shows the Cosmos Reason description here.",
                "objects": "", "model": "fixture"}

    def detections(self, source):
        n = 1 if "segment_001" in source else 2
        frames = []
        for i in range(50):  # 10 fps, 5 s; one generated person walking left to right
            t = i / 10
            x = 300 + (i + (n - 1) * 50) * 13
            frames.append([round(t, 3), [["person", 0.9, x, 420, x + 90, 700]]])
        return {"w": 1920, "h": 1080, "fps": 10, "classes": ["person"], "source": "dev-fixture", "frames": frames}

    def evidence(self, module, params, camera_id):
        feeds = self.feeds(camera_id)["feeds"][:2]
        moments = [{"feed": f, "source": f["segments"][1]["source"], "score": 0.5, "start": 5.0, "end": 10.0,
                    "caption": "Development fixture moment. Real runs show the Cosmos caption that matched.", "segment_number": 2}
                   for f in feeds]
        return {"query": module["query"], "moments": moments, "ms": 0}

    def open_stream(self, source, byte_range):
        name = re.search(r"devfixture_(.+?)_segment_", source).group(1)
        data = (FOOTAGE / f"{name}.mp4").read_bytes()
        size, start, end, status = len(data), 0, len(data) - 1, 200
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", byte_range or "")
        if match and any(match.groups()):
            a, b = match.groups()
            start = int(a) if a else max(0, size - int(b))
            end = min(int(b), size - 1) if a and b else size - 1
            status = 206
        body = io.BytesIO(data[start:end + 1])
        body.status = status
        body.headers = {"Content-Type": "video/mp4", "Content-Length": str(end - start + 1), "Accept-Ranges": "bytes",
                        **({"Content-Range": f"bytes {start}-{end}/{size}"} if status == 206 else {})}
        return body


class FixtureCompiler:
    configured = True
    model = "dev-fixture/keyword-stub"

    def compile(self, text, catalog):
        t = text.lower()
        mods = []
        if re.search(r"lane|zone|area", t):
            mods.append({"id": "zone_entry", "params": {"dwell_seconds": 1}, "reason": "fixture: lane"})
        if "forklift" in t and re.search(r"near|close|next", t):
            mods.append({"id": "near_forklift", "params": {"min_score": 0.4}, "reason": "fixture: near a forklift"})
        if re.search(r"still|linger", t):
            mods.append({"id": "lingering", "params": {"dwell_seconds": 3}, "reason": "fixture: stands still"})
        unsupported = [catalog["unsupported"][0]] if re.search(r"hard hat|helmet|ppe|vest", t) else []
        return {"modules": mods, "unsupported": unsupported, "problems": [], "clarification": None,
                "model": self.model, "ms": 0, "tokens": None}


class FixtureLane:
    configured = True

    def propose(self, image):
        return {"polygon": [[0.45, 0.55], [0.95, 0.55], [0.95, 0.85], [0.45, 0.85]], "reason": "fixture lane",
                "model": "dev-fixture/lane-stub", "ms": 0}


main.ARCHIVE = FixtureArchive()
main.COSMOS = FixtureLane()
main.WANDB = FixtureCompiler()
main.DEV_FIXTURE = True

if __name__ == "__main__":
    print("DEV FIXTURE - not real data", flush=True)
    main.main()
