# Hackathon readiness review — October 9, 2026

## Verdict

The current repository is a functional offline UI prototype. It uses no sponsor inference, index, storage, or deployment service. It cannot currently demonstrate the intended sponsor-backed video-agent workflow. This is an implementation assessment, not a formal organizer eligibility ruling.

## Sources checked

- [Official event listing](https://luma.com/vastnyc)
- [Official current build guide](https://github.com/vast-data/vast-builders-challenge/blob/main/README.md)
- [Architecture reference](https://github.com/vast-data/vast-builders-challenge/blob/main/ARCHITECTURE_REFERENCE.md)
- [Preparation guide](https://github.com/vast-data/vast-builders-challenge/blob/main/BEFORE_YOU_BUILD.md)

`BUILD_DAY.md` now points to the README. Search-engine excerpts showed older text, so the current raw files were checked.

## Published operating instructions

The build guide directs participants to the assigned workshop VM and Cursor, with at most two VM users per team. It prohibits ingesting internet videos, provides W&B inference for application reasoning, and points to the workshop deployment flow. Re-ingestion takes minutes; coordinate large runs among teammates. Submission instructions are linked at https://tokensand.com/vastnyc, which could not be retrieved during this review. These are documented operating instructions; a separate complete eligibility rubric was not found.

The architecture reference describes a pre-indexed archive, VAST DataEngine/VastDB, Cosmos reasoning/embeddings, and YOLO on CoreWeave GPUs. Use existing segments and your assigned team resources; do not rebuild the pipeline. Pack C lists warehouse footage, but actual availability must be checked in the team index. Descriptive archive results do not establish calibrated real-time safety detection.

The event listing describes teams of up to four, personal-email registration, and demos at 4:30 PM. It identifies the sponsor stack; its SpaceXAI sponsor link points to Cursor. It does not establish a separate SpaceXAI API requirement.

## Current gaps and proposed fixes

| Component | Current evidence | Proposed fix |
|---|---|---|
| VAST | No API calls or index | Retrieve actual segments and metadata through a server-side adapter |
| NVIDIA | No actual model outputs | Render actual Cosmos descriptions and relevant YOLO detections from the event pipeline |
| CoreWeave | No hosted GPU use | Use the provided pipeline backed by its GPU services; no separate self-hosted GPU setup needed |
| W&B | Local keyword matching | Run structured rule compilation using event-provided inference |
| Cursor | This implementation was built in Codex | Use the documented workshop toolchain for integration; verify if exclusive use is required |
| Footage | Independently downloaded factory clips | Keep offline; use the provided corpus for the event path unless an exception is explicitly approved |
| Deployment | Local Python server | Implement and verify the workshop app deployment |
| Evidence | Authored intervals | Replace submission-path events with real retrieved/inferred evidence |

## Unknowns that require organizer clarification

- Are existing UI scaffolds/prebuilt modules eligible, and what disclosure is expected?
- Must every named sponsor be used, or is the supplied integrated stack sufficient?
- Is Claude Code alongside Cursor permitted? No explicit universal ban on other coding assistants was found.
- Can the independently sourced factory dataset be approved as an exception?
- What are the exact submission deadline, demo length, required artifacts, and weighted judging criteria?

No invented answers should be added to the handoff. Team registration, assigned credentials, and account setup have not been verified. An inability to read the submission portal means this review cannot certify every constraint.

## Product plan

Preserve the existing offline demo. Build an explicitly separate workshop path around one narrow safety-review use case and real evidence. Avoid expanding to PPE, fire, theft, RL, and multiple industries before the sponsor-backed path works.
