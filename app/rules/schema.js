/** Shared rule/event contracts for UI, keyword compiler, and future adapters. */

export const THRESHOLD_MIN = 0.1;
export const THRESHOLD_MAX = 60;

/** How an evidence event was produced. Never mix these silently. */
export const SOURCE_MODES = Object.freeze({
  DEMO: 'demo',
  CACHED: 'cached',
  LIVE: 'live',
});

export function normalizeThreshold(value, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return n;
}

export function thresholdInRange(value) {
  return Number.isFinite(value) && value >= THRESHOLD_MIN && value <= THRESHOLD_MAX;
}

/**
 * Validate and normalize a rule for attach/persist.
 * @returns {{ ok: true, rule: object } | { ok: false, error: string }}
 */
export function validateRule(rule, { modules } = {}) {
  if (!rule || typeof rule !== 'object') {
    return { ok: false, error: 'Rule is missing.' };
  }
  const moduleId = rule.module;
  if (!moduleId || (modules && !modules[moduleId])) {
    return { ok: false, error: 'Unknown or missing module.' };
  }
  const threshold = normalizeThreshold(rule.threshold, NaN);
  if (!thresholdInRange(threshold)) {
    return {
      ok: false,
      error: `Choose a duration between ${THRESHOLD_MIN} and ${THRESHOLD_MAX} seconds.`,
    };
  }
  return {
    ok: true,
    rule: createRule({
      module: moduleId,
      threshold,
      text: typeof rule.text === 'string' ? rule.text.trim() : '',
      source: rule.source || 'keyword',
    }),
  };
}

export function createRule({ module, threshold, text = '', source = 'keyword' }) {
  return {
    module,
    threshold: Number(threshold),
    text: String(text || '').trim(),
    source,
  };
}

/**
 * Evidence event shape shared by demo evaluator and future inference adapters.
 */
export function createEvidenceEvent({
  title,
  detail,
  start,
  end,
  trigger,
  module,
  sourceMode = SOURCE_MODES.DEMO,
  region = null,
  boxes = null,
  segmentId = null,
}) {
  return {
    title,
    detail,
    start,
    end,
    trigger,
    module,
    sourceMode,
    region,
    boxes,
    segmentId,
  };
}
