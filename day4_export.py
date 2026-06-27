# ============================================================
# Day 4: Export Clean Data for Excel Scorecard
# ============================================================
# Pulls everything from MySQL and exports two clean CSVs:
#   1. sp500_scorecard.csv     — for Tab 1 & 2
#   2. sp500_sector_summary.csv — for Tab 2
# ============================================================

import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from config import DB_CONFIG, ENGINE_URL
import warnings
warnings.filterwarnings('ignore')

def main():
    print("=" * 60)
    print("Day 4: Exporting clean data for Excel")
    print("=" * 60)

    engine = create_engine(ENGINE_URL)

    # --------------------------------------------------------
    # Query 1: Full scorecard — one row per company (latest year)
    # --------------------------------------------------------
    scorecard_query = """
        SELECT
            c.company_name        AS Company,
            c.ticker              AS Ticker,
            c.sector              AS Sector,
            m.fiscal_year         AS Year,
            -- Raw metrics (formatted as percentages or ratios)
            ROUND(m.revenue_growth_rate * 100, 1)  AS Revenue_Growth_Pct,
            ROUND(m.net_profit_margin  * 100, 1)   AS Net_Profit_Margin_Pct,
            ROUND(m.debt_to_equity,            2)  AS Debt_to_Equity,
            ROUND(m.ocf_trend          * 100, 1)   AS OCF_Margin_Pct,
            ROUND(m.return_on_equity   * 100, 1)   AS ROE_Pct,
            ROUND(m.asset_turnover,            2)  AS Asset_Turnover,
            -- Percentile scores
            ROUND(m.score_revenue_growth, 1)  AS Score_Revenue_Growth,
            ROUND(m.score_profit_margin,  1)  AS Score_Profit_Margin,
            ROUND(m.score_debt_to_equity, 1)  AS Score_Debt_Equity,
            ROUND(m.score_ocf_trend,      1)  AS Score_OCF,
            ROUND(m.score_roe,            1)  AS Score_ROE,
            ROUND(m.score_asset_turnover, 1)  AS Score_Asset_Turnover,
            -- Final scores
            ROUND(m.health_score, 1)  AS Health_Score,
            m.cluster_label           AS Tier,
            -- Revenue in billions
            ROUND(i.total_revenue / 1000000000, 1) AS Revenue_Billions
        FROM metrics m
        JOIN companies c ON m.ticker = c.ticker
        JOIN income_statement i
            ON m.ticker = i.ticker
            AND m.fiscal_year = i.fiscal_year
        WHERE m.fiscal_year = (SELECT MAX(fiscal_year) FROM metrics)
          AND m.cluster_label IS NOT NULL
        ORDER BY m.health_score DESC
    """

    # --------------------------------------------------------
    # Query 2: Sector summary
    # --------------------------------------------------------
    sector_query = """
        SELECT
            c.sector                              AS Sector,
            COUNT(DISTINCT m.ticker)              AS Company_Count,
            ROUND(AVG(m.health_score), 1)         AS Avg_Health_Score,
            ROUND(MAX(m.health_score), 1)         AS Best_Health_Score,
            ROUND(MIN(m.health_score), 1)         AS Worst_Health_Score,
            ROUND(AVG(m.net_profit_margin*100),1) AS Avg_Profit_Margin_Pct,
            ROUND(AVG(m.revenue_growth_rate*100),1) AS Avg_Revenue_Growth_Pct,
            ROUND(AVG(m.debt_to_equity), 2)       AS Avg_Debt_to_Equity,
            SUM(CASE WHEN m.cluster_label = 'Thriving' THEN 1 ELSE 0 END) AS Thriving_Count,
            SUM(CASE WHEN m.cluster_label = 'Stable'   THEN 1 ELSE 0 END) AS Stable_Count,
            SUM(CASE WHEN m.cluster_label = 'At-Risk'  THEN 1 ELSE 0 END) AS At_Risk_Count
        FROM metrics m
        JOIN companies c ON m.ticker = c.ticker
        WHERE m.fiscal_year = (SELECT MAX(fiscal_year) FROM metrics)
          AND m.cluster_label IS NOT NULL
        GROUP BY c.sector
        ORDER BY Avg_Health_Score DESC
    """

    # --------------------------------------------------------
    # Query 3: Multi-year trend data (all years, all companies)
    # --------------------------------------------------------
    trend_query = """
        SELECT
            c.company_name  AS Company,
            c.ticker        AS Ticker,
            c.sector        AS Sector,
            m.fiscal_year   AS Year,
            ROUND(m.health_score, 1) AS Health_Score,
            m.cluster_label AS Tier
        FROM metrics m
        JOIN companies c ON m.ticker = c.ticker
        WHERE m.health_score IS NOT NULL
        ORDER BY c.sector, c.company_name, m.fiscal_year
    """

    print("\n[1/3] Exporting company scorecard...")
    scorecard_df = pd.read_sql(scorecard_query, engine)
    scorecard_df.to_csv("sp500_scorecard.csv", index=False)
    print(f"  ✓ {len(scorecard_df)} companies exported to sp500_scorecard.csv")

    print("\n[2/3] Exporting sector summary...")
    sector_df = pd.read_sql(sector_query, engine)
    sector_df.to_csv("sp500_sector_summary.csv", index=False)
    print(f"  ✓ {len(sector_df)} sectors exported to sp500_sector_summary.csv")

    print("\n[3/3] Exporting trend data...")
    trend_df = pd.read_sql(trend_query, engine)
    trend_df.to_csv("sp500_trends.csv", index=False)
    print(f"  ✓ {len(trend_df)} rows exported to sp500_trends.csv")

    print("\n" + "=" * 60)
    print("✅ Export complete! Open Excel and follow Day 4 instructions.")
    print("=" * 60)

    # Print a preview
    print("\n📊 SCORECARD PREVIEW (Top 5):")
    print(scorecard_df[["Company","Sector","Health_Score","Tier","Revenue_Billions"]].head())

    print("\n📊 SECTOR SUMMARY:")
    print(sector_df[["Sector","Avg_Health_Score","Thriving_Count","Stable_Count","At_Risk_Count"]])

if __name__ == "__main__":
    main()