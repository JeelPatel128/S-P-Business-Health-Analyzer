# ============================================================
# Day 2: Calculate Metrics + Composite Health Score
# S&P 500 Business Health Analyzer
# ============================================================
# What this script does:
#   1. Pulls raw financial data from MySQL
#   2. Calculates 6 business health metrics per company per year
#   3. Normalizes each metric to a 0-100 percentile score
#      within each sector peer group
#   4. Builds a weighted composite Health Score
#   5. Stores everything back into MySQL metrics table
# ============================================================

import pandas as pd
import numpy as np
import mysql.connector
from sqlalchemy import create_engine
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# SECTION 1: CONFIGURATION — Same as Day 1
# ============================================================

DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "JPvivid2025#",    # ← UPDATE THIS
    "database": "sp500_analyzer"
}

ENGINE_URL = (
    f"mysql+mysqlconnector://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}/{DB_CONFIG['database']}"
)

# ============================================================
# SECTION 2: METRIC WEIGHTS
# These weights determine how much each metric contributes
# to the final Health Score. They add up to 1.0 (100%)
# ============================================================

WEIGHTS = {
    "revenue_growth":  0.20,   # 20% — growth is critical
    "profit_margin":   0.25,   # 25% — profitability is most important
    "debt_to_equity":  0.15,   # 15% — financial risk
    "ocf_trend":       0.20,   # 20% — cash is king
    "roe":             0.10,   # 10% — efficiency of equity
    "asset_turnover":  0.10,   # 10% — operational efficiency
}

# ============================================================
# SECTION 3: LOAD DATA FROM MYSQL
# ============================================================

def load_data(engine):
    """
    Pull all raw financial data from MySQL and merge into
    one master DataFrame with all fields we need.
    """
    print("  Loading data from MySQL...")

    # Load all three tables
    income_df  = pd.read_sql("SELECT * FROM income_statement", engine)
    balance_df = pd.read_sql("SELECT * FROM balance_sheet",    engine)
    cashflow_df = pd.read_sql("SELECT * FROM cash_flow",       engine)
    companies_df = pd.read_sql("SELECT * FROM companies",      engine)

    # Merge income + balance on ticker + fiscal_year
    df = income_df.merge(balance_df,  on=["ticker", "fiscal_year"], how="outer")
    df = df.merge(cashflow_df,         on=["ticker", "fiscal_year"], how="outer")
    df = df.merge(companies_df,        on="ticker",                  how="left")

    # Drop duplicate id columns created by merge
    df = df[[
        "ticker", "company_name", "sector", "fiscal_year",
        "total_revenue", "net_income", "operating_income",
        "total_assets", "total_debt", "stockholders_equity",
        "operating_cash_flow"
    ]]

    print(f"  ✓ Loaded {len(df)} rows for {df['ticker'].nunique()} companies.")
    return df


# ============================================================
# SECTION 4: CALCULATE RAW METRICS
# ============================================================

def calculate_metrics(df):
    """
    Calculate all 6 business health metrics.
    Each metric is calculated per company per year.
    """
    print("  Calculating raw metrics...")

    # Sort so we can calculate year-over-year growth correctly
    df = df.sort_values(["ticker", "fiscal_year"]).reset_index(drop=True)

    # ----------------------------------------------------------
    # Metric 1: Revenue Growth Rate
    # Formula: (Revenue_t - Revenue_t-1) / Revenue_t-1
    # Grouped by ticker so growth doesn't bleed across companies
    # ----------------------------------------------------------
    df["revenue_growth_rate"] = df.groupby("ticker")["total_revenue"].pct_change()

    # ----------------------------------------------------------
    # Metric 2: Net Profit Margin
    # Formula: Net Income / Total Revenue
    # ----------------------------------------------------------
    df["net_profit_margin"] = df["net_income"] / df["total_revenue"]

    # ----------------------------------------------------------
    # Metric 3: Debt-to-Equity Ratio
    # Formula: Total Debt / Stockholders Equity
    # LOWER is better — we invert this when scoring
    # ----------------------------------------------------------
    df["debt_to_equity"] = df["total_debt"] / df["stockholders_equity"]

    # ----------------------------------------------------------
    # Metric 4: OCF Trend (Operating Cash Flow Margin)
    # Formula: Operating Cash Flow / Total Revenue
    # Shows how much of revenue becomes actual cash
    # ----------------------------------------------------------
    df["ocf_trend"] = df["operating_cash_flow"] / df["total_revenue"]

    # ----------------------------------------------------------
    # Metric 5: Return on Equity (ROE)
    # Formula: Net Income / Stockholders Equity
    # ----------------------------------------------------------
    df["return_on_equity"] = df["net_income"] / df["stockholders_equity"]

    # ----------------------------------------------------------
    # Metric 6: Asset Turnover Efficiency
    # Formula: Total Revenue / Total Assets
    # ----------------------------------------------------------
    df["asset_turnover"] = df["total_revenue"] / df["total_assets"]

    # Replace infinite values with NaN (happens when dividing by 0)
    df = df.replace([np.inf, -np.inf], np.nan)

    print("  ✓ All 6 metrics calculated.")
    return df


# ============================================================
# SECTION 5: NORMALIZE TO PERCENTILE SCORES (0-100)
# ============================================================

def percentile_score(series):
    """
    Convert a series of raw values to percentile scores 0-100.
    A company scoring 90 means it's better than 90% of its peers.
    Uses rank-based percentile so outliers don't distort scores.
    """
    return series.rank(pct=True, na_option='keep') * 100


def normalize_metrics(df):
    """
    For each metric, calculate percentile scores WITHIN each sector.
    This means we compare Walmart vs Target (Retail peers),
    not Walmart vs Apple (different sector).

    For Debt-to-Equity: LOWER is better, so we invert the score.
    """
    print("  Normalizing metrics to percentile scores by sector...")

    metric_cols = [
        "revenue_growth_rate",
        "net_profit_margin",
        "debt_to_equity",
        "ocf_trend",
        "return_on_equity",
        "asset_turnover"
    ]

    score_cols = [
        "score_revenue_growth",
        "score_profit_margin",
        "score_debt_to_equity",
        "score_ocf_trend",
        "score_roe",
        "score_asset_turnover"
    ]

    # Initialize score columns
    for col in score_cols:
        df[col] = np.nan

    # Score each metric within each sector + year group
    # This ensures fair peer comparison
    for (sector, year), group in df.groupby(["sector", "fiscal_year"]):
        idx = group.index

        # Higher revenue growth = better score
        df.loc[idx, "score_revenue_growth"] = percentile_score(group["revenue_growth_rate"])

        # Higher profit margin = better score
        df.loc[idx, "score_profit_margin"]  = percentile_score(group["net_profit_margin"])

        # LOWER debt-to-equity = better score (invert by using ascending=False)
        df.loc[idx, "score_debt_to_equity"] = percentile_score(
            group["debt_to_equity"].rank(ascending=True) * -1
        )

        # Higher OCF trend = better score
        df.loc[idx, "score_ocf_trend"]      = percentile_score(group["ocf_trend"])

        # Higher ROE = better score
        df.loc[idx, "score_roe"]            = percentile_score(group["return_on_equity"])

        # Higher asset turnover = better score
        df.loc[idx, "score_asset_turnover"] = percentile_score(group["asset_turnover"])

    print("  ✓ Percentile scores calculated.")
    return df


# ============================================================
# SECTION 6: CALCULATE COMPOSITE HEALTH SCORE
# ============================================================

def calculate_health_score(df):
    """
    Combine all 6 percentile scores into one weighted Health Score.
    Score ranges from 0-100:
        80-100 = Thriving
        50-79  = Stable
        0-49   = At-Risk
    """
    print("  Calculating composite Health Score...")

    df["health_score"] = (
        df["score_revenue_growth"] * WEIGHTS["revenue_growth"] +
        df["score_profit_margin"]  * WEIGHTS["profit_margin"]  +
        df["score_debt_to_equity"] * WEIGHTS["debt_to_equity"] +
        df["score_ocf_trend"]      * WEIGHTS["ocf_trend"]      +
        df["score_roe"]            * WEIGHTS["roe"]            +
        df["score_asset_turnover"] * WEIGHTS["asset_turnover"]
    )

    # Round to 2 decimal places for clean display
    df["health_score"] = df["health_score"].round(2)

    print("  ✓ Health Score calculated.")
    return df


# ============================================================
# SECTION 7: SAVE RESULTS TO MYSQL
# ============================================================

def save_metrics(df, engine):
    """
    Save calculated metrics and scores to the metrics table.
    """
    print("  Saving metrics to MySQL...")

    cols_to_save = [
        "ticker", "fiscal_year",
        "revenue_growth_rate", "net_profit_margin",
        "debt_to_equity", "ocf_trend",
        "return_on_equity", "asset_turnover",
        "score_revenue_growth", "score_profit_margin",
        "score_debt_to_equity", "score_ocf_trend",
        "score_roe", "score_asset_turnover",
        "health_score"
    ]

    metrics_df = df[cols_to_save].dropna(subset=["health_score"])

    # Clear existing data and reload fresh
    with engine.connect() as conn:
        from sqlalchemy import text
        conn.execute(text("DELETE FROM metrics"))
        conn.commit()

    metrics_df.to_sql(
        name="metrics",
        con=engine,
        if_exists="append",
        index=False,
        method="multi"
    )

    print(f"  ✓ Saved {len(metrics_df)} rows to metrics table.")


# ============================================================
# SECTION 8: PRINT SUMMARY REPORT
# ============================================================

def print_summary(df):
    """
    Print a quick summary so we can eyeball the results.
    """
    print("\n" + "=" * 60)
    print("TOP 10 COMPANIES BY HEALTH SCORE (Latest Year)")
    print("=" * 60)

    latest_year = df["fiscal_year"].max()
    latest = df[df["fiscal_year"] == latest_year].copy()
    latest = latest.sort_values("health_score", ascending=False)

    top10 = latest[["company_name", "sector", "health_score"]].head(10)
    for _, row in top10.iterrows():
        bar = "█" * int(row["health_score"] / 5)
        print(f"  {row['company_name']:<25} {row['sector']:<12} "
              f"{row['health_score']:>6.1f}  {bar}")

    print("\n" + "=" * 60)
    print("BOTTOM 5 COMPANIES BY HEALTH SCORE (Latest Year)")
    print("=" * 60)
    bottom5 = latest[["company_name", "sector", "health_score"]].tail(5)
    for _, row in bottom5.iterrows():
        print(f"  {row['company_name']:<25} {row['sector']:<12} "
              f"{row['health_score']:>6.1f}")

    print("\n" + "=" * 60)
    print("AVERAGE HEALTH SCORE BY SECTOR (Latest Year)")
    print("=" * 60)
    sector_avg = latest.groupby("sector")["health_score"].mean().round(2)
    for sector, score in sector_avg.items():
        print(f"  {sector:<15} {score:.1f}")


# ============================================================
# SECTION 9: RUN EVERYTHING
# ============================================================

def main():
    print("=" * 60)
    print("S&P 500 Business Health Analyzer — Day 2: Metrics")
    print("=" * 60)

    engine = create_engine(ENGINE_URL)

    print("\n[1/5] Loading raw data...")
    df = load_data(engine)

    print("\n[2/5] Calculating metrics...")
    df = calculate_metrics(df)

    print("\n[3/5] Normalizing to percentile scores...")
    df = normalize_metrics(df)

    print("\n[4/5] Calculating Health Score...")
    df = calculate_health_score(df)

    print("\n[5/5] Saving to MySQL...")
    save_metrics(df, engine)

    print_summary(df)

    print("\n" + "=" * 60)
    print("✅ Day 2 Complete! Metrics and Health Scores saved.")
    print("=" * 60)


if __name__ == "__main__":
    main()