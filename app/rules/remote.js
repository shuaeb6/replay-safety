/**
 * Bridge: workshop W&B /api/compile ↔ Track B rule shape.
 * Workshop modules stay allowlisted in live/catalog.json; we only map ones
 * that the offline Replay demo cameras can attach.
 */

import { createRule } from './schema.js';
import { modules } from './catalog.js';

/** Workshop module id → offline demo module + which param becomes threshold. */
export const WORKSHOP_TO_DEMO = Object.freeze({
  zone_entry: Object.freeze({ module: 'zone', param: 'dwell_seconds' }),
  near_forklift: Object.freeze({ module: 'load', param: null }),
  lingering: Object.freeze({ module: null, param: 'dwell_seconds' }),
  crowding: Object.freeze({ module: null, param: 'min_seconds' }),
});

/**
 * Turn a workshop /api/compile JSON body into a Replay suggestion or a rich error.
 * @returns {object} createRule-compatible rule, or { error }, or { workshop: true, ... }
 */
export function normalizeWorkshopCompile(payload, text = '') {
  if (!payload || typeof payload !== 'object') {
    return { error: 'The compiler returned an empty response.' };
  }
  if (payload.error) {
    return { error: String(payload.error) };
  }

  const workshopModules = Array.isArray(payload.modules) ? payload.modules : [];
  const unsupported = Array.isArray(payload.unsupported) ? payload.unsupported : [];
  const problems = Array.isArray(payload.problems) ? payload.problems : [];

  if (!workshopModules.length) {
    const topics = unsupported.map((u) => u.topic || u).filter(Boolean);
    if (topics.length) {
      return {
        error: `Not supported here yet: ${topics.join('; ')}.`,
      };
    }
    return {
      error:
        payload.clarification ||
        'No module in the library matches this requirement. Try a walkway, tall-load, or panel rule — or open the live archive board.',
    };
  }

  for (const item of workshopModules) {
    const map = WORKSHOP_TO_DEMO[item.id];
    if (!map || !map.module || !modules[map.module]) continue;
    const demo = modules[map.module];
    let threshold = demo.defaultThreshold;
    if (map.param && item.params && Number.isFinite(Number(item.params[map.param]))) {
      threshold = Number(item.params[map.param]);
    }
    return createRule({
      module: map.module,
      threshold,
      text: String(text || '').trim(),
      source: 'wandb',
    });
  }

  // Workshop matched real modules the offline demo cameras cannot run.
  const names = workshopModules.map((m) => m.id).join(', ');
  return {
    error: `Compiled workshop module(s) (${names}) — attach them on the live archive board at /live/. Offline Replay only demos walkway, tall-load, and panel clips.`,
    workshop: {
      modules: workshopModules,
      unsupported,
      problems,
      model: payload.model,
      ms: payload.ms,
    },
  };
}

/**
 * POST text to a workshop-compatible /api/compile endpoint.
 * @param {string} text
 * @param {{ url?: string }} [options]
 */
export async function compileRemote(text, options = {}) {
  const url = options.url || '/api/compile';
  const trimmed = String(text ?? '').trim();
  if (!trimmed) {
    return { error: 'Describe what you want to watch, or choose an example below.' };
  }
  if (trimmed.length > 400) {
    return { error: 'Keep the requirement to 400 characters or fewer.' };
  }

  let response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: trimmed }),
    });
  } catch {
    return { error: 'Compiler unreachable. Is the server running with W&B configured?' };
  }

  let payload;
  try {
    payload = await response.json();
  } catch {
    return { error: 'Compiler returned a non-JSON response.' };
  }

  if (!response.ok) {
    return { error: payload.error || `Compiler failed (${response.status}).` };
  }

  return normalizeWorkshopCompile(payload, trimmed);
}
