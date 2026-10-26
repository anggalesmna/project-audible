import csv
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import io

from classify_lenders_nyu import LOAN_LABELS, fetch_reference, group_for, join_loans, match_nyu


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class ClassificationTests(unittest.TestCase):
    def test_fetch_reference_downloads_once_and_never_overwrites(self):
        calls = []

        def opener(request, timeout):
            calls.append(request.full_url)
            return _FakeResponse(b'xlsx-bytes')

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'raw' / 'ref.xlsx'
            self.assertTrue(fetch_reference(target, url='https://example.test/ref.xlsx', opener=opener))
            self.assertEqual(target.read_bytes(), b'xlsx-bytes')
            self.assertFalse(fetch_reference(target, url='https://example.test/ref.xlsx', opener=opener))
            self.assertEqual(len(calls), 1)

    def test_fetch_reference_removes_partial_file_on_failure(self):
        def opener(request, timeout):
            return _FakeResponse(b'')

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'ref.xlsx'
            with self.assertRaisesRegex(ValueError, 'empty'):
                fetch_reference(target, url='https://example.test/ref.xlsx', opener=opener)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_nonlisted_nonbank_is_not_a_bank_or_proven_nonfintech(self):
        self.assertEqual(group_for(False, 40), 'Other lender')
        self.assertEqual(group_for(False, 11), 'Other lender')
        self.assertEqual(group_for(False, 30), 'Credit union')
        self.assertEqual(group_for(False, 10), 'Bank comparator')
        self.assertEqual(group_for(False, 999), 'Unknown')
        self.assertEqual(group_for(True, 40), 'Fintech')

    def test_crosswalk_rejects_ambiguous_rssd_and_duplicate_lei(self):
        table = pd.DataFrame({'LEI': ['A', 'B'], 'RSSD': [123, 123]})
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            match_nyu({123: 'Historical lender'}, table)
        table = pd.DataFrame({'LEI': ['A', 'A'], 'RSSD': [123, 456]})
        with self.assertRaisesRegex(ValueError, 'Duplicate LEI'):
            match_nyu({123: 'Historical lender'}, table)

    def test_join_preserves_missing_tokens_zero_negative_and_quoted_text(self):
        rows = [
            {'activity_year': '2025', 'lei': 'A', 'rate_spread': 'NA', 'income': '', 'name': 'Bank, Inc.'},
            {'activity_year': '2025', 'lei': 'A', 'rate_spread': '-0.25', 'income': '0', 'name': 'Quoted "name"'},
            {'activity_year': '2025', 'lei': 'B', 'rate_spread': 'Exempt', 'income': '100', 'name': 'Other'},
        ]
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory)/'source.csv', Path(directory)/'output.csv'
            with source.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            original_bytes = source.read_bytes()
            labels = {lei: {field: '' for field in LOAN_LABELS} for lei in ['A', 'B']}
            labels['A']['lender_type'] = 'Fintech'
            labels['B']['lender_type'] = 'Other lender'
            observed, groups = join_loans(source, output, labels, {'A': 2, 'B': 1}, 2025)
            with output.open(newline='') as stream:
                result = list(csv.DictReader(stream))
            self.assertEqual([{key: row[key] for key in rows[0]} for row in result], rows)
            self.assertEqual(source.read_bytes(), original_bytes)
            self.assertEqual(dict(observed), {'A': 2, 'B': 1})
            self.assertEqual(dict(groups), {'Fintech': 2, 'Other lender': 1})
            output.write_text('previous valid output')
            with self.assertRaisesRegex(ValueError, 'reconcile'):
                join_loans(source, output, labels, {'A': 1, 'B': 1}, 2025)
            self.assertEqual(output.read_text(), 'previous valid output')
            self.assertFalse(output.with_suffix('.csv.tmp').exists())

    def test_unmapped_loan_fails_instead_of_defaulting_to_bank(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory)/'source.csv', Path(directory)/'output.csv'
            source.write_text('activity_year,lei\n2025,UNMAPPED\n')
            with self.assertRaisesRegex(ValueError, 'absent from classification'):
                join_loans(source, output, {}, {}, 2025)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
