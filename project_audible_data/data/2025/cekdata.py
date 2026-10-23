# %% [markdown]
# # Eksplorasi & Pengecekan Data: Mortgages 2025 (`mortgages_2025.csv`)
# File ini menggunakan format cell interaktif (`# %%`). Anda dapat menjalankannya
# baris-per-baris atau blok-per-blok di VS Code / IDE, atau langsung via `python3 cekdata.py`.
# Silakan tambahkan kode pengecekan baru Anda di bagian paling bawah.

# %%
import time
from pathlib import Path
import pandas as pd
import numpy as np

# Konfigurasi path file data (prioritaskan dataset berlabel klasifikasi jika tersedia)
CURRENT_DIR = Path(__file__).resolve().parent if "__file__" in locals() else Path(".")
CLASSIFIED_PATH = CURRENT_DIR / "mortgages_2025_classified.csv"
DATA_PATH = CLASSIFIED_PATH if CLASSIFIED_PATH.exists() else CURRENT_DIR / "mortgages_2025.csv"

print(f"[*] Memuat data dari: {DATA_PATH}")
start_time = time.time()

# Memuat data (menangani nilai NA, Exempt, dan string kosong khas data HMDA)
df = pd.read_csv(
    DATA_PATH,
    low_memory=False,
    na_values=["NA", "Exempt", ""],
)
print(f"[✓] Data berhasil dimuat dalam {time.time() - start_time:.2f} detik.")
print(f"    Dimensi: {df.shape[0]:,} baris x {df.shape[1]} kolom")

# %% [markdown]
# ## 1. Struktur Data & Penggunaan Memori
# Menampilkan total baris, kolom, estimasi memori, serta tipe data masing-masing kolom.

# %%
mem_usage_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)
print("=" * 70)
print("1. STRUKTUR & DIMENSI DATA")
print("=" * 70)
print(f"Total Baris    : {df.shape[0]:,}")
print(f"Total Kolom    : {df.shape[1]:,}")
print(f"Estimasi Memori: {mem_usage_mb:.2f} MB\n")

col_summary = pd.DataFrame({
    "No": range(1, len(df.columns) + 1),
    "Kolom": df.columns,
    "Tipe Data": df.dtypes.values,
    "Valid Count": df.notnull().sum().values,
    "Missing Count": df.isnull().sum().values,
    "Missing (%)": ((df.isnull().sum() / len(df)) * 100).round(2).values,
})

pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)
pd.set_option("display.width", 1000)
print(col_summary.to_string(index=False))

# %% [markdown]
# ## 2. Analisis Missing Values (Nilai Kosong)
# Menampilkan kolom-kolom yang memiliki nilai kosong diurutkan dari yang terbanyak.

# %%
print("\n" + "=" * 70)
print("2. ANALISIS MISSING VALUES (NILAI KOSONG)")
print("=" * 70)

missing_only = col_summary[col_summary["Missing Count"] > 0].sort_values(
    by="Missing Count", ascending=False
).reset_index(drop=True)

no_missing = col_summary[col_summary["Missing Count"] == 0].reset_index(drop=True)

print(f"- Kolom dengan missing values : {len(missing_only)} dari {len(df.columns)} kolom")
print(f"- Kolom yang 100% lengkap       : {len(no_missing)} kolom\n")

print("-" * 70)
print("Tabel Kolom yang Memiliki Missing Values:")
print("-" * 70)
print(missing_only.to_string(index=False))

# %% [markdown]
# ## 3. Kolom yang 100% Lengkap (0% Missing)

# %%
print("\n" + "-" * 70)
print(f"Kolom Lengkap (0% Missing) [{len(no_missing)} kolom]:")
print("-" * 70)
print(", ".join(no_missing["Kolom"].tolist()))

# %% [markdown]
# ## 4. Preview Data (5 Baris Pertama)

# %%
print("\n" + "=" * 70)
print("4. PREVIEW DATA (5 Baris Pertama)")
print("=" * 70)
pd.set_option("display.max_columns", 10)
print(df.head())

# %% [markdown]
# ## 5. Statistik Deskriptif Kolom Numerik Kunci

# %%
key_numeric_cols = [
    "loan_amount", "interest_rate", "rate_spread", "total_loan_costs",
    "combined_loan_to_value_ratio", "income", "loan_term"
]
print("\n" + "=" * 70)
print("5. RINGKASAN STATISTIK DESKRIPTIF")
print("=" * 70)
print(df[key_numeric_cols].describe().T)

# %% [markdown]
# ---
# ## 6. Tambahkan Kode Pengecekan Lanjutan di Bawah Ini:
# Anda bisa langsung menambahkan cell `# %%` baru untuk analisis lanjutan.

# %%
# Contoh: Analisis distribusi action_taken (status keputusan pinjaman)
print("\n[Eksplorasi] Distribusi action_taken:")
print(df["action_taken"].value_counts(dropna=False))

# %%
# Contoh: Top 10 Lender berdasarkan volume pinjaman
print("\n[Eksplorasi] Top 10 Lender dengan aplikasi terbanyak:")
print(df["lender_name"].value_counts().head(10))

# %%
# Contoh: Distribusi kategori lender_type
if "lender_type" in df.columns:
    print("\n[Eksplorasi] Distribusi lender_type:")
    print(df["lender_type"].value_counts(dropna=False))

# %% [markdown]
# ---
# ## 7. Ringkasan Perbandingan Indikator: Bank Comparator vs Fintech
# Analisis komparatif awal untuk indikator kunci:
# - Median & Rata-rata Rate Spread
# - Median & Rata-rata Suku Bunga (Interest Rate)
# - Median Nilai Pinjaman (Loan Amount)
# - Median Biaya Origination (Origination Charges)
# - Rasio Biaya Origination terhadap Nilai Pinjaman (% Loan Amount)
# - Median Total Seluruh Biaya Pinjaman (Total Loan Costs)

# %%
print("\n" + "=" * 78)
print("7. PERBANDINGAN INDIKATOR: BANK COMPARATOR VS FINTECH")
print("=" * 78)

# 1. Pastikan kolom numerik relevan bertipe numerik
compare_metrics = ["rate_spread", "interest_rate", "origination_charges", "loan_amount", "total_loan_costs"]
for col in compare_metrics:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# 2. Hitung rasio origination charges terhadap nilai pinjaman (%)
df["orig_charge_pct"] = (df["origination_charges"] / df["loan_amount"]) * 100

# 3. Filter kelompok target (Bank Comparator vs Fintech)
target_groups = ["Bank comparator", "Fintech"]
subset = df[df["lender_type"].isin(target_groups)]

# 4. Agregasi statistik perbandingan
summary_table = pd.DataFrame({
    "Bank Comparator": [
        subset[subset["lender_type"] == "Bank comparator"]["loan_amount"].count(),
        subset[subset["lender_type"] == "Bank comparator"]["rate_spread"].median(),
        subset[subset["lender_type"] == "Bank comparator"]["rate_spread"].mean(),
        subset[subset["lender_type"] == "Bank comparator"]["interest_rate"].median(),
        subset[subset["lender_type"] == "Bank comparator"]["interest_rate"].mean(),
        subset[subset["lender_type"] == "Bank comparator"]["loan_amount"].median(),
        subset[subset["lender_type"] == "Bank comparator"]["loan_amount"].mean(),
        subset[subset["lender_type"] == "Bank comparator"]["origination_charges"].median(),
        subset[subset["lender_type"] == "Bank comparator"]["origination_charges"].mean(),
        subset[subset["lender_type"] == "Bank comparator"]["orig_charge_pct"].median(),
        subset[subset["lender_type"] == "Bank comparator"]["orig_charge_pct"].mean(),
        subset[subset["lender_type"] == "Bank comparator"]["total_loan_costs"].median(),
    ],
    "Fintech": [
        subset[subset["lender_type"] == "Fintech"]["loan_amount"].count(),
        subset[subset["lender_type"] == "Fintech"]["rate_spread"].median(),
        subset[subset["lender_type"] == "Fintech"]["rate_spread"].mean(),
        subset[subset["lender_type"] == "Fintech"]["interest_rate"].median(),
        subset[subset["lender_type"] == "Fintech"]["interest_rate"].mean(),
        subset[subset["lender_type"] == "Fintech"]["loan_amount"].median(),
        subset[subset["lender_type"] == "Fintech"]["loan_amount"].mean(),
        subset[subset["lender_type"] == "Fintech"]["origination_charges"].median(),
        subset[subset["lender_type"] == "Fintech"]["origination_charges"].mean(),
        subset[subset["lender_type"] == "Fintech"]["orig_charge_pct"].median(),
        subset[subset["lender_type"] == "Fintech"]["orig_charge_pct"].mean(),
        subset[subset["lender_type"] == "Fintech"]["total_loan_costs"].median(),
    ]
}, index=[
    "Jumlah Pinjaman (Volume)",
    "Median Rate Spread (%)",
    "Rata-rata Rate Spread (%)",
    "Median Suku Bunga (%)",
    "Rata-rata Suku Bunga (%)",
    "Median Nilai Pinjaman ($)",
    "Rata-rata Nilai Pinjaman ($)",
    "Median Biaya Origination ($)",
    "Rata-rata Biaya Origination ($)",
    "Median Rasio Biaya vs Pokok (%)",
    "Rata-rata Rasio Biaya vs Pokok (%)",
    "Median Total Biaya Pinjaman ($)"
])

# 5. Hitung selisih (Fintech - Bank Comparator)
summary_table["Selisih (Fintech - Bank)"] = summary_table["Fintech"] - summary_table["Bank Comparator"]

# 6. Format tampilan tabel yang rapi
display_table = summary_table.copy()
display_table.loc["Jumlah Pinjaman (Volume)"] = display_table.loc["Jumlah Pinjaman (Volume)"].apply(lambda x: f"{int(x):,}")
for idx in ["Median Rate Spread (%)", "Rata-rata Rate Spread (%)"]:
    display_table.loc[idx] = summary_table.loc[idx].apply(lambda x: f"{x:+.3f}%")
for idx in ["Median Suku Bunga (%)", "Rata-rata Suku Bunga (%)"]:
    display_table.loc[idx] = summary_table.loc[idx].apply(lambda x: f"{x:.3f}%" if pd.notnull(x) else "")
for idx in ["Median Nilai Pinjaman ($)", "Rata-rata Nilai Pinjaman ($)"]:
    display_table.loc[idx] = summary_table.loc[idx].apply(lambda x: f"${x:,.2f}")
for idx in ["Median Biaya Origination ($)", "Rata-rata Biaya Origination ($)", "Median Total Biaya Pinjaman ($)"]:
    display_table.loc[idx] = summary_table.loc[idx].apply(lambda x: f"${x:,.2f}")
for idx in ["Median Rasio Biaya vs Pokok (%)", "Rata-rata Rasio Biaya vs Pokok (%)"]:
    display_table.loc[idx] = summary_table.loc[idx].apply(lambda x: f"{x:.3f}%")

print("\n--- TABEL RINGKASAN PERBANDINGAN BANK COMPARATOR VS FINTECH ---")
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 1000)
print(display_table.to_string())
print("=" * 78)
