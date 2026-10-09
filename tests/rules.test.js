import test from 'node:test';
import assert from 'node:assert/strict';
import {interpret,evaluate,cameras,compatible} from '../app/rules.js';
test('interprets a supported rule and requested duration',()=>assert.deepEqual(interpret('Alert outside the walkway for 3 seconds'),{module:'zone',threshold:3,text:'Alert outside the walkway for 3 seconds'}));
test('does not promise unsupported PPE or blocked route detection',()=>{assert.ok(interpret('Find missing hard hats').error);assert.ok(interpret('Detect a blocked exit').error);});
test('requires a single unambiguous capability and valid threshold',()=>{assert.ok(interpret('Watch walkway and panel').error);assert.ok(interpret('Watch panels for 0 seconds').error);assert.ok(interpret('Watch walkway for 100 seconds').error);});
test('threshold changes event activation and can suppress an event',()=>{const c=cameras[0];assert.equal(evaluate(c,{module:'zone',threshold:2},2),null);assert.ok(evaluate(c,{module:'zone',threshold:2},3));assert.equal(evaluate(c,{module:'zone',threshold:20},8),null);});
test('reference and incompatible camera do not emit an event',()=>{assert.equal(evaluate(cameras[0],{module:'zone',threshold:1},4,true),null);assert.equal(evaluate(cameras[0],{module:'panel',threshold:1},4),null);assert.equal(compatible(cameras[1],{module:'zone'}),false);});
