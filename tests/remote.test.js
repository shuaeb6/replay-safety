import test from 'node:test';
import assert from 'node:assert/strict';
import {
  normalizeWorkshopCompile,
  compileRequirementAsync,
  WORKSHOP_TO_DEMO,
} from '../app/rules.js';

test('maps zone_entry workshop compile onto demo walkway rule', () => {
  const rule = normalizeWorkshopCompile(
    {
      modules: [{ id: 'zone_entry', params: { dwell_seconds: 3 }, reason: 'lane' }],
      unsupported: [],
      problems: [],
    },
    'Keep people out of the forklift lane for 3 seconds',
  );
  assert.equal(rule.module, 'zone');
  assert.equal(rule.threshold, 3);
  assert.equal(rule.source, 'wandb');
});

test('maps near_forklift onto load visibility with default threshold', () => {
  const rule = normalizeWorkshopCompile({
    modules: [{ id: 'near_forklift', params: { min_score: 0.5 }, reason: 'close' }],
  });
  assert.equal(rule.module, 'load');
  assert.equal(rule.source, 'wandb');
  assert.ok(rule.threshold >= 0.1);
});

test('workshop-only modules point at the live board', () => {
  const out = normalizeWorkshopCompile({
    modules: [{ id: 'crowding', params: { max_people: 2, min_seconds: 1 }, reason: 'crowd' }],
  });
  assert.ok(out.error);
  assert.ok(out.workshop);
  assert.equal(out.workshop.modules[0].id, 'crowding');
});

test('unsupported topics surface catalog wording', () => {
  const out = normalizeWorkshopCompile({
    modules: [],
    unsupported: [{ topic: 'PPE such as hard hats, vests, or gloves', why: '…' }],
  });
  assert.match(out.error, /PPE/);
});

test('WORKSHOP_TO_DEMO covers catalog module ids', () => {
  assert.equal(WORKSHOP_TO_DEMO.zone_entry.module, 'zone');
  assert.equal(WORKSHOP_TO_DEMO.lingering.module, null);
});

test('compileRequirementAsync keyword mode stays offline', async () => {
  const rule = await compileRequirementAsync('Alert outside the walkway for 3 seconds', {
    mode: 'keyword',
  });
  assert.equal(rule.module, 'zone');
  assert.equal(rule.threshold, 3);
});

test('compileRequirementAsync auto falls back to keyword when compile URL is down', async () => {
  const rule = await compileRequirementAsync('Watch for an open panel', {
    mode: 'auto',
    url: 'http://127.0.0.1:9/api/compile',
  });
  assert.equal(rule.module, 'panel');
  assert.equal(rule.fallbackFrom, 'wandb');
});
