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


TEAM = REPO / "hackathon_violations" / "upload"  # local, git-ignored team clips (converted); optional
TEAM_CHECKS = {"do-not-enter": "entered_do_not_enter", "office-entry": "entered_office", "running-indoors": "running",
               "table-moved": "moved_do_not_move_item", "fire-alarm": "touched_fire_alarm"}


def team_source(name):
    return f"s3://vss-chunks-segments/segments/devteam_{name}_segment_001_of_001.mp4"


class FixtureArchive:
    configured = True

    def sites(self):
        return {"cameras": [{"id": "sdg_warehouse_cam-2", **main.camera_meta("sdg_warehouse_cam-2"), "segments": 12},
                            {"id": "replay_office_cam-1", **main.camera_meta("replay_office_cam-1"), "segments": 8}]}

    def _team_feeds(self, camera_id):
        feeds = []
        for f in sorted(TEAM.glob("*.mp4")) if TEAM.exists() else []:
            name = f.stem
            seg = {"n": 1, "start": 0.0, "end": 5.0, "source": team_source(name), "caption": "", "objects": "",
                   "checks": {k: ("yes" if TEAM_CHECKS.get(name) == k else "no") for k in TEAM_CHECKS.values()}}
            feeds.append({"id": f"devteam:{name}", "name": main.view_name(f"20261009_120000_{name}.mp4")[0], "subtitle": "",
                          "camera_id": camera_id, "location": "office", "synthetic": False, "fixed": False,
                          "duration": 5.0, "segments": [seg], "filename": f.name})
        return feeds

    def feeds(self, camera_id, limit=8):
        if camera_id.startswith("replay_"):
            feeds = self._team_feeds(camera_id)
            return {"camera_id": camera_id, "feeds": feeds[:limit], "available": len(feeds)}
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
        if "devteam_" in source:
            return {"w": 1920, "h": 1080, "fps": 10, "classes": [], "source": "dev-fixture", "frames": []}
        n = 1 if "segment_001" in source else 2
        frames = []
        for i in range(50):  # 10 fps, 5 s; one generated person walking left to right
            t = i / 10
            x = 300 + (i + (n - 1) * 50) * 13
            frames.append([round(t, 3), [["person", 0.9, x, 420, x + 90, 700]]])
        return {"w": 1920, "h": 1080, "fps": 10, "classes": ["person"], "source": "dev-fixture", "frames": frames}

    def evidence(self, module, params, camera_id):
        if module["kind"] == "caption":
            hits = [f for f in self._team_feeds(camera_id) if f["segments"][0]["checks"].get(module["check"]["key"]) == module["check"]["value"]]
            return {"query": module["query"], "ms": 0, "moments": [
                {"feed": f, "source": f["segments"][0]["source"], "score": 0.42, "start": 0.0, "end": 5.0, "confirmed": True,
                 "caption": "Development fixture caption.", "segment_number": 1,
                 "basis": f"Cosmos Reason checklist: {module['check']['key']} = {module['check']['value']}"} for f in hits]}
        feeds = self.feeds(camera_id)["feeds"][:2]
        moments = [{"feed": f, "source": f["segments"][1]["source"], "score": 0.5, "start": 5.0, "end": 10.0,
                    "caption": "Development fixture moment. Real runs show the Cosmos caption that matched.", "segment_number": 2}
                   for f in feeds]
        return {"query": module["query"], "moments": moments, "ms": 0}

    def open_stream(self, source, byte_range):
        team = re.search(r"devteam_(.+?)_segment_", source)
        if team:
            data = (TEAM / f"{team.group(1)}.mp4").read_bytes()
        else:
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
        unsupported = [catalog["unsupported"][0]] if re.search(r"hard hat|helmet|ppe|vest", t) else []
        if re.search(r"lane|zone|area", t):
            mods.append({"id": "zone_entry", "params": {"dwell_seconds": 1}, "reason": "fixture: lane"})
        if "forklift" in t and re.search(r"near|close|next", t):
            mods.append({"id": "near_forklift", "params": {"min_score": 0.4}, "reason": "fixture: near a forklift"})
        for word, mid in (("do not enter", "do_not_enter"), ("runs", "running_indoors"), ("fire alarm", "fire_alarm"),
                          ("do not move", "moved_item"), ("office", "office_entry"), ("pizza", "food_missing")):
            if word in t and any(m["id"] == mid for m in catalog["modules"]):
                mods.append({"id": mid, "params": {"min_score": 0.25}, "reason": f"fixture: {word}"})
        if "staff" in t:
            unsupported.append(catalog["unsupported"][4])
        if "restroom" in t:
            unsupported.append(catalog["unsupported"][5])
        if re.search(r"still|linger", t):
            mods.append({"id": "lingering", "params": {"dwell_seconds": 3}, "reason": "fixture: stands still"})
        import compiler  # same validation as the real W&B path, including the camera's module filter
        answer = {"modules": mods, "unsupported": [catalog["unsupported"].index(u) for u in unsupported]}
        mods, unsupported, problems, _ = compiler.validate(answer, catalog)
        return {"modules": mods, "unsupported": unsupported, "problems": problems, "clarification": None,
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
