import test from 'node:test';
import assert from 'node:assert/strict';
import {normaliseDetections, boxesAt, track, pointInPolygon, computeEvents, activeEvents, trackBoxAt} from '../live/engine.js';

// One person walking right at constant speed, 10 fps, 3 s, in a 1000x500 frame.
const walker = {w: 1000, h: 500, frames: Array.from({length: 30}, (_, i) => [i / 10, [['person', 0.9, 100 + i * 20, 100, 160 + i * 20, 300]]])};
const lane = [[0.5, 0.5], [1, 0.5], [1, 0.7], [0.5, 0.7]]; // right half, around foot height (300/500 = 0.6)

test('normalises sidecar boxes and applies the segment offset', () => {
  const f = normaliseDetections(walker, 5);
  assert.equal(f[0].t, 5);
  assert.deepEqual(f[0].boxes[0].box, [0.1, 0.2, 0.16, 0.6]);
  assert.equal(boxesAt(f, 5.05).length, 1);
  assert.equal(boxesAt(f, 4.9).length, 0);
});

test('tracker keeps one id for one moving person', () => {
  assert.equal(track(normaliseDetections(walker)).length, 1);
});

test('point in polygon', () => {
  assert.ok(pointInPolygon([0.6, 0.6], lane));
  assert.ok(!pointInPolygon([0.2, 0.6], lane));
});

test('zone event triggers only after the dwell threshold and threshold can suppress it', () => {
  const frames = normaliseDetections(walker);
  // Foot x = (130 + 20i)/1000 >= 0.5 from i = 19 (t = 1.9) to t = 2.9: one second inside.
  const [e] = computeEvents(frames, [{id: 'zone_entry', kind: 'zone', params: {dwell_seconds: 0.5}}], lane);
  assert.equal(e.module, 'zone_entry');
  assert.ok(Math.abs(e.start - 1.9) < 1e-9 && Math.abs(e.trigger - 2.4) < 1e-9);
  assert.equal(computeEvents(frames, [{id: 'zone_entry', kind: 'zone', params: {dwell_seconds: 2}}], lane).length, 0);
  assert.equal(computeEvents(frames, [{id: 'zone_entry', kind: 'zone', params: {dwell_seconds: 0.5}}], null).length, 0);
  assert.equal(activeEvents([e], 2.0).length, 0);
  assert.equal(activeEvents([e], 2.5).length, 1);
});

test('lingering needs a stationary person; a walker never lingers', () => {
  const still = {w: 1000, h: 500, frames: Array.from({length: 40}, (_, i) => [i / 10, [['person', 0.9, 400 + (i % 2), 100, 460, 300]]])};
  const rule = [{id: 'lingering', kind: 'dwell', params: {dwell_seconds: 2}}];
  const [e] = computeEvents(normaliseDetections(still), rule);
  assert.ok(e && e.trigger === 2);
  assert.equal(computeEvents(normaliseDetections(walker), rule).length, 0);
});

test('crowding counts people per frame', () => {
  const two = {w: 100, h: 100, frames: Array.from({length: 20}, (_, i) => [i / 10, [['person', 0.9, 0, 0, 10, 10], ['person', 0.8, 50, 50, 60, 60], ['car', 0.9, 20, 20, 40, 40]]])};
  const frames = normaliseDetections(two);
  assert.equal(computeEvents(frames, [{id: 'crowding', kind: 'headcount', params: {max_people: 1, min_seconds: 1}}]).length, 1);
  assert.equal(computeEvents(frames, [{id: 'crowding', kind: 'headcount', params: {max_people: 2, min_seconds: 1}}]).length, 0);
});

test('trackBoxAt returns the tracked box near a time', () => {
  const frames = normaliseDetections(walker);
  const tracks = track(frames);
  assert.deepEqual(trackBoxAt(tracks, tracks[0].id, 0.05), frames[0].boxes[0].box);
  assert.equal(trackBoxAt(tracks, 99, 1), null);
});
