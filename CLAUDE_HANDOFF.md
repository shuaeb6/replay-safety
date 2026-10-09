# Replay: implementation handoff

Use the following as your task brief. Inspect the repository before making changes; this describes the baseline and may become outdated.

## Product and user intent

Continue improving Replay, a clean CCTV safety-monitoring demo built for a real-time video agents hackathon. The desired interaction is:

1. Choose recorded video feeds displayed like existing CCTV cameras.
2. Write a safety requirement in plain language in a side panel.
3. Receive a suggestion for a compatible prebuilt module.
4. Review parameters and attach it immediately.
5. See the region/objects being evaluated, a readable event explanation, evidence replay, and a contrasting reference clip.

The user prioritizes simplicity, visual polish, convincing real footage, and a fast demonstration. Preserve the restrained off-white/green design, generous spacing, camera strip, large player, and focused sidebar. Avoid clutter, dense enterprise dashboards, or exposing implementation details in primary user controls. Keep a clear demo/inference mode label and explanatory detail available.

This is a public repository shared with friends. Make it reproducible from a fresh clone. Never add credentials. Preserve third-party footage attribution.

## Current stack and commands

- Plain HTML, CSS, and browser JavaScript ES modules. No framework, bundler, npm dependencies, or API keys.
- Python 3 standard-library HTTP server on 127.0.0.1:8765, including byte-range handling for video seeking.
- `npm start` starts `python3 server.py`; Python 3 must exist as `python3`.
- `python3 server.py` also works without Node.
- `npm test` runs five Node test-runner tests. Node 20+ is a reasonable development baseline; initial work used Node 24.
- Open http://127.0.0.1:8765. That address is local to each computer, not a public deployment.
- Google Fonts is an optional network request; system fonts are fallbacks.

## File map

- `index.html`: application structure, camera area, viewer, sidebar, evidence, and about dialog.
- `app/style.css`: visual design and responsive breakpoints.
- `app/main.js`: DOM rendering, camera selection, playback, rules, localStorage, suggestions, overlays, evidence, and notifications.
- `app/rules/`: `catalog.js` (modules, camera/clip mappings), `schema.js` (rule/event contracts), `compiler.js` (keyword interpreter), `evaluator.js` (illustrative events). `app/rules.js` re-exports them.
- `server.py`: local static server and video range responses. Development-only; do not expose the repository root on a public server.
- `tests/rules.test.js`: interpreter, unsupported requests, thresholds, compatibility, reference-mode suppression.
- `demo-footage/factory-cctv/`: 16 original MP4 clips.
- `demo-footage/previews/`: extracted JPEG frames and contact sheets.
- `demo-footage/selected-clips.json`: metadata, original class labels, URLs, checksums, sizes, durations, and review notes.
- `demo-footage/dataset-inventory.json`: source test-split inventory.
- `demo-footage/index.html`: separate source-footage review gallery.
- `demo-footage/README.md`: source provenance, attribution, candidate pairings, and limitations.
- `replay-preview.jpg`: historical screenshot, not a guaranteed representation of later changes.

## What actually works

Camera selection, scenario/reference toggling, play/pause, seeking, restart, speed, overlay visibility, local requirement matching, duration editing, compatible-camera switching, module attachment/removal, persisted attachments, clickable evidence seeking, reset, and the about dialog.

Evidence is generated when playback reaches a configured illustrative interval plus its dwell threshold. Increasing the threshold can delay or suppress the event. References deliberately emit no authored events. Removing/replacing a module removes that camera's evidence. Attachments persist using localStorage key `replay-rules`; evidence does not persist.

## Critical implementation boundary

There is NO connected LLM, computer vision detector, tracker, live camera service, streaming inference, training, or RL pipeline. Natural-language matching is a small keyword parser. Events are hardcoded illustrative intervals. The walkway polygon is a hardcoded visual overlay and does not drive tracking or event computation.

Do not describe this baseline as actual video understanding. Do not hide demo labeling or invent model confidence, boxes, or benchmark numbers. If integrating inference, keep separate authored-demo, cached-real-inference, and live-inference states. A reference label means a contrasting dataset example; it is not proof of overall safety, and AI did not alter the footage.

## Current module/clip mapping

| Camera | Module | Scenario | Reference | Authored interval |
|---|---|---|---|---|
| Production walkway | Walkway watch (`zone`) | `0_te21.mp4` | `4_te5.mp4` | 1–8 seconds |
| Material handling | Load visibility (`load`) | `3_te7.mp4` | `7_te3.mp4` | 0.2–3.7 seconds |
| Machine floor | Panel watch (`panel`) | `2_te12.mp4` | `6_te12.mp4` | 0.5–9 seconds |

Current thresholds default to 2s, 1s, and 2s respectively. Allowed range is 0.1–60s. Only one module per camera is currently stored. The selected scenario determines compatibility.

These intervals were authored for the workflow demo, not exhaustively frame-annotated. Four sampled frames from each downloaded clip were inspected; do not treat that as validated temporal ground truth.

## Footage and broader ambitions

All downloaded clips are from ONE factory. Do not rename them as separate warehouse/construction sites. They are from Önal and Dandıl's Video Dataset for Safe and Unsafe Behaviours, version 1, DOI 10.17632/xjmtb22pff.1, published under CC BY 4.0. Preserve author/source/license attribution and mark edits or derived assets. The dataset and accompanying article have distinct licenses.

The original desired capability set was PPE, restricted-zone entry, and blocked access routes across warehouses, factories, and construction sites. Dedicated verified footage pairs for PPE and route obstructions have not been obtained. Current supported modules were chosen around available factory examples. Unsupported PPE/fire/speed/blocked-route/theft requests must remain honest about missing support.

Video alone cannot establish forklift load weight, actual worker authorization, energized machinery, or legal OSHA compliance. For real detection, use observable events and uncertainty states. Calibrated physical distance/speed needs camera geometry. A helmet hidden by occlusion is unknown, not missing.

## Recommended implementation priorities

1. Run the existing app and tests; inspect actual code and video behavior. Identify bugs before rewriting architecture. Keep the working baseline.
2. Improve usability and accessibility: readable contrast, mobile layout, clear focus, input validation, and uncluttered error/loading states. Make camera and active-rule context obvious.
3. Add real per-camera region editing if requested: persist polygons and explain what they control. Do not imply that a drawn region drives a real detector until it does.
4. Introduce an inference adapter interface. Normalize camera ID, timestamp, module ID, event type, bounding boxes/region, evidence interval, source mode, and model version. Handle unavailable inference without silently falling back to fabricated detections.
5. Integrate a real model service only when its endpoint/credentials and deployment constraints are known. Keep API keys server-side in ignored environment files. If missing, build the adapter and document the needed configuration; never claim integration is finished.
6. Replace keyword matching with a constrained LLM rule compiler when available. Validate against an allowlisted module schema, check camera compatibility, extract explicit parameters, and reject unsupported requests. Handle negation and ambiguous requirements; arbitrary user text must not execute code.
7. Improve genuine event logic: object-person association for PPE, tracked footpoint/polygon relationships for zones, persistence and clearance for obstructions. Add temporal smoothing and deduplication. Use an uncertainty state when visibility is insufficient.
8. Obtain further free footage with clear reuse terms and actual visual review. Keep a manifest linking every asset to its source/license and intended demonstration. Never label a stock actor as committing wrongdoing without appropriate context/rights.

Training/RL from user feedback is a future concept, not part of the demo. If pursued later, use explicit consent, vetted labels, offline evaluation and versioned releases. Do not automatically train on the model's own unverified outputs.

## Known review targets

- Keyword parsing is deliberately narrow and does not understand general language or negation. Audit how malformed/negative durations are handled.
- Evidence creation currently relies on playback `timeupdate`; jumping over an interval may miss it, while seeking inside one may create an event.
- Clear-evidence behavior during an active interval may immediately repopulate the event.
- Camera switching and delayed metadata callbacks should not apply an old seek to a newly selected camera.
- UI module registration is currently tightly coupled to three camera examples; generalize carefully if adding feeds.
- The static server is for local use, not internet deployment or production security.
- No project-wide software license has been selected. Footage retains its own CC BY attribution requirements.

## Acceptance criteria

- Fresh clone starts with documented prerequisites and commands; bundled source clips load.
- Supported rule -> suggestion -> attach -> playback -> evidence -> replay works end to end.
- Reference mode, removal, reset, threshold changes, and incompatible cameras behave consistently.
- Unsupported requests explain what is missing, without a fabricated success state.
- Demo events, cached inference, and real inference remain distinguishable.
- Desktop and narrow layouts remain usable, with accessible keyboard controls.
- Run appropriate tests and verify playback/seeking in a browser after changes. Report what was actually tested and what remains unimplemented.

Start implementing within this scope. Ask only for information that blocks a real integration; continue independent work while waiting. Summarize concrete changes, validation, and remaining limitations.
