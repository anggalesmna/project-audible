# Power BI Agentic AI Show & Tell — Live Demo Script & Ground Truth

**Course:** FINTECH 590: Advanced Topics in Fintech (Duke University)  
**Topic:** Show and Tell — AI / Agentic Extensions of Power BI (Lecture 12)  
**Dataset:** `powerbi_demo_data_controlled_baseline.csv` (511,199 loans, 61.6 MB)  
**Architecture:** Power BI Desktop + VS Code (GitHub Copilot Chat) + Power BI Modeling MCP Server

---

## 💻 Hardware & Setup Notes (Intel Core i5 2019)
- **Is a 2019 Core i5 enough?** **Yes, 100% safe.** 
  - A 2019 Intel Core i5 (8th–10th Gen) has 4 cores and 8 threads. Power BI's in-memory engine (VertiPaq) is multi-threaded and highly optimized for x86 CPUs.
  - The curated demo CSV is **61.6 MB**. In Power BI, VertiPaq compresses this to **~15–20 MB of RAM**.
  - Query response times for DAX calculations (including `MEDIAN`) take **under 150 milliseconds**.
  - *Tip:* Close resource-heavy apps (e.g. 50 Chrome tabs) before starting Power BI Desktop and VS Code.

---

## 🎬 3-Phase Live Demo Flow (3–4 Minutes)

### Phase 1: Natural Language Data Q&A (Ad-Hoc Exploration)
*Demonstrates: The AI agent autonomously inspects the model schema, writes DAX queries behind the scenes, and executes them against Power BI's local engine.*

#### Prompt 1.1: Highest Interest Rate Fintech
> **You type in VS Code Copilot Chat:**  
> `"Which Fintech lender has the highest median interest rate in our dataset, and what is that rate?"`
>
> **What the Agent Does:**  
> Queries `MEDIAN(Loans[interest_rate])` grouped by `lender_name` where `lender_type = "Fintech"`.
>
> **Ground Truth Verification:**  
> - **Top Lender:** `EVERETT FINANCIAL, INC.`
> - **Median Interest Rate:** `6.875%` (5,561 loans)  
> - *(Runner up: American Neighborhood Mortgage Acceptance Co. at 6.750%)*

#### Prompt 1.2: Largest Fintech by Volume
> **You type in VS Code Copilot Chat:**  
> `"Show me the top 3 Fintech lenders by loan volume and their share of total Fintech loans."`
>
> **Ground Truth Verification:**  
> 1. `ROCKET MORTGAGE`: **81,415 loans** (~47.0%)
> 2. `GUARANTEED RATE, INC.`: **26,840 loans** (~15.5%)
> 3. `MOVEMENT MORTGAGE, LLC`: **20,341 loans** (~11.8%)

---

### Phase 2: Agentic Modeling & Measure Creation
*Demonstrates: The AI agent acts as an autonomous data engineer, writing production DAX and injecting measures directly into the Power BI semantic model without touching the GUI.*

#### Prompt 2.1: Authoring Baseline Measures
> **You type in VS Code Copilot Chat:**  
> `"Create two DAX measures in the Loans table:`  
> `1. 'Fintech Median Spread' calculating the median rate_spread for Fintech loans.`  
> `2. 'Bank Median Spread' calculating the median rate_spread for Bank comparator loans."`
>
> **Expected DAX Generated:**
> ```dax
> Fintech Median Spread = 
> CALCULATE(
>     MEDIAN(Loans[rate_spread]),
>     Loans[lender_type] = "Fintech"
> )
> ```
> ```dax
> Bank Median Spread = 
> CALCULATE(
>     MEDIAN(Loans[rate_spread]),
>     Loans[lender_type] = "Bank comparator"
> )
> ```

#### Prompt 2.2: Authoring the Headline Pricing Gap
> **You type in VS Code Copilot Chat:**  
> `"Now create a measure called 'Rate Spread Gap (bps)' that computes the difference between Fintech Median Spread and Bank Median Spread, multiplied by 100 to convert to basis points."`
>
> **Expected DAX Generated:**
> ```dax
> Rate Spread Gap (bps) = 
> ([Fintech Median Spread] - [Bank Median Spread]) * 100
> ```
>
> **Ground Truth Verification:**  
> - When displayed on a Card visual in Power BI, the result should read: **`+16.4 bps`** (or `16.36 bps`).  
> - *Fintech:* `0.213%`  
> - *Bank:* `0.049%`

---

### Phase 3: Human-in-the-Loop Validation & Critical Thinking ("The Tell")
*Demonstrates to your professor: You understand the difference between AI execution and domain validation. You are not blindly trusting the LLM.*

#### Prompt 3.1: Probing Risk Segmentation
> **You type in VS Code Copilot Chat:**  
> `"Calculate the Rate Spread Gap across the 4 CLTV groups. Which borrower segment faces the highest gap?"`
>
> **Ground Truth Verification:**  
> - `CLTV <= 80%`: **+11.9 bps**  
> - `CLTV 80.01% - 90%`: **+13.5 bps**  
> - `CLTV 90.01% - 95%`: **+16.6 bps**  
> - `CLTV > 95%` (Low down payment): **+30.3 bps** (peaks over +31 bps in 2-way matrix)  
>
> **Talking Point for Class ("The Tell"):**  
> *"Notice that the agent successfully extracted that low-down-payment borrowers face 2.5x the pricing gap of 20%-down borrowers. However, as human analysts, we know HMDA omits borrower credit scores (FICO). The agent cannot tell you whether this +30 bps gap is price discrimination or unobserved credit risk—that requires human domain knowledge."*

---

## 📋 Quick Talking Points for Presentation

1. **What was shown:**
   - Power BI Desktop holding 511,199 loans in memory.
   - VS Code using GitHub Copilot paired with the **Power BI Modeling MCP Server**.
   - Zero manual DAX writing: the agent reasoned over the schema, executed queries, and injected production measures.

2. **The "Agentic" advantage:**
   - Fast, reproducible, and eliminates syntax errors in complex DAX calculations.
   - Allows natural language querying for ad-hoc business questions.

3. **The Limitation & Human Ownership:**
   - Agentic tools build the *model* and *measures*, but report layout / storytelling still requires human curation.
   - Aggregations like `MEDIAN` vs `AVERAGE` can be hallucinated or chosen incorrectly by AI if prompts aren't mathematically specific.
