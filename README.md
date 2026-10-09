# Replay safety workspace

Start with `npm start`, then open http://127.0.0.1:8765. Uses Python 3 and a modern browser; no npm dependencies or API keys required. `npm test` runs the rule-engine checks.

## Demo flow

1. Select a camera.
2. Choose a suggested requirement or type a supported rule.
3. Review the module and adjust its duration threshold.
4. Attach it. If another camera contains the supported example, the button explicitly switches camera and attaches.
5. Play the scenario. An authored event becomes evidence after the configured dwell threshold.
6. Click evidence to seek to its trigger time. Switch to Reference for the contrasting clip.

Camera attachments persist in this browser. Reset clears them. Videos are served locally with byte-range support for seeking. UI works without external fonts, although Google Fonts enhances typography when online.

## Actual implementation boundary

This is a functional UI demo, not a connected AI safety system. `app/rules.js` contains local keyword matching and explicit manually authored example intervals. There is no LLM, object detector, live camera ingestion, OSHA compliance certification, or automatic retraining. All demo analysis is labeled. PPE and blocked-route prompts return an unsupported-capability message.

Replace the interpreter with a validated model-produced rule specification and the event evaluator with actual timestamped inference to connect a model service. Keep the capability checks, visibility/uncertainty handling, and clear source labeling. The current walkway polygon is illustrative, not calibrated, and does not drive a real tracker.

Source attribution and footage provenance: `demo-footage/README.md`. Original videos remain unmodified.

## Sharing and collaboration

Clone this repository, install Python 3 (and Node 20+ for `npm` commands/tests), then run `python3 server.py` or `npm start`. No `npm install` is necessary. The bundled footage makes the initial clone approximately 104 MB plus application assets. Each friend runs their own local server; the localhost URL is not a shareable hosted site.

For continued implementation with Claude or another coding assistant, use [CLAUDE_HANDOFF.md](CLAUDE_HANDOFF.md). The software has no project-wide license selected yet; the third-party footage retains the attribution and license documented in [the footage notes](demo-footage/README.md).


## Run after cloning or pulling

First time (macOS/Linux):

```bash
git clone https://github.com/shuaeb6/replay-safety.git
cd replay-safety
python3 server.py
```

After updates, stop the running server with Ctrl+C, then from the repository:

```bash
git pull --ff-only
python3 server.py
```

On Windows, use `py -3 server.py` instead of `python3 server.py`. Install Python 3 if neither command exists. Open http://127.0.0.1:8765 and keep the terminal running. Refresh the browser after pulling. If the port is in use, stop the earlier Replay server before restarting. If Git reports conflicting local changes, preserve/commit them before pulling; do not discard them blindly.

No dependencies or credentials are required for this offline demo. Node 20+ is optional for `npm test`; no `npm install` is needed. Sponsor-integrated workshop mode is not implemented yet and will require the event environment.

See [Hackathon readiness](HACKATHON_READINESS.md) for the verified gaps and [Claude handoff](CLAUDE_HANDOFF.md) for the revised implementation priority.
