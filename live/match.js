const GROUPS = [
  ['restroom', 'bathroom', 'toilet', 'washroom'],
  ['woman', 'women', 'womans', 'womens'],
  ['entry', 'enter', 'entering', 'entered'],
  ['running', 'run', 'runs'],
  ['moved', 'move', 'moving'],
  ['table', 'tables'],
  ['lunch', 'lunchtime'],
];

const STOP = new Set(['a', 'an', 'the', 'man', 'person', 'someone', 'show', 'me', 'when', 'is', 'at', 'of', 'to', 'and', 'or', 'into', 'in', 'on', 'for', 'with', 'this', 'that']);
const GENERIC = new Set(['entry', 'person', 'door', 'indoor', 'indoors', 'pull']);

function canon(word) {
  for (const group of GROUPS) if (group.includes(word)) return group[0];
  return word;
}

export function tokens(text) {
  const seen = new Set();
  const out = [];
  for (const raw of String(text || '').toLowerCase().split(/[^a-z0-9]+/)) {
    const word = canon(raw);
    if (!word || word.length < 2 || STOP.has(word) || seen.has(word)) continue;
    seen.add(word);
    out.push(word);
  }
  return out;
}

function haystack(rule) {
  return new Set(tokens([rule.name, rule.query, rule.violation, ...(rule.terms || [])].join(' ')));
}

function feedHitsRule(feed, rule) {
  // The clip name can stay short ("Restroom entry") while the rule states the violation
  // ("Women's bathroom"). Match when the clip's own words are covered by the rule.
  // Ignore the camera subtitle; "Office" is shared by every clip in the set.
  const filename = String(feed.filename || '').replace(/\.[a-z0-9]+$/i, '');
  const needles = tokens(`${feed.name || ''} ${filename}`).filter((word) => !GENERIC.has(word));
  if (!needles.length) return false;
  const hay = new Set(tokens(rule.name));
  return needles.every((word) => hay.has(word));
}

export function matchFeeds(query, feeds, rules) {
  const wanted = tokens(query);
  if (!wanted.length) return {rules: [], feeds};
  const scored = (rules || []).map((rule) => {
    const words = haystack(rule);
    return {rule, score: wanted.filter((word) => words.has(word)).length};
  }).filter((row) => row.score > 0);
  if (!scored.length) return {rules: [], feeds: []};
  const top = Math.max(...scored.map((row) => row.score));
  const winners = scored.filter((row) => row.score === top).map((row) => row.rule);
  return {rules: winners, feeds: feeds.filter((feed) => winners.some((rule) => feedHitsRule(feed, rule)))};
}

function segmentMatchesRule(seg, rule) {
  const hay = new Set(tokens(seg?.caption || ''));
  if (!hay.size) return false;
  const needles = tokens([rule.name, ...(rule.terms || [])].join(' ')).filter((word) => !GENERIC.has(word));
  return needles.some((word) => hay.has(word));
}

function mergeRanges(ranges) {
  const sorted = ranges
    .map((range) => ({start: Number(range.start) || 0, end: Number(range.end) || 0}))
    .filter((range) => range.end > range.start)
    .sort((a, b) => a.start - b.start);
  const out = [];
  for (const range of sorted) {
    const prev = out.at(-1);
    if (prev && range.start <= prev.end + 0.05) prev.end = Math.max(prev.end, range.end);
    else out.push({start: range.start, end: range.end});
  }
  return out;
}

// Time ranges where this clip breaks a rule. A caption that names the rule
// narrows the bar to those segments. Otherwise the whole clip is the violation.
export function violationSpans(feed, rules) {
  if (!feed) return [];
  const segments = Array.isArray(feed.segments) ? feed.segments : [];
  const duration = Number(feed.duration) || Number(segments.at(-1)?.end) || 0;
  return (rules || []).filter((rule) => feedHitsRule(feed, rule)).map((rule) => {
    const hits = segments.filter((seg) => segmentMatchesRule(seg, rule));
    const ranges = hits.length ? mergeRanges(hits) : (duration > 0 ? [{start: 0, end: duration}] : []);
    return {id: rule.id, name: rule.name, violation: rule.violation || '', ranges, whole: !hits.length};
  }).filter((row) => row.ranges.length);
}
