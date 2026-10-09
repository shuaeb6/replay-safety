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
  const hay = new Set(tokens(`${feed.name || ''} ${feed.filename || ''} ${feed.subtitle || ''}`));
  const needles = tokens(rule.name).filter((word) => !GENERIC.has(word));
  const need = needles.length ? needles : tokens(rule.name);
  return need.every((word) => hay.has(word));
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
