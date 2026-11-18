# Project Audible: Fintech vs. Traditional Bank Mortgage Pricing Analysis

Duke University — Master of Engineering in Financial Technology (Fintech)  
**FINTECH 590: Advanced Topics in Fintech**  
Author: **Angga Lesmana** & **Violla Tania**

---

## 📌 Executive Summary

Project Audible investigates whether online/Fintech mortgage lenders charge higher or lower interest rate spreads than traditional commercial banks for 30-year fixed-rate conforming mortgages. 

Using the official **2025 FFIEC HMDA static snapshot** (1,508,076 eligible purchase loans) joined with the **Philadelphia Fed Lender File** and **NYU Stern (Fuster et al., 2019)** fintech classifications, the empirical findings demonstrate:

> **Fintech Mortgages Cost +16.4 bps More Than Bank Mortgages, in Line With Other Nonbank Lenders**  
> In the controlled baseline (valid DTI, CLTV, income and loan amount; DTI below 50%; 511,199 loans), the Fintech median rate spread is **0.213%** (IQR: −0.053% to 0.518%; 173,033 loans, 14 lenders) compared with **0.049%** (IQR: −0.190% to 0.325%; 338,166 loans, 655 banks) for traditional banks. Fintech pricing is higher in **all 16 of 16** standard DTI × CLTV segments; 12 of 14 Fintech lenders sit above the bank median (11 of 14 by 5 bps or more). The unadjusted full sample gives +17.2 bps (lender-clustered 95% CI: +12.2 to +25.3 bps).

**Versus other nonbanks, the gap largely disappears.** Against 600 non-fintech independent mortgage banks (Philadelphia Fed TYPE 40/41; 808,681 loans, same filters), the Fintech median rate spread is **−1.2 bps** (rate gap 0.0 bps; fee gap +6.4 bps). The premium points to the nonbank business model rather than a fintech-specific markup. Public HMDA has no credit scores, so these are observed pricing differences, not proof of intent.

**Recommendation for AFC:** launch a voluntary member pricing review **benchmarked against nonbank peers as well as banks**, starting with the segments flagged by `analyze_pricing.py` (`nonbank_priority`) or, if none, origination fees.

---

## 📂 Deliverables & Repository Structure

```text
Project Audible/
├── Submit/                                  # Final Deliverables for Grading & Review
│   ├── Project Audible Dashboard.html       # 3-page HTML dashboard: Executive, Analyst, Regulator
│   ├── Project Audible Position Memo.docx   # 2-page position memo for AFC leadership (recommendation first)
│   ├── Project Audible Technical Memo.docx  # Strictly 1-page technical memo (data provenance, design choices)
│   └── Project Audible LLM Validation Log.docx # Full audit log of human-led AI pair programming & corrections
├── Project Audible Initial Pitch AFC.docx   # Approved project pitch & methodology framework
├── Project Audible Rubric.docx              # Project evaluation rubric & criteria
├── project_audible_data/                    # Complete Python analytical pipeline & tests
│   ├── download_hmda.py                     # Step 1: Download official HMDA 2025 static snapshot
│   ├── classify_lenders_nyu.py              # Step 2: NYU Stern lender classification algorithm
│   ├── clean_mortgages.py                   # Step 3: Lossless data cleaning, validation & risk binning
│   ├── analyze_pricing.py                   # Step 4: Stratified pricing medians, IQRs & robustness tests
│   ├── build_dashboard.py                   # Step 5: Builds the 3-page HTML dashboard
│   ├── check_source.py                      # Live FFIEC source check (ETag / Last-Modified)
│   ├── build_position_memo.py               # Compiles the 2-page Position Memo (.docx)
│   ├── build_technical_memo.py              # Compiles the 1-page Technical Memo (.docx)
│   ├── build_llm_validation_log.py          # Compiles the LLM Validation Log (.docx)
│   ├── test_*.py                            # Comprehensive unit tests for all pipeline modules
│   └── data/2025/
│       ├── analysis/                        # Processed summary tables, slices JSON, pricing summaries
│       └── data_quality/                    # Data quality metrics, missingness tables, cleaning audits
├── run_demo.sh                              # Cold-start demo: tests → source check → build → open
└── README.md                                # Project overview and reproduction instructions
```

---

## 📊 Capstone Dashboard (three audience pages, one data model)

`Submit/Project Audible Dashboard.html`: a single self-contained HTML file (no CDN, no server, no internet needed).

| Page | Panel | Question it answers | What is on it |
|---|---|---|---|
| **Executive · Decision** | Executive | What should AFC do? | Recommendation as title (`as of 2026-06-23`); three-step KPI chain (`What → So What → Now What` with `~$1,117` upfront fee context on `$300k` loans); 4-row priority dot plot (`All loans`, `Loan ≤$200k`, `Income ≤$75k`, `CLTV >95%`); next steps. No filters. |
| **Analyst · Evidence & Risk** | Risk | When would we be wrong? | Click-to-drill DTI × CLTV matrix; median + IQR comparison (with coverage badge & Reset); segment and 14-lender charts with `[vs. Banks | vs. Nonbank Peers]` & `[Rate spread | Origination fee]` toggles and Action Titles; 6-row "What would change our recommendation" table (including the 5-spec sample range and 95% CI). |
| **Regulator · Traceability** | Compliance | Can every number be traced? | Fact ledger `F-01`–`F-12` (value, formula/field, JSON key, `As-of`, `Used in`); data lineage 13.5M → 511,199; fixed parameters; sources with versions and SHA-256; live FFIEC source check; what the analysis does not claim. |

All pages read the same numbers from the pipeline outputs at build time, stamp the unified `2026-06-23` snapshot as-of date, expose Fact Ledger hover tooltips (`F-01`–`F-12`), and use round-half-up formatting identical to the Word memos. Open a page directly with `#analyst` or `#reg` at the end of the file URL.

### Tufte Visual Audit Log (`V-01`–`V-06`)

Peer-audited across Executive (`E`), Analyst (`R`), and Compliance (`C`) views. All bars use explicit zero baselines; mixed-sign spreads use dot plots (`Lie Factor = 1.00`).

| Visual | Page | Ink | Junk | Lie (LF) | Integ. | Density | Change made (peer-audited: Violla Tania) |
|---|---|---|---|---|---|---|---|
| **V-01** | Executive | ✓ | ✓ | ✓ LF 1.0 | ✓ | ✓ | Collapsed duplicate What/So What/Now What bullets into 3 KPI chain cards; added `$1,117` dollar fee context (`F-06`). |
| **V-02** | Executive | ✓ | ✓ | ✓ LF 1.0 | ✓ | ✓ | Trimmed dumbbell from 6 to 4 priority rows; aligned vs.-bank dot color to amber (`≥ +5 bps`); stamped `bps` units & `As-of`. |
| **V-03** | Analyst | ✓ | ✓ | ✓ LF 1.0 | ✓ | ✓ | Removed redundant 3-KPI slice bar & dropdown slicers; matrix click drives drill-down with `[F-08]` tooltip. |
| **V-04** | Analyst | ✓ | ✓ | ✓ LF 1.0 | ✓ | ✓ | Fixed origination-fee bar baseline explicitly at `0%` (scale `0–2%`, `LF = 1.00`); labeled `−0.6%` to `+1.2%` scale on IQR chart. |
| **V-05** | Analyst | ✓ | ✓ | ✓ LF 1.0 | ✓ | ✓ | Added `[vs. Banks \| vs. Nonbank Peers]` & `[Rate spread \| Origination fee]` toggles to segment/lender charts; switched to Action Titles. |
| **V-06** | Regulator | ✓ | ✓ | ✓ LF 1.0 | ✓ | ✓ | Added `As-of` and `Used-in (E·R·C)` columns to Fact Ledger `F-01`–`F-12`, hover tooltips across pages, and folded robustness into decision rules. |

### Run it (cold start, no manual steps)

```bash
./run_demo.sh          # unit tests → live FFIEC source check → rebuild dashboard & 3 Word memos → open it
./run_demo.sh --full   # rerun all five pipeline steps from the FFIEC download first (~700 MB)
```

`check_source.py` sends a HEAD request to the FFIEC files listed in `data/2025/manifest.json` and compares ETag and Last-Modified with the archive that was analysed; the result (`match` / `changed` / `unreachable`) is shown on the Regulator page.

---

## 🛠️ How to Reproduce Analysis

To run the pipeline locally from scratch:

```bash
# Clone the repository
git clone https://github.com/anggalesmna/project-audible.git
cd "project-audible/project_audible_data"
pip install pandas openpyxl   # needed for step 2 only; everything else is standard library

# (Optional) Run tests
python3 -m unittest -v

# Run the 5-step analysis pipeline:
python3 download_hmda.py        # Downloads 2025 HMDA archive (~703MB)
python3 classify_lenders_nyu.py # Downloads the Philadelphia Fed lender file if missing, applies NYU classification
python3 clean_mortgages.py      # Cleans and bins data
python3 analyze_pricing.py      # Computes statistics and robustness checks
python3 check_source.py         # Optional: live check that FFIEC still publishes the same files
python3 build_dashboard.py      # Generates Submit/Project Audible Dashboard.html
                                # (--from-json rebuilds the HTML from saved results without the loan-level CSV)

# Rebuild the Word deliverables
python3 build_position_memo.py
python3 build_technical_memo.py
python3 build_llm_validation_log.py
```

**Inputs not stored in Git** (size limits; see `.gitignore`): the two HMDA ZIP archives, the Philadelphia Fed workbook and the loan-level CSVs. `download_hmda.py` and `classify_lenders_nyu.py` fetch them. If the Philadelphia Fed download is blocked, download `hmda-2018-present.xlsx` from the [HMDA Lender File page](https://www.philadelphiafed.org/surveys-and-data/consumer-finance-data/home-mortgage-disclosure-act-lender-file) and save it as `project_audible_data/data/2025/raw/hmda_lender_2018_2025_philadelphia_fed.xlsx`, or pass `--institution-reference <path>`. The NYU workbook (`data/2025/fintech_classification.xlsx`) is committed.

---

## 📄 Documentation & Auditability

All analytical design choices, sample definitions, and validation checks are strictly documented in the accompanying Word documents in `Submit/`:
- **Technical Memo**: 1-page concise synthesis of data provenance, conforming baseline parameters, and design trade-offs.
- **LLM Validation Log**: Complete transparent record of prompts, human oversight, model error detections, and corrections across all development sessions, including the teammate review session.
