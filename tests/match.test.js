import test from 'node:test';
import assert from 'node:assert/strict';
import {matchFeeds, violationSpans} from '../live/match.js';

const rules = [
  {id: 'restroom_entry', name: "Women's bathroom", query: "a man entering the women's bathroom", violation: "A man is entering the women's bathroom.", terms: ['restroom', 'male', 'toilet']},
  {id: 'office_entry', name: 'Office entry', query: 'a person entering an office', violation: 'A person is entering an office.'},
  {id: 'fire_alarm', name: 'Fire alarm', query: 'a person at a fire alarm', violation: 'A person is at the fire alarm.'},
  {id: 'pizza_lunchtime', name: 'Pizza at lunch', query: 'the pizza was not on the lunch table at the promised time of 12:30', violation: 'The pizza was not there at the promised time of 12:30.', terms: ['late', 'missing', 'promised']},
  {id: 'pizza_other_tables', name: 'Pizza on other tables', query: 'pizza on a work table', violation: 'Food is on a table that is not the lunch table.', terms: ['other']},
  {id: 'do_not_enter', name: 'Do not enter', query: 'a door marked do not enter', violation: 'A person is at a door marked do not enter.'},
  {id: 'table_moved', name: 'Table moved', query: 'a table that has been moved', violation: 'A table has been moved.'},
];

const clear = [{id: 'running_indoors', name: 'Running indoors', note: 'No violation in this clip.'}];

const feeds = [
  {name: 'Restroom entry', filename: 'restroom-entry.mp4'},
  {name: 'Office entry', filename: 'office-entry.mp4'},
  {name: 'Fire alarm', filename: 'fire-alarm.mp4'},
  {name: 'Pizza lunchtime', filename: 'pizza-lunchtime.mp4'},
  {name: 'Pizza other tables', filename: 'pizza-other-tables.mp4'},
  {name: 'Do not enter', filename: 'do-not-enter.mp4'},
  {name: 'Running indoors', filename: 'running-indoors.mp4'},
  {name: 'Table moved', filename: 'table-moved.mp4'},
];

test('bathroom query keeps only the restroom clip', () => {
  const found = matchFeeds("man entering woman's bathroom", feeds, rules);
  assert.deepEqual(found.feeds.map((feed) => feed.filename), ['restroom-entry.mp4']);
  assert.equal(found.rules[0].violation, "A man is entering the women's bathroom.");
});

test('male query keeps only the restroom clip', () => {
  const found = matchFeeds("male entering the women's bathroom", feeds, rules);
  assert.deepEqual(found.feeds.map((feed) => feed.filename), ['restroom-entry.mp4']);
});

test('fire alarm query keeps only the fire alarm clip', () => {
  const found = matchFeeds('person pulling the fire alarm', feeds, rules);
  assert.deepEqual(found.feeds.map((feed) => feed.filename), ['fire-alarm.mp4']);
});

test('a missed 12:30 promise keeps only the lunch clip', () => {
  const found = matchFeeds('the pizza was not there at the promised time of 12:30', feeds, rules);
  assert.deepEqual(found.feeds.map((feed) => feed.filename), ['pizza-lunchtime.mp4']);
  assert.equal(found.rules[0].violation, 'The pizza was not there at the promised time of 12:30.');
});

test('other tables query does not keep the lunch clip', () => {
  const found = matchFeeds('pizza left on other tables', feeds, rules);
  assert.deepEqual(found.feeds.map((feed) => feed.filename), ['pizza-other-tables.mp4']);
});

test('an empty query keeps every clip', () => {
  const found = matchFeeds('   ', feeds, rules);
  assert.equal(found.feeds.length, feeds.length);
});

test('an unknown query keeps no clips', () => {
  const found = matchFeeds('forklift in the aisle', feeds, rules, clear);
  assert.deepEqual(found.feeds, []);
  assert.equal(found.clear, false);
});

test('a search for no violations keeps only the running clip', () => {
  const found = matchFeeds('show where there are no violations', feeds, rules, clear);
  assert.equal(found.clear, true);
  assert.deepEqual(found.rules, []);
  assert.deepEqual(found.feeds.map((feed) => feed.filename), ['running-indoors.mp4']);
});

test('the running clip is not a violation', () => {
  const feed = {name: 'Running indoors', filename: 'running-indoors.mp4', duration: 5, segments: [{start: 0, end: 5, caption: 'a person running indoors'}]};
  assert.deepEqual(violationSpans(feed, rules), []);
});

test('a caption narrows the violation to that segment', () => {
  const feed = {
    name: 'Restroom entry', filename: 'restroom-entry.mp4', duration: 10,
    segments: [
      {start: 0, end: 5, caption: 'people sitting at desks'},
      {start: 5, end: 10, caption: "a man entering the women's bathroom"},
    ],
  };
  const spans = violationSpans(feed, rules);
  assert.equal(spans.length, 1);
  assert.equal(spans[0].id, 'restroom_entry');
  assert.equal(spans[0].whole, false);
  assert.deepEqual(spans[0].ranges, [{start: 5, end: 10}]);
});

test('a clip with no matching caption marks the whole duration', () => {
  const feed = {name: 'Fire alarm', filename: 'fire-alarm.mp4', duration: 5, segments: [{start: 0, end: 5, caption: ''}]};
  const spans = violationSpans(feed, rules);
  assert.equal(spans[0].whole, true);
  assert.deepEqual(spans[0].ranges, [{start: 0, end: 5}]);
});

test('a shared camera subtitle does not mark every clip', () => {
  const feed = {name: 'Restroom entry', filename: 'restroom-entry.mp4', subtitle: 'Office', duration: 5, segments: []};
  const spans = violationSpans(feed, rules);
  assert.deepEqual(spans.map((span) => span.id), ['restroom_entry']);
});

test('a clip that is not this violation has no span', () => {
  const feed = {name: 'Office entry', filename: 'office-entry.mp4', duration: 5, segments: []};
  const spans = violationSpans(feed, [rules[0]]);
  assert.deepEqual(spans, []);
});
