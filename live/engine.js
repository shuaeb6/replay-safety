// Rule engine for workshop mode. Runs on real YOLO11 person boxes returned by VSS.
// Frames: [{t, boxes:[{label, conf, box:[x1,y1,x2,y2]}]}] with t in feed seconds and
// boxes normalised to 0..1. Events never come from authored intervals here.

const GAP = 0.25; // seconds of missed detections tolerated inside one interval

export function normaliseDetections(raw, offset = 0) {
  // Server-compacted sidecar: {w, h, frames: [[t, [[label, conf, x1, y1, x2, y2], ...]], ...]}
  const w = raw.w || 1, h = raw.h || 1;
  return (raw.frames || []).map(([t, dets]) => ({
    t: t + offset,
    boxes: dets.map(([label, conf, x1, y1, x2, y2]) => ({label, conf, box: [x1 / w, y1 / h, x2 / w, y2 / h]}))
  }));
}

export function boxesAt(frames, t) {
  let lo = 0, hi = frames.length - 1, best = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (frames[mid].t <= t + 1e-6) { best = mid; lo = mid + 1; } else hi = mid - 1;
  }
  if (best < 0 || t - frames[best].t > 0.2) return [];
  return frames[best].boxes;
}

function iou(a, b) {
  const x1 = Math.max(a[0], b[0]), y1 = Math.max(a[1], b[1]), x2 = Math.min(a[2], b[2]), y2 = Math.min(a[3], b[3]);
  const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  const union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter;
  return union > 0 ? inter / union : 0;
}

// Greedy IoU tracker: enough to keep one id per person across consecutive frames.
export function track(frames, label = 'person') {
  const tracks = [];
  let next = 1;
  for (const f of frames) {
    const dets = f.boxes.filter(b => b.label === label);
    const live = tracks.filter(tr => f.t - tr.points.at(-1).t <= 0.5);
    const pairs = [];
    dets.forEach((d, di) => live.forEach((tr, ti) => {
      const s = iou(d.box, tr.points.at(-1).box);
      if (s > 0.2) pairs.push([s, di, ti]);
    }));
    pairs.sort((a, b) => b[0] - a[0]);
    const usedD = new Set(), usedT = new Set();
    for (const [, di, ti] of pairs) {
      if (usedD.has(di) || usedT.has(ti)) continue;
      usedD.add(di); usedT.add(ti);
      live[ti].points.push({t: f.t, box: dets[di].box});
    }
    dets.forEach((d, di) => { if (!usedD.has(di)) tracks.push({id: next++, points: [{t: f.t, box: d.box}]}); });
  }
  return tracks;
}

export function pointInPolygon([x, y], poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

const foot = b => [(b[0] + b[2]) / 2, b[3]];
const centre = b => [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];

// Turn per-sample booleans into intervals, tolerating short detection gaps.
function intervals(samples) {
  const out = [];
  let cur = null;
  for (const {t, on} of samples) {
    if (on) {
      if (cur && t - cur.end <= GAP) cur.end = t;
      else { if (cur) out.push(cur); cur = {start: t, end: t}; }
    }
  }
  if (cur) out.push(cur);
  return out;
}

function zoneEvents(tracks, params, zone) {
  if (!zone || zone.length < 3) return [];
  const out = [];
  for (const tr of tracks) {
    for (const iv of intervals(tr.points.map(p => ({t: p.t, on: pointInPolygon(foot(p.box), zone)})))) {
      if (iv.end - iv.start >= params.dwell_seconds) out.push({...iv, trigger: iv.start + params.dwell_seconds, track: tr.id});
    }
  }
  return out;
}

function dwellEvents(tracks, params, radius = 0.035) {
  const out = [];
  for (const tr of tracks) {
    let anchor = null;
    let start = null;
    const flush = end => {
      if (start !== null && end - start >= params.dwell_seconds) out.push({start, end, trigger: start + params.dwell_seconds, track: tr.id});
    };
    let last = null;
    for (const p of tr.points) {
      const c = centre(p.box);
      if (anchor && Math.hypot(c[0] - anchor[0], c[1] - anchor[1]) <= radius && p.t - last <= GAP) { last = p.t; continue; }
      flush(last);
      anchor = c; start = p.t; last = p.t;
    }
    flush(last);
  }
  return out;
}

function headcountEvents(frames, params) {
  const samples = frames.map(f => ({t: f.t, on: f.boxes.filter(b => b.label === 'person').length > params.max_people}));
  return intervals(samples).filter(iv => iv.end - iv.start >= params.min_seconds)
    .map(iv => ({...iv, trigger: iv.start + params.min_seconds}));
}

// Compute events for every attached computed module on one feed.
export function computeEvents(frames, rules, zone) {
  const tracks = track(frames);
  const events = [];
  for (const rule of rules) {
    let found = [];
    if (rule.kind === 'zone') found = zoneEvents(tracks, rule.params, zone);
    else if (rule.kind === 'dwell') found = dwellEvents(tracks, rule.params);
    else if (rule.kind === 'headcount') found = headcountEvents(frames, rule.params);
    for (const e of found) events.push({...e, module: rule.id, source: 'computed'});
  }
  return events.sort((a, b) => a.trigger - b.trigger);
}

// Boxes worth highlighting at time t: people inside an active event of a computed module.
export function activeEvents(events, t) {
  return events.filter(e => t >= e.trigger && t <= e.end + 0.05);
}

// Box of one tracked person at time t (nearest earlier sample within 0.2 s).
export function trackBoxAt(tracks, id, t) {
  const tr = tracks.find(x => x.id === id);
  if (!tr) return null;
  let best = null;
  for (const p of tr.points) { if (p.t <= t + 1e-6) best = p; else break; }
  return best && t - best.t <= 0.2 ? best.box : null;
}

export {foot, centre};
