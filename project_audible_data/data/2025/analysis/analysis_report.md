# Project Audible — Step 1 & 2 Pricing Analysis Report (2025 HMDA)

Generated: 2026-10-23T01:03:34+00:00 by `analyze_pricing.py`.

## 1. Headline Finding & AFC Decision Implication

- **Unadjusted National Median Rate Spread**: Fintech **0.217%** (n = 175,754) vs. Bank Comparator **0.045%** (n = 346,999) -> **+17.2 bps** higher at Fintech (order-statistic 95% CI: `+16.9` to `+17.5` bps; lender-clustered 95% CI: `+12.2` to `+25.3` bps).
- **Composition-Controlled 4-Way Cell Average Gap** (across 200 DTI x CLTV x Income x Loan Amount cells with >=25 loans per side): **+15.7 bps** (Fintech weights) / **+16.5 bps** (Bank weights). Fintech median spread is higher in **198 of 200** cells.
- **DTI x CLTV Risk Matrix**: Of 20 cells, **17** meet the sufficient-coverage threshold (>=100 loans/side, >=3 Fintech lenders, >=10 Bank lenders). Fintech pricing is meaningfully higher (>= +5 bps) in **16 of 17** covered cells.
- **Persistence Across Lenders**: **13 of 15** NYU Fintech lenders have a median rate spread above the Bank comparator median; equal-weighted lender-median gap is **+15.8 bps**.
- **Supporting Measures**: Fintech median interest rate is **6.625%** vs. **6.500%** at banks (**+12.5 bps**), and Fintech median origination charges are **0.956%** of loan amount vs. **0.568%** at banks (**+38.8 bps**).

## 2. Robustness Checks

| Specification | Fintech Loans | Bank Loans | Fintech Med Spread | Bank Med Spread | Spread Gap (bps) | Rate Gap (bps) | Orig Fee Gap (bps) |
|---|---:|---:|---:|---:|---:|---:|---:|
| National — all eligible loans | 175,754 | 346,999 | 0.217% | 0.045% | **+17.2** | +12.5 | +38.8 |
| National — controlled sample (all 4 borrower vars valid) | 173,253 | 339,609 | 0.213% | 0.049% | **+16.4** | +12.5 | +37.3 |
| Site-built 1-unit properties only (excl. manufactured & multi-unit) | 169,156 | 338,811 | 0.205% | 0.043% | **+16.2** | +12.5 | +36.8 |
| Excluding 21st Mortgage (manufactured-housing specialist) | 174,081 | 346,999 | 0.212% | 0.045% | **+16.7** | +12.5 | +37.4 |
| Excluding all review-flagged loans | 175,540 | 346,049 | 0.217% | 0.046% | **+17.1** | +12.5 | +38.7 |

## 3. Single-Dimension Borrower Group Comparisons

| Dimension | Group | Fintech Loans | Bank Loans | Fintech Med Spread | Bank Med Spread | Spread Gap (bps) | Rate Gap (bps) | Orig Fee Gap (bps) | Status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `dti_group` | <30% | 31,122 | 79,062 | 0.152% | -0.004% | **+15.6** | +12.5 | +40.3 | Fintech higher (+5 bps or more) |
| `dti_group` | 30%-<36% | 28,507 | 64,841 | 0.201% | 0.035% | **+16.6** | +12.5 | +37.0 | Fintech higher (+5 bps or more) |
| `dti_group` | 36%-43% | 54,011 | 111,330 | 0.236% | 0.064% | **+17.2** | +12.5 | +34.4 | Fintech higher (+5 bps or more) |
| `dti_group` | 44%-49% | 61,334 | 89,917 | 0.241% | 0.083% | **+15.8** | +12.5 | +40.7 | Fintech higher (+5 bps or more) |
| `dti_group` | >=50% | 719 | 1,478 | 1.944% | -0.029% | **+197.3** | +199.5 | +163.8 | Fintech higher (+5 bps or more) |
| `cltv_group` | <=80% | 83,281 | 177,123 | 0.053% | -0.066% | **+11.9** | +7.5 | +34.4 | Fintech higher (+5 bps or more) |
| `cltv_group` | 80.01%-90% | 28,191 | 52,134 | 0.229% | 0.094% | **+13.5** | +12.5 | +37.8 | Fintech higher (+5 bps or more) |
| `cltv_group` | 90.01%-95% | 38,677 | 64,222 | 0.413% | 0.247% | **+16.6** | +12.5 | +38.3 | Fintech higher (+5 bps or more) |
| `cltv_group` | >95% | 23,925 | 53,494 | 0.538% | 0.235% | **+30.3** | +25.0 | +42.7 | Fintech higher (+5 bps or more) |
| `income_group` | <=$75k | 41,603 | 91,568 | 0.221% | 0.034% | **+18.7** | +7.2 | +57.9 | Fintech higher (+5 bps or more) |
| `income_group` | $75k-$125k | 52,385 | 102,154 | 0.236% | 0.073% | **+16.3** | +12.5 | +42.0 | Fintech higher (+5 bps or more) |
| `income_group` | $125k-$200k | 46,483 | 83,569 | 0.221% | 0.070% | **+15.1** | +0.0 | +32.1 | Fintech higher (+5 bps or more) |
| `income_group` | >$200k | 34,462 | 62,364 | 0.184% | 0.005% | **+17.9** | +5.0 | +19.4 | Fintech higher (+5 bps or more) |
| `loan_amount_group` | <=$200k | 32,915 | 84,036 | 0.331% | 0.094% | **+23.7** | +12.5 | +69.5 | Fintech higher (+5 bps or more) |
| `loan_amount_group` | $200k-$350k | 62,919 | 130,059 | 0.237% | 0.060% | **+17.7** | +12.5 | +43.5 | Fintech higher (+5 bps or more) |
| `loan_amount_group` | $350k-$500k | 39,721 | 68,494 | 0.195% | 0.050% | **+14.5** | +12.5 | +35.9 | Fintech higher (+5 bps or more) |
| `loan_amount_group` | >$500k | 40,199 | 64,410 | 0.140% | -0.045% | **+18.5** | +12.5 | +13.1 | Fintech higher (+5 bps or more) |

## 4. Two-Way Risk Matrix: DTI x CLTV (20 Cells)

| DTI Group | CLTV Group | Fintech Loans | Bank Loans | Fintech Med Spread | Bank Med Spread | Gap (bps) | Ex-Rocket Gap (bps) | Orig Fee Gap (bps) | Status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| <30% | <=80% | 19,317 | 48,964 | 0.055% | -0.073% | **+12.8** | +13.9 | +36.8 | Fintech higher (+5 bps or more) |
| <30% | 80.01%-90% | 4,393 | 10,668 | 0.208% | 0.071% | **+13.7** | +14.3 | +41.4 | Fintech higher (+5 bps or more) |
| <30% | 90.01%-95% | 4,373 | 10,087 | 0.372% | 0.220% | **+15.2** | +13.8 | +39.8 | Fintech higher (+5 bps or more) |
| <30% | >95% | 2,655 | 7,446 | 0.546% | 0.234% | **+31.2** | +25.8 | +49.5 | Fintech higher (+5 bps or more) |
| 30%-<36% | <=80% | 13,824 | 31,744 | 0.047% | -0.066% | **+11.3** | +14.0 | +33.3 | Fintech higher (+5 bps or more) |
| 30%-<36% | 80.01%-90% | 4,694 | 10,067 | 0.226% | 0.076% | **+14.9** | +15.9 | +33.0 | Fintech higher (+5 bps or more) |
| 30%-<36% | 90.01%-95% | 5,764 | 11,531 | 0.392% | 0.219% | **+17.3** | +17.4 | +38.4 | Fintech higher (+5 bps or more) |
| 30%-<36% | >95% | 3,862 | 10,131 | 0.535% | 0.219% | **+31.6** | +29.5 | +45.3 | Fintech higher (+5 bps or more) |
| 36%-43% | <=80% | 22,847 | 48,543 | 0.059% | -0.059% | **+11.8** | +14.2 | +29.8 | Fintech higher (+5 bps or more) |
| 36%-43% | 80.01%-90% | 8,915 | 16,794 | 0.222% | 0.093% | **+12.9** | +15.2 | +35.7 | Fintech higher (+5 bps or more) |
| 36%-43% | 90.01%-95% | 12,968 | 22,247 | 0.408% | 0.241% | **+16.7** | +18.1 | +35.2 | Fintech higher (+5 bps or more) |
| 36%-43% | >95% | 8,619 | 21,558 | 0.522% | 0.232% | **+29.0** | +29.3 | +37.7 | Fintech higher (+5 bps or more) |
| 44%-49% | <=80% | 26,840 | 43,180 | 0.052% | -0.054% | **+10.6** | +14.0 | +37.7 | Fintech higher (+5 bps or more) |
| 44%-49% | 80.01%-90% | 10,026 | 13,319 | 0.249% | 0.146% | **+10.3** | +13.5 | +41.2 | Fintech higher (+5 bps or more) |
| 44%-49% | 90.01%-95% | 15,292 | 18,730 | 0.444% | 0.306% | **+13.8** | +18.3 | +42.3 | Fintech higher (+5 bps or more) |
| 44%-49% | >95% | 8,644 | 13,157 | 0.556% | 0.277% | **+27.9** | +31.4 | +42.9 | Fintech higher (+5 bps or more) |
| >=50% | <=80% | 133 | 689 | 0.124% | 0.289% | **-16.5** | -13.8 | +7.7 | Fintech lower (-5 bps or more) |
| >=50% | 80.01%-90% | 33 | 201 | 0.231% | 0.063% | **+16.8** | +16.8 | +47.3 | Insufficient coverage |
| >=50% | 90.01%-95% | 37 | 212 | 0.600% | -0.289% | **+88.9** | +86.7 | +131.3 | Insufficient coverage |
| >=50% | >95% | 17 | 341 | 0.787% | -0.563% | **+135.0** | +143.7 | +80.4 | Insufficient coverage |

## 5. Individual Fintech Lenders vs. Bank Benchmark

| Fintech Lender | Loans | Share (%) | Med Rate Spread | Gap vs Bank Med (bps) | Med Interest Rate | Med Orig Charges (% Loan) |
|---|---:|---:|---:|---:|---:|---:|
| ROCKET MORTGAGE | 82,109 | 46.7% | 0.202% | **+15.7** | 6.625% | 1.080% |
| GUARANTEED RATE, INC. | 27,081 | 15.4% | 0.212% | **+16.7** | 6.625% | 0.643% |
| MOVEMENT MORTGAGE, LLC | 20,440 | 11.6% | 0.203% | **+15.8** | 6.625% | 0.844% |
| loanDepot.com LLC | 15,776 | 9.0% | 0.059% | **+1.4** | 6.500% | 0.881% |
| EVERETT FINANCIAL, INC. | 5,586 | 3.2% | 0.497% | **+45.2** | 6.875% | 1.552% |
| ARK-LA-TEX FINANCIAL SERVICES LLC | 5,534 | 3.1% | 0.254% | **+20.9** | 6.625% | 0.558% |
| American Neighborhood Mortgage Acceptance Company | 4,931 | 2.8% | 0.389% | **+34.4** | 6.750% | 1.058% |
| Better Mortgage Corporation | 3,375 | 1.9% | 0.166% | **+12.1** | 6.625% | 0.854% |
| ENVOY MORTGAGE, LTD | 2,770 | 1.6% | 0.278% | **+23.3** | 6.625% | 0.816% |
| EVERGREEN MONEYSOURCE MORTGAGE COMPANY | 2,292 | 1.3% | 0.281% | **+23.6** | 6.625% | 1.474% |
| Acrisure Mortgage, LLC | 2,027 | 1.1% | 0.032% | **-1.3** | 6.490% | 0.879% |
| MORTGAGE INVESTORS GROUP | 1,828 | 1.0% | 0.220% | **+17.5** | 6.625% | 0.878% |
| 21ST MORTGAGE | 1,673 | 0.9% | 2.152% | **+210.7** | 8.560% | 2.432% |
| AMERISAVE MORTGAGE COMPANY | 315 | 0.2% | 0.318% | **+27.3** | 6.625% | 1.647% |
| American Internet Mortgage, Inc. | 191 | 0.1% | -0.209% | **-25.4** | 6.375% | 0.337% |

## 6. Top 15 Property States by Sample Volume ( plus NC)

| State | Fintech Loans | Bank Loans | Fintech Med Spread | Bank Med Spread | Gap (bps) | Orig Fee Gap (bps) | Status |
|---|---:|---:|---:|---:|---:|---:|---|
| TX | 13,944 | 21,733 | 0.177% | 0.019% | **+15.8** | +53.7 | Fintech higher (+5 bps or more) |
| FL | 12,794 | 16,550 | 0.230% | 0.022% | **+20.8** | +60.6 | Fintech higher (+5 bps or more) |
| CA | 15,681 | 13,432 | 0.139% | -0.081% | **+22.0** | +28.3 | Fintech higher (+5 bps or more) |
| IL | 9,143 | 18,409 | 0.370% | 0.148% | **+22.2** | +23.1 | Fintech higher (+5 bps or more) |
| OH | 5,753 | 21,052 | 0.316% | 0.103% | **+21.3** | +51.2 | Fintech higher (+5 bps or more) |
| NY | 5,221 | 19,604 | 0.193% | -0.047% | **+24.0** | +41.2 | Fintech higher (+5 bps or more) |
| PA | 8,626 | 15,541 | 0.201% | 0.069% | **+13.2** | +33.9 | Fintech higher (+5 bps or more) |
| NC | 8,195 | 12,410 | 0.192% | 0.018% | **+17.4** | +32.4 | Fintech higher (+5 bps or more) |
| MI | 6,951 | 12,487 | 0.335% | 0.137% | **+19.8** | +35.8 | Fintech higher (+5 bps or more) |
| GA | 6,673 | 11,109 | 0.215% | 0.050% | **+16.5** | +50.8 | Fintech higher (+5 bps or more) |
| NJ | 7,034 | 9,207 | 0.167% | -0.112% | **+27.9** | +27.8 | Fintech higher (+5 bps or more) |
| MN | 3,513 | 12,376 | 0.293% | 0.097% | **+19.6** | +30.5 | Fintech higher (+5 bps or more) |
| TN | 5,210 | 9,054 | 0.188% | 0.020% | **+16.8** | +43.1 | Fintech higher (+5 bps or more) |
| IN | 3,036 | 10,353 | 0.347% | 0.162% | **+18.5** | +62.4 | Fintech higher (+5 bps or more) |
| MA | 4,678 | 8,622 | 0.147% | -0.155% | **+30.2** | +12.9 | Fintech higher (+5 bps or more) |
