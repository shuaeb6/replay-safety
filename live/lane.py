"""Forklift-lane proposal with NVIDIA Cosmos Reason (the event's vision model on CoreWeave GPUs).

The browser sends one JPEG frame of the selected camera. Cosmos Reason returns the
floor region where forklifts travel as a polygon in image fractions. The answer is
validated (3-8 points inside the frame, plausible area); anything else is rejected,
and the UI falls back to manual drawing instead of inventing a lane.
"""

import json
import re
import time
import urllib.error
import urllib.request

# Endpoint documented in the official gpu/model-smoke-test skill; override with COSMOS3_REASON_URL.
DEFAULT_URL = "http://166.19.38.112:8001"
PROMPT = (
    "This is one frame from a fixed warehouse CCTV camera. Find the floor area where a forklift drives or is parked: "
    "the forklift travel lane or the aisle floor around the forklift. If there is no forklift, use the main open aisle floor "
    "where vehicles would drive. Reply with JSON only, no other text: "
    '{"found": true or false, "polygon": [[x, y], ...], "reason": "one short sentence"}. '
    "Use 4 to 6 points that outline that floor area. x and y are fractions of the image width and height from 0 to 1, "
    "measured from the top-left corner."
)


FALLBACK_MODEL = "nvidia/cosmos3-reason"


def choose_model(configured, served):
    """Use the configured model only if the server serves it; a stale name returns 404."""
    if configured and (not served or configured in served):
        return configured
    return served[0] if served else FALLBACK_MODEL


def polygon_area(points):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]))) / 2


def parse_lane(text):
    """Extract and validate {"polygon": [[x, y], ...]} from the model's reply."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError("Cosmos Reason did not return JSON.")
    data = json.loads(match.group(0))
    if data.get("found") is False:
        raise ValueError("Cosmos Reason found no forklift lane in this view.")
    raw = data.get("polygon")
    if not isinstance(raw, list) or not 3 <= len(raw) <= 8:
        raise ValueError("Cosmos Reason returned an unusable outline.")
    points = []
    for pt in raw:
        if not (isinstance(pt, (list, tuple)) and len(pt) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in pt)):
            raise ValueError("Cosmos Reason returned an unusable outline.")
        x, y = float(pt[0]), float(pt[1])
        if max(x, y) > 1.5:  # pixel coordinates on a 1000-scale are a common VLM habit; accept and normalise
            x, y = x / 1000, y / 1000
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError("Cosmos Reason placed the lane outside the frame.")
        points.append([round(x, 4), round(y, 4)])
    area = polygon_area(points)
    if not 0.01 <= area <= 0.8:
        raise ValueError("Cosmos Reason proposed a lane that is too small or covers the whole frame.")
    return points, " ".join(str(data.get("reason") or "").split())[:200]


class LaneProposer:
    def __init__(self, url, token, model=None):
        self.url = (url or DEFAULT_URL).rstrip("/")
        self.token = token
        self.model = model
        self._resolved = False

    @property
    def configured(self):
        return bool(self.url)

    def _headers(self):
        headers = {"Content-Type": "application/json", "User-Agent": "replay-safety/1.0"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _served_models(self):
        try:
            req = urllib.request.Request(f"{self.url}/v1/models", headers=self._headers())
            with urllib.request.urlopen(req, timeout=10) as r:
                return [m["id"] for m in json.load(r)["data"]]
        except Exception:
            return []

    def _model(self):
        if not self._resolved:
            self.model = choose_model(self.model, self._served_models())
            self._resolved = True
        return self.model

    def propose(self, image_data_url):
        body = {
            "model": self._model(),
            "temperature": 0,
            "max_tokens": 900,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": image_data_url}},
                {"type": "text", "text": PROMPT},
            ]}],
        }
        req = urllib.request.Request(f"{self.url}/v1/chat/completions", data=json.dumps(body).encode(), headers=self._headers())
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                payload = json.load(r)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Cosmos Reason returned {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("Cosmos Reason is unreachable from this server.") from exc
        ms = round((time.perf_counter() - started) * 1000)
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Cosmos Reason returned an empty answer.") from exc
        try:
            polygon, reason = parse_lane(text)
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(str(exc) if isinstance(exc, ValueError) and str(exc).startswith("Cosmos") else "Cosmos Reason did not return a usable lane.") from exc
        return {"polygon": polygon, "reason": reason, "model": payload.get("model") or self.model, "ms": ms}
