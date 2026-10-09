"""Replay safety board. Serves the UI and proxies the team video archive.

Credentials come from VSS_URL, VSS_USERNAME, and VSS_PASSWORD. They stay on the
server. The browser never receives them.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlparse
import json
import os
import threading
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "8080"))
VSS_URL = os.environ.get("VSS_URL", "").rstrip("/")
VSS_USERNAME = os.environ.get("VSS_USERNAME", "")
VSS_PASSWORD = os.environ.get("VSS_PASSWORD", "")

CAMERA_INFO = {
    "sdg_warehouse_cam-2": ("Warehouse aisle", "Warehouse · ceiling", "warehouse"),
    "smartspace_cam-1": ("Indoor floor", "Facility · indoor", "warehouse"),
    "i24_cam-1": ("Highway", "Nashville · I-24", "road"),
    "pie_cam-3": ("City drive", "Toronto · forward cam", "road"),
    "neighborhood_cam-1": ("Neighborhood", "Residential street", "street"),
    "nyc_streets_cam-1": ("NYC street A", "New York", "street"),
    "nyc_streets_cam-2": ("NYC street B", "New York", "street"),
    "nyc_bike_gopro-1": ("NYC bike", "New York · rider cam", "street"),
    "sf_streets_cam-1": ("SF street 1", "San Francisco", "street"),
    "sf_streets_cam-2": ("SF street 2", "San Francisco", "street"),
    "sf_streets_cam-3": ("SF street 3", "San Francisco", "street"),
    "sf_streets_cam-4": ("SF street 4", "San Francisco", "street"),
    "sf_streets_cam-5": ("SF street 5", "San Francisco", "street"),
}
CAMERA_ORDER = list(CAMERA_INFO)
QUIET_QUERY = "empty scene with no people and no moving vehicles"
STATIC = {
    "/": "index.html",
    "/index.html": "index.html",
    "/style.css": "style.css",
    "/client.js": "client.js",
}


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


def _sentence(text):
    text = " ".join((text or "").split())
    if not text:
        return ""
    for mark in (". ", "。"):
        if mark in text:
            return text.split(mark, 1)[0].strip() + "."
    return text[:140]


def moment_from_chunk(chunk):
    timeline = chunk.get("timeline") or []
    best = next((row for row in timeline if row.get("is_best_match")), None)
    if best is None and timeline:
        best = max(timeline, key=lambda row: row.get("similarity_score") or 0)
    reasoning = (best or {}).get("reasoning_content") or chunk.get("reasoning_content") or ""
    objects = (best or {}).get("object_classes") or ""
    if isinstance(objects, list):
        objects = ", ".join(str(item) for item in objects)
    source = chunk.get("preview_source") or ""
    if not safe_source(source, VSS_USERNAME):
        source = ""
    return {
        "title": _sentence(reasoning) or "Indexed moment",
        "detail": " ".join(reasoning.split())[:700],
        "camera_id": chunk.get("camera_id") or "",
        "location": chunk.get("location") or "",
        "start_sec": chunk.get("best_match_start_sec"),
        "end_sec": chunk.get("best_match_end_sec"),
        "score": chunk.get("similarity_score"),
        "source": source,
        "objects": objects,
        "filename": chunk.get("filename") or "",
    }


def trim_detections(payload):
    frames = payload.get("frames") or []
    step = max(1, len(frames) // 150) if len(frames) > 180 else 1
    trimmed = []
    for frame in frames[::step]:
        boxes = []
        for det in (frame.get("detections") or [])[:24]:
            boxes.append({
                "label": det.get("label") or "",
                "confidence": det.get("confidence"),
                "bbox": det.get("bbox"),
            })
        trimmed.append({"time_sec": frame.get("time_sec"), "detections": boxes})
    return {
        "video_shape": payload.get("video_shape"),
        "fps": payload.get("fps"),
        "object_classes": payload.get("object_classes") or [],
        "frames": trimmed,
        "sampled": step > 1,
    }


class Archive:
    def __init__(self):
        self._token = None
        self._lock = threading.Lock()

    def _login(self):
        if not VSS_URL or not VSS_USERNAME or not VSS_PASSWORD:
            raise RuntimeError("Video archive is not configured on this server.")
        body = json.dumps({"username": VSS_USERNAME, "password": VSS_PASSWORD}).encode()
        request = urllib.request.Request(
            f"{VSS_URL}/api/v1/auth/login",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError("Archive login failed.") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("Archive is unreachable.") from exc
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("Archive login failed.")
        self._token = token
        return token

    def token(self, force=False):
        with self._lock:
            if self._token and not force:
                return self._token
            return self._login()

    def call(self, method, path, payload=None, timeout=90):
        data = None if payload is None else json.dumps(payload).encode()
        last_error = None
        for attempt in range(2):
            token = self.token(force=attempt == 1)
            headers = {"Authorization": f"Bearer {token}"}
            if data is not None:
                headers["Content-Type"] = "application/json"
            request = urllib.request.Request(f"{VSS_URL}{path}", data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    raw = response.read()
                    if not raw:
                        return {}
                    return json.loads(raw)
            except urllib.error.HTTPError as exc:
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
            name, place, tone = CAMERA_INFO.get(camera_id, (camera_id, "Indexed camera", "street"))
            cameras.append({
                "id": camera_id,
                "name": name,
                "place": place,
                "tone": tone,
                "segments": counts.get(camera_id) or 0,
            })
        overview = stats.get("overview") or {}
        return {
            "cameras": cameras,
            "indexed_clips": overview.get("indexed_clips"),
            "quiet_query": QUIET_QUERY,
        }

    def search(self, query, camera_id):
        body = {
            "query": query,
            "top_k": 8,
            "llm_top_n": 3,
            "min_similarity": 0.28,
            "include_public": True,
        }
        if camera_id:
            body["metadata_filters"] = {"camera_id": camera_id}
        result = self.call("POST", "/api/v1/search", body, timeout=120)
        synthesis = result.get("llm_synthesis") or {}
        moments = [moment_from_chunk(chunk) for chunk in result.get("chunk_results") or []]
        moments = [moment for moment in moments if moment["source"]]
        return {
            "query": query,
            "answer": synthesis.get("response") or "",
            "model": synthesis.get("model") or "",
            "moments": moments,
        }


ARCHIVE = Archive()


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

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or "0")
        if length > 8000:
            raise ValueError("Request is too large.")
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw.decode() or "{}")
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object.")
        return data

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(200, {"ok": True})
            return
        if parsed.path == "/api/sites":
            self._guard(lambda: self._json(200, ARCHIVE.sites()))
            return
        if parsed.path == "/api/detections":
            self._guard(lambda: self._detections(parse_qs(parsed.query)))
            return
        if parsed.path == "/api/stream":
            self._stream(parse_qs(parsed.query))
            return
        if parsed.path in STATIC:
            self._file(STATIC[parsed.path])
            return
        self._json(404, {"error": "Not found."})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/search":
            self._json(404, {"error": "Not found."})
            return
        try:
            body = self._read_json()
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "Send a short text requirement."})
            return
        query = " ".join(str(body.get("query") or "").split())
        camera_id = str(body.get("camera_id") or "")
        if not query or len(query) > 400:
            self._json(400, {"error": "Describe what to watch in one short sentence."})
            return
        if camera_id and (camera_id not in CAMERA_INFO or len(camera_id) > 80):
            # Unknown ids are still accepted when they match the archive charset.
            if not camera_id.replace("-", "").replace("_", "").isalnum() or len(camera_id) > 80:
                self._json(400, {"error": "Unknown camera."})
                return
        self._guard(lambda: self._json(200, ARCHIVE.search(query, camera_id)))

    def _guard(self, action):
        try:
            action()
        except RuntimeError as exc:
            self._json(502, {"error": str(exc)})
        except Exception:
            self._json(502, {"error": "The archive request failed."})

    def _detections(self, query):
        source = (query.get("source") or [""])[0]
        if not safe_source(source, VSS_USERNAME):
            self._json(400, {"error": "That clip is outside this archive."})
            return
        path = "/api/v1/videos/detections?" + urlencode({"source": source})
        try:
            payload = ARCHIVE.call("GET", path, timeout=40)
        except RuntimeError as exc:
            message = str(exc).lower()
            if "404" in message or "not found" in message:
                self._json(200, {"frames": [], "object_classes": [], "unavailable": True})
                return
            raise
        self._json(200, trim_detections(payload))

    def _file(self, name):
        path = ROOT / name
        if not path.is_file():
            self._json(404, {"error": "Missing application file."})
            return
        kind = "text/html" if name.endswith(".html") else "text/css" if name.endswith(".css") else "text/javascript"
        self._send(200, path.read_bytes(), f"{kind}; charset=utf-8")

    def _stream(self, query):
        source = (query.get("source") or [""])[0]
        if not safe_source(source, VSS_USERNAME):
            self._json(400, {"error": "That clip is outside this archive."})
            return
        try:
            token = ARCHIVE.token()
        except RuntimeError as exc:
            self._json(502, {"error": str(exc)})
            return
        upstream = f"{VSS_URL}/api/v1/videos/stream?source={quote(source, safe='')}&token={quote(token, safe='')}"
        headers = {}
        if self.headers.get("Range"):
            headers["Range"] = self.headers["Range"]
        request = urllib.request.Request(upstream, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=120)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                try:
                    token = ARCHIVE.token(force=True)
                    upstream = f"{VSS_URL}/api/v1/videos/stream?source={quote(source, safe='')}&token={quote(token, safe='')}"
                    response = urllib.request.urlopen(urllib.request.Request(upstream, headers=headers), timeout=120)
                except Exception:
                    self._json(502, {"error": "Clip playback failed."})
                    return
            else:
                self._json(502, {"error": "Clip playback failed."})
                return
        except urllib.error.URLError:
            self._json(502, {"error": "Clip playback failed."})
            return
        status = getattr(response, "status", 200)
        self.send_response(status)
        content_type = response.headers.get("Content-Type") or "video/mp4"
        if "octet-stream" in content_type or source.endswith(".mp4"):
            content_type = "video/mp4"
        self.send_header("Content-Type", content_type)
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
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
