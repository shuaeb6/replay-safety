# CCTV demo footage pack

16 original MP4s, 104,726,186 bytes (~100 MiB), downloaded and SHA-256 verified against publisher metadata. ffprobe successfully read every clip; four sampled frames per clip were visually inspected. This is not exhaustive temporal annotation or model validation.

Open `index.html` for the video review gallery. `selected-clips.json` retains original class names, source URLs, checksums, dimensions, durations, and review notes. `dataset-inventory.json` indexes the source test split for future selection.

## Attribution and license

Oğuzhan Önal and Emre Dandıl, **Video Dataset for Safe and Unsafe Behaviours**, version 1, Mendeley Data, DOI **10.17632/xjmtb22pff.1**.

- Source: https://data.mendeley.com/datasets/xjmtb22pff/1
- Dataset license: CC BY 4.0, https://creativecommons.org/licenses/by/4.0/
- Videos are original, unmodified downloads. JPEG previews are extracted/resized derivatives.
- Preserve attribution and indicate any later edits. The dataset license is distinct from the accompanying article's license.
- These are real recordings from one production facility in Turkey, not three separate industries and not US OSHA adjudications.

## Best immediate demo pairs

| Event | Candidate | Comparison | Proposed prompt |
|---|---|---|---|
| Walkway adherence | factory-cctv/0_te21.mp4 (10.5s) | factory-cctv/4_te5.mp4 (10.4s) | Alert when a person walks outside the marked pedestrian route for more than 2 seconds. |
| Tall forklift load | factory-cctv/3_te7.mp4 (4s) | factory-cctv/7_te3.mp4 (4s) | Flag a forklift transporting a tall stack for review. |
| Panel state | factory-cctv/2_te12.mp4 (10.4s) | factory-cctv/6_te12.mp4 (10.4s) | Alert when this panel is visibly open for more than 2 seconds. |

These are candidate pairs selected from sampled frames, not validated detector outputs. Panel state needs a clear enlarged region. The forklift pair is especially visually distinct, but has short context: do not promise collision prediction or actual weight overload. Walkway adherence is a variant of a configured zone rule; it is not evidence of a blocked exit.

## Proposed product modules

1. PPE: person-associated helmet/vest detection in a designated zone, with visible / missing / uncertain states. Require sufficient image detail. Gloves, goggles, sleeve entanglement, and harness attachment are separate capabilities, not automatically covered.
2. Zone rules: tracked person footpoint entering a user-defined polygon, with dwell threshold and optional permitted-route inversion. Physical distance needs calibration. Identity/authorization cannot be inferred from clothing alone.
3. Route obstruction: persistent object overlap with a configured access-route polygon, including obstruction appearance/clearance events. Distinguish a passing worker from stationary obstruction. A clear camera view is not certification of legal egress.

The current pack directly supports walkway and other factory candidates. Dedicated PPE and blocked-route paired videos, plus footage of an actual construction site and warehouse, remain unfilled. Candidate stock pages below are not downloaded or visually validated.

## Camera-grid interaction

Camera tiles contain recorded clips with replay badges. Select one or multiple cameras, then type the requirement in a right sidebar. An LLM maps the requirement onto an allowlisted module and validated parameters. Show the suggested module, affected cameras, rule, duration threshold, and needed setup. Attach activates the prebuilt pipeline, not instant training of an arbitrary detector.

For zones, ask the user to draw/confirm a polygon. Preview must show what is evaluated: person/object boxes, tracked footpoint, region boundary, evidence crop, and event duration. Show event -> evidence -> replay. Include an uncertain state when visibility fails.

Example: select factory corridor, type 'Keep workers inside the green walkway', suggest Zone Rules, confirm permitted region, attach, replay the two contrasting clips. Then change dwell duration and rerun the same evidence. A real change in output driven by the user's rule is more persuasive than an unexplained alarm.

Do not fake a live detector with hidden timestamps. If using precomputed detections, disclose cached inference; if using manually authored overlays, label them illustrative. Do not claim the entire site is OSHA compliant or noncompliant from a single clip.

## Additional source leads — not included assets

- Construction aerial: https://www.pexels.com/video/workers-on-construction-site-13700847/
- Warehouse worker / forklift: https://www.pexels.com/video/man-walking-towards-the-forklift-inside-the-warehouse-4294434/
- Warehouse helmet: https://www.pexels.com/video/man-with-orange-helmet-getting-into-forklift-5100048/
- Construction surveillance sample: https://github.com/supervisely-ecosystem/construction-site-crew-and-machinery-tracking-sample-video-project-annotated (underlying footage license not verified).
- Safe-Construct: https://safe-construct.github.io/Safe-Construct/ (research reference; repository says demo implementation coming soon).

Stock footage should be described neutrally; Pexels restricts portraying identifiable people in a bad light. Check the specific asset and current terms before using it as alleged wrongdoing: https://www.pexels.com/license/
