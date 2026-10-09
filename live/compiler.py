"""Requirement -> rule compiler backed by Weights & Biases Inference.

The model may only choose modules from catalog.json. Its JSON answer is validated
here: unknown modules, unknown parameters, and out-of-range values are rejected,
never silently repaired. Unsupported topics always use the catalog's own wording.
"""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WANDB_BASE = os.environ.get("WANDB_BASE_URL", "https://api.inference.wandb.ai/v1").rstrip("/")
# Verified on the workshop VM: returns valid JSON with response_format json_object in ~0.85 s.
DEFAULT_MODEL = "meta-llama/Llama-3.3-70B-Instruct"
USER_AGENT = "replay-safety/1.0"  # W&B's Cloudflare front rejects urllib's default agent (error 1010)
MAX_MODULES = 3


def load_catalog():
    return json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))


def system_prompt(catalog):
    modules = [
        {
            "id": m["id"],
            "does": m["summary"],
            "params": {k: {"min": p["min"], "max": p["max"], "default": p["default"], "unit": p["unit"]} for k, p in m["params"].items()},
        }
        for m in catalog["modules"]
    ]
    unsupported = [{"index": i, "topic": u["topic"]} for i, u in enumerate(catalog["unsupported"])]
    return (
        "You configure a video safety-review tool. Map the user's requirement to modules from this fixed catalog.\n"
        f"MODULES: {json.dumps(modules)}\n"
        f"UNSUPPORTED TOPICS: {json.dumps(unsupported)}\n"
        "Rules:\n"
        "- Use only module ids and parameter names from MODULES. Use at most 3 modules, each at most once.\n"
        "- Take parameter values the user states (convert minutes to seconds). Otherwise use the default.\n"
        "- A 'restricted lane', 'forklift lane', 'keep-out zone', 'walkway edge' or 'area' means zone_entry.\n"
        "- 'Close to', 'next to', or 'near' a forklift means near_forklift.\n"
        "- Do not add a module for something the user says to ignore or not to flag.\n"
        "- If part of the request matches an UNSUPPORTED TOPIC, list its index. Never approximate it with another module.\n"
        "- reason: one short sentence quoting the words of the requirement that justify the module.\n"
        'Reply with JSON only: {"modules": [{"id": str, "params": {name: number}, "reason": str}], '
        '"unsupported": [int], "clarification": str or null}'
    )


def validate(answer, catalog):
    """Return (modules, unsupported, problems). Raises ValueError if the answer is unusable."""
    if not isinstance(answer, dict):
        raise ValueError("The model did not return a JSON object.")
    by_id = {m["id"]: m for m in catalog["modules"]}
    modules, problems, seen = [], [], set()
    for item in answer.get("modules") or []:
        if not isinstance(item, dict):
            continue
        mid = item.get("id")
        if mid not in by_id:
            problems.append(f"Ignored an unknown module ({str(mid)[:40]}).")
            continue
        if mid in seen:
            continue
        spec = by_id[mid]
        raw = item.get("params") or {}
        if not isinstance(raw, dict):
            raw = {}
        params, ok = {}, True
        for name in raw:
            if name not in spec["params"]:
                problems.append(f"{spec['name']}: ignored unknown setting '{str(name)[:30]}'.")
        for name, p in spec["params"].items():
            value = raw.get(name, p["default"])
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                problems.append(f"{spec['name']}: '{p['label']}' must be a number.")
                ok = False
                continue
            if not (p["min"] <= value <= p["max"]):
                problems.append(f"{spec['name']}: {p['label']} must be between {p['min']} and {p['max']}{p['unit']}.")
                ok = False
                continue
            params[name] = value
        if ok:
            seen.add(mid)
            modules.append({"id": mid, "params": params, "reason": " ".join(str(item.get("reason") or "").split())[:200]})
    if len(modules) > MAX_MODULES:
        modules = modules[:MAX_MODULES]
        problems.append(f"Kept the first {MAX_MODULES} modules.")
    unsupported = []
    for idx in answer.get("unsupported") or []:
        if isinstance(idx, int) and 0 <= idx < len(catalog["unsupported"]) and catalog["unsupported"][idx] not in unsupported:
            unsupported.append(catalog["unsupported"][idx])
    clarification = answer.get("clarification")
    if clarification is not None and not isinstance(clarification, str):
        clarification = None
    return modules, unsupported, problems, (clarification or "")[:240] or None


class WandbCompiler:
    def __init__(self, api_key, team, project, model=None):
        self.api_key = api_key
        self.project = f"{team}/{project}" if team and project else ""
        self.model = model or DEFAULT_MODEL

    @property
    def configured(self):
        return bool(self.api_key)

    def compile(self, text, catalog):
        if not self.configured:
            raise RuntimeError("W&B Inference is not configured on this server.")
        body = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt(catalog)},
                {"role": "user", "content": text},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "User-Agent": USER_AGENT}
        if self.project:
            headers["OpenAI-Project"] = self.project
        request = urllib.request.Request(f"{WANDB_BASE}/chat/completions", data=json.dumps(body).encode(), headers=headers)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"W&B Inference returned {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("W&B Inference is unreachable.") from exc
        ms = round((time.perf_counter() - started) * 1000)
        try:
            content = payload["choices"][0]["message"]["content"]
            answer = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("W&B Inference returned text that is not valid JSON.") from exc
        modules, unsupported, problems, clarification = validate(answer, catalog)
        usage = payload.get("usage") or {}
        return {
            "modules": modules,
            "unsupported": unsupported,
            "problems": problems,
            "clarification": clarification,
            "model": payload.get("model") or self.model,
            "ms": ms,
            "tokens": usage.get("total_tokens"),
        }
