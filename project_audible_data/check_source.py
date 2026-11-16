#!/usr/bin/env python3
"""Live check that the FFIEC HMDA files behind the dashboard are still the ones published.

Sends a HEAD request to each URL recorded in data/2025/manifest.json and compares the
server's ETag and Last-Modified with the values logged when download_hmda.py ran.
Writes data/2025/source_check.json, which build_dashboard.py shows on the Regulator page.

Status:
  match        every file is unchanged on the server
  changed      FFIEC republished a file; rerun the full pipeline (./run_demo.sh --full)
  unreachable  offline or the server refused; the dashboard still uses the checksummed archive

Python 3.10+, standard library only. Never fails the build: exit code is always 0.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DATA_DIR = Path(__file__).resolve().parent / 'data' / '2025'


def head(url: str, timeout: int = 20) -> dict:
    # Same default urllib User-Agent as download_hmda.py (custom agents got HTTP 403).
    with urlopen(Request(url, method='HEAD'), timeout=timeout) as resp:
        return {'etag': resp.headers.get('ETag'), 'last_modified': resp.headers.get('Last-Modified')}


def check(manifest: dict, fetch=head) -> dict:
    results, statuses = {}, []
    for name, rec in manifest.get('downloads', {}).items():
        url = rec.get('url')
        try:
            live = fetch(url)
        except (HTTPError, URLError, OSError, ValueError) as exc:
            results[name] = {'url': url, 'status': 'unreachable', 'error': str(exc)[:200]}
            statuses.append('unreachable')
            continue
        same = live['etag'] == rec.get('etag') and live['last_modified'] == rec.get('last_modified')
        status = 'match' if same else 'changed'
        results[name] = {'url': url, 'status': status, 'logged': {'etag': rec.get('etag'),
                         'last_modified': rec.get('last_modified')}, 'live': live}
        statuses.append(status)
    if not statuses:
        overall = 'unreachable'
    elif 'changed' in statuses:
        overall = 'changed'
    elif all(s == 'match' for s in statuses):
        overall = 'match'
    else:
        overall = 'unreachable'
    return {'checked_at_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            'status': overall, 'files': results}


def main() -> None:
    manifest_path = DATA_DIR / 'manifest.json'
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        print(f'check_source: no readable {manifest_path}; skipping.')
        return
    out = check(manifest)
    (DATA_DIR / 'source_check.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    detail = ', '.join('{}={}'.format(k, v['status']) for k, v in out['files'].items())
    print(f"check_source: {out['status']} ({detail})")


if __name__ == '__main__':
    main()
