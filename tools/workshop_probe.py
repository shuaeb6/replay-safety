#!/usr/bin/env python3
"""Read-only probe of the team's workshop services (VSS backend + W&B Inference).

Run on the workshop VM only:  python3 tools/workshop_probe.py [--model MODEL_ID]

It reads /config/<team>.config, never prints credentials or tokens, makes only
read requests (plus one tiny W&B chat completion when --model is given), and
prints a sanitized JSON summary of response shapes, camera metadata, search hit
counts, one detection sample, and one playback check. Output is also saved to
.workshop/probe.json (gitignored). Paste the printed summary back to the team.
"""
import argparse, glob, json, os, re, ssl, sys, time, urllib.error, urllib.parse, urllib.request

QUERIES = [
    'forklift near a person in a warehouse aisle',
    'person walking in an aisle while a forklift moves',
    'pallet or object blocking a walkway',
    'person close to a moving vehicle',
]
SECRET_KEYS = re.compile(r'pass|secret|token|key|auth|credential', re.I)


def load_config():
    files = sorted(glob.glob('/config/*.config'))
    cfg = {}
    if len(files) == 1:
        for line in open(files[0], encoding='utf-8'):
            m = re.match(r'\s*(?:export\s+)?([A-Z0-9_]+)=(.*)$', line)
            if m:
                cfg[m.group(1)] = m.group(2).strip().strip('"\'')
    for k in ('WANDB_API_KEY', 'WANDB_TEAM', 'WANDB_PROJECT', 'WANDB_ENTITY'):
        if not cfg.get(k) and os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg, files


def sanitize(value, depth=0):
    """Shape-preserving summary: truncates, masks URL hosts/queries and secret-looking fields."""
    if depth > 6:
        return '…'
    if isinstance(value, dict):
        return {k: ('<redacted>' if SECRET_KEYS.search(k) else sanitize(v, depth + 1)) for k, v in list(value.items())[:40]}
    if isinstance(value, list):
        out = [sanitize(v, depth + 1) for v in value[:3]]
        if len(value) > 3:
            out.append(f'… {len(value) - 3} more')
        return out
    if isinstance(value, str):
        s = re.sub(r'https?://[^/\s"]+', 'http://<host>', value)
        s = re.sub(r'([?&](?:token|sig|signature|X-Amz-[A-Za-z-]+)=)[^&\s"]+', r'\1<redacted>', s)
        return s if len(s) <= 300 else s[:300] + '…'
    return value


class Client:
    def __init__(self, insecure):
        self.ctx = ssl._create_unverified_context() if insecure else None

    def call(self, method, url, headers=None, body=None, raw=False):
        data = json.dumps(body).encode() if body is not None else None
        # Cloudflare in front of W&B Inference rejects urllib's default User-Agent (error 1010).
        req = urllib.request.Request(url, data=data, method=method, headers={'Content-Type': 'application/json', 'User-Agent': 'replay-workshop-probe/1.0', **(headers or {})})
        t = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60, context=self.ctx) as r:
                payload = r.read(2048) if raw else r.read()
                ms = round((time.perf_counter() - t) * 1000)
                if raw:
                    return r.status, {k: r.headers.get(k) for k in ('Content-Type', 'Content-Range', 'Accept-Ranges', 'Content-Length')}, ms
                return r.status, json.loads(payload or b'null'), ms
        except urllib.error.HTTPError as e:
            return e.code, {'error': sanitize(e.read(500).decode('utf-8', 'replace'))}, round((time.perf_counter() - t) * 1000)
        except Exception as e:  # network/TLS errors: report type only
            return None, {'error': type(e).__name__, 'detail': sanitize(str(e))}, round((time.perf_counter() - t) * 1000)


def probe_vss(c, cfg, report):
    base = cfg.get('INGRESS_URL', '').rstrip('/')
    if not (base and cfg.get('USERNAME') and cfg.get('PASSWORD')):
        report['vss'] = {'error': 'INGRESS_URL/USERNAME/PASSWORD missing from team config'}
        return
    api = base + '/api/v1'
    vss = report['vss'] = {}
    st, body, ms = c.call('POST', api + '/auth/login', body={'username': cfg['USERNAME'], 'password': cfg['PASSWORD']})
    token = body.get('access_token') if isinstance(body, dict) else None
    vss['login'] = {'status': st, 'ms': ms, 'ok': bool(token), 'response_keys': sorted(body) if isinstance(body, dict) else None}
    if not token:
        return
    auth = {'Authorization': f'Bearer {token}'}

    st, body, ms = c.call('GET', api + '/metadata/schema', auth)
    fields = body.get('schema', []) if isinstance(body, dict) else []
    vss['metadata_schema'] = {'status': st, 'ms': ms, 'fields': [{'name': f.get('name'), 'ui_type': f.get('ui_type'), 'options': (f.get('options') or [])[:30]} for f in fields]}

    st, body, ms = c.call('GET', api + '/metadata/ingest-config')
    vss['ingest_config'] = {'status': st, 'ms': ms, 'shape': sanitize(body)}

    st, body, ms = c.call('GET', api + '/dashboard/stats', auth)
    vss['dashboard_stats'] = {'status': st, 'ms': ms, 'shape': sanitize(body)}

    st, body, ms = c.call('GET', api + '/videos/explore?scope=all&limit=100&offset=0', auth)
    items = []
    if isinstance(body, dict):
        items = next((v for v in body.values() if isinstance(v, list)), [])
    per_camera = {}
    for it in items:
        key = f"{it.get('camera_id')} | {it.get('location')} | {it.get('capture_type')}"
        per_camera[key] = per_camera.get(key, 0) + 1
    vss['explore'] = {'status': st, 'ms': ms, 'top_level_keys': sorted(body) if isinstance(body, dict) else None,
                      'total': body.get('total') if isinstance(body, dict) else None,
                      'first_page_by_camera': per_camera, 'sample_item': sanitize(items[0]) if items else None}

    vss['search'] = []
    best = None
    for q in QUERIES:
        st, body, ms = c.call('POST', api + '/search', auth, {'query': q, 'top_k': 8, 'llm_top_n': 1, 'min_similarity': 0.1, 'include_public': True})
        results = body.get('results', []) if isinstance(body, dict) else []
        entry = {'query': q, 'status': st, 'ms': ms, 'n_results': len(results),
                 'n_chunk_results': len(body.get('chunk_results', [])) if isinstance(body, dict) else None,
                 'hits': [{'camera_id': r.get('camera_id'), 'score': r.get('similarity_score'), 'source': r.get('source'),
                           'reasoning': sanitize(r.get('reasoning_content') or '')[:220]} for r in results[:4]]}
        if q == QUERIES[0]:
            entry['result_shape'] = sanitize(results[0]) if results else None
            entry['chunk_result_shape'] = sanitize(body.get('chunk_results', [None])[0]) if isinstance(body, dict) and body.get('chunk_results') else None
            entry['llm_synthesis_keys'] = sorted(body['llm_synthesis']) if isinstance(body, dict) and isinstance(body.get('llm_synthesis'), dict) else None
        vss['search'].append(entry)
        if not best and results:
            best = results[0].get('source')

    if not best:
        return
    src = urllib.parse.quote(best, safe='')
    st, body, ms = c.call('GET', f'{api}/videos/metadata?source={src}', auth)
    vss['segment_metadata'] = {'source': best, 'status': st, 'ms': ms, 'shape': sanitize(body)}
    st, body, ms = c.call('GET', f'{api}/videos/detections?source={src}', auth)
    vss['segment_detections'] = {'status': st, 'ms': ms, 'shape': sanitize(body)}
    st, headers, ms = c.call('GET', f'{api}/videos/stream?source={src}&token={urllib.parse.quote(token)}', {'Range': 'bytes=0-1023'}, raw=True)
    vss['segment_stream_range_check'] = {'status': st, 'ms': ms, 'headers': headers}


def probe_wandb(c, cfg, model, report):
    key = cfg.get('WANDB_API_KEY')
    wb = report['wandb'] = {'api_key_present': bool(key), 'team_present': bool(cfg.get('WANDB_TEAM') or cfg.get('WANDB_ENTITY')), 'project_present': bool(cfg.get('WANDB_PROJECT'))}
    if not key:
        return
    base = 'https://api.inference.wandb.ai/v1'
    headers = {'Authorization': f'Bearer {key}'}
    team, project = cfg.get('WANDB_TEAM') or cfg.get('WANDB_ENTITY'), cfg.get('WANDB_PROJECT')
    if team and project:
        headers['OpenAI-Project'] = f'{team}/{project}'
    st, body, ms = c.call('GET', base + '/models', headers)
    wb['models'] = {'status': st, 'ms': ms, 'ids': [m.get('id') for m in body.get('data', [])] if isinstance(body, dict) else sanitize(body)}
    if not model:
        return
    msg = [{'role': 'system', 'content': 'Reply with JSON only: {"module": "forklift_proximity" | "unsupported", "seconds": number}'},
           {'role': 'user', 'content': 'Flag a forklift within reach of a person for 2 seconds'}]
    for fmt in ({'type': 'json_object'}, None):
        req = {'model': model, 'messages': msg, 'max_tokens': 80, 'temperature': 0}
        if fmt:
            req['response_format'] = fmt
        st, body, ms = c.call('POST', base + '/chat/completions', headers, req)
        text = body.get('choices', [{}])[0].get('message', {}).get('content') if isinstance(body, dict) and body.get('choices') else None
        try:
            parsed = json.loads(text) if text else None
        except ValueError:
            parsed = None
        wb.setdefault('chat_tests', []).append({'response_format': fmt, 'status': st, 'ms': ms, 'valid_json': parsed is not None,
                                                 'content': sanitize(text or body)})


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--model', help='W&B Inference model id to test with one tiny chat call (pick from the listed ids)')
    ap.add_argument('--insecure', action='store_true', help='skip TLS verification (only if the backend uses a self-signed cert)')
    ap.add_argument('--skip-vss', action='store_true')
    args = ap.parse_args()
    cfg, files = load_config()
    report = {'config_files_found': len(files), 'config_keys_present': sorted(k for k, v in cfg.items() if v)}
    c = Client(args.insecure)
    if not args.skip_vss:
        probe_vss(c, cfg, report)
    probe_wandb(c, cfg, args.model, report)
    out = json.dumps(report, indent=1, ensure_ascii=False, default=str)
    os.makedirs('.workshop', exist_ok=True)
    with open('.workshop/probe.json', 'w', encoding='utf-8') as f:
        f.write(out)
    print(out)


if __name__ == '__main__':
    main()
