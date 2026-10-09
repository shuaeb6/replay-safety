/**
 * Playback-time event evaluator.
 * Demo mode uses authored illustrative intervals. Cached/live adapters plug in later
 * via the same createEvidenceEvent contract — do not fabricate detections here.
 */

import { compatible } from './catalog.js';
import { SOURCE_MODES, createEvidenceEvent, validateRule } from './schema.js';
import { modules } from './catalog.js';

/**
 * @param {object} camera
 * @param {object|null} rule
 * @param {number} time current playback time (seconds)
 * @param {boolean} [reference=false] reference clips never emit demo events
 * @returns {object|null} evidence event or null
 */
export function evaluate(camera, rule, time, reference = false) {
  if (!camera || reference) return null;

  const checked = validateRule(rule, { modules });
  if (!checked.ok) return null;
  if (!compatible(camera, checked.rule)) return null;

  const authored = camera.event;
  if (!authored || !Number.isFinite(authored.start) || !Number.isFinite(authored.end)) {
    return null;
  }

  const { threshold, module: moduleId } = checked.rule;
  const dwell = authored.end - authored.start;
  if (dwell < threshold) return null;

  const trigger = authored.start + threshold;
  if (time < trigger || time > authored.end) return null;

  return createEvidenceEvent({
    title: authored.title,
    detail: authored.detail,
    start: authored.start,
    end: authored.end,
    trigger,
    module: moduleId,
    sourceMode: SOURCE_MODES.DEMO,
    region: null,
    boxes: null,
    segmentId: null,
  });
}

/**
 * Stable evidence key for dedupe in the UI (one event per camera+threshold in demo).
 */
export function evidenceKey(cameraId, rule) {
  if (!cameraId || !rule) return null;
  return `${cameraId}:${rule.module}:${rule.threshold}`;
}
