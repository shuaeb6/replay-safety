"""Local static server with byte ranges, plus optional W&B /api/compile bridge.

Serves the offline Replay UI. POST /api/compile uses live/compiler.py (workshop
catalog + Weights & Biases Inference) when credentials are present; otherwise
returns a clear 503 so the browser falls back to keyword compile.
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import glob
import json
import os
import re
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "live"))

try:
    from compiler import WandbCompiler, load_catalog
except Exception:  # pragma: no cover - missing live/ during partial checkouts
    WandbCompiler = None
    load_catalog = None


def _team_config():
    files = sorted(glob.glob("/config/*.config"))
    values = {}
    if len(files) == 1:
        for line in open(files[0], encoding="utf-8"):
            match = re.match(r"\s*(?:export\s+)?([A-Z0-9_]+)=(.*)$", line)
            if match:
                values[match.group(1)] = match.group(2).strip().strip("\"'")
    return values


_CFG = _team_config()
WANDB = None
CATALOG = None
if WandbCompiler and load_catalog:
    try:
        CATALOG = load_catalog()
        WANDB = WandbCompiler(
            os.environ.get("WANDB_API_KEY") or _CFG.get("WANDB_API_KEY", ""),
            os.environ.get("WANDB_TEAM") or _CFG.get("WANDB_TEAM", ""),
            os.environ.get("WANDB_PROJECT") or _CFG.get("WANDB_PROJECT", ""),
            os.environ.get("WANDB_MODEL") or None,
        )
    except Exception:
        WANDB = None
        CATALOG = None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.byte_range = None
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self, limit=8000):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > limit:
            raise ValueError("bad length")
        return json.loads(self.rfile.read(length))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self._json(
                200,
                {
                    "wandb": bool(WANDB and WANDB.configured),
                    "catalog": bool(CATALOG),
                    "live": "/live/",
                },
            )
            return
        if parsed.path in ("/live", "/live/"):
            self.path = "/live/index.html"
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/compile":
            self.send_error(404, "Not found")
            return
        try:
            body = self._read_json()
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "Send a short JSON request."})
            return
        text = " ".join(str(body.get("text") or "").split())
        if not text or len(text) > 400:
            self._json(
                400,
                {"error": "Describe what to watch in one or two sentences (up to 400 characters)."},
            )
            return
        if not (WANDB and WANDB.configured and CATALOG):
            self._json(
                503,
                {
                    "error": "W&B Inference is not configured on this server.",
                },
            )
            return
        try:
            result = WANDB.compile(text, CATALOG)
        except RuntimeError as exc:
            self._json(502, {"error": str(exc)})
            return
        self._json(200, result)

    def send_head(self):
        self.byte_range = None
        requested = self.headers.get("Range")
        path = Path(self.translate_path(self.path))
        if not requested or not path.is_file():
            return super().send_head()
        size = path.stat().st_size
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
        if not match or not any(match.groups()):
            self.send_error(416, "Invalid range")
            return None
        a, b = match.groups()
        start = int(a) if a else max(0, size - int(b))
        end = min(int(b), size - 1) if a and b else size - 1
        if start > end or start >= size:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        file = path.open("rb")
        file.seek(start)
        self.byte_range = (start, end)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        return file

    def copyfile(self, source, outputfile):
        try:
            if self.byte_range:
                remaining = self.byte_range[1] - self.byte_range[0] + 1
                while remaining:
                    data = source.read(min(65536, remaining))
                    if not data:
                        break
                    outputfile.write(data)
                    remaining -= len(data)
            else:
                super().copyfile(source, outputfile)
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == "__main__":
    wandb = "on" if (WANDB and WANDB.configured) else "off"
    print(f"Replay at http://127.0.0.1:8765  (W&B compile: {wandb})", flush=True)
    print("Live board at http://127.0.0.1:8765/live/  (or: python3 live/main.py)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
