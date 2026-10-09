import {normaliseDetections, boxesAt, track, computeEvents, activeEvents, trackBoxAt} from './engine.js';

const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const fmt = (t) => { const s = Math.max(0, t || 0); return `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, '0')}`; };
const secs = (ms) => ms == null ? '' : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
const store = {
  get(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode: zones last for this visit */ } },
};

async function api(path, options) {
  const response = await fetch(path, options);
  let body = {};
  try { body = await response.json(); } catch { /* non-JSON error page */ }
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status}).`);
  return body;
}
const post = (path, body) => api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
const streamUrl = (source) => `api/stream?source=${encodeURIComponent(source)}`;

const ICON = {
  play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4.5v15l13-7.5z"/></svg>',
  pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4h4.5v16H6zM13.5 4H18v16h-4.5z"/></svg>',
};

const S = {
  status: null, catalog: null, camera: '',
  feeds: [], feed: null, seg: 0, playing: true,
  det: new Map(), tracks: new Map(), yolo: false, captionsSeen: false,
  captions: new Map(),
  attached: [],
  zones: Object.fromEntries(Object.entries(store.get('replay-zones', {})).map(([k, v]) => [k, Array.isArray(v) ? {points: v, by: 'manual'} : v])),
  laneBusy: new Set(),
  events: new Map(),
  retrieval: new Map(),
  thumbs: new Map(),
  wipe: 1, wipeOn: false, view: 'before',
  drawing: null,
  lastT: 0,
};

const videos = [$('videoA'), $('videoB')];
let active = 0;
const vid = () => videos[active];
const spare = () => videos[1 - active];

/* ---------------- status, services, notices ---------------- */

let noticeTimer;
function notify(text) {
  $('notice').textContent = text;
  $('notice').hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { $('notice').hidden = true; }, 4200);
}

function setMode() {
  const st = S.status;
  const pill = $('modePill');
  let cls = 'down', text = 'Services not configured';
  if (st?.mode === 'dev-fixture') { cls = 'partial'; text = 'Development fixture'; }
  else if (st?.archive && st?.wandb) { cls = 'live'; text = 'Live services · archive replay'; }
  else if (st?.archive) { cls = 'partial'; text = 'Archive live · W&B not configured'; }
  pill.className = `mode ${cls}`;
  pill.querySelector('span').textContent = text;
}

async function refreshServices() {
  let calls = [];
  try { calls = (await api('api/calls')).calls || []; } catch { /* keep last state */ }
  const last = (fn) => [...calls].reverse().find(fn);
  const vss = last((c) => c.service === 'VAST VSS' && c.ok);
  const vssSearch = last((c) => c.service === 'VAST VSS' && c.ok && c.op === '/search');
  const wb = last((c) => c.service === 'W&B Inference' && c.ok);
  const cosmos = last((c) => c.service === 'Cosmos Reason' && c.ok);
  const fixture = S.status?.mode === 'dev-fixture';
  const items = [
    ['VAST VSS', !fixture && vss, vssSearch ? secs(vssSearch.ms) : vss ? 'archive' : ''],
    ['Cosmos Reason', !fixture && (S.captionsSeen || cosmos), cosmos ? `lane ${secs(cosmos.ms)}` : 'captions'],
    ['YOLO11', !fixture && S.yolo, 'boxes'],
    ['W&B Inference', !fixture && wb, wb ? secs(wb.ms) : ''],
  ];
  $('services').innerHTML = items.map(([name, used, note]) =>
    `<li class="${used ? 'used' : ''}" title="${used ? 'Used in this session' : 'Not used yet in this session'}">${esc(name)}${used && note ? ` <small>${esc(note)}</small>` : ''}</li>`).join('');
}

/* ---------------- module library + running layers ---------------- */

const moduleSpec = (id) => S.catalog.modules.find((m) => m.id === id);
const colorOf = (id) => (moduleSpec(id) || S.catalog.baseline.find((b) => b.id === id) || {}).color || '#fff';

function renderLayers(newIds = []) {
  const n = S.catalog.baseline.length + S.attached.length;
  const count = $('runningCount');
  if (count.textContent !== String(n)) {
    count.textContent = String(n);
    count.classList.remove('bump'); void count.offsetWidth; count.classList.add('bump');
    setTimeout(() => count.classList.remove('bump'), 400);
  }
  const all = [...S.catalog.baseline.map((b) => ({...b})), ...S.attached.map((a) => moduleSpec(a.id))];
  $('layerList').innerHTML = all.map((m) => `<li class="${newIds.includes(m.id) ? 'new' : ''}" style="--c:${m.color}"><i></i>${esc(m.name)}</li>`).join('');
  const attachedIds = S.attached.map((a) => a.id);
  $('library').innerHTML = [
    ...S.catalog.baseline.map((b) => `<li class="on" style="--c:${b.color}"><i></i><span><b>${esc(b.name)}</b><br>${esc(b.source)}</span><span class="state">running</span></li>`),
    ...S.catalog.modules.map((m) => `<li class="${attachedIds.includes(m.id) ? 'on' : ''}" style="--c:${m.color}"><i></i><span><b>${esc(m.name)}</b><br>${esc(m.summary)}</span>${attachedIds.includes(m.id)
      ? `<span><span class="state">attached</span><br><button type="button" data-remove="${m.id}">Remove</button></span>` : '<span class="state">available</span>'}</li>`),
  ].join('');
  document.querySelectorAll('[data-remove]').forEach((b) => { b.onclick = () => detach(b.dataset.remove); });
  $('beforeLabel').textContent = `Before · ${S.catalog.baseline.length} modules`;
  $('beforeCount').textContent = String(S.catalog.baseline.length);
  $('afterCount').textContent = String(n);
  $('viewCompare').disabled = $('viewAfter').disabled = !S.attached.length;
  $('afterLabel').textContent = `After · ${n} modules`;
  $('laneButton').hidden = !S.attached.some((a) => a.id === 'zone_entry');
}

/* ---------------- feeds, wall, detections ---------------- */

async function loadDetections(feed) {
  if (S.det.has(feed.id)) return;
  S.det.set(feed.id, []);
  try {
    const parts = await Promise.all(feed.segments.map((seg) => api(`api/detections?source=${encodeURIComponent(seg.source)}`)
      .then((d) => { if ((d.source || '').startsWith('yolo') && d.frames?.length) S.yolo = true; return normaliseDetections(d, seg.start); })
      .catch(() => [])));
    const frames = parts.flat().sort((a, b) => a.t - b.t);
    S.det.set(feed.id, frames);
    S.tracks.set(feed.id, track(frames));
    recompute(feed);
  } catch { S.det.set(feed.id, []); }
}

function renderWall() {
  const shown = S.feeds.slice(0, 4);
  $('wall').innerHTML = shown.map((f, i) => `
    <button class="tile ${S.feed?.id === f.id ? 'selected' : ''}" type="button" data-feed="${i}" aria-pressed="${S.feed?.id === f.id}" aria-label="${esc(f.name)} ${esc(f.subtitle)}">
      <video muted loop playsinline autoplay preload="auto" src="${streamUrl(f.segments[0].source)}"></video>
      <canvas></canvas>
      <span class="rec">REPLAY</span>
      ${flagCount(f) ? `<span class="flag">${flagCount(f)} flagged</span>` : ''}
      <span class="tile-meta"><strong>${esc(f.name)}</strong><small>${esc(f.subtitle)}</small></span>
    </button>`).join('') || '<div class="empty">No indexed feeds were returned for this camera.</div>';
  document.querySelectorAll('[data-feed]').forEach((b) => { b.onclick = () => selectFeed(S.feeds[Number(b.dataset.feed)]); });
}

function flagCount(feed) {
  if (!S.attached.length) return 0;
  const computed = (S.events.get(feed.id) || []).length;
  const found = [...S.retrieval.values()].flat().filter((m) => m.feed.id === feed.id).length;
  return computed + found;
}

/* ---------------- playback (segment double-buffering) ---------------- */

function prepare(video, seg) {
  if (video.dataset.src !== seg.source) {
    video.dataset.src = seg.source;
    video.src = streamUrl(seg.source);
    video.load();
  }
}

function playSeg(index, offset = 0) {
  const feed = S.feed;
  if (!feed) return;
  S.seg = index;
  const seg = feed.segments[index];
  if (spare().dataset.src === seg.source) { active = 1 - active; }
  const v = vid();
  prepare(v, seg);
  v.hidden = false;
  spare().hidden = true;
  spare().pause();
  const start = () => {
    v.currentTime = Math.min(offset, Math.max(0, (v.duration || 5) - 0.05));
    if (S.playing) v.play().catch(() => {});
  };
  if (v.readyState >= 1) start(); else v.addEventListener('loadedmetadata', start, {once: true});
  const next = feed.segments[(index + 1) % feed.segments.length];
  if (next !== seg) prepare(spare(), next);
  loadCaption(seg);
}

videos.forEach((v) => {
  v.addEventListener('ended', () => {
    if (v !== vid() || !S.feed) return;
    playSeg((S.seg + 1) % S.feed.segments.length, 0);
  });
  v.addEventListener('error', () => {
    if (v === vid() && v.dataset.src) {
      $('stageEmpty').hidden = false;
      $('emptyTitle').textContent = 'This clip could not be played';
      $('emptyText').textContent = 'The archive stream did not return video. Check the server log, then choose another camera.';
    }
  });
  v.addEventListener('playing', () => { if (v === vid()) $('stageEmpty').hidden = true; });
});

const feedTime = () => (S.feed ? S.feed.segments[S.seg].start + (vid().currentTime || 0) : 0);

function seekFeed(t) {
  const feed = S.feed;
  if (!feed) return;
  const idx = Math.max(0, feed.segments.findIndex((s) => t < s.end - 0.01));
  const i = idx === -1 ? feed.segments.length - 1 : idx;
  if (i === S.seg && vid().dataset.src === feed.segments[i].source) vid().currentTime = Math.max(0, t - feed.segments[i].start);
  else playSeg(i, Math.max(0, t - feed.segments[i].start));
}

function setPlaying(on) {
  S.playing = on;
  $('playButton').innerHTML = on ? ICON.pause : ICON.play;
  $('playButton').setAttribute('aria-label', on ? 'Pause' : 'Play');
  if (on) vid().play().catch(() => {}); else vid().pause();
}

async function selectFeed(feed, at = 0) {
  if (!feed) return;
  if (!S.feeds.includes(feed)) S.feeds.push(feed);
  S.feed = feed;
  videos.forEach((v) => { v.pause(); });
  S.lastT = at;
  playSeg(0, 0);
  if (at) seekFeed(at);
  $('feedTag').textContent = `${feed.name}${feed.subtitle ? ` · ${feed.subtitle}` : ''}`;
  $('sourceTag').textContent = feed.synthetic ? 'Indexed replay · synthetic footage' : 'Indexed replay';
  document.querySelectorAll('.tile').forEach((t) => {
    const on = S.feeds[Number(t.dataset.feed)]?.id === feed.id;
    t.classList.toggle('selected', on);
    t.setAttribute('aria-pressed', String(on));
  });
  await loadDetections(feed);
  renderLanes();
  if (S.attached.some((a) => a.id === 'zone_entry') && !S.zones[feed.id]) proposeLane(feed, vid());
}

async function loadCaption(seg) {
  if (seg.caption) { S.captions.set(seg.source, seg.caption); S.captionsSeen = true; return; }
  if (S.captions.has(seg.source)) return;
  S.captions.set(seg.source, '');
  try {
    const row = await api(`api/segment?source=${encodeURIComponent(seg.source)}`);
    S.captions.set(seg.source, row.caption || '');
    if (row.caption) S.captionsSeen = true;
  } catch { /* caption is optional */ }
}

/* ---------------- rules ---------------- */

function recompute(feed) {
  const frames = S.det.get(feed.id) || [];
  const rules = S.attached.map((a) => ({...a, kind: moduleSpec(a.id).kind})).filter((r) => r.kind !== 'retrieval');
  S.events.set(feed.id, rules.length ? computeEvents(frames, rules, S.zones[feed.id]?.points) : []);
}

function recomputeAll() {
  S.feeds.forEach(recompute);
  renderLanes();
  renderMoments();
  renderWall();
}

function detach(id) {
  S.attached = S.attached.filter((a) => a.id !== id);
  S.retrieval.delete(id);
  renderLayers();
  setView(S.attached.length ? S.view : 'before');
  recomputeAll();
  notify(`${moduleSpec(id).name} removed`);
}

/* ---------------- lanes + moments ---------------- */

function renderLanes() {
  const feed = S.feed;
  if (!feed) { $('laneRows').innerHTML = ''; return; }
  const D = feed.duration || 1;
  const pct = (t) => `${Math.max(0, Math.min(100, (t / D) * 100))}%`;
  const frames = S.det.get(feed.id) || [];
  const presence = [];
  let cur = null;
  for (const f of frames) {
    const on = f.boxes.some((b) => b.label === 'person');
    if (on) { if (cur && f.t - cur.e <= 0.25) cur.e = f.t; else { cur = {s: f.t, e: f.t}; presence.push(cur); } }
  }
  const rows = [
    `<div class="lane" style="--c:${colorOf('people')}"><span class="lane-name"><i></i>People</span><span class="lane-track">${presence.map((p) => `<b class="soft" style="left:${pct(p.s)};width:${pct(p.e - p.s + 0.04)}"></b>`).join('')}</span></div>`,
    `<div class="lane" style="--c:${colorOf('captions')}"><span class="lane-name"><i></i>Scene captions</span><span class="lane-track">${feed.segments.map((s, i) => `<b class="soft" style="left:calc(${pct(s.start)} + 1px);width:calc(${pct(s.end - s.start)} - 2px);opacity:${i % 2 ? .22 : .32}"></b>`).join('')}</span></div>`,
  ];
  for (const a of S.attached) {
    const m = moduleSpec(a.id);
    let marks = '';
    if (m.kind === 'retrieval') {
      marks = (S.retrieval.get(a.id) || []).filter((x) => x.feed.id === feed.id)
        .map((x) => `<button type="button" data-seek="${x.start}" title="VAST match ${x.score}" style="left:${pct(x.start)};width:${pct(x.end - x.start)}"></button>`).join('');
    } else {
      marks = (S.events.get(feed.id) || []).filter((e) => e.module === a.id)
        .map((e) => `<button type="button" data-seek="${e.trigger}" title="${esc(m.name)} at ${fmt(e.trigger)}" style="left:${pct(e.start)};width:${pct(e.end - e.start)}"></button>`).join('');
      if (m.kind === 'zone' && !S.zones[feed.id]) marks = `<small style="padding-left:6px;line-height:12px;font-size:10.5px">${S.laneBusy.has(feed.id) ? 'Cosmos Reason is finding the lane…' : 'No lane on this camera yet'}</small>`;
    }
    rows.push(`<div class="lane" style="--c:${m.color}"><span class="lane-name"><i></i>${esc(m.name)}</span><span class="lane-track">${marks}</span></div>`);
  }
  $('laneRows').innerHTML = rows.join('');
  $('laneRows').querySelectorAll('[data-seek]').forEach((b) => { b.onclick = () => seekFeed(Number(b.dataset.seek)); });
}

function allMoments() {
  const out = [];
  for (const feed of S.feeds) {
    for (const e of S.events.get(feed.id) || []) {
      const m = moduleSpec(e.module);
      out.push({key: `${e.module}:${feed.id}:${e.trigger.toFixed(2)}`, module: m, feed, at: e.trigger, start: e.start, end: e.end,
        why: `Person ${m.kind === 'zone' ? 'inside the lane' : m.kind === 'dwell' ? 'stayed in place' : 'count over the limit'} for ${(e.end - e.start).toFixed(1)} s.`,
        basis: 'Computed from YOLO11 person boxes'});
    }
  }
  for (const [id, list] of S.retrieval) {
    const m = moduleSpec(id);
    for (const x of list) {
      out.push({key: `${id}:${x.source}`, module: m, feed: x.feed, at: x.start, start: x.start, end: x.end, source: x.source,
        why: x.caption, basis: `VAST match ${x.score.toFixed(2)} · relevance, not confidence`});
    }
  }
  return out;
}

function renderMoments() {
  const list = allMoments();
  $('momentCount').textContent = String(list.length);
  const cams = new Set(list.map((m) => m.feed.id)).size;
  $('compareNote').textContent = S.attached.length
    ? `Before: people boxed, nothing flagged. After: ${list.length} moment${list.length === 1 ? '' : 's'} across ${cams} camera${cams === 1 ? '' : 's'}, ready for review.`
    : 'Before: people are boxed, nothing is flagged.';
  $('moments').innerHTML = list.length ? list.map((m, i) => `
    <button class="moment" type="button" data-moment="${i}" style="--c:${m.module.color};animation-delay:${Math.min(i, 8) * 60}ms">
      <span class="thumb">${S.thumbs.get(m.key) ? `<img src="${S.thumbs.get(m.key)}" alt="">` : 'Plays to capture a frame'}<span class="stamp">${fmt(m.at)}</span></span>
      <span class="body">
        <span class="mod"><i></i>${esc(m.module.name)}</span>
        <span class="where">${esc(m.feed.name)}${m.feed.subtitle ? ` · ${esc(m.feed.subtitle)}` : ''} · ${fmt(m.start)}–${fmt(m.end)}</span>
        <span class="why">${esc(m.why || '')}</span>
        <span class="basis">${esc(m.basis)}</span>
      </span>
    </button>`).join('')
    : `<div class="empty">${S.attached.length ? 'No moments matched yet. Draw a lane, lower a threshold, or play other cameras.' : 'Describe a rule on the right. Matching moments from the archive appear here with their evidence.'}</div>`;
  document.querySelectorAll('[data-moment]').forEach((b) => {
    b.onclick = () => {
      const m = list[Number(b.dataset.moment)];
      if (S.feed?.id === m.feed.id) seekFeed(Math.max(0, m.at - 0.3));
      else selectFeed(m.feed, Math.max(0, m.at - 0.3));
      setPlaying(true);
      $('stage').scrollIntoView({behavior: 'smooth', block: 'center'});
    };
  });
}

function captureThumb(key) {
  if (S.thumbs.has(key)) return;
  const v = vid();
  if (!v.videoWidth) return;
  try {
    const c = document.createElement('canvas');
    c.width = 384; c.height = 216;
    c.getContext('2d').drawImage(v, 0, 0, c.width, c.height);
    S.thumbs.set(key, c.toDataURL('image/jpeg', 0.75));
    renderMoments();
  } catch { /* cross-origin frames cannot be captured; keep the placeholder */ }
}

/* ---------------- overlay drawing ---------------- */

const canvas = $('overlay');
const ctx = canvas.getContext('2d');

function contentRect(v, cw, ch) {
  const vw = v.videoWidth || 16, vh = v.videoHeight || 9;
  const s = Math.min(cw / vw, ch / vh);
  return {x: (cw - vw * s) / 2, y: (ch - vh * s) / 2, w: vw * s, h: vh * s};
}

function tagLabel(g, text, x, y, fill, ink) {
  g.font = '600 12px "DM Sans", system-ui, sans-serif';
  const w = g.measureText(text).width + 12;
  g.fillStyle = fill;
  g.beginPath(); g.roundRect(x, Math.max(0, y - 20), w, 18, 4); g.fill();
  g.fillStyle = ink;
  g.fillText(text, x + 6, Math.max(13, y - 7));
}

function drawBox(g, r, b, color, width, label) {
  const [x1, y1, x2, y2] = b;
  const x = r.x + x1 * r.w, y = r.y + y1 * r.h, w = (x2 - x1) * r.w, h = (y2 - y1) * r.h;
  g.strokeStyle = color; g.lineWidth = width;
  g.beginPath(); g.roundRect(x, y, w, h, 3); g.stroke();
  if (label) tagLabel(g, label, x, y, color, '#0d1512');
}

function drawZone(g, r, poly, color, closed = true) {
  if (!poly?.length) return;
  g.beginPath();
  poly.forEach(([px, py], i) => (i ? g.lineTo : g.moveTo).call(g, r.x + px * r.w, r.y + py * r.h));
  if (closed) g.closePath();
  g.fillStyle = color + '2e'; if (closed) g.fill();
  g.setLineDash([9, 6]); g.strokeStyle = color; g.lineWidth = 2.5; g.stroke(); g.setLineDash([]);
  poly.forEach(([px, py]) => { g.fillStyle = color; g.beginPath(); g.arc(r.x + px * r.w, r.y + py * r.h, 4.5, 0, 7); g.fill(); });
}

// Chrome may pause muted videos that scroll off screen. Resume anything that should be playing.
let lastNudge = 0;
function keepPlaying(now) {
  if (now - lastNudge < 800) return;
  lastNudge = now;
  const v = vid();
  if (S.feed && S.playing && !S.drawing && v.paused && !v.ended && v.readyState >= 2) v.play().catch(() => {});
  document.querySelectorAll('.tile video').forEach((t) => { if (t.paused && t.readyState >= 2) t.play().catch(() => {}); });
}

function render(now = 0) {
  requestAnimationFrame(render);
  keepPlaying(now);
  const feed = S.feed;
  const dpr = window.devicePixelRatio || 1;
  const cw = canvas.clientWidth, ch = canvas.clientHeight;
  if (canvas.width !== Math.round(cw * dpr) || canvas.height !== Math.round(ch * dpr)) { canvas.width = Math.round(cw * dpr); canvas.height = Math.round(ch * dpr); }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cw, ch);
  drawTiles();
  if (!feed) return;
  const t = feedTime();
  const r = contentRect(vid(), cw, ch);
  const boxes = boxesAt(S.det.get(feed.id) || [], t).filter((b) => b.label === 'person');
  const divider = S.wipeOn ? r.x + r.w * S.wipe : cw + 1;
  const events = S.wipeOn ? activeEvents(S.events.get(feed.id) || [], t) : [];
  const seg = feed.segments[S.seg];
  const retrievalHit = S.wipeOn ? [...S.retrieval.entries()].map(([id, list]) => ({id, hit: list.find((x) => x.source === seg?.source)})).find((x) => x.hit) : null;

  // Before: baseline layers only.
  ctx.save(); ctx.beginPath(); ctx.rect(0, 0, divider, ch); ctx.clip();
  boxes.forEach((b) => drawBox(ctx, r, b.box, 'rgba(231,236,233,.85)', 1.6, `person ${b.conf.toFixed(2)}`));
  ctx.restore();

  // After: baseline plus every attached rule.
  if (S.wipeOn) {
    ctx.save(); ctx.beginPath(); ctx.rect(divider, 0, cw - divider, ch); ctx.clip();
    const lane = S.zones[feed.id];
    if (S.attached.some((a) => a.id === 'zone_entry') && lane) {
      drawZone(ctx, r, lane.points, colorOf('zone_entry'));
      const [lx, ly] = lane.points.reduce(([ax, ay], [px, py]) => (py < ay ? [px, py] : [ax, ay]), [1, 1]);
      tagLabel(ctx, lane.by === 'cosmos' ? 'Lane · proposed by Cosmos Reason' : 'Lane · drawn by you', Math.max(divider, r.x + lx * r.w), r.y + ly * r.h - 4, 'rgba(13,21,18,.8)', colorOf('zone_entry'));
    }
    const hot = new Map();
    const tracks = S.tracks.get(feed.id) || [];
    for (const e of events) { const box = trackBoxAt(tracks, e.track, t); if (box) hot.set(box, e); }
    boxes.forEach((b) => {
      const hitEvent = [...hot.entries()].find(([box]) => box === b.box)?.[1];
      if (hitEvent) {
        const m = moduleSpec(hitEvent.module);
        drawBox(ctx, r, b.box, m.color, 3.2, `${m.name} · ${(t - hitEvent.start).toFixed(1)} s`);
      } else drawBox(ctx, r, b.box, 'rgba(231,236,233,.85)', 1.6, `person ${b.conf.toFixed(2)}`);
    });
    const crowd = events.find((e) => e.module === 'crowding');
    if (crowd) tagLabel(ctx, `Crowding · ${boxes.length} people`, r.x + 12, r.y + r.h - 70, colorOf('crowding'), '#0d1512');
    if (retrievalHit) {
      const color = colorOf(retrievalHit.id);
      ctx.strokeStyle = color; ctx.lineWidth = 4;
      ctx.strokeRect(Math.max(divider, r.x) + 2, r.y + 2, r.x + r.w - Math.max(divider, r.x) - 4, r.h - 4);
    }
    ctx.restore();
  }

  if (S.drawing) drawZone(ctx, r, S.drawing, colorOf('zone_entry'), false);

  // Toast: the newest active rule on the After side.
  const current = events.at(-1);
  const toast = $('toast');
  if (current || retrievalHit) {
    const m = moduleSpec(current ? current.module : retrievalHit.id);
    toast.style.setProperty('--c', m.color);
    $('toastTitle').textContent = m.name;
    $('toastMeta').textContent = current ? `Flagged at ${fmt(current.trigger)} · YOLO11 boxes` : `Caption match ${retrievalHit.hit.score.toFixed(2)} · VAST search`;
    toast.hidden = false;
  } else toast.hidden = true;

  // Capture evidence thumbnails as the replay passes each moment.
  for (const e of S.events.get(feed.id) || []) {
    if (S.lastT < e.trigger && t >= e.trigger) captureThumb(`${e.module}:${feed.id}:${e.trigger.toFixed(2)}`);
  }
  if (retrievalHit && t - seg.start > 1) captureThumb(`${retrievalHit.id}:${retrievalHit.hit.source}`);
  S.lastT = t;

  // Transport, caption, clock.
  const D = feed.duration || 1;
  if (document.activeElement !== $('scrub')) $('scrub').value = String(Math.round((t / D) * 1000));
  $('timeLabel').textContent = `${fmt(t)} / ${fmt(D)}`;
  $('clock').textContent = `SEG ${S.seg + 1}/${feed.segments.length} · ${fmt(t)}`;
  const caption = S.captions.get(seg?.source) || '';
  $('caption').hidden = !caption;
  if (caption && $('captionText').textContent !== caption) $('captionText').textContent = caption;
  const head = `${(t / D) * 100}%`;
  document.querySelectorAll('.lane-track').forEach((track) => {
    let h = track.querySelector('.head');
    if (!h) { h = document.createElement('i'); h.className = 'head'; track.appendChild(h); }
    h.style.left = head;
  });
}

function drawTiles() {
  document.querySelectorAll('.tile').forEach((tile) => {
    const feed = S.feeds[Number(tile.dataset.feed)];
    const v = tile.querySelector('video'), c = tile.querySelector('canvas');
    if (!feed || !v || !c) return;
    const w = c.clientWidth, h = c.clientHeight;
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    const g = c.getContext('2d');
    g.clearRect(0, 0, w, h);
    const vw = v.videoWidth || 16, vh = v.videoHeight || 9;
    const s = Math.max(w / vw, h / vh);
    const r = {x: (w - vw * s) / 2, y: (h - vh * s) / 2, w: vw * s, h: vh * s};
    const t = feed.segments[0].start + (v.currentTime || 0);
    const flagged = S.wipeOn ? activeEvents(S.events.get(feed.id) || [], t) : [];
    boxesAt(S.det.get(feed.id) || [], t).filter((b) => b.label === 'person').forEach((b) => {
      const [x1, y1, x2, y2] = b.box;
      g.strokeStyle = flagged.length ? colorOf(flagged[0].module) : 'rgba(231,236,233,.9)';
      g.lineWidth = flagged.length ? 2.2 : 1.2;
      g.strokeRect(r.x + x1 * r.w, r.y + y1 * r.h, (x2 - x1) * r.w, (y2 - y1) * r.h);
    });
  });
}

/* ---------------- wipe ---------------- */

function setWipe(x) {
  S.wipe = Math.max(0, Math.min(1, x));
  const stage = $('stage');
  const r = contentRect(vid(), stage.clientWidth, stage.clientHeight);
  $('wipe').style.setProperty('--x', `${((r.x + r.w * S.wipe) / stage.clientWidth) * 100}%`);
}

function setView(view) {
  if (!S.catalog) return;
  if (!S.attached.length) view = 'before';
  S.view = view;
  for (const [id, v] of [['viewBefore', 'before'], ['viewCompare', 'compare'], ['viewAfter', 'after']]) $(id).setAttribute('aria-pressed', String(view === v));
  S.wipeOn = view !== 'before';
  $('wipe').hidden = !S.wipeOn;
  $('wipe').classList.toggle('solo', view === 'after');
  if (view === 'after') setWipe(0);
  if (view === 'compare') setWipe(S.wipe > 0.02 && S.wipe < 0.98 ? S.wipe : 0.5);
  const n = S.catalog.baseline.length, m = S.attached.length;
  $('viewNote').innerHTML = !m ? 'Before: people and scene captions only. Attach a rule to compare.'
    : view === 'before' ? `<b>Before</b>: ${n} modules. Nothing is flagged.`
    : view === 'after' ? `<b>After</b>: ${n + m} modules, including your ${m} rule${m === 1 ? '' : 's'}.`
    : `Drag the handle. <b>Left</b>: before (${n} modules). <b>Right</b>: after (${n + m} modules).`;
}

function sweepWipe() {
  setView('compare');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) { setWipe(0.5); return; }
  const from = 1, to = 0.5, start = performance.now();
  const step = (now) => {
    const k = Math.min(1, (now - start) / 1100);
    setWipe(from + (to - from) * (1 - Math.pow(1 - k, 3)));
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

(function bindWipe() {
  const handle = $('wipeHandle');
  const move = (e) => {
    const stage = $('stage').getBoundingClientRect();
    const r = contentRect(vid(), stage.width, stage.height);
    setWipe((e.clientX - stage.left - r.x) / r.w);
  };
  handle.addEventListener('pointerdown', (e) => {
    handle.setPointerCapture(e.pointerId);
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', () => handle.removeEventListener('pointermove', move), {once: true});
  });
  handle.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') { setWipe(S.wipe - 0.05); e.preventDefault(); }
    if (e.key === 'ArrowRight') { setWipe(S.wipe + 0.05); e.preventDefault(); }
  });
  window.addEventListener('resize', () => S.wipeOn && setWipe(S.wipe));
})();

/* ---------------- lane drawing ---------------- */

function startDrawing() {
  if (!S.feed) return;
  S.drawing = [];
  $('stage').classList.add('drawing');
  $('drawHint').hidden = false;
  setPlaying(false);
}

function finishDrawing(save) {
  const pts = S.drawing;
  S.drawing = null;
  $('stage').classList.remove('drawing');
  $('drawHint').hidden = true;
  if (save && pts && pts.length >= 3) {
    S.zones[S.feed.id] = {points: pts, by: 'manual'};
    store.set('replay-zones', Object.fromEntries(Object.entries(S.zones).filter(([, z]) => z.by === 'manual')));
    recompute(S.feed);
    renderLanes(); renderMoments(); renderWall();
    notify(`Lane saved for ${S.feed.name}. Events are computed from the person boxes.`);
  }
  setPlaying(true);
}

canvas.addEventListener('click', (e) => {
  if (!S.drawing) return;
  const rect = canvas.getBoundingClientRect();
  const r = contentRect(vid(), rect.width, rect.height);
  const x = (e.clientX - rect.left - r.x) / r.w, y = (e.clientY - rect.top - r.y) / r.h;
  if (x < 0 || x > 1 || y < 0 || y > 1) return;
  const first = S.drawing[0];
  if (first && S.drawing.length >= 3 && Math.hypot((x - first[0]) * r.w, (y - first[1]) * r.h) < 14) { finishDrawing(true); return; }
  S.drawing.push([+x.toFixed(4), +y.toFixed(4)]);
});
$('drawCancel').onclick = () => finishDrawing(false);
$('drawUndo').onclick = () => S.drawing?.pop();
$('laneButton').onclick = startDrawing;

/* ---------------- automatic lane (Cosmos Reason) ---------------- */

function frameJpeg(video) {
  const c = document.createElement('canvas');
  c.width = 640; c.height = 360;
  c.getContext('2d').drawImage(video, 0, 0, c.width, c.height);
  return c.toDataURL('image/jpeg', 0.82);
}

async function waitForFrame(video, ms = 6000) {
  const end = performance.now() + ms;
  while (video.readyState < 2 && performance.now() < end) await new Promise((r) => setTimeout(r, 150));
  return video.readyState >= 2;
}

function addStep(state, text, note) {
  const steps = $('steps');
  if (!steps) return null;
  steps.insertAdjacentHTML('beforeend', stepHtml(state, text, note));
  return steps.lastElementChild;
}

async function proposeLane(feed, video) {
  if (!feed || S.zones[feed.id] || S.laneBusy.has(feed.id)) return;
  S.laneBusy.add(feed.id);
  renderLanes();
  const li = addStep('run', `Finding the forklift lane on ${feed.name}`, 'Cosmos Reason');
  try {
    if (!(await waitForFrame(video))) throw new Error('The camera frame did not load.');
    const res = await post('api/lane', {image: frameJpeg(video)});
    S.zones[feed.id] = {points: res.polygon, by: 'cosmos', model: res.model, reason: res.reason};
    recompute(feed);
    const replaced = stepHtml('done', `Lane found on ${feed.name}`, `Cosmos · ${secs(res.ms)}`);
    if (li) li.outerHTML = replaced;
  } catch (err) {
    const failed = stepHtml('fail', `${feed.name}: ${err.message}`, 'Cosmos Reason');
    if (li) li.outerHTML = failed;
    if (feed === S.feed && !$('drawSelf')) {
      $('replyBody')?.insertAdjacentHTML('beforeend', '<button type="button" class="attach" id="drawSelf" style="background:transparent;color:var(--forest);border:1px solid var(--forest)">Draw the lane yourself</button>');
      $('drawSelf').onclick = () => { $('drawSelf').remove(); startDrawing(); };
    }
  } finally {
    S.laneBusy.delete(feed.id);
    renderLanes(); renderMoments(); renderWall();
    refreshServices();
  }
}

async function proposeLanes() {
  if (S.feed) await proposeLane(S.feed, vid());
  for (const tile of document.querySelectorAll('.tile')) {
    const feed = S.feeds[Number(tile.dataset.feed)];
    if (feed && feed !== S.feed) await proposeLane(feed, tile.querySelector('video'));
  }
}
window.addEventListener('keydown', (e) => {
  if (S.drawing && e.key === 'Enter') { e.preventDefault(); finishDrawing(true); }
  if (S.drawing && e.key === 'Escape') finishDrawing(false);
  if (e.key === ' ' && !['TEXTAREA', 'INPUT', 'BUTTON'].includes(document.activeElement?.tagName)) { e.preventDefault(); setPlaying(!S.playing); }
});

/* ---------------- assistant thread ---------------- */

function stepHtml(state, text, note = '') {
  return `<li class="${state}"><span class="dot"></span><span>${esc(text)}</span><small>${esc(note)}</small></li>`;
}

async function submit(text) {
  text = text.trim();
  if (!text) { notify('Describe what Replay should watch for.'); return; }
  const thread = $('thread');
  thread.innerHTML = `<div class="bubble">${esc(text)}</div><div class="reply"><ul class="steps" id="steps">${stepHtml('run', 'Reading the requirement', 'W&B Inference')}</ul><div id="replyBody"></div></div>`;
  $('sendButton').disabled = true;
  let result;
  try {
    result = await post('api/compile', {text});
  } catch (err) {
    $('steps').innerHTML = stepHtml('fail', 'Reading the requirement', 'W&B Inference');
    $('replyBody').innerHTML = `<div class="error"><strong>No modules were attached.</strong> ${esc(err.message)} Replay does not guess rules without the model.</div>`;
    $('sendButton').disabled = false;
    return;
  }
  $('sendButton').disabled = false;
  const model = (result.model || '').split('/').pop();
  $('steps').innerHTML = stepHtml('done', 'Read the requirement', `${model} · ${secs(result.ms)}`)
    + stepHtml('done', `Matched ${result.modules.length} module${result.modules.length === 1 ? '' : 's'} from your library`, 'validated');
  const cards = result.modules.map((mod) => {
    const m = moduleSpec(mod.id);
    const inputs = Object.entries(m.params).map(([k, p]) =>
      `<label>${esc(p.label)} <span><input type="number" id="p-${m.id}-${k}" data-mod="${m.id}" data-param="${k}" min="${p.min}" max="${p.max}" step="${p.step}" value="${mod.params[k]}" required> ${esc(p.unit)}</span></label>`).join('');
    return `<div class="mod-card" style="--c:${m.color}"><header><i></i><strong>${esc(m.name)}</strong><span class="kind">${esc(m.kind === 'retrieval' ? 'archive search' : 'computed')}</span></header>
      ${mod.reason ? `<div class="quote">${esc(mod.reason)}</div>` : ''}${inputs}<div class="basis">${esc(m.evidence)}</div></div>`;
  }).join('');
  const unsupported = result.unsupported.map((u) => `<div class="unsupported"><strong>Not available: ${esc(u.topic)}</strong><span>${esc(u.why)}</span></div>`).join('');
  const problems = result.problems?.length ? `<div class="basis" style="font-size:12px;color:var(--muted)">${result.problems.map(esc).join(' ')}</div>` : '';
  const clarify = result.clarification ? `<div class="unsupported"><strong>Question</strong><span>${esc(result.clarification)}</span></div>` : '';
  const none = !result.modules.length ? '<div class="error"><strong>Nothing to attach.</strong> No module in the library matches this requirement.</div>' : '';
  const attach = result.modules.length ? `<button class="attach" type="button" id="attachButton">Attach ${result.modules.length} module${result.modules.length === 1 ? '' : 's'}</button>` : '';
  $('replyBody').innerHTML = `<div class="mods">${cards}</div>${unsupported}${clarify}${none}${problems}${attach}`;
  if (result.modules.length) $('attachButton').onclick = () => attach_(result.modules);
}

async function attach_(mods) {
  const chosen = [];
  for (const mod of mods) {
    const params = {};
    for (const input of document.querySelectorAll(`[data-mod="${mod.id}"]`)) {
      const v = Number(input.value);
      if (!input.checkValidity() || !Number.isFinite(v)) { input.focus(); notify(`Check ${moduleSpec(mod.id).params[input.dataset.param].label.toLowerCase()} for ${moduleSpec(mod.id).name}.`); return; }
      params[input.dataset.param] = v;
    }
    chosen.push({id: mod.id, params});
  }
  const ids = chosen.map((c) => c.id);
  S.attached = [...S.attached.filter((a) => !ids.includes(a.id)), ...chosen];
  $('attachButton').outerHTML = `<div class="attached-note">Attached. ${S.catalog.baseline.length + S.attached.length} modules running.</div>`;
  renderLayers(ids);
  recomputeAll();
  sweepWipe();
  if (ids.includes('zone_entry')) proposeLanes();
  for (const c of chosen.filter((c) => moduleSpec(c.id).kind === 'retrieval')) {
    const m = moduleSpec(c.id);
    $('steps').insertAdjacentHTML('beforeend', stepHtml('run', `Searching the archive for "${m.name.toLowerCase()}"`, 'VAST VSS'));
    const li = $('steps').lastElementChild;
    try {
      const res = await post('api/evidence', {module: c.id, params: c.params, camera_id: S.camera});
      S.retrieval.set(c.id, res.moments);
      li.outerHTML = stepHtml('done', `Found ${res.moments.length} matching moment${res.moments.length === 1 ? '' : 's'}`, `VAST · ${secs(res.ms)}`);
      recomputeAll();
    } catch (err) {
      li.outerHTML = stepHtml('fail', `Archive search failed: ${err.message}`, 'VAST VSS');
    }
  }
  refreshServices();
}

$('ruleForm').addEventListener('submit', (e) => { e.preventDefault(); submit($('requirement').value); });
$('requirement').addEventListener('input', () => { $('charCount').textContent = `${$('requirement').value.length} / 400`; });
$('requirement').addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submit($('requirement').value); } });
document.querySelectorAll('[data-prompt]').forEach((b) => {
  b.onclick = () => {
    const box = $('requirement');
    box.value = b.dataset.prompt;
    $('charCount').textContent = `${box.value.length} / 400`;
    document.querySelectorAll('[data-prompt]').forEach((x) => x.classList.toggle('picked', x === b));
    box.focus();
    box.setSelectionRange(box.value.length, box.value.length);
  };
});
document.querySelectorAll('[data-view]').forEach((b) => { b.onclick = () => setView(b.dataset.view); });$('playButton').onclick = () => setPlaying(!S.playing);
$('scrub').addEventListener('input', (e) => { if (S.feed) seekFeed((Number(e.target.value) / 1000) * S.feed.duration); });
$('aboutButton').onclick = () => $('about').showModal();

/* ---------------- boot ---------------- */

async function boot() {
  setPlaying(true);
  try {
    [S.status, S.catalog] = await Promise.all([api('api/status'), api('catalog.json')]);
  } catch (err) {
    $('emptyTitle').textContent = 'Replay could not reach its server';
    $('emptyText').textContent = err.message;
    return;
  }
  S.camera = S.status.default_camera;
  setMode();
  renderLayers();
  renderMoments();
  $('devBanner').hidden = S.status.mode !== 'dev-fixture';
  if (!S.status.archive) {
    $('emptyTitle').textContent = 'The video archive is not connected';
    $('emptyText').textContent = 'Set VSS_URL, VSS_USERNAME, and VSS_PASSWORD on the server, or run it on the workshop VM where /config holds the team values.';
    $('wallNote').textContent = 'No archive connection';
    refreshServices();
    return;
  }
  $('wall').innerHTML = '<div class="tile skeleton"></div>'.repeat(4);
  try {
    const res = await api(`api/feeds?camera_id=${encodeURIComponent(S.camera)}`);
    S.feeds = res.feeds;
    const first = S.feeds[0];
    $('wallNote').textContent = first
      ? `Showing ${Math.min(4, S.feeds.length)} of ${res.available} indexed videos · ${S.camera}${first.synthetic ? ' · synthetic footage' : ''}`
      : 'No complete indexed videos for this camera yet.';
    if (first?.location) $('siteName').textContent = first.location.replace(/^warehouse(\d+)$/i, 'Warehouse $1');
  } catch (err) {
    $('wall').innerHTML = `<div class="empty">The archive did not return feeds: ${esc(err.message)}</div>`;
    $('emptyTitle').textContent = 'No feeds to replay';
    $('emptyText').textContent = err.message;
    refreshServices();
    return;
  }
  renderWall();
  if (S.feeds.length) {
    $('emptyTitle').textContent = 'Loading the replay…';
    await selectFeed(S.feeds[0]);
    S.feeds.slice(1, 6).forEach(loadDetections);
  }
  refreshServices();
  setInterval(refreshServices, 4000);
}

render();
boot();
