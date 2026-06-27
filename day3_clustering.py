# ============================================================
# Day 3: K-Means Clustering + Outlier Analysis
# S&P 500 Business Health Analyzer
# ============================================================
# What this script does:
#   1. Loads health scores from MySQL
#   2. Applies K-Means clustering (k=3) to segment companies
#   3. Labels clusters as Thriving / Stable / At-Risk
#   4. Identifies declining trend companies
#   5. Finds outliers (large revenue, poor health)
#   6. Saves cluster labels back to MySQL
#   7. Exports a CSV for Power BI dashboard (Day 5)
# ============================================================

import pandas as pd
import numpy as np
import mysql.connector
from sqlalchemy import create_engine, text
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# SECTION 1: CONFIGURATION
# ============================================================

DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "JPvivid2025#",  # ← UPDATE THIS
    "database": "sp500_analyzer"
}

ENGINE_URL = (
    f"mysql+mysqlconnector://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}/{DB_CONFIG['database']}"
)

# ============================================================
# SECTION 2: LOAD DATA
# ============================================================

def load_data(engine):
    """
    Load metrics + company info from MySQL into one DataFrame.
    """
    print("  Loading data from MySQL...")

    query = """
        SELECT
            m.ticker,
            m.fiscal_year,
            m.revenue_growth_rate,
            m.net_profit_margin,
            m.debt_to_equity,
            m.ocf_trend,
            m.return_on_equity,
            m.asset_turnover,
            m.score_revenue_growth,
            m.score_profit_margin,
            m.score_debt_to_equity,
            m.score_ocf_trend,
            m.score_roe,
            m.score_asset_turnover,
            m.health_score,
            c.company_name,
            c.sector,
            i.total_revenue
        FROM metrics m
        JOIN companies c ON m.ticker = c.ticker
        JOIN income_statement i ON m.ticker = i.ticker
            AND m.fiscal_year = i.fiscal_year
    """

    df = pd.read_sql(query, engine)
    print(f"  ✓ Loaded {len(df)} rows for {df['ticker'].nunique()} companies.")
    return df


# ============================================================
# SECTION 3: K-MEANS CLUSTERING
# ============================================================

def apply_kmeans(df):
    """
    Apply K-Means clustering using all 6 percentile scores.
    k=3 because we want exactly 3 tiers: Thriving/Stable/At-Risk.

    Why StandardScaler first?
    K-Means uses distance calculations. Without scaling,
    a metric with values 0-100 would dominate one with 0-1.
    StandardScaler puts all features on equal footing.
    """
    print("  Applying K-Means clustering (k=3)...")

    # Use the latest year only for clustering
    latest_year = df["fiscal_year"].max()
    latest_df = df[df["fiscal_year"] == latest_year].copy()

    # Features we cluster on — the 6 percentile scores
    feature_cols = [
        "score_revenue_growth",
        "score_profit_margin",
        "score_debt_to_equity",
        "score_ocf_trend",
        "score_roe",
        "score_asset_turnover"
    ]

    # Drop rows with any missing scores
    cluster_df = latest_df.dropna(subset=feature_cols).copy()

    # Step 1: Scale features to mean=0, std=1
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(cluster_df[feature_cols])

    # Step 2: Apply K-Means with k=3
    # random_state=42 ensures reproducible results every run
    kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
    cluster_df["cluster_id"] = kmeans.fit_predict(X_scaled)

    # Step 3: Map cluster IDs to labels based on average health score
    # The cluster with highest avg health score = Thriving
    # Middle = Stable, Lowest = At-Risk
    cluster_scores = cluster_df.groupby("cluster_id")["health_score"].mean()
    sorted_clusters = cluster_scores.sort_values(ascending=False)

    label_map = {
        sorted_clusters.index[0]: "Thriving",   # Highest health score
        sorted_clusters.index[1]: "Stable",     # Middle
        sorted_clusters.index[2]: "At-Risk"     # Lowest health score
    }

    cluster_df["cluster_label"] = cluster_df["cluster_id"].map(label_map)

    print("  ✓ Clustering complete.")
    return cluster_df, label_map


# ============================================================
# SECTION 4: TREND ANALYSIS
# ============================================================

def analyze_trends(df):
    """
    Find companies whose health score has been declining
    for 3 or more consecutive years.
    These are the 'early warning' companies — the key
    interview insight for this project.
    """
    print("  Analyzing multi-year health score trends...")

    df = df.sort_values(["ticker", "fiscal_year"])
    declining_companies = []

    for ticker, group in df.groupby("ticker"):
        group = group.sort_values("fiscal_year")
        scores = group["health_score"].values
        years  = group["fiscal_year"].values

        # Check for 3+ consecutive years of decline
        consecutive_decline = 0
        max_decline = 0

        for i in range(1, len(scores)):
            if pd.notna(scores[i]) and pd.notna(scores[i-1]):
                if scores[i] < scores[i-1]:
                    consecutive_decline += 1
                    max_decline = max(max_decline, consecutive_decline)
                else:
                    consecutive_decline = 0

        if max_decline >= 2:  # 2 means 3 consecutive years declining
            company_name = group["company_name"].iloc[0]
            sector       = group["sector"].iloc[0]
            first_score  = scores[0]
            last_score   = scores[-1]
            total_drop   = first_score - last_score

            declining_companies.append({
                "ticker":        ticker,
                "company_name":  company_name,
                "sector":        sector,
                "first_score":   round(first_score, 1),
                "latest_score":  round(last_score,  1),
                "total_drop":    round(total_drop,  1),
                "max_consecutive_decline": max_decline + 1
            })

    declining_df = pd.DataFrame(declining_companies)
    if not declining_df.empty:
        declining_df = declining_df.sort_values("total_drop", ascending=False)

    print(f"  ✓ Found {len(declining_df)} companies with declining trends.")
    return declining_df


# ============================================================
# SECTION 5: OUTLIER ANALYSIS
# ============================================================

def analyze_outliers(df):
    """
    Find companies that are outliers — specifically:
    1. High revenue but LOW health score (efficient vs big)
    2. Low revenue but HIGH health score (lean and healthy)

    This is the core of your interview insight:
    'Revenue size has almost no correlation with financial health.'
    """
    print("  Identifying outliers...")

    latest_year = df["fiscal_year"].max()
    latest = df[df["fiscal_year"] == latest_year].copy()
    latest = latest.dropna(subset=["total_revenue", "health_score"])

    # Percentile rank revenue within the full dataset
    latest["revenue_percentile"] = latest["total_revenue"].rank(pct=True) * 100

    # Outlier Type 1: Top 33% revenue but Bottom 33% health score
    big_but_sick = latest[
        (latest["revenue_percentile"] >= 67) &
        (latest["health_score"] <= 33)
    ][["company_name", "sector", "total_revenue", "health_score", "revenue_percentile"]]

    # Outlier Type 2: Bottom 33% revenue but Top 33% health score
    small_but_healthy = latest[
        (latest["revenue_percentile"] <= 33) &
        (latest["health_score"] >= 67)
    ][["company_name", "sector", "total_revenue", "health_score", "revenue_percentile"]]

    print(f"  ✓ Found {len(big_but_sick)} 'big but sick' outliers.")
    print(f"  ✓ Found {len(small_but_healthy)} 'small but healthy' outliers.")

    return big_but_sick, small_but_healthy


# ============================================================
# SECTION 6: SAVE RESULTS TO MYSQL + CSV
# ============================================================

def save_results(cluster_df, engine):
    """
    Save cluster labels back to MySQL metrics table.
    Also export full dataset as CSV for Power BI.
    """
    print("  Saving cluster labels to MySQL...")

    # Update cluster labels in metrics table
    with engine.connect() as conn:
        for _, row in cluster_df.iterrows():
            conn.execute(text("""
                UPDATE metrics
                SET cluster_label = :label,
                    cluster_id    = :cid
                WHERE ticker = :ticker
                AND   fiscal_year = :year
            """), {
                "label":  row["cluster_label"],
                "cid":    int(row["cluster_id"]),
                "ticker": row["ticker"],
                "year":   int(row["fiscal_year"])
            })
        conn.commit()

    print("  ✓ Cluster labels saved to MySQL.")

    # Export full dataset as CSV for Power BI dashboard (Day 5)
    export_cols = [
        "ticker", "company_name", "sector", "fiscal_year",
        "revenue_growth_rate", "net_profit_margin",
        "debt_to_equity", "ocf_trend",
        "return_on_equity", "asset_turnover",
        "score_revenue_growth", "score_profit_margin",
        "score_debt_to_equity", "score_ocf_trend",
        "score_roe", "score_asset_turnover",
        "health_score", "cluster_label", "cluster_id",
        "total_revenue"
    ]

    cluster_df[export_cols].to_csv("sp500_health_data.csv", index=False)
    print("  ✓ Exported sp500_health_data.csv for Power BI.")


# ============================================================
# SECTION 7: PRINT FULL REPORT
# ============================================================

def print_report(cluster_df, declining_df, big_but_sick, small_but_healthy):
    """
    Print a clean summary report of all findings.
    """

    # --- Cluster Summary ---
    print("\n" + "=" * 60)
    print("CLUSTER RESULTS — COMPANY TIERS")
    print("=" * 60)

    for label in ["Thriving", "Stable", "At-Risk"]:
        group = cluster_df[cluster_df["cluster_label"] == label]
        avg_score = group["health_score"].mean()
        print(f"\n  {label} (avg health score: {avg_score:.1f})")
        print(f"  {'─' * 40}")
        for _, row in group.sort_values("health_score", ascending=False).iterrows():
            print(f"    {row['company_name']:<25} {row['sector']:<12} "
                  f"Score: {row['health_score']:.1f}")

    # --- Declining Trends ---
    print("\n" + "=" * 60)
    print("⚠️  COMPANIES WITH DECLINING HEALTH SCORES (3+ Years)")
    print("=" * 60)
    if declining_df.empty:
        print("  No companies with 3+ consecutive declining years found.")
    else:
        for _, row in declining_df.iterrows():
            print(f"  {row['company_name']:<25} {row['sector']:<12} "
                  f"Drop: {row['first_score']:.1f} → {row['latest_score']:.1f} "
                  f"(-{row['total_drop']:.1f} pts)")

    # --- Outliers ---
    print("\n" + "=" * 60)
    print("🔍 OUTLIERS: HIGH REVENUE, LOW HEALTH SCORE")
    print("(Your key interview insight)")
    print("=" * 60)
    if big_but_sick.empty:
        print("  No outliers found in this category.")
    else:
        for _, row in big_but_sick.iterrows():
            rev_b = row['total_revenue'] / 1e9
            print(f"  {row['company_name']:<25} Revenue: ${rev_b:.0f}B  "
                  f"Health Score: {row['health_score']:.1f}")

    print("\n" + "=" * 60)
    print("💡 OUTLIERS: LOWER REVENUE, HIGH HEALTH SCORE")
    print("=" * 60)
    if small_but_healthy.empty:
        print("  No outliers found in this category.")
    else:
        for _, row in small_but_healthy.iterrows():
            rev_b = row['total_revenue'] / 1e9
            print(f"  {row['company_name']:<25} Revenue: ${rev_b:.0f}B  "
                  f"Health Score: {row['health_score']:.1f}")


# ============================================================
# SECTION 8: RUN EVERYTHING
# ============================================================

def main():
    print("=" * 60)
    print("S&P 500 Business Health Analyzer — Day 3: Clustering")
    print("=" * 60)

    engine = create_engine(ENGINE_URL)

    print("\n[1/5] Loading data...")
    df = load_data(engine)

    print("\n[2/5] Applying K-Means clustering...")
    cluster_df, label_map = apply_kmeans(df)

    print("\n[3/5] Analyzing multi-year trends...")
    declining_df = analyze_trends(df)

    print("\n[4/5] Finding outliers...")
    big_but_sick, small_but_healthy = analyze_outliers(df)

    print("\n[5/5] Saving results...")
    save_results(cluster_df, engine)

    print_report(cluster_df, declining_df, big_but_sick, small_but_healthy)

    print("\n" + "=" * 60)
    print("✅ Day 3 Complete! Clustering and analysis saved.")
    print("   File exported: sp500_health_data.csv")
    print("=" * 60)


if __name__ == "__main__":
    main()