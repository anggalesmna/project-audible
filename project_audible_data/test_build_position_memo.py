#!/usr/bin/env python3
"""Unit tests for build_position_memo.py (framing follows the nonbank benchmark)."""
from __future__ import annotations

import csv
import random
import re
import tempfile
import unittest
from pathlib import Path

import analyze_pricing as ap
import build_dashboard as bd
import build_position_memo as pm
from test_analyze_pricing import FIELDS, loan


def build_inputs(nonbank_spread):
    random.seed(7)
    rows = []
    for i in range(8000):
        d = random.choice(bd.DTI_STANDARD_ORDER)
        c = random.choice(ap.CLTV_ORDER)
        kind = i % 4
        if kind == 0:
            r = loan(f'F{i % 5}', 'Fintech', '40', 0.30, dti=d, cltv=c)
        elif kind == 3:
            r = loan(f'N{i % 15}', 'Other lender', '40', nonbank_spread, dti=d, cltv=c)
        else:
            r = loan(f'B{i % 20}', 'Bank comparator', '10', 0.10, dti=d, cltv=c)
        r['income_group'] = random.choice(ap.INCOME_ORDER)
        r['loan_amount_group'] = random.choice(ap.LOAN_ORDER)
        rows.append(r)
    tmp = Path(tempfile.mkdtemp())
    src = tmp / 'clean.csv'
    with src.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    summary = ap.analyze(src, tmp)
    sd = bd.compute_slices(src)
    dash = {**bd.summary_fields(summary), 'robustness_checks': sd['robustness_checks'],
            'fintech_lenders': sd['fintech_lenders'], 'lender_stats': sd['lender_stats'],
            'slices_data': {'states': sd['states'], 'slices': sd['slices'], 'bars': sd['bars']}}
    grid = list(csv.DictReader((tmp / 'by_dti_cltv_grid.csv').open(encoding='utf-8')))
    return dash, summary, grid


def text(xml):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', xml))


class TestPositionMemo(unittest.TestCase):
    def test_bps_rounds_like_the_dashboard(self):
        self.assertEqual(pm.bps(12.25), '+12.3 bps')
        self.assertEqual(pm.bps(0.0), '0.0 bps')
        self.assertEqual(pm.bps(-1.2), '-1.2 bps')

    def test_peer_framing_when_fintech_matches_nonbanks(self):
        f = pm.facts(*build_inputs(nonbank_spread=0.30))
        self.assertEqual(pm.nb_state(f), 'peer')
        out = text(pm.build_document_xml(f, 'test'))
        self.assertIn('in line with other nonbank lenders', out)
        self.assertNotIn('PENDING', out)
        self.assertNotIn('rerun', out)

    def test_fintech_framing_when_premium_survives(self):
        f = pm.facts(*build_inputs(nonbank_spread=0.15))
        self.assertEqual(pm.nb_state(f), 'fintech')
        out = text(pm.build_document_xml(f, 'test'))
        self.assertIn('not just a nonbank effect', out)
        self.assertNotIn('largely disappears', out)

    def test_pending_when_nonbank_check_missing(self):
        dash, summary, grid = build_inputs(nonbank_spread=0.30)
        dash['robustness_checks'] = [r for r in dash['robustness_checks']
                                     if not r['slice'].startswith(pm.NONBANK_PREFIX)]
        summary['headline_metrics'].pop('national_vs_nonbank')
        f = pm.facts(dash, summary, grid)
        self.assertEqual(pm.nb_state(f), 'pending')
        self.assertIn('PENDING', text(pm.build_document_xml(f, 'test')))


if __name__ == '__main__':
    unittest.main()
