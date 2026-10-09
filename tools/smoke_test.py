#!/usr/bin/env python3
"""End-to-end smoke test of a running Replay board (VM run or deployed /app URL).

Proves real service access: VAST archive feeds, YOLO11 detections, Cosmos captions,
a seekable clip stream, a W&B Inference rule compile, and a VAST evidence search.
Prints a sanitized report (segment IDs, model id, latencies) and saves it to
.workshop/smoke.json for the sponsor-evidence report. Never prints credentials.

Usage: python3 tools/smoke_test.py [BASE_URL] [CAMERA_ID]   default http://127.0.0.1:8080/ and the server's default camera
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8080/').rstrip('/') + '/'
REQUIREMENT = 'Warn me when someone walks into the forklift lane for more than a second, or stands near a forklift.'
results, ok_all = [], True


def call(path, body=None, headers=None, raw=False):
    req = urllib.request.Request(urllib.parse.urljoin(BASE, path), data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json', **(headers or {})}, method='POST' if body is not None else 'GET')
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=150) as r:
            data = r.read(4096) if raw else r.read()
            return r.status, (dict(r.headers) if raw else json.loads(data or b'null')), round((time.perf_counter() - t) * 1000)
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read() or b'{}').get('error')
        except ValueError:
            detail = None
        return e.code, {'error': detail or f'HTTP {e.code}'}, round((time.perf_counter() - t) * 1000)
    except Exception as e:
        return None, {'error': type(e).__name__}, round((time.perf_counter() - t) * 1000)


def check(name, passed, ms=None, **info):
    global ok_all
    ok_all &= bool(passed)
    results.append({'check': name, 'pass': bool(passed), 'ms': ms, **info})
    print(f"{'PASS' if passed else 'FAIL'}  {name:<28} {'' if ms is None else str(ms) + ' ms':>9}  {json.dumps(info, ensure_ascii=False)[:220]}")


st, body, ms = call('health')
check('health', st == 200 and body.get('ok'), ms)
for asset in ('', 'style.css', 'app.js', 'engine.js', 'catalog.json'):
    st, headers, ms = call(asset, raw=True)
    check(f'static /{asset or "index"}', st == 200, ms, type=(headers or {}).get('Content-Type'))
st, status, ms = call('api/status')
check('status', st == 200 and status.get('archive') and status.get('wandb') and status.get('mode') == 'workshop', ms,
      mode=status.get('mode'), archive=status.get('archive'), wandb=status.get('wandb'), model=status.get('model'))
camera = (sys.argv[2] if len(sys.argv) > 2 else None) or status.get('default_camera') or 'sdg_warehouse_cam-2'
handheld = camera.startswith('replay_')
if handheld:
    REQUIREMENT = 'Watch for do-not-enter areas, running indoors, and anyone touching the fire alarm.'

st, feeds, ms = call(f'api/feeds?camera_id={urllib.parse.quote(camera)}')
items = feeds.get('feeds') or [] if isinstance(feeds, dict) else []
check('VAST feeds', st == 200 and items, ms, camera=camera, feeds=len(items), available=feeds.get('available'),
      first=items[0]['filename'] if items else None)
seg = items[0]['segments'][0] if items else None
if seg:
    q = urllib.parse.quote(seg['source'], safe='')
    st, det, ms = call(f'api/detections?source={q}')
    frames = det.get('frames') or []
    check('YOLO11 detections', st == 200 and frames and str(det.get('source', '')).startswith('yolo'), ms, segment=seg['source'].rsplit('/', 1)[-1], frames=len(frames),
          detector=det.get('source'), classes=det.get('classes'))
    st, row, ms = call(f'api/segment?source={q}')
    caption = seg.get('caption') or row.get('caption') or ''
    check('Cosmos caption', bool(caption), ms, model=row.get('model'), caption=caption[:120])
    st, headers, ms = call(f'api/stream?source={q}', headers={'Range': 'bytes=0-1023'}, raw=True)
    check('clip stream (range)', st == 206 and 'video/mp4' in (headers or {}).get('Content-Type', ''), ms,
          status=st, content_range=(headers or {}).get('Content-Range'))

st, comp, ms = call('api/compile', {'text': REQUIREMENT, 'camera_id': camera})
mods = [m['id'] for m in comp.get('modules') or []] if isinstance(comp, dict) else []
check('W&B rule compile', st == 200 and mods, ms, model=comp.get('model'), modules=mods, problems=comp.get('problems'), error=comp.get('error'))
st, comp2, ms = call('api/compile', {'text': "Alert me when a man goes into the women's restroom." if handheld else 'Alert me when workers are not wearing hard hats.', 'camera_id': camera})
check('W&B rejects unsupported', st == 200 and not comp2.get('modules') and comp2.get('unsupported'), ms,
      unsupported=[u['topic'] for u in comp2.get('unsupported') or []])

evidence_modules = [m for m in mods if m in ('do_not_enter', 'office_entry', 'running_indoors', 'moved_item', 'fire_alarm', 'food_missing')] if handheld else ['near_forklift']
for module_id in evidence_modules or (['do_not_enter'] if handheld else ['near_forklift']):
    st, ev, ms = call('api/evidence', {'module': module_id, 'params': {'min_score': 0.25 if handheld else 0.4}, 'camera_id': camera})
    found = ev.get('moments') or [] if isinstance(ev, dict) else []
    check(f'VAST evidence: {module_id}', st == 200 and found, ms, moments=len(found), error=ev.get('error') if isinstance(ev, dict) else None,
          top=[{'clip': m['feed']['filename'], 'segment': m['source'].rsplit('/', 1)[-1], 'score': m['score'], 'basis': m.get('basis')} for m in found[:3]])
st, ev, ms = call('api/evidence', {'module': evidence_modules[0] if evidence_modules else ('do_not_enter' if handheld else 'near_forklift'), 'params': {'min_score': 0.25 if handheld else 0.4}, 'camera_id': camera})
moments = ev.get('moments') or [] if isinstance(ev, dict) else []

st, calls, ms = call('api/calls')
services = sorted({c['service'] for c in calls.get('calls', []) if c.get('ok')}) if isinstance(calls, dict) else []
check('call log', st == 200 and 'VAST VSS' in services and 'W&B Inference' in services, ms, services=services)

os.makedirs('.workshop', exist_ok=True)
with open('.workshop/smoke.json', 'w', encoding='utf-8') as f:
    json.dump({'base': BASE, 'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'results': results}, f, indent=1)
print(f"\n{'ALL CHECKS PASSED' if ok_all else 'SOME CHECKS FAILED'}  ·  report saved to .workshop/smoke.json")
sys.exit(0 if ok_all else 1)
