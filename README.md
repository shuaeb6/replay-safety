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

Source attribution and footage provenance: `demo-footage/README.md`. Original videos remain unmodified.

## Sharing and collaboration

Clone this repository, install Python 3 (and Node 20+ for `npm` commands/tests), then run `python3 server.py` or `npm start`. No `npm install` is necessary. The bundled footage makes the initial clone approximately 104 MB plus application assets. Each friend runs their own local server; the localhost URL is not a shareable hosted site.

For continued implementation with Claude or another coding assistant, use [CLAUDE_HANDOFF.md](CLAUDE_HANDOFF.md). The software has no project-wide license selected yet; the third-party footage retains the attribution and license documented in [the footage notes](demo-footage/README.md).
