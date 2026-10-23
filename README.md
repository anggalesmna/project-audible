# Project Audible: Fintech vs. Traditional Bank Mortgage Pricing Analysis

Duke University — Master of Engineering in Financial Technology (Fintech)  
**FINTECH 590: Advanced Topics in Fintech**  
Author: **Angga Lesmana** (`angga.lesmana@duke.edu`)

---

## 📌 Executive Summary

Project Audible investigates whether online/Fintech mortgage lenders charge higher or lower interest rate spreads than traditional commercial banks for 30-year fixed-rate conforming mortgages. 

Using the official **2025 FFIEC HMDA static snapshot** (1,508,076 eligible purchase loans) joined with the **Philadelphia Fed Lender File** and **NYU Stern (Fuster et al., 2019)** fintech classifications, the empirical findings demonstrate:

> **Fintech Mortgages Are Priced +16.4 bps Higher on Median Rate Spread Than Traditional Bank Mortgages**  
> In the controlled conforming borrower baseline (valid DTI, CLTV, income, and conforming limits), Fintech median rate spread is **0.750%** (IQR: 0.380% to 1.150%) compared to **0.586%** (IQR: 0.280% to 0.940%) for Traditional Banks. The premium holds persistently across 14 of 16 risk segments and remains statistically significant across multiple robustness specifications.

---

## 📂 Deliverables & Repository Structure

```text
Project Audible/
├── Submit/                                  # Final Deliverables for Grading & Review
│   ├── Project Audible Dashboard.html       # Standalone interactive 3-tab HTML dashboard (clean, minimalist)
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
1. **Overview Tab**: Key executive takeaway (+16.4 bps higher), 4 summary KPI metric cards, and 16-cell Risk Matrix (DTI vs. CLTV) highlighting the Fintech pricing spread.
2. **Segment Drill-Down Tab**: Interactive 4-column filter slicers (DTI, CLTV, Income, Geography) with visual Paired Bar Comparison and Quartile Distribution (IQR) charts.
3. **Lenders & Robustness Tab**: Top 10 Fintech vs. Bank lenders side-by-side comparison, and 4 key sensitivity/robustness checks verifying the persistence of the premium.

*To view the dashboard, simply open `Submit/Project Audible Dashboard.html` in any web browser (Chrome, Safari, Edge, Firefox). It is completely standalone with no internet connection or server required.*

---

## 🛠️ How to Reproduce Analysis

To run the pipeline locally from scratch:

```bash
# Clone the repository
git clone https://github.com/<your-username>/project-audible.git
cd "project-audible/project_audible_data"

# (Optional) Run tests
python3 -m unittest -v

# Run the 5-step analysis pipeline:
python3 download_hmda.py        # Downloads 2025 HMDA archive (~703MB)
python3 classify_lenders_nyu.py # Applies NYU lender classification
python3 clean_mortgages.py      # Cleans and bins data
python3 analyze_pricing.py      # Computes statistics and robustness models
python3 build_dashboard.py      # Generates Submit/Project Audible Dashboard.html
```

---

## 📄 Documentation & Auditability

All analytical design choices, sample definitions, and validation checks are strictly documented in the accompanying Word documents in `Submit/`:
- **Technical Memo**: 1-page concise synthesis of data provenance, conforming baseline parameters, and design trade-offs.
- **LLM Validation Log**: Complete transparent record of prompts, human oversight, model error detections, and corrections across both development phases.
