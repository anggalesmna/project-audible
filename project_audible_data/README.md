# Project Audible — End-to-End HMDA Data & Dashboard Pipeline

Downloads the official static 2025 HMDA snapshot, classifies Fintech vs. Traditional Bank lenders, performs lossless data cleansing and borrower-group binning, computes risk-controlled pricing comparisons, and builds the standalone interactive HTML dashboard (`../Submit/Project Audible Dashboard.html`).

## End-to-End Execution (5 Steps)

Open a terminal in `project_audible_data/` and run the pipeline in sequence:

```sh
# Step 1: Download official 2025 FFIEC HMDA static snapshot & filter to product sample (1,508,076 loans)
python3 download_hmda.py

# Step 2 (downloads the Philadelphia Fed file if missing): Join Philadelphia Fed Lender File & NYU Stern (Fuster et al., 2019) Fintech classification
python3 classify_lenders_nyu.py

# Step 3: Create lossless cleaned copy with numeric fields, review flags, and borrower bins
python3 clean_mortgages.py

# Step 4: Compute borrower-group medians, IQRs, lender comparisons, and robustness checks
python3 analyze_pricing.py

# Step 5: Build standalone interactive HTML dashboard in ../Submit/Project Audible Dashboard.html
python3 build_dashboard.py

# Step 6: Rebuild the Word deliverables
python3 build_position_memo.py
python3 build_technical_memo.py
python3 build_llm_validation_log.py

# Run all unit tests across all pipeline modules
python3 -m unittest -v
```

The 2025 loan archive is approximately **703 MiB compressed**. It is downloaded
once, retained in `data/2025/raw`, and read directly from the ZIP without
extracting the multi-gigabyte national CSV. Processing is sequential and uses
little memory. Allow additional disk space for the filtered CSV. Progress is
printed during both download and processing.

Optional commands:

```sh
# Small connectivity check: download only the lender-name reference.
python3 download_hmda.py --reference-only --output-dir /tmp/hmda_reference_check

# Keep only loans secured by properties in NC or SC, in a separate output folder.
# This still downloads the national snapshot, then filters locally.
python3 download_hmda.py --states NC SC --output-dir data/2025_nc_sc

# A separate reporting year, if its official snapshot is available.
python3 download_hmda.py --year 2024

# Download and cache the original archives without processing.
python3 download_hmda.py --download-only
```

Default output paths are relative to the script, not your terminal's current
directory. `--output-dir` paths are relative to your current directory. Use a
different output folder for each state selection so scope changes do not replace
an earlier extract.

## Files produced

| File | Purpose |
| --- | --- |
| `raw/2025_public_lar_csv.zip` | Untouched official loan-record archive |
| `raw/2025_public_ts_csv.zip` | Untouched official lender-name reference |
| `raw/*.zip.json` | URL, retrieval time, HTTP metadata, size and SHA-256 |
| `mortgages_2025.csv` | Eligible loan-level records with the project's fields and lender names |
| `lender_inventory_2025.csv` | Each sample lender, agency code, headquarters state and eligible loan count |
| `lender_classification_2025.csv` | Initially a blank template; populated by the separate NYU classification step |
| `mortgages_2025_classified.csv` | Derived analysis copy with all original rows and five lender-classification columns |
| `nyu_fintech_reference_2017.csv` | All 18 NYU source lenders and their 2025 match status |
| `nyu_classification_summary.json` | Classification provenance, group counts and output hashes |
| `sample_summary.json` | Filter counts, property-state counts and pricing-field coverage |
| `manifest.json` | Source URLs, run settings, script hash, output hashes and completion status |

The output is complete only when `manifest.json` has `"status": "complete"`.
`reference_only` and `download_only` do not mean a mortgage sample was created.
Completed archives are verified and reused on reruns. Interrupted downloads can
resume when the server's ETag still matches. Network failures are retried, and
TLS certificate validation remains enabled.

## Exact sample

Rules are applied in this order: `action_taken=1`, `loan_type=1`, `loan_purpose=1`,
`lien_status=1`, `occupancy_type=1`, `conforming_loan_limit=C`, `loan_term=360`,
`intro_rate_period=NA`. An optional property-state filter is applied first.
The `NA` test is case-sensitive after trimming whitespace. Numeric introductory
periods, blank values and `Exempt` do not pass.

This implements the pitch's fixed-rate screening rule. Under reporting guidance,
`NA` applies to fixed rates, but can also apply to certain preferred-rate features;
it is not independent verification of every mortgage contract.

No additional property-type or borrower-risk restrictions are silently imposed.
Construction method, unit count, reverse/open-end/business flags and application
channel fields are retained for possible later refinements. Other institution
types remain in the sample until the classification step is completed.

## NYU lender classification

The selected fintech definition uses the cumulative 2017 NYU/Fuster list.
Run the separate classification step after the downloader:

```sh
python3 classify_lenders_nyu.py
```

This step requires `pandas` and `openpyxl`, plus the retained Philadelphia Fed
institution reference in `data/2025/raw`. The downloader itself still uses only
standard-library Python. See [NYU classification guide](NYU_CLASSIFICATION_README.md)
for source details, group definitions, limitations and reproducibility.

Use `mortgages_2025_classified.csv` for subsequent cleaning and dashboard analysis.
It retains all original fields and rows and adds five classification columns.
Keep `mortgages_2025.csv` as the original filtered extract.

`lender_classification_2025.csv` contains one row per sample LEI. `Fintech` means
matched to the historical NYU list; `Bank comparator` uses Philadelphia Fed's
2025 institution type. Credit unions and other lenders remain separate. A lender
not listed by NYU is not automatically non-fintech or a bank. The historical
digital-process labels have not been reverified for 2025.

The downloader never overwrites an existing classification file. On scope or
year changes, regenerate the classification and derived loan copy explicitly.
`--states` means **property location**, not lender headquarters.

## Data handling

Original values are preserved: `NA`, `Exempt`, blanks and zeroes remain distinct.
Missing rate spreads do not remove an otherwise eligible loan. Do not treat
missing fields as zero or assume all metrics have the same coverage. Reported
DTI ranges are kept as text. Income remains in thousands of dollars; loan amounts
and charges are in dollars. The script does not calculate prices or recommendations.

Public HMDA excludes credit scores. Comparisons using this sample describe
observed pricing and cannot fully control for risk or establish causal effects.
Origination charges are not total closing costs. Blank lender credits require
their own reporting interpretation during later cleaning, rather than an
automatic missing-to-zero conversion across all fields.

## Verification

```sh
python3 -m unittest -v
```

Tests cover sample eligibility, geography, raw-value preservation, missing
pricing, duplicate lender identifiers, unexpected years or schemas, edited
classification preservation, interrupted download resumption, cache corruption,
and failure without silently substituting a live dataset.

## Official sources

- [HMDA dataset publication](https://ffiec.cfpb.gov/data-publication/)
- [Official snapshot link definitions](https://github.com/cfpb/hmda-frontend/blob/master/src/data-publication/constants/snapshot-dataset.jsx)
- [Loan-level field definitions](https://ffiec.cfpb.gov/documentation/publications/loan-level-datasets/lar-data-fields)
- [HMDA reporting guidance](https://www.consumerfinance.gov/rules-policy/regulations/1003/4/)

The script uses static snapshot URLs. It never substitutes the live Data Browser
API if a snapshot is unavailable. Retain the original archives and source logs
with your technical memo materials.
