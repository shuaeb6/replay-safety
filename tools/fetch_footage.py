#!/usr/bin/env python3
"""Download the offline-demo factory clips from their original source.

The MP4s are not stored in this repository. This script fetches each clip listed in
demo-footage/selected-clips.json from Mendeley Data (Önal & Dandıl, Video Dataset for
Safe and Unsafe Behaviours, v1, DOI 10.17632/xjmtb22pff.1, CC BY 4.0) and verifies its
SHA-256 checksum. Existing files with a matching checksum are skipped.

Usage: python3 tools/fetch_footage.py [--only 0_te21.mp4 ...]
"""
import argparse, hashlib, json, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / 'demo-footage' / 'selected-clips.json'
TARGET = ROOT / 'demo-footage' / 'factory-cctv'


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--only', nargs='*', help='filenames to fetch (default: all)')
    args = ap.parse_args()
    clips = json.loads(MANIFEST.read_text(encoding='utf-8'))
    if args.only:
        clips = [c for c in clips if c['filename'] in args.only]
    TARGET.mkdir(parents=True, exist_ok=True)
    failed = 0
    for clip in clips:
        dest = TARGET / clip['filename']
        expected = clip['content_details']['sha256_hash']
        if dest.exists() and sha256(dest) == expected:
            print(f'ok      {clip["filename"]}')
            continue
        tmp = dest.with_suffix('.part')
        try:
            req = urllib.request.Request(clip['content_details']['download_url'], headers={'User-Agent': 'replay-fetch-footage'})
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, 'wb') as f:
                while block := r.read(1 << 20):
                    f.write(block)
            if sha256(tmp) != expected:
                raise ValueError('checksum mismatch')
            tmp.replace(dest)
            print(f'fetched {clip["filename"]}')
        except Exception as e:
            tmp.unlink(missing_ok=True)
            failed += 1
            print(f'FAILED  {clip["filename"]}: {e}', file=sys.stderr)
    print(f'{len(clips) - failed}/{len(clips)} clips ready in {TARGET.relative_to(ROOT)}')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
