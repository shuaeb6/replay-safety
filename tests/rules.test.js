import test from 'node:test';
import assert from 'node:assert/strict';
import {
  interpret,
  compileRequirement,
  evaluate,
  cameras,
  compatible,
  modules,
  validateRule,
  applyThreshold,
  createRule,
  evidenceKey,
  listModules,
  cameraForModule,
  SOURCE_MODES,
  THRESHOLD_MIN,
  THRESHOLD_MAX,
} from '../app/rules.js';

test('interprets a supported rule and requested duration', () => {
  assert.deepEqual(interpret('Alert outside the walkway for 3 seconds'), {
    module: 'zone',
    threshold: 3,
    text: 'Alert outside the walkway for 3 seconds',
    source: 'keyword',
  });
});

test('compileRequirement matches interpret in keyword mode', () => {
  const a = interpret('Flag tall forklift loads');
  const b = compileRequirement('Flag tall forklift loads');
  assert.deepEqual(a, b);
  assert.equal(a.module, 'load');
  assert.equal(a.threshold, modules.load.defaultThreshold);
});

test('does not promise unsupported PPE or blocked route detection', () => {
  assert.ok(interpret('Find missing hard hats').error);
  assert.ok(interpret('Detect a blocked exit').error);
});

test('rejects negated requirements', () => {
  assert.ok(interpret("Don't watch the walkway").error);
  assert.ok(interpret('Never flag open panels').error);
});

test('requires a single unambiguous capability and valid threshold', () => {
  assert.ok(interpret('Watch walkway and panel').error);
  assert.ok(interpret('Watch panels for 0 seconds').error);
  assert.ok(interpret('Watch walkway for 100 seconds').error);
  assert.ok(interpret('').error);
  assert.ok(interpret('   ').error);
});

test('threshold changes event activation and can suppress an event', () => {
  const c = cameras[0];
  assert.equal(evaluate(c, { module: 'zone', threshold: 2 }, 2), null);
  const hit = evaluate(c, { module: 'zone', threshold: 2 }, 3);
  assert.ok(hit);
  assert.equal(hit.sourceMode, SOURCE_MODES.DEMO);
  assert.equal(hit.trigger, 3);
  assert.equal(evaluate(c, { module: 'zone', threshold: 20 }, 8), null);
});

test('reference and incompatible camera do not emit an event', () => {
  assert.equal(evaluate(cameras[0], { module: 'zone', threshold: 1 }, 4, true), null);
  assert.equal(evaluate(cameras[0], { module: 'panel', threshold: 1 }, 4), null);
  assert.equal(compatible(cameras[1], { module: 'zone' }), false);
});

test('validateRule normalizes attachable rules and rejects bad thresholds', () => {
  const ok = validateRule({ module: 'panel', threshold: '2', text: ' Watch panels ' });
  assert.equal(ok.ok, true);
  assert.deepEqual(ok.rule, createRule({ module: 'panel', threshold: 2, text: 'Watch panels', source: 'keyword' }));

  const bad = validateRule({ module: 'panel', threshold: 0 });
  assert.equal(bad.ok, false);
  assert.match(bad.error, new RegExp(`${THRESHOLD_MIN}`));
  assert.match(bad.error, new RegExp(`${THRESHOLD_MAX}`));
});

test('applyThreshold updates suggestion duration safely', () => {
  const base = interpret('Watch for an open panel');
  const next = applyThreshold(base, 4);
  assert.equal(next.ok, true);
  assert.equal(next.rule.threshold, 4);
  assert.equal(applyThreshold(base, 999).ok, false);
});

test('catalog helpers expose modules and camera bindings', () => {
  const listed = listModules();
  assert.equal(listed.length, 3);
  assert.equal(cameraForModule('zone').id, 'corridor');
  assert.equal(evidenceKey('corridor', { module: 'zone', threshold: 2 }), 'corridor:zone:2');
});

test('unknown compiler mode does not invent LLM output', () => {
  const r = compileRequirement('Keep people on the walkway', { mode: 'llm' });
  assert.ok(r.error);
});
