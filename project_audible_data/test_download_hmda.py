"""Offline checks for eligibility, raw-value preservation and interrupted downloads."""

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

import download_hmda as hmda


def zip_csv(path, fields, rows):
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("data.csv", text.getvalue())
        archive.writestr("__MACOSX/._data.csv", "metadata,not,data")


def eligible(**changes):
    return {**dict.fromkeys(hmda.FIELDS, ""), **dict(hmda.FILTERS),
            "activity_year": "2025", "lei": "LENDER_A", "state_code": "NC",
            "rate_spread": "-0.125", "interest_rate": "6.500", "loan_amount": "305000",
            "origination_charges": "0", "debt_to_income_ratio": "20%-<30%",
            "income": "125", "discount_points": "Exempt", "lender_credits": "",
            "total_loan_costs": "NA", **changes}


class Response(io.BytesIO):
    def __init__(self, body=b"", headers=None, status=200):
        super().__init__(body)
        self.headers = headers or {}
        self.status = status


class DownloaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.lar = self.directory / "lar.zip"
        self.lenders = {"LENDER_A": {"respondent_name": "A Lender", "agency_code": "7",
                                     "respondent_state": "CA"}}

    def test_property_state_filter_preserves_raw_values_and_keeps_missing_prices(self):
        zip_csv(self.lar, hmda.FIELDS, [eligible(), eligible(state_code="VA"),
                                       eligible(rate_spread="NA")])
        report, _ = hmda.extract_sample(self.lar, self.lenders, self.directory, 2025, {"NC"})
        with (self.directory / "mortgages_2025.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["lender_name"], "A Lender")
        self.assertEqual(rows[0]["rate_spread"], "-0.125")
        self.assertEqual(rows[0]["origination_charges"], "0")
        self.assertEqual(rows[0]["discount_points"], "Exempt")
        self.assertEqual(rows[0]["debt_to_income_ratio"], "20%-<30%")
        self.assertEqual(rows[0]["income"], "125")
        self.assertEqual(rows[1]["rate_spread"], "NA")
        self.assertEqual(report["pricing_missing_or_not_applicable"]["rate_spread"], 1)
        self.assertNotIn("lender_type", rows[0])

    def test_all_eligibility_rules_and_numeric_intro_period_are_enforced(self):
        bad_rows = [eligible(**{field: "999"}) for field, _ in hmda.FILTERS]
        bad_rows.extend([eligible(intro_rate_period="0"), eligible(intro_rate_period="Exempt")])
        zip_csv(self.lar, hmda.FIELDS, [eligible(), *bad_rows])
        report, _ = hmda.extract_sample(self.lar, self.lenders, self.directory, 2025)
        self.assertEqual(report["eligible_loans"], 1)
        self.assertEqual(report["filter_funnel"]["rows_read"], 11)

    def test_classification_edits_survive_rerun_and_unknown_lenders_are_visible(self):
        zip_csv(self.lar, hmda.FIELDS, [eligible(lei="UNKNOWN")])
        hmda.extract_sample(self.lar, self.lenders, self.directory, 2025)
        template = self.directory / "lender_classification_2025.csv"
        template.write_text("user-verified classification\n")
        report, _ = hmda.extract_sample(self.lar, self.lenders, self.directory, 2025)
        self.assertEqual(template.read_text(), "user-verified classification\n")
        self.assertEqual(report["eligible_lenders_missing_from_ts"], ["UNKNOWN"])

    def test_wrong_year_does_not_replace_completed_sample(self):
        output = self.directory / "mortgages_2025.csv"
        output.write_text("previous completed sample\n")
        zip_csv(self.lar, hmda.FIELDS, [eligible(activity_year="2024")])
        with self.assertRaisesRegex(ValueError, "Unexpected year"):
            hmda.extract_sample(self.lar, self.lenders, self.directory, 2025)
        self.assertEqual(output.read_text(), "previous completed sample\n")

    def test_schema_change_and_duplicate_lender_join_fail_explicitly(self):
        zip_csv(self.lar, ["lei"], [{"lei": "A"}])
        with self.assertRaisesRegex(ValueError, "missing required columns"):
            hmda.extract_sample(self.lar, self.lenders, self.directory, 2025)
        ts = self.directory / "ts.zip"
        row = {"activity_year": "2025", "lei": "A", "respondent_name": "Bank", "agency_code": "1"}
        zip_csv(ts, list(row), [row, row])
        with self.assertRaisesRegex(ValueError, "duplicate lender"):
            hmda.read_lenders(ts, 2025)

    def test_truncated_download_resumes_and_completed_cache_is_verified(self):
        zip_csv(self.lar, ["x"], [{"x": "hello"}])
        payload = self.lar.read_bytes()
        cut = len(payload) // 2
        headers = {"ETag": '"stable"', "Content-Length": str(len(payload))}
        requests = []

        def fake_request(url, *, method="GET", headers=None, **kwargs):
            requests.append((method, headers))
            if method == "HEAD":
                return Response(headers={"ETag": '"stable"', "Content-Length": str(len(payload))})
            if headers:
                self.assertEqual(headers["Range"], f"bytes={cut}-")
                return Response(payload[cut:], {"Content-Range": f"bytes {cut}-{len(payload)-1}/{len(payload)}"}, 206)
            return Response(payload[:cut])

        target = self.directory / "download.zip"
        with patch.object(hmda, "request", fake_request), patch.object(hmda.time, "sleep"):
            result = hmda.download("https://official.example/file.zip", target)
        self.assertEqual(target.read_bytes(), payload)
        self.assertEqual(result["sha256"], hmda.sha256_file(target))
        with patch.object(hmda, "request", side_effect=AssertionError("Cached file should not use network")):
            hmda.download("https://official.example/file.zip", target)
        target.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "Cannot verify cached"):
            hmda.download("https://official.example/file.zip", target)

    def test_missing_snapshot_returns_failure_without_live_data_fallback(self):
        from urllib.error import HTTPError
        with patch.object(hmda, "request", side_effect=HTTPError("url", 404, "missing", {}, None)):
            code = hmda.main(["--reference-only", "--output-dir", str(self.directory)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads((self.directory / "manifest.json").read_text())["status"], "failed")

    def test_changed_remote_file_cannot_resume_stale_bytes_after_get_failure(self):
        from urllib.error import URLError
        target = self.directory / "fresh.zip"
        target.with_suffix(".zip.part").write_bytes(b"old file bytes")
        hmda.write_json(target.with_suffix(".zip.part.json"),
                        {"url": "url", "etag": '"old"', "bytes_expected": 14})
        zip_csv(self.lar, ["x"], [{"x": "new content"}])
        payload = self.lar.read_bytes()
        get_calls = []

        def fake_request(url, *, method="GET", headers=None, **kwargs):
            if method == "HEAD":
                return Response(headers={"ETag": '"new"', "Content-Length": str(len(payload))})
            get_calls.append(headers)
            if len(get_calls) == 1:
                raise URLError("network failure before GET headers")
            return Response(payload)

        with patch.object(hmda, "request", fake_request), patch.object(hmda.time, "sleep"):
            hmda.download("url", target)
        self.assertEqual(get_calls, [{}, {}])
        self.assertEqual(target.read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
