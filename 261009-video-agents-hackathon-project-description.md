# Video Compliance Agent

OSHA, ISO, and cGMP violation detection with vision-language agents.
VAST Builders Challenge: Video Agents, 2026-10-09.

## 1. Purpose

This app finds safety and quality violations in video.
It shows the evidence for each violation.
It gives the applicable rule for each violation.
It writes a draft corrective action for each violation.

## 2. Problem

Inspectors cannot watch all camera video.
Audits occur at long intervals.
Violations between audits are not recorded.
Manual review is slow and expensive.

## 3. Solution

The app reads video from site cameras.
A vision-language model describes each video segment.
An agent compares each description with a set of rules.
The app shows each finding with a frame, a caption, and a clause.
A person accepts or rejects each finding.

## 4. Applicable standards

| Pack | Standard | Examples |
|---|---|---|
| OSHA | 29 CFR 1910 | PPE (1910.132, .133), exits (1910.37), hazard labels (1910.1200), surfaces (1910.23) |
| ISO | ISO 45001, ISO 14644 | Workplace safety, cleanroom control |
| cGMP | 21 CFR 211 | Personnel and gowning (211.28) |

## 5. How it works

1. The user selects a rule pack.
2. The app changes the rule pack into an ingestion prompt.
3. The pipeline divides the video into segments.
4. Cosmos Reason describes each segment. It uses the ingestion prompt.
5. Cosmos Embed makes a vector for each description.
6. YOLO detects and tracks objects in each segment.
7. The agent searches the index for each rule.
8. The LLM compares each result with the clause text.
9. The app records a finding when the evidence agrees with the rule.
10. The user accepts or rejects the finding.
11. The LLM writes a draft CAPA for each accepted finding.

### Important

The model records only the items that the ingestion prompt asks about.
If the prompt does not ask about an item, you cannot search for that item.
Thus, each rule must have a matching question in the prompt.

## 6. User interface

### 6.1 Inspect view

- Video player on the left. YOLO boxes show on the video.
- Timeline under the video. Colored marks show findings by severity.
- Findings list on the right. New findings appear at the top.

### 6.2 Finding card

- Severity: critical, major, or minor.
- Clause reference, for example 29 CFR 1910.132(a).
- Frame and timestamp.
- Model description (the evidence).
- Confidence.
- Buttons: Accept, Reject, Draft CAPA.

### 6.3 Rule pack panel

- The user writes a rule in plain language.
- The panel shows the ingestion prompt that the app makes from the rule.
- The Re-ingest button sends the video through the pipeline again.

### 6.4 Site overview

- Grid of cameras. Each camera has a status indicator.
- Totals: open findings, findings by clause, time since last critical finding.

### 6.5 Report

- Export of accepted findings with frames, clauses, and CAPA drafts.
- Format is similar to an audit report or FDA Form 483.

## 7. Data

The team records its own video.
Each scene has two versions: one with a violation and one without a violation.
The version without a violation is the negative control.
Negative controls show that the detector does not give false findings.

Do not use video from the internet.
The challenge rules do not permit it.

| Scene | Violation | Standard |
|---|---|---|
| Chemical handling | No gloves or no goggles | 29 CFR 1910.132, .133 |
| Exit or extinguisher | Boxes block access | 29 CFR 1910.37 |
| Container on bench | Container is open and has no label | 29 CFR 1910.1200 |
| Ladder or cart | Unsafe use | 29 CFR 1910.23 |
| Gowning area | Gowning step not done, door held open | 21 CFR 211.28, ISO 14644 |

## 8. Technology

| Layer | Component |
|---|---|
| Storage and index | VAST S3, DataEngine, DataBase |
| GPU | CoreWeave |
| Video description | Cosmos Reason |
| Embeddings | Cosmos Embed |
| Object detection | YOLO |
| App logic | Weights & Biases serverless inference |
| Build | Cursor agent with challenge skills |
| UI | shadcn/ui, Tremor, Vidstack, Sonner, Lucide |

## 9. Demo procedure

1. Show the site overview.
2. Select the OSHA rule pack.
3. Show the ingestion prompt that the app made.
4. Play a clip with a violation. Show the finding card.
5. Play the matching clip without a violation. Show that there is no finding.
6. Accept the finding. Show the CAPA draft.
7. Export the report.

## 10. Limits

- The app does not replace a qualified inspector.
- A finding is a candidate. A person must accept it.
- Detection quality depends on camera angle, light, and resolution.
- Some violations are not visible. Examples: documents and training records.

## 11. Next steps

- Add more rule packs: ISO 9001, EU GMP Annex 1.
- Connect findings to inventory and regulatory documents (cheminventory.co).
- Collect accepted and rejected findings as training data.
- Send alerts to the site manager for critical findings.
