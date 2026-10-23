#!/usr/bin/env python3
"""Unit tests for analyze_pricing.py."""
from __future__ import annotations

import unittest
import analyze_pricing as ap


class TestAnalyzePricing(unittest.TestCase):
    def test_bucket_median_and_gap_bps_and_coverage(self):
        b = ap.Bucket()
        # Add 120 Fintech loans across 3 lenders with rate_spread 0.30, ir 6.5, oc 1.0
        for i in range(120):
            b.add(True, f'F_{i % 3}', 0.30, 6.50, 1.00)
        # Add 150 Bank loans across 12 lenders with rate_spread 0.05, ir 6.25, oc 0.60
        for i in range(150):
            b.add(False, f'B_{i % 12}', 0.05, 6.25, 0.60)

        s = b.summarize({'slice': 'test'})
        self.assertTrue(s['coverage_ok'])
        self.assertEqual(s['status'], 'Fintech higher (+5 bps or more)')
        self.assertAlmostEqual(s['fintech_median_rate_spread'], 0.30)
        self.assertAlmostEqual(s['bank_median_rate_spread'], 0.05)
        self.assertAlmostEqual(s['rate_spread_gap_bps'], 25.0)
        self.assertAlmostEqual(s['interest_rate_gap_bps'], 25.0)
        self.assertAlmostEqual(s['orig_pct_gap_bps'], 40.0)

    def test_insufficient_coverage_flagged(self):
        b = ap.Bucket()
        for i in range(50):
            b.add(True, 'F_ONLY_ONE', 0.40, 6.50, 1.00)
        for i in range(200):
            b.add(False, f'B_{i % 15}', 0.10, 6.25, 0.50)
        s = b.summarize()
        self.assertFalse(s['coverage_ok'])
        self.assertEqual(s['status'], 'Insufficient coverage')


if __name__ == '__main__':
    unittest.main()
