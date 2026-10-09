# Workshop VM handoff (Cursor prompts)

Work is split between two machines:

- **Laptop (Claude Code):** writes all application code (`index.html`, `app/`, `server.py`, `tools/`, `tests/`) and pushes to the `workshop-mode` branch.
- **Workshop VM (Cursor Agent):** runs, probes, verifies, and deploys. It reads credentials from `/config/<team>.config` and never copies them anywhere.

To avoid merge conflicts, Cursor should **not edit tracked application files**. Notes, probe output, and recorded responses go in `.workshop/` (gitignored). If Cursor finds a bug, it reports it so the laptop side can fix it.

## One-time setup on the VM

Start Cursor from the official repository so its skills and rules load. Clone Replay next to it:

```bash
cd ~ && git clone https://github.com/shuaeb6/replay-safety.git
cd ~/replay-safety && git checkout workshop-mode
cd ~/vast-builders-challenge && git pull && agent
```

Refer to the app as `~/replay-safety` in prompts. To get laptop updates: `git -C ~/replay-safety pull --ff-only`.

---

## Prompt 1 — Probe the stack (run now)

```text
Read ~/replay-safety/WORKSHOP_HANDOFF.md for context. Do not edit any tracked file in ~/replay-safety.
1. Run the health check (retrieval/login + retrieval/dashboard). Report pass/fail only.
2. Run: cd ~/replay-safety && python3 tools/workshop_probe.py
   It is read-only and prints no secrets. Show me its full output.
3. From the listed W&B model ids, pick one instruction-tuned chat model that is good at JSON, then run:
   python3 tools/workshop_probe.py --skip-vss --model <that id>
   Show me that output too.
Never print env values, tokens, or passwords. List variable names only if needed.
```

Paste both outputs back to Claude.

## Prompt 1b — Re-test W&B Inference (after the user-agent fix)

The first probe got Cloudflare `error code: 1010` from W&B because Python's default user agent is blocked. The probe now sends its own user agent.

```text
git -C ~/replay-safety pull --ff-only   (if history was rewritten, use the resync commands at the end of this file instead)
cd ~/replay-safety && python3 tools/workshop_probe.py --skip-vss
Show me the full model id list. Then pick the strongest instruction-tuned model from that list that supports JSON output
(prefer a Llama 3.3 70B / Qwen / DeepSeek / gpt-oss style instruct model) and run:
python3 tools/workshop_probe.py --skip-vss --model <that id>
Show both outputs. Do not print secrets.
```

## Prompt 2 — Data test drive for the use case

```text
Using the retrieval skills (list-metadata, search, videos), and without editing files in ~/replay-safety:
1. List every camera_id / location / capture_type value, with how many indexed videos each has.
2. For the warehouse pack (sdg_warehouse_cam-2 or whatever warehouse camera exists), and the indoor smartspace camera if present, run these searches with min_similarity 0.3, top_k 10:
   "forklift near a person in an aisle", "person walking in a warehouse aisle",
   "pallet or object blocking a walkway", "person standing in a restricted area", "several people grouped together".
   For each: hit count, top 3 scores, segment source URIs, start/end seconds, and the first 200 chars of reasoning.
3. For the best forklift hit, fetch /videos/detections and show the raw JSON structure (truncate long arrays to 3 items). Tell me whether boxes are per-frame or per-segment, the coordinate format, and which class labels appear (is there any "forklift"/"truck"?).
4. Tell me whether this footage looks synthetic (rendered) or real camera footage, based on the reasoning text and your view of a played clip.
Save a summary to ~/replay-safety/.workshop/data-notes.md and print it.
```

## Prompt 3 — Run Replay in workshop mode on the VM (after Claude says it is ready)

```text
git -C ~/replay-safety pull --ff-only
Then follow the "Workshop mode" section of ~/replay-safety/README.md to start the server on the VM and run its smoke test (tools/smoke_test.py).
Report each check's pass/fail, latency, and any error text. Do not print secrets.
```

## Prompt 4 — Deploy to /app (after Prompt 3 passes)

```text
Use the deployment/deploy-app-no-registry skill to deploy ~/replay-safety to my team namespace at path /app.
The app needs a flat bundle; build it with: python3 ~/replay-safety/tools/build_bundle.py (it prints the bundle directory).
Use that directory for the ConfigMap. Create the Secret from my team config with VSS_URL/VSS_USERNAME/VSS_PASSWORD plus WANDB_API_KEY, WANDB_TEAM, WANDB_PROJECT, and REPLAY_MODE=workshop.
Verify the pod is Running and that /app/health, /app/api/status, the page, static assets, and one video stream all work. Then tell me to open https://workshop.thecosmoslabs.com → App.
```

## Prompt 5 — Analysis prep / re-ingest (only if captions lack detail; coordinate with teammates first)

```text
Use ingest/reingest-chunk (or reingest-videos) on ONE warehouse clip only: <clip>.
Custom prompt: "<prompt Claude provides>". Show me the confirmation summary before starting, then monitor until completed and re-run the same search to compare.
```

---

## What to paste back to Claude

- Probe or smoke-test output (already sanitized).
- Exact error text and the command that produced it.
- Never paste tokens, passwords, keys, or `/config` contents. Segment URIs, camera IDs, and model IDs are fine.

## Resync the VM after a history rewrite

The factory MP4s were removed from Git history, so `git pull` fails with "divergent branches". The VM has no tracked edits; `.workshop/` is ignored and is kept.

```bash
git -C ~/replay-safety fetch origin
git -C ~/replay-safety reset --hard origin/workshop-mode
```
