#!/usr/bin/env python3
"""Download official HMDA snapshots and extract the Project Audible mortgage sample.

Python 3.10+; standard library only. No API key or third-party packages required.
Run: python3 download_hmda.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

BASE_URL = "https://files.ffiec.cfpb.gov/static-data/snapshot"
STATE_CODES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY AS GU MP PR VI".split())
FILTERS = (
    ("action_taken", "1"),
    ("loan_type", "1"),
    ("loan_purpose", "1"),
    ("lien_status", "1"),
    ("occupancy_type", "1"),
    ("conforming_loan_limit", "C"),
    ("loan_term", "360"),
    ("intro_rate_period", "NA"),
)
FIELDS = [
    "activity_year", "lei", "state_code", "county_code",
    "rate_spread", "interest_rate", "origination_charges", "discount_points",
    "lender_credits", "total_loan_costs", "total_points_and_fees", "loan_amount",
    "debt_to_income_ratio", "combined_loan_to_value_ratio", "income",
    "action_taken", "loan_type", "loan_purpose", "lien_status", "occupancy_type",
    "conforming_loan_limit", "loan_term", "intro_rate_period", "total_units",
    "construction_method", "reverse_mortgage", "open_end_line_of_credit",
    "business_or_commercial_purpose", "submission_of_application",
    "initially_payable_to_institution",
]
PRICING_FIELDS = ["rate_spread", "interest_rate", "origination_charges",
                  "discount_points", "lender_credits", "total_loan_costs"]
SOURCE_DOCS = {
    "data_publication": "https://ffiec.cfpb.gov/data-publication/",
    "field_definitions": "https://ffiec.cfpb.gov/documentation/publications/loan-level-datasets/lar-data-fields",
    "reporting_instructions": "https://www.consumerfinance.gov/rules-policy/regulations/1003/4/",
    "official_download_link_definitions": "https://github.com/cfpb/hmda-frontend/blob/master/src/data-publication/constants/snapshot-dataset.jsx",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def request(url, *, headers=None, method="GET", timeout=120):
    # The official file server accepts urllib's standard User-Agent; custom
    # application/browser User-Agents returned HTTP 403 during verification.
    return urlopen(Request(url, headers=headers or {},
                           method=method), timeout=timeout)


def download(url, target, attempts=4):
    """Cache completed archives; resume a partial only when its remote ETag matches."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = target.with_suffix(target.suffix + ".json")
    if target.exists():
        saved = load_json(metadata_path)
        digest = sha256_file(target)
        if saved.get("url") != url or saved.get("sha256") != digest:
            raise ValueError(f"Cannot verify cached archive {target}. Move it aside and retry.")
        with ZipFile(target):
            pass
        print(f"Using verified cached archive: {target.name}", flush=True)
        return saved

    partial = target.with_suffix(target.suffix + ".part")
    partial_meta = target.with_suffix(target.suffix + ".part.json")
    for attempt in range(1, attempts + 1):
        try:
            with request(url, method="HEAD") as response:
                etag = response.headers.get("ETag")
                total = int(response.headers.get("Content-Length", "0"))
                last_modified = response.headers.get("Last-Modified")
            old = load_json(partial_meta)
            can_resume = (partial.exists() and etag and old.get("etag") == etag
                          and old.get("url") == url and old.get("bytes_expected") == total)
            offset = partial.stat().st_size if can_resume else 0
            if not can_resume or (total and offset > total):
                # Truncate stale bytes BEFORE associating the partial with a new
                # ETag, even if the subsequent GET fails before returning headers.
                partial.open("wb").close()
                offset = 0
            write_json(partial_meta, {"url": url, "etag": etag, "bytes_expected": total})
            # A prior transfer may have finished before its final rename.
            if not (total and offset == total):
                headers = {"Range": f"bytes={offset}-", "If-Range": etag} if offset else {}
                with request(url, headers=headers) as response:
                    if offset and response.status == 206:
                        if not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                            raise ValueError("Server returned an unexpected download range.")
                    elif response.status == 200:
                        offset = 0  # Server sent the full object; restart, never append it.
                    else:
                        raise ValueError(f"Unexpected HTTP status: {response.status}")
                    print(f"Downloading {target.name}: {total / 1024**2:,.1f} MiB; starting at {offset / 1024**2:,.1f} MiB", flush=True)
                    received, last_print = offset, time.monotonic()
                    with partial.open("ab" if offset else "wb") as stream:
                        while block := response.read(1024 * 1024):
                            stream.write(block)
                            received += len(block)
                            if time.monotonic() - last_print >= 5:
                                percent = f" ({received / total:.0%})" if total else ""
                                print(f"  {received / 1024**2:,.1f} MiB{percent}", flush=True)
                                last_print = time.monotonic()
                    if total and received != total:
                        raise OSError(f"Incomplete download: {received} of {total} bytes")
            with ZipFile(partial):
                pass  # Central directory checked here; member CRC checked during extraction.
            metadata = {
                "url": url, "downloaded_at_utc": utc_now(), "etag": etag,
                "last_modified": last_modified, "bytes": partial.stat().st_size,
                "sha256": sha256_file(partial),
            }
            os.replace(partial, target)
            write_json(metadata_path, metadata)
            partial_meta.unlink(missing_ok=True)
            print(f"Saved {target.name}", flush=True)
            return metadata
        except (HTTPError, URLError, OSError, BadZipFile) as error:
            if isinstance(error, HTTPError) and error.code not in (408, 429, 500, 502, 503, 504):
                raise
            if isinstance(error, BadZipFile):
                # A corrupt archive must not be resumed as if it were complete.
                partial_meta.unlink(missing_ok=True)
            if attempt == attempts:
                raise
            delay = min(2 ** attempt, 16)
            print(f"Download attempt {attempt} failed: {error}. Retrying in {delay}s.", file=sys.stderr, flush=True)
            time.sleep(delay)
    raise RuntimeError("Download did not complete")


def csv_member(archive):
    """Ignore macOS metadata; fail rather than silently picking the wrong CSV."""
    members = [n for n in archive.namelist() if n.lower().endswith(".csv")
               and not n.startswith("__MACOSX/") and not Path(n).name.startswith("._")]
    if len(members) != 1:
        raise ValueError(f"Expected one CSV in archive; found {members}")
    return members[0]


def require_fields(actual, required, label):
    missing = set(required) - set(actual or [])
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(sorted(missing))}")


def read_lenders(path, year):
    lenders = {}
    with ZipFile(path) as archive:
        with io.TextIOWrapper(archive.open(csv_member(archive)), encoding="utf-8-sig", newline="") as stream:
            rows = csv.DictReader(stream)
            require_fields(rows.fieldnames, ["activity_year", "lei", "respondent_name", "agency_code"], "Transmittal sheet")
            for row in rows:
                if row.get(None) is not None or None in row.values():
                    raise ValueError("Malformed transmittal-sheet row")
                if row["activity_year"].strip() != str(year):
                    raise ValueError("Unexpected year in transmittal sheet")
                lei = row["lei"].strip()
                if not lei or lei in lenders:
                    raise ValueError(f"Missing or duplicate lender LEI: {lei!r}")
                lenders[lei] = {k: v.strip() for k, v in row.items()}
    return lenders


def extract_sample(lar_path, lenders, output_dir, year, states=None):
    """Stream rows, preserve raw values, and apply only the pitch's eligibility rules."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"mortgages_{year}.csv"
    temporary = output.with_suffix(".csv.part")
    funnel = Counter({"rows_read": 0, "after_property_state_filter": 0,
                      **{f"after_{field}": 0 for field, _ in FILTERS}})
    by_lender, by_state, missing = Counter(), Counter(), Counter()
    output_fields = FIELDS + ["lender_name", "agency_code"]
    with ZipFile(lar_path) as archive:
        with io.TextIOWrapper(archive.open(csv_member(archive)), encoding="utf-8-sig", newline="") as stream:
            rows = csv.DictReader(stream)
            require_fields(rows.fieldnames, FIELDS, "Loan records")
            with temporary.open("w", encoding="utf-8", newline="") as destination:
                writer = csv.DictWriter(destination, fieldnames=output_fields)
                writer.writeheader()
                for row in rows:
                    if row.get(None) is not None or None in row.values():
                        raise ValueError(f"Malformed loan record near CSV row {rows.line_num}")
                    if row["activity_year"].strip() != str(year):
                        raise ValueError(f"Unexpected year near CSV row {rows.line_num}")
                    funnel["rows_read"] += 1
                    if funnel["rows_read"] % 1_000_000 == 0:
                        print(f"Read {funnel['rows_read']:,} loan records; retained {sum(by_lender.values()):,}", flush=True)
                    if states and row["state_code"].strip() not in states:
                        continue
                    funnel["after_property_state_filter"] += 1
                    for field, expected in FILTERS:
                        if row[field].strip() != expected:
                            break
                        funnel[f"after_{field}"] += 1
                    else:
                        lei = row["lei"].strip()
                        if not lei:
                            raise ValueError(f"Missing lender LEI near CSV row {rows.line_num}")
                        lender = lenders.get(lei, {})
                        writer.writerow({**{field: row[field] for field in FIELDS},
                                         "lender_name": lender.get("respondent_name", ""),
                                         "agency_code": lender.get("agency_code", "")})
                        by_lender[lei] += 1
                        by_state[row["state_code"].strip() or "Unknown"] += 1
                        for field in PRICING_FIELDS:
                            if row[field].strip().upper() in {"", "NA", "EXEMPT"}:
                                missing[field] += 1
    # All archive input is read to EOF before this rename, validating its CRC.
    os.replace(temporary, output)
    inventory_path = output_dir / f"lender_inventory_{year}.csv"
    with inventory_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["lei", "lender_name", "agency_code", "respondent_state", "eligible_loans"])
        writer.writeheader()
        for lei, count in by_lender.most_common():
            lender = lenders.get(lei, {})
            writer.writerow({"lei": lei, "lender_name": lender.get("respondent_name", ""),
                             "agency_code": lender.get("agency_code", ""),
                             "respondent_state": lender.get("respondent_state", ""), "eligible_loans": count})
    template_path = output_dir / f"lender_classification_{year}.csv"
    template_created = not template_path.exists()
    if template_created:
        with template_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["lei", "lender_name", "lender_type", "evidence_url", "review_date", "notes"])
            writer.writeheader()
            for lei, _ in by_lender.most_common():
                writer.writerow({"lei": lei, "lender_name": lenders.get(lei, {}).get("respondent_name", "")})
    report = {
        "year": year, "property_states": sorted(states) if states else "All reported geographies",
        "filters_in_order": [{"field": k, "equals": v} for k, v in FILTERS],
        "filter_funnel": dict(funnel), "eligible_loans": sum(by_lender.values()),
        "eligible_lenders": len(by_lender), "loans_by_property_state": dict(sorted(by_state.items())),
        "pricing_missing_or_not_applicable": {field: missing[field] for field in PRICING_FIELDS},
        "eligible_lenders_missing_from_ts": sorted(set(by_lender) - set(lenders)),
        "classification_template_created": template_created,
        "notes": [
            "All institution types are retained pending documented fintech/bank classification.",
            "NA, Exempt, zeroes and blank values are preserved as reported; no imputation or price-based exclusions.",
            "Income is reported in thousands of dollars; DTI includes reported ranges.",
            "intro_rate_period=NA is the pitch's fixed-rate screening rule, not an independent product verification.",
            "An existing classification file is never overwritten; compare it with lender_inventory when changing scope.",
        ],
    }
    write_json(output_dir / "sample_summary.json", report)
    return report, [output, inventory_path]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, default=2025, help="Snapshot reporting year; default 2025 (2018 or later)")
    parser.add_argument("--output-dir", type=Path, help="Default: data/YEAR next to this script")
    parser.add_argument("--states", nargs="+", metavar="STATE", help="Optional property-state codes, e.g. NC SC; download remains national")
    parser.add_argument("--download-only", action="store_true", help="Save archives without processing loan records")
    parser.add_argument("--reference-only", action="store_true", help="Download and verify only the small lender reference (connectivity check)")
    args = parser.parse_args(argv)
    if args.year < 2018:
        parser.error("Use 2018 or later; older data does not support this pitch's fields.")
    states = {state.upper() for state in args.states} if args.states else None
    if states and states - STATE_CODES:
        parser.error(f"Unknown property-state code(s): {', '.join(sorted(states - STATE_CODES))}")
    output_dir = (args.output_dir or Path(__file__).resolve().parent / "data" / str(args.year)).resolve()
    raw = output_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    manifest_path = output_dir / "manifest.json"
    manifest = {"status": "in_progress", "started_at_utc": started, "reporting_year": args.year,
                "dataset": "Official static snapshot; not the live Data Browser API",
                "documentation": SOURCE_DOCS, "command_arguments": vars(args).copy(),
                "script_sha256": sha256_file(Path(__file__)), "downloads": {}}
    manifest["command_arguments"]["output_dir"] = str(output_dir)
    write_json(manifest_path, manifest)
    try:
        for kind in (["ts"] if args.reference_only else ["ts", "lar"]):
            filename = f"{args.year}_public_{kind}_csv.zip"
            manifest["downloads"][kind] = download(f"{BASE_URL}/{args.year}/{filename}", raw / filename)
            write_json(manifest_path, manifest)
        lenders = read_lenders(raw / f"{args.year}_public_ts_csv.zip", args.year)
        if args.reference_only:
            manifest.update(status="reference_only", lender_reference_rows=len(lenders))
        elif args.download_only:
            manifest["status"] = "download_only"
        else:
            report, outputs = extract_sample(raw / f"{args.year}_public_lar_csv.zip", lenders,
                                             output_dir, args.year, states)
            manifest.update(status="complete", eligible_loans=report["eligible_loans"],
                            outputs=[{"file": p.name, "bytes": p.stat().st_size, "sha256": sha256_file(p)} for p in outputs])
            print(f"Complete: {report['eligible_loans']:,} eligible loans from {report['eligible_lenders']:,} lenders.", flush=True)
        manifest["finished_at_utc"] = utc_now()
        write_json(manifest_path, manifest)
        print(f"Output folder: {output_dir}", flush=True)
        return 0
    except (Exception, KeyboardInterrupt) as error:
        manifest.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed",
                        error=str(error), finished_at_utc=utc_now())
        write_json(manifest_path, manifest)
        print(f"Stopped: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        print("Rerun the same command to reuse verified archives or resume a download. No TLS checks are disabled.", file=sys.stderr)
        return 130 if isinstance(error, KeyboardInterrupt) else 1


if __name__ == "__main__":
    sys.exit(main())
