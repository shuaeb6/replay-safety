import test from 'node:test';
import assert from 'node:assert/strict';
import {matchFeeds} from '../live/match.js';

const rules = [
  {id: 'restroom_entry', name: 'Restroom entry', query: 'a person entering a restroom', violation: 'A person is at the restroom door.', terms: ['bathroom', 'woman', 'women', 'toilet']},
  {id: 'office_entry', name: 'Office entry', query: 'a person entering an office', violation: 'A person is entering an office.'},
  {id: 'fire_alarm', name: 'Fire alarm', query: 'a person at a fire alarm', violation: 'A person is at the fire alarm.'},
  {id: 'pizza_lunchtime', name: 'Pizza at lunch', query: 'people eating pizza at lunch', violation: 'People are eating pizza at the lunch table.', terms: ['eating']},
  {id: 'pizza_other_tables', name: 'Pizza on other tables', query: 'pizza on a work table', violation: 'Food is on a table that is not the lunch table.', terms: ['other']},
  {id: 'do_not_enter', name: 'Do not enter', query: 'a door marked do not enter', violation: 'A person is at a door marked do not enter.'},
  {id: 'running_indoors', name: 'Running indoors', query: 'a person running indoors', violation: 'A person is running indoors.'},
  {id: 'table_moved', name: 'Table moved', query: 'a table that has been moved', violation: 'A table has been moved.'},
];

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
});

test('fire alarm query keeps only the fire alarm clip', () => {
  const found = matchFeeds('person pulling the fire alarm', feeds, rules);
  assert.deepEqual(found.feeds.map((feed) => feed.filename), ['fire-alarm.mp4']);
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
  const found = matchFeeds('forklift in the aisle', feeds, rules);
  assert.deepEqual(found.feeds, []);
});
