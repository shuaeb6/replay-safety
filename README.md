# Replay safety workspace

Start with `npm start`, then open http://127.0.0.1:8765. Uses Python 3 and a modern browser; no npm dependencies or API keys required. `npm test` runs the rule-engine checks.

### Chat → rules (keyword + optional W&B)

The requirement box compiles text through `app/rules` (`compileRequirementAsync`, mode `auto`):

1. `POST /api/compile` uses the workshop catalog (`live/catalog.json`) and W&B Inference when credentials are in the environment or `/config/*.config`.
2. Valid workshop modules that map to demo cameras (`zone_entry` → walkway, `near_forklift` → tall load) become attachable Replay suggestions labeled **W&B COMPILE**.
3. If W&B is down or unconfigured, the UI falls back to local keyword matching so offline clones keep working.
4. Full archive evaluation (YOLO zones, search evidence) lives on the **live board** at http://127.0.0.1:8765/live/ (or `python3 live/main.py` on port 8080).

## Demo flow

1. Select a camera.
2. Choose a suggested requirement or type a supported rule.
3. Review the module and adjust its duration threshold.
4. Attach it. If another camera contains the supported example, the button explicitly switches camera and attaches.
5. Play the scenario. An authored event becomes evidence after the configured dwell threshold.
6. Click evidence to seek to its trigger time. Switch to Reference for the contrasting clip.

Camera attachments persist in this browser. Reset clears them. Videos are served locally with byte-range support for seeking. UI works without external fonts, although Google Fonts enhances typography when online.

## Actual implementation boundary

Offline Replay still uses authored demo intervals for evidence on the three factory clips. W&B compile only selects allowlisted modules; it does not invent detectors. YOLO/search evidence runs on the live board, not in the offline player. There is no OSHA compliance certification. PPE and similar unsupported topics return an explicit error. The walkway polygon in the demo player is illustrative, not calibrated.

Source attribution and footage provenance: `demo-footage/README.md`. Original videos remain unmodified and are downloaded from their source with `python3 tools/fetch_footage.py` rather than stored in this repository.

## Sharing and collaboration

Clone this repository, install Python 3 (and Node 20+ for `npm` commands/tests), then run `python3 server.py` or `npm start`. No `npm install` is necessary. The factory clips (~104 MB) are not stored in Git; `python3 tools/fetch_footage.py` downloads them from the original Mendeley Data source and verifies their checksums. Each friend runs their own local server; the localhost URL is not a shareable hosted site.

The software has no project-wide license selected yet; the third-party footage retains the attribution and license documented in [the footage notes](demo-footage/README.md).


## Run after cloning or pulling

First time (macOS/Linux):

```bash
git clone https://github.com/shuaeb6/replay-safety.git
cd replay-safety
python3 tools/fetch_footage.py
python3 server.py
```

After updates, stop the running server with Ctrl+C, then from the repository:

```bash
git pull --ff-only
python3 server.py
```

On Windows, use `py -3 server.py` instead of `python3 server.py`. Install Python 3 if neither command exists. Open http://127.0.0.1:8765 and keep the terminal running. Refresh the browser after pulling. If the port is in use, stop the earlier Replay server before restarting. If Git reports conflicting local changes, preserve/commit them before pulling; do not discard them blindly.

No dependencies or credentials are required for this offline demo. Node 20+ is optional for `npm test`; no `npm install` is needed.

See [Hackathon readiness](HACKATHON_READINESS.md) for the verified gaps.

## Workshop board (`live/`)

The `live/` folder is the hackathon app built on the event's pre-indexed archive. It needs the workshop VM or the team's Kubernetes namespace; it does not use the factory clips.

Flow: indexed warehouse feeds replay with their recorded person boxes and scene captions (2 modules running). You type a safety requirement or click an example. W&B Inference maps it to modules from `live/catalog.json`; the server rejects anything outside the catalog. Attached modules add layers (2 + m running); for the lane rule, Cosmos Reason proposes the forklift lane on each camera (manual drawing is only a fallback). A Before / Compare / After control compares the footage with and without your rules. Flagged moments link back to real segment IDs.

| Service | What Replay uses it for | Code |
|---|---|---|
| VAST VSS (DataEngine + VastDB) | Login, feed list, segment stream, captions, detections, hybrid search | `live/main.py` (`Archive`) |
| NVIDIA Cosmos Reason | Proposes the forklift lane from a camera frame; segment captions shown on the stage and searched for caption-based rules | `live/lane.py` (direct call), `Archive.segment` / `Archive.evidence` (via VSS) |
| YOLO11 | Per-frame person boxes; lane, lingering and crowding rules are computed from them | `Archive.detections`, `live/engine.js` |
| W&B Inference | Requirement-to-rule compilation, validated against the catalog | `live/compiler.py` |
| CoreWeave | GPUs behind the pipeline models; the app is deployed to the team namespace | deployment below |

Limits: the warehouse feeds are synthetic (rendered) scenes; the detector does not box forklifts, so forklift rules use captions; positions are image-space, not calibrated distance; match scores rank relevance and are not safety confidence; flagged moments are for human review, not compliance findings.

Run on the workshop VM (reads `/config/<team>.config`, prints no secrets):

```bash
cd live && HOST=127.0.0.1 PORT=8080 python3 main.py
```

Then, in another terminal, `python3 tools/smoke_test.py http://127.0.0.1:8080/`. Deploy the `live/` folder with the official `deployment/deploy-app-no-registry` skill (ConfigMap from `live/`, Secret with `VSS_URL`, `VSS_USERNAME`, `VSS_PASSWORD`, `WANDB_API_KEY`, `WANDB_TEAM`, `WANDB_PROJECT`, `GPU_BEARER_TOKEN`), and run the smoke test against the deployed `/app/` URL.

Layout work without the VM: `python3 tools/dev_fixture.py` serves the board on http://127.0.0.1:8770 with local stand-in data and a "Development fixture" banner. It is never deployed and lights no sponsor services.

Tests: `npm test` (rule engine) and `python3 -m unittest discover -s tests` (validation and feed parsing).
