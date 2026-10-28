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

**Versus other nonbanks, the gap largely disappears.** Against 600 non-fintech independent mortgage banks (Philadelphia Fed TYPE 40/41; 808,681 loans, same filters), the Fintech median rate spread is **−1.2 bps** (rate gap 0.0 bps; fee gap +6.3 bps). The premium points to the nonbank business model rather than a fintech-specific markup. Public HMDA has no credit scores, so these are observed pricing differences, not proof of intent.

**Recommendation for AFC:** launch a voluntary member pricing review **benchmarked against nonbank peers as well as banks**, starting with the segments flagged by `analyze_pricing.py` (`nonbank_priority`) or, if none, origination fees.

---

## 📂 Deliverables & Repository Structure

```text
Project Audible/
├── Submit/                                  # Final Deliverables for Grading & Review
│   ├── Project Audible Dashboard.html       # Standalone interactive 3-tab HTML dashboard (clean, minimalist)
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
│   ├── build_dashboard.py                   # Step 5: Builds the standalone HTML dashboard
│   ├── build_position_memo.py               # Compiles the 2-page Position Memo (.docx)
│   ├── build_technical_memo.py              # Compiles the 1-page Technical Memo (.docx)
│   ├── build_llm_validation_log.py          # Compiles the LLM Validation Log (.docx)
│   ├── test_*.py                            # Comprehensive unit tests for all pipeline modules
│   └── data/2025/
│       ├── analysis/                        # Processed summary tables, slices JSON, pricing summaries
│       └── data_quality/                    # Data quality metrics, missingness tables, cleaning audits
└── README.md                                # Project overview and reproduction instructions
```

---

## 📊 Interactive Dashboard

The interactive dashboard is located at:
`Submit/Project Audible Dashboard.html`

### Features:
1. **Overview Tab**: What → So What → Now What (computed from the data), 4 KPI cards, a benchmark table comparing Fintech with banks and with other nonbanks, and the 16-cell DTI × CLTV risk matrix.
2. **Segment Drill-Down Tab**: Interactive 4-column filter slicers (DTI, CLTV, Income, Geography) with visual Paired Bar Comparison and Quartile Distribution (IQR) charts.
3. **Lenders & Robustness Tab**: Every Fintech lender vs. the bank median, and the robustness table (baseline, Fintech vs. non-fintech nonbanks, incl. DTI ≥50%, site-built only, no review flags, unadjusted) with the baseline lender-clustered 95% CI.

*To view the dashboard, simply open `Submit/Project Audible Dashboard.html` in any web browser (Chrome, Safari, Edge, Firefox). It is completely standalone with no internet connection or server required.*

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
