"""Replay safety board. Serves the UI and proxies the team video archive.

Credentials come from VSS_URL, VSS_USERNAME, VSS_PASSWORD and WANDB_API_KEY /
WANDB_TEAM / WANDB_PROJECT (Kubernetes Secret), or from the VM's single
/config/<team>.config file when run directly on the workshop VM. They stay on
the server. The browser never receives them.
"""

from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlparse
import glob
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

from compiler import WandbCompiler, load_catalog
from lane import LaneProposer


def _team_config():
    """Read the VM's /config/<team>.config without sourcing it (USERNAME clashes with the shell)."""
    files = sorted(glob.glob("/config/*.config"))
    values = {}
    if len(files) == 1:
        for line in open(files[0], encoding="utf-8"):
            match = re.match(r"\s*(?:export\s+)?([A-Z0-9_]+)=(.*)$", line)
            if match:
                values[match.group(1)] = match.group(2).strip().strip("\"'")
    return values


_CFG = {} if os.environ.get("VSS_URL") else _team_config()
ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "8080"))
HOST = os.environ.get("HOST", "0.0.0.0")
VSS_URL = (os.environ.get("VSS_URL") or _CFG.get("INGRESS_URL", "")).rstrip("/")
VSS_USERNAME = os.environ.get("VSS_USERNAME") or _CFG.get("USERNAME", "")
VSS_PASSWORD = os.environ.get("VSS_PASSWORD") or _CFG.get("PASSWORD", "")
WANDB = WandbCompiler(
    os.environ.get("WANDB_API_KEY") or _CFG.get("WANDB_API_KEY", ""),
    os.environ.get("WANDB_TEAM") or _CFG.get("WANDB_TEAM", ""),
    os.environ.get("WANDB_PROJECT") or _CFG.get("WANDB_PROJECT", ""),
    os.environ.get("WANDB_MODEL") or None,
)
COSMOS = LaneProposer(
    os.environ.get("COSMOS3_REASON_URL") or _CFG.get("COSMOS3_REASON_URL", ""),
    os.environ.get("GPU_BEARER_TOKEN") or _CFG.get("GPU_BEARER_TOKEN", ""),
    os.environ.get("COSMOS3_REASON_MODEL") or _CFG.get("COSMOS3_REASON_MODEL") or None,
)
DEFAULT_CAMERA = os.environ.get("REPLAY_CAMERA", "sdg_warehouse_cam-2")
PINNED_FEEDS = [s for s in os.environ.get("REPLAY_FEEDS", "").split(",") if s.strip()]

# camera_id: (name, place, tone, synthetic). Synthetic = rendered footage, confirmed by visual review on the VM.
CAMERA_INFO = {
    "sdg_warehouse_cam-2": ("Warehouse aisle", "Warehouse 3 · synthetic", "warehouse", True),
    "smartspace_cam-1": ("Indoor floor", "Facility · synthetic", "warehouse", True),
    "i24_cam-1": ("Highway", "Nashville · I-24", "road", False),
    "pie_cam-3": ("City drive", "Toronto · forward cam", "road", False),
    "neighborhood_cam-1": ("Neighborhood", "Residential street", "street", False),
    "nyc_streets_cam-1": ("NYC street A", "New York", "street", False),
    "nyc_streets_cam-2": ("NYC street B", "New York", "street", False),
    "nyc_bike_gopro-1": ("NYC bike", "New York · rider cam", "street", False),
    "sf_streets_cam-1": ("SF street 1", "San Francisco", "street", False),
    "sf_streets_cam-2": ("SF street 2", "San Francisco", "street", False),
    "sf_streets_cam-3": ("SF street 3", "San Francisco", "street", False),
    "sf_streets_cam-4": ("SF street 4", "San Francisco", "street", False),
    "sf_streets_cam-5": ("SF street 5", "San Francisco", "street", False),
}
CAMERA_INFO["replay_office_cam-1"] = ("Event floor", "Team-recorded · handheld", "office", False)
CAMERA_ORDER = list(CAMERA_INFO)
# Fixed cameras support image-space rules (lanes, lingering, crowding). Handheld clips pan and zoom, so
# only caption-based modules apply. Team uploads use camera ids that start with "replay_".
HANDHELD_PREFIXES = ("replay_",)


def camera_meta(camera_id):
    name, place, tone, synthetic = CAMERA_INFO.get(camera_id, (camera_id, "Indexed camera", "street", False))
    return {"name": name, "place": place, "tone": tone, "synthetic": synthetic,
            "fixed": not camera_id.startswith(HANDHELD_PREFIXES)}


def modules_for(camera_id):
    """Catalog copy limited to modules this camera can support."""
    fixed = camera_meta(camera_id)["fixed"]
    catalog = dict(CATALOG)
    catalog["modules"] = [m for m in CATALOG["modules"] if m.get("cameras", "any") == "any" or fixed]
    return catalog


def parse_checks(caption):
    """Read the 'CHECKS: key=yes|no; ...' line that the custom ingest prompt asks Cosmos Reason to append."""
    match = re.search(r"CHECKS?\s*:\s*(.+)", caption or "", flags=re.I)
    if not match:
        return {}
    return {k.lower(): v.lower() for k, v in re.findall(r"([a-z_]+)\s*=\s*(yes|no|unclear)", match.group(1), flags=re.I)}


def clean_caption(caption):
    text = re.split(r"CHECKS?\s*:", caption or "", flags=re.I)[0]
    return " ".join(text.split())[:700]
STATIC = {
    "/": ("index.html", "text/html"),
    "/index.html": ("index.html", "text/html"),
    "/style.css": ("style.css", "text/css"),
    "/app.js": ("app.js", "text/javascript"),
    "/engine.js": ("engine.js", "text/javascript"),
    "/catalog.json": ("catalog.json", "application/json"),
}

# Every upstream service call, for the in-app "services used" strip and the evidence report.
CALLS = deque(maxlen=300)


def record(service, op, started, ok, note=""):
    CALLS.append({"at": time.strftime("%H:%M:%S"), "service": service, "op": op,
                  "ms": round((time.perf_counter() - started) * 1000), "ok": ok, "note": note[:160]})


def safe_source(source, username):
    """Allow only this team's archive object URIs, or the shared chunk buckets."""
    if not isinstance(source, str) or not source.startswith("s3://"):
        return False
    if len(source) > 512 or any(ch in source for ch in "\r\n\t ?#") or ".." in source:
        return False
    bucket = source[5:].split("/", 1)[0]
    if not bucket:
        return False
    allowed = {"vss-chunks", "vss-chunks-segments"}
    if username:
        allowed.add(f"{username}-vss-chunks")
        allowed.add(f"{username}-vss-chunks-segments")
    return bucket in allowed


def view_name(filename):
    """Readable feed name from the archive filename, e.g. '...run_7_seed_9.ceiling_04.rgb_chunk_0000.mp4'."""
    name = filename or ""
    match = re.search(r"\.(ceiling|eye)_(\d+)\.rgb", name)
    run = re.search(r"run_(\d+)", name)
    if match:
        title = f"{'Ceiling' if match.group(1) == 'ceiling' else 'Eye level'} {match.group(2)}"
        return title, f"Scene {run.group(1)}" if run else ""
    match = re.search(r"Camera_?(\d+)", name)
    if match:
        chunk = re.search(r"chunk_(\d+)", name)
        return f"Camera {match.group(1)}", f"Part {int(chunk.group(1)) + 1}" if chunk else ""
    stem = name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    stem = re.sub(r"^\d{6,}[_-]?\d*[_-]?", "", stem)          # upload timestamp prefix
    stem = re.sub(r"_chunk_\d+$", "", stem)
    title = re.sub(r"[-_]+", " ", stem).strip().capitalize()
    return title[:28] or "Feed", ""


def feed_from_item(item, segments_bucket=""):
    """Normalise one /videos/explore (or search chunk) item into a playable feed of ordered segments."""
    original = item.get("original_video") or ""
    filename = item.get("filename") or original.rsplit("/", 1)[-1]
    timeline = [row for row in item.get("timeline") or [] if isinstance(row, dict)]
    total = int(item.get("total_segments") or len(timeline) or 0)
    segments = []
    if timeline:
        for row in sorted(timeline, key=lambda r: r.get("segment_number") or 0):
            segments.append({
                "n": row.get("segment_number"),
                "start": float(row.get("segment_start_sec") or 0),
                "end": float(row.get("segment_end_sec") or 0),
                "source": row.get("source") or "",
                "caption": clean_caption(row.get("reasoning_content")),
                "checks": parse_checks(row.get("reasoning_content")),
                "score": row.get("similarity_score"),
                "objects": row.get("object_counts") or "",
            })
    elif total and original.endswith(".mp4"):
        # Segment keys follow '<bucket>-segments/segments/<stem>_segment_00N_of_00T.mp4' (seen in search results).
        bucket = segments_bucket or original[5:].split("/", 1)[0] + "-segments"
        stem = filename[:-4]
        length = float(item.get("chunk_duration_sec") or total * 5.0) / total
        for n in range(1, total + 1):
            segments.append({"n": n, "start": (n - 1) * length, "end": n * length, "caption": "", "objects": "", "checks": {},
                             "source": f"s3://{bucket}/segments/{stem}_segment_{n:03d}_of_{total:03d}.mp4"})
    segments = [s for s in segments if safe_source(s["source"], VSS_USERNAME)]
    if not segments or (total and len(segments) != total):
        return None
    title, subtitle = view_name(filename)
    camera_id = item.get("camera_id") or ""
    return {
        "id": original,
        "name": title,
        "subtitle": subtitle,
        "camera_id": camera_id,
        "location": item.get("location") or "",
        "synthetic": camera_meta(camera_id)["synthetic"],
        "fixed": camera_meta(camera_id)["fixed"],
        "duration": segments[-1]["end"],
        "segments": segments,
        "filename": filename,
    }


def compact_detections(payload):
    """YOLO sidecar -> {w, h, fps, frames: [[t, [[label, conf, x1, y1, x2, y2], ...]], ...]}."""
    height, width = (payload.get("video_shape") or [1080, 1920])[:2]
    frames = []
    for frame in payload.get("frames") or []:
        boxes = []
        for det in (frame.get("detections") or [])[:24]:
            bbox = det.get("bbox") or []
            if len(bbox) == 4:
                boxes.append([det.get("label") or "", round(det.get("confidence") or 0, 3)] + [round(v, 1) for v in bbox])
        frames.append([round(float(frame.get("time_sec") or 0), 4), boxes])
    return {"w": width, "h": height, "fps": payload.get("fps"), "classes": payload.get("object_classes") or [],
            "source": payload.get("source") or "", "frames": frames}


class Archive:
    def __init__(self):
        self._token = None
        self._lock = threading.Lock()
        self._explore = (0, [])

    @property
    def configured(self):
        return bool(VSS_URL and VSS_USERNAME and VSS_PASSWORD)

    def _login(self):
        if not self.configured:
            raise RuntimeError("Video archive is not configured on this server.")
        body = json.dumps({"username": VSS_USERNAME, "password": VSS_PASSWORD}).encode()
        request = urllib.request.Request(
            f"{VSS_URL}/api/v1/auth/login",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            record("VAST VSS", "login", started, False)
            raise RuntimeError("Archive login failed.") from exc
        except urllib.error.URLError as exc:
            record("VAST VSS", "login", started, False)
            raise RuntimeError("Archive is unreachable.") from exc
        token = payload.get("access_token")
        record("VAST VSS", "login", started, bool(token))
        if not token:
            raise RuntimeError("Archive login failed.")
        self._token = token
        return token

    def token(self, force=False):
        with self._lock:
            if self._token and not force:
                return self._token
            return self._login()

    def call(self, method, path, payload=None, timeout=90, op=None):
        data = None if payload is None else json.dumps(payload).encode()
        last_error = None
        op = op or path.split("?", 1)[0].replace("/api/v1", "")
        for attempt in range(2):
            token = self.token(force=attempt == 1)
            headers = {"Authorization": f"Bearer {token}"}
            if data is not None:
                headers["Content-Type"] = "application/json"
            request = urllib.request.Request(f"{VSS_URL}{path}", data=data, headers=headers, method=method)
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    raw = response.read()
                    record("VAST VSS", op, started, True)
                    if not raw:
                        return {}
                    return json.loads(raw)
            except urllib.error.HTTPError as exc:
                record("VAST VSS", op, started, False, f"HTTP {exc.code}")
                last_error = exc
                if exc.code == 401 and attempt == 0:
                    continue
                detail = ""
                try:
                    body = json.loads(exc.read().decode() or "{}")
                    detail = body.get("detail") or body.get("message") or ""
                except Exception:
                    detail = ""
                if not isinstance(detail, str):
                    detail = ""
                raise RuntimeError(detail[:240] or f"Archive request failed ({exc.code}).") from exc
            except urllib.error.URLError as exc:
                record("VAST VSS", op, started, False, "unreachable")
                raise RuntimeError("Archive is unreachable.") from exc
        raise RuntimeError("Archive login failed.") from last_error

    def sites(self):
        stats = self.call("GET", "/api/v1/dashboard/stats?scope=all")
        counts = {
            row.get("label"): row.get("count")
            for row in (stats.get("metadata") or {}).get("camera_id") or []
            if isinstance(row, dict)
        }
        ordered = [camera_id for camera_id in CAMERA_ORDER if camera_id in counts]
        ordered += sorted(camera_id for camera_id in counts if camera_id not in CAMERA_ORDER)
        cameras = []
        for camera_id in ordered:
            cameras.append({"id": camera_id, **camera_meta(camera_id), "segments": counts.get(camera_id) or 0})
        overview = stats.get("overview") or {}
        return {"cameras": cameras, "indexed_clips": overview.get("indexed_clips")}

    def _explore_all(self):
        fetched_at, items = self._explore
        if items and time.time() - fetched_at < 300:
            return items
        items, offset = [], 0
        while offset < 2000:
            page = self.call("GET", f"/api/v1/videos/explore?scope=all&limit=100&offset={offset}", op="/videos/explore")
            rows = next((v for v in page.values() if isinstance(v, list)), []) if isinstance(page, dict) else []
            items += [row for row in rows if isinstance(row, dict)]
            offset += 100
            total = page.get("total") if isinstance(page, dict) else None
            if not rows or (isinstance(total, int) and offset >= total):
                break
        self._explore = (time.time(), items)
        return items

    def feeds(self, camera_id, limit=6):
        feeds = [f for f in (feed_from_item(it, _CFG.get("S3_SEGMENTS_BUCKET", "")) for it in self._explore_all()
                             if it.get("camera_id") == camera_id) if f]
        if PINNED_FEEDS:
            pinned = [f for key in PINNED_FEEDS for f in feeds if key.strip() in f["filename"]]
            feeds = pinned + [f for f in feeds if f not in pinned]
        else:
            # Prefer distinct viewpoints so the wall shows different angles of the archive.
            seen, varied, rest = set(), [], []
            for f in sorted(feeds, key=lambda f: f["filename"]):
                (rest if f["name"] in seen else varied).append(f)
                seen.add(f["name"])
            feeds = varied + rest
        return {"camera_id": camera_id, "feeds": feeds[:limit], "available": len(feeds)}

    def segment(self, source):
        row = self.call("GET", "/api/v1/videos/metadata?" + urlencode({"source": source}))
        return {"source": source, "caption": clean_caption(row.get("reasoning_content")),
                "checks": parse_checks(row.get("reasoning_content")),
                "objects": row.get("object_counts") or "", "model": row.get("cosmos_model") or "",
                "start": row.get("segment_start_sec"), "end": row.get("segment_end_sec")}

    def detections(self, source):
        try:
            payload = self.call("GET", "/api/v1/videos/detections?" + urlencode({"source": source}), timeout=40)
        except RuntimeError as exc:
            message = str(exc).lower()
            if "404" in message or "not found" in message:
                return {"frames": [], "classes": [], "unavailable": True}
            raise
        return compact_detections(payload)

    def evidence(self, module, params, camera_id):
        """Search modules: VAST hybrid search over Cosmos captions on one camera.

        'retrieval' modules keep hits at or above the score threshold. 'caption' modules read the
        Cosmos Reason checklist in each matching segment's caption: a stated answer decides, and
        the score threshold is used only when the caption has no checklist (or the module requires both).
        """
        started = time.perf_counter()
        body = {"query": module["query"], "top_k": 20, "llm_top_n": 1,
                "min_similarity": 0.05 if module["kind"] == "caption" else params["min_score"],
                "include_public": True, "metadata_filters": {"camera_id": camera_id}}
        result = self.call("POST", "/api/v1/search", body, timeout=120)
        check = module.get("check")
        moments = []
        for chunk in result.get("chunk_results") or []:
            feed = feed_from_item(chunk, _CFG.get("S3_SEGMENTS_BUCKET", ""))
            if not feed:
                continue
            chunk_score = chunk.get("similarity_score") or 0
            best_source = chunk.get("preview_source") or ""
            for seg in feed["segments"]:
                score = seg.get("score") if isinstance(seg.get("score"), (int, float)) else (chunk_score if seg["source"] == best_source else 0)
                matched = score >= params["min_score"]
                stated = seg.get("checks", {}).get(check["key"]) if check else None
                if check and stated is not None:
                    hit = stated == check["value"] and (matched or not check.get("require_match"))
                    basis = f"Cosmos Reason checklist: {check['key']} = {stated}"
                else:
                    hit = matched and (seg["source"] == best_source or not check)
                    basis = "Caption match (no checklist in this caption)" if check else "Caption match"
                if hit:
                    moments.append({"feed": feed, "source": seg["source"], "score": round(score, 3),
                                    "start": seg["start"], "end": seg["end"], "caption": seg.get("caption", ""),
                                    "segment_number": seg.get("n"), "basis": basis, "confirmed": stated is not None})
        moments.sort(key=lambda m: (not m["confirmed"], -m["score"]))
        return {"query": module["query"], "moments": moments[:12], "ms": round((time.perf_counter() - started) * 1000)}

    def open_stream(self, source, byte_range):
        """Open the upstream clip stream. The token stays server-side."""
        headers = {"Range": byte_range} if byte_range else {}
        for attempt in range(2):
            token = self.token(force=attempt == 1)
            upstream = f"{VSS_URL}/api/v1/videos/stream?source={quote(source, safe='')}&token={quote(token, safe='')}"
            try:
                return urllib.request.urlopen(urllib.request.Request(upstream, headers=headers), timeout=120)
            except urllib.error.HTTPError as exc:
                if exc.code != 401 or attempt:
                    raise RuntimeError("Clip playback failed.") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError("Clip playback failed.") from exc
        raise RuntimeError("Clip playback failed.")


ARCHIVE = Archive()
CATALOG = load_catalog()
DEV_FIXTURE = False  # set only by tools/dev_fixture.py for local layout work; the UI then shows a banner


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Request lines only. Do not log upstream URLs; they carry the archive token.
        super().log_message(fmt, *args)

    def _send(self, status, body, content_type="application/json", extra=None):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for key, value in extra or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status, payload):
        self._send(status, json.dumps(payload), "application/json")

    def _read_json(self, limit=8000):
        length = int(self.headers.get("Content-Length") or "0")
        if length > limit:
            raise ValueError("Request is too large.")
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw.decode() or "{}")
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object.")
        return data

    def _source(self, query):
        source = (query.get("source") or [""])[0]
        if not safe_source(source, VSS_USERNAME):
            self._json(400, {"error": "That clip is outside this archive."})
            return None
        return source

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/health":
            self._json(200, {"ok": True})
        elif parsed.path == "/api/status":
            self._json(200, {
                "mode": "dev-fixture" if DEV_FIXTURE else "workshop",
                "archive": ARCHIVE.configured,
                "wandb": WANDB.configured,
                "cosmos": COSMOS.configured,
                "model": WANDB.model,
                "default_camera": DEFAULT_CAMERA,
                "camera": camera_meta(DEFAULT_CAMERA),
            })
        elif parsed.path == "/api/sites":
            self._guard(lambda: self._json(200, ARCHIVE.sites()))
        elif parsed.path == "/api/feeds":
            camera_id = (query.get("camera_id") or [DEFAULT_CAMERA])[0]
            self._guard(lambda: self._json(200, ARCHIVE.feeds(camera_id)))
        elif parsed.path == "/api/segment":
            source = self._source(query)
            if source:
                self._guard(lambda: self._json(200, ARCHIVE.segment(source)))
        elif parsed.path == "/api/detections":
            source = self._source(query)
            if source:
                self._guard(lambda: self._json(200, ARCHIVE.detections(source)))
        elif parsed.path == "/api/calls":
            self._json(200, {"calls": list(CALLS)})
        elif parsed.path == "/api/stream":
            source = self._source(query)
            if source:
                self._stream(source)
        elif parsed.path in STATIC:
            self._file(*STATIC[parsed.path])
        else:
            self._json(404, {"error": "Not found."})

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            body = self._read_json(900_000 if parsed.path == "/api/lane" else 8000)
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "Send a short JSON request."})
            return
        if parsed.path == "/api/lane":
            image = body.get("image")
            if not isinstance(image, str) or not image.startswith("data:image/jpeg;base64,"):
                self._json(400, {"error": "Send one JPEG frame of the camera."})
                return
            self._guard(lambda: self._lane(image))
        elif parsed.path == "/api/compile":
            text = " ".join(str(body.get("text") or "").split())
            if not text or len(text) > 400:
                self._json(400, {"error": "Describe what to watch in one or two sentences (up to 400 characters)."})
                return
            camera_id = str(body.get("camera_id") or DEFAULT_CAMERA)[:80]
            self._guard(lambda: self._compile(text, camera_id))
        elif parsed.path == "/api/evidence":
            camera_id = str(body.get("camera_id") or DEFAULT_CAMERA)
            module = next((m for m in modules_for(camera_id)["modules"] if m["id"] == body.get("module")), None)
            if not module or module["kind"] not in ("retrieval", "caption"):
                self._json(400, {"error": "That module does not search the archive."})
                return
            score = (body.get("params") or {}).get("min_score", module["params"]["min_score"]["default"])
            spec = module["params"]["min_score"]
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not spec["min"] <= score <= spec["max"]:
                self._json(400, {"error": f"Minimum match score must be between {spec['min']} and {spec['max']}."})
                return
            self._guard(lambda: self._json(200, ARCHIVE.evidence(module, {"min_score": score}, camera_id)))
        else:
            self._json(404, {"error": "Not found."})

    def _compile(self, text, camera_id):
        started = time.perf_counter()
        service = "Dev fixture" if DEV_FIXTURE else "W&B Inference"  # never log a stub as a sponsor call
        try:
            result = WANDB.compile(text, modules_for(camera_id))
        except RuntimeError as exc:
            record(service, "chat/completions", started, False, str(exc))
            raise
        record(service, "chat/completions", started, True, result["model"])
        self._json(200, result)

    def _lane(self, image):
        started = time.perf_counter()
        service = "Dev fixture" if DEV_FIXTURE else "Cosmos Reason"
        try:
            result = COSMOS.propose(image)
        except RuntimeError as exc:
            record(service, "lane proposal", started, False, str(exc))
            raise
        record(service, "lane proposal", started, True, result["model"])
        self._json(200, result)

    def _guard(self, action):
        try:
            action()
        except RuntimeError as exc:
            self._json(502, {"error": str(exc)})
        except Exception:
            self._json(502, {"error": "The archive request failed."})

    def _file(self, name, kind):
        path = ROOT / name
        if not path.is_file():
            self._json(404, {"error": "Missing application file."})
            return
        self._send(200, path.read_bytes(), f"{kind}; charset=utf-8")

    def _stream(self, source):
        try:
            response = ARCHIVE.open_stream(source, self.headers.get("Range"))
        except RuntimeError as exc:
            self._json(502, {"error": str(exc)})
            return
        status = getattr(response, "status", 200)
        self.send_response(status)
        content_type = response.headers.get("Content-Type") or "video/mp4"
        if "octet-stream" in content_type or source.endswith(".mp4"):
            content_type = "video/mp4"  # upstream labels clips binary/octet-stream
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "private, max-age=3600")
        for header in ("Content-Length", "Content-Range", "Accept-Ranges"):
            value = response.headers.get(header)
            if value:
                self.send_header(header, value)
        self.end_headers()
        try:
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            response.close()


def main():
    print(f"Replay workshop board on http://{HOST}:{PORT}  archive={'configured' if ARCHIVE.configured else 'missing'}  "
          f"wandb={'configured' if WANDB.configured else 'missing'}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
