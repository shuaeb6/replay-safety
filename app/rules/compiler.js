/**
 * Requirement → structured rule compiler.
 * Keyword mode is the offline default. LLM/W&B adapters must validate against the same allowlist.
 */

import { modules, supportedCapabilitySummary } from './catalog.js';
import {
  THRESHOLD_MAX,
  THRESHOLD_MIN,
  createRule,
  normalizeThreshold,
  thresholdInRange,
  validateRule,
} from './schema.js';

const UNSUPPORTED =
  /helmet|hard.?hat|ppe|vest|glove|fire|smoke|speed|block|obstruct.*(route|exit)|theft|steal/;

const NEGATION =
  /\b(don'?t|do\s+not|never|without|no\s+(?:more\s+)?(?:alerts?|flags?|watching))\b/;

const DURATION =
  /(\d+(?:\.\d+)?)\s*(seconds?|secs?|s)\b/;

/**
 * Compile plain-language text into an allowlisted rule, or return { error }.
 * @param {string} text
 * @param {{ mode?: 'keyword' }} [options]
 */
export function compileRequirement(text, options = {}) {
  const mode = options.mode || 'keyword';
  if (mode !== 'keyword') {
    return {
      error:
        'Only the local keyword compiler is available in this build. Workshop LLM compilation is not wired yet.',
    };
  }
  return compileKeyword(text);
}

/** Backward-compatible alias used by the UI. */
export function interpret(text) {
  return compileRequirement(text, { mode: 'keyword' });
}

function compileKeyword(text) {
  const raw = String(text ?? '');
  const trimmed = raw.trim();
  if (!trimmed) {
    return { error: 'Describe what you want to watch, or choose an example below.' };
  }

  const t = trimmed.toLowerCase();

  if (UNSUPPORTED.test(t)) {
    return { error: `This capability is not connected yet. ${supportedCapabilitySummary()}` };
  }

  if (NEGATION.test(t)) {
    return {
      error:
        'Negated requirements are not supported yet. State what to watch for, not what to ignore.',
    };
  }

  const hits = matchModules(t);
  if (hits.length !== 1) {
    return {
      error: hits.length
        ? 'Use one requirement at a time so each rule can be reviewed.'
        : 'Try “Keep people on the walkway”, “Flag tall forklift loads”, or “Watch for an open panel”.',
    };
  }

  const moduleId = hits[0];
  const match = t.match(DURATION);
  const threshold = match
    ? normalizeThreshold(match[1], modules[moduleId].defaultThreshold)
    : modules[moduleId].defaultThreshold;

  if (!thresholdInRange(threshold)) {
    return {
      error: `Choose a duration between ${THRESHOLD_MIN} and ${THRESHOLD_MAX} seconds.`,
    };
  }

  const rule = createRule({
    module: moduleId,
    threshold,
    text: trimmed,
    source: 'keyword',
  });

  const checked = validateRule(rule, { modules });
  return checked.ok ? checked.rule : { error: checked.error };
}

function matchModules(normalizedText) {
  const hits = [];
  for (const [id, mod] of Object.entries(modules)) {
    if (mod.keywords.some((kw) => normalizedText.includes(kw))) hits.push(id);
  }
  return hits;
}

/**
 * Re-validate a suggestion after the user edits the threshold in the UI.
 */
export function applyThreshold(rule, threshold) {
  return validateRule({ ...rule, threshold }, { modules });
}
