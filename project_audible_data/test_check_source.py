#!/usr/bin/env python3
"""Unit tests for check_source.check (no network)."""
from __future__ import annotations

import unittest
from urllib.error import URLError

import check_source as cs

MANIFEST = {'downloads': {
    'lar': {'url': 'https://x/lar.zip', 'etag': '"a"', 'last_modified': 'Tue, 23 Jun 2026 13:29:33 GMT'},
    'ts': {'url': 'https://x/ts.zip', 'etag': '"b"', 'last_modified': 'Tue, 23 Jun 2026 13:29:49 GMT'},
}}


class TestCheckSource(unittest.TestCase):
    def fake(self, table):
        return lambda url: table[url]

    def test_match(self):
        out = cs.check(MANIFEST, self.fake({
            'https://x/lar.zip': {'etag': '"a"', 'last_modified': 'Tue, 23 Jun 2026 13:29:33 GMT'},
            'https://x/ts.zip': {'etag': '"b"', 'last_modified': 'Tue, 23 Jun 2026 13:29:49 GMT'},
        }))
        self.assertEqual(out['status'], 'match')

    def test_changed_wins(self):
        out = cs.check(MANIFEST, self.fake({
            'https://x/lar.zip': {'etag': '"NEW"', 'last_modified': 'Wed, 01 Jul 2026 00:00:00 GMT'},
            'https://x/ts.zip': {'etag': '"b"', 'last_modified': 'Tue, 23 Jun 2026 13:29:49 GMT'},
        }))
        self.assertEqual(out['status'], 'changed')
        self.assertEqual(out['files']['lar']['status'], 'changed')

    def test_offline(self):
        def boom(url):
            raise URLError('offline')
        out = cs.check(MANIFEST, boom)
        self.assertEqual(out['status'], 'unreachable')


if __name__ == '__main__':
    unittest.main()
