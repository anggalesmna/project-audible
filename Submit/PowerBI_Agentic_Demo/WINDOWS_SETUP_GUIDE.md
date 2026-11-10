# Step-by-Step Setup Guide on Windows (15 Minutes)

Follow these steps once on your Windows laptop:

---

### Step 1: Install Power BI Desktop & VS Code (if not already installed)
1. **Power BI Desktop:** Download and install free from the Microsoft Store or [powerbi.microsoft.com/desktop](https://powerbi.microsoft.com/desktop).
2. **Visual Studio Code:** Download and install from [code.visualstudio.com](https://code.visualstudio.com).

---

### Step 2: Install VS Code Extensions
Open VS Code, press `Ctrl + Shift + X` (Extensions Marketplace), and install:
1. **GitHub Copilot** (by GitHub)
2. **GitHub Copilot Chat** (by GitHub)
3. **Power BI Modeling MCP Server** (search `Power BI Modeling` or `Power BI MCP` in the Marketplace, by Microsoft/Analysis Services).

*Note: Sign in to GitHub Copilot using your GitHub account (your Duke email gives you free GitHub Student/Education Copilot if you have verified it).*

---

### Step 3: Load the Demo Dataset in Power BI Desktop
1. Copy `powerbi_demo_data_controlled_baseline.csv` to your Windows laptop (via USB drive, Google Drive, OneDrive, or git pull).
2. Open **Power BI Desktop**.
3. Click **Get Data** $\rightarrow$ **Text/CSV** $\rightarrow$ Select `powerbi_demo_data_controlled_baseline.csv`.
4. Click **Load** (takes about 5–10 seconds).
5. Name the table `Loans` (in the right-hand Fields pane, rename if necessary).
6. **Important:** Leave Power BI Desktop open! The MCP extension talks to Power BI Desktop while it is running.

---

### Step 4: Connect VS Code to Power BI Desktop
1. Open VS Code.
2. Open **Copilot Chat** (`Ctrl + Alt + I` or click the chat bubble icon on the left sidebar).
3. Ensure the Power BI Modeling MCP tools are enabled (a small plug/tools icon in Copilot Chat will list Power BI tools like `execute_dax_query`, `create_measure`, etc.).
4. Test connectivity by typing:
   > `"Can you see my active Power BI model? What tables are loaded?"`
   
   *Copilot should reply: "Yes, I see the Loans table with columns like lender_name, rate_spread, interest_rate..."*

---

### Step 5: Run the Demo Script
Follow the prompts in `DEMO_PROMPT_SCRIPT.md`!
