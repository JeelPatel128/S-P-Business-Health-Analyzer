# ============================================================
# Day 1: Data Collection + MySQL Storage
# S&P 500 Business Health Analyzer
# ============================================================
# What this script does:
#   1. Defines 30 S&P 500 companies across 3 sectors
#   2. Pulls 5 years of financial data using yfinance
#   3. Cleans and stores data in MySQL
# ============================================================

import yfinance as yf
import pandas as pd
import mysql.connector
from sqlalchemy import create_engine
import time
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# SECTION 1: CONFIGURATION — Update your MySQL credentials here
# ============================================================

DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",          
    "password": "JPvivid2025#",
    "database": "sp500_analyzer"
}

# Build SQLAlchemy connection string for pandas to_sql()
ENGINE_URL = (
    f"mysql+mysqlconnector://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}/{DB_CONFIG['database']}"
)

# ============================================================
# SECTION 2: COMPANY LIST — 30 companies, 3 sectors, 10 each
# ============================================================

COMPANIES = {
    # --- RETAIL (10 companies) ---
    "WMT":  ("Walmart",          "Retail"),
    "AMZN": ("Amazon",           "Retail"),
    "COST": ("Costco",           "Retail"),
    "TGT":  ("Target",           "Retail"),
    "HD":   ("Home Depot",       "Retail"),
    "LOW":  ("Lowe's",           "Retail"),
    "BURL": ("Burlington Stores","Retail"),
    "KSS":  ("Kohl's",           "Retail"),
    "M":    ("Macy's",           "Retail"),
    "DG":   ("Dollar General",   "Retail"),

    # --- TECH (10 companies) ---
    "AAPL": ("Apple",            "Tech"),
    "MSFT": ("Microsoft",        "Tech"),
    "GOOGL":("Alphabet",         "Tech"),
    "META": ("Meta",             "Tech"),
    "NVDA": ("NVIDIA",           "Tech"),
    "CRM":  ("Salesforce",       "Tech"),
    "ORCL": ("Oracle",           "Tech"),
    "IBM":  ("IBM",              "Tech"),
    "INTC": ("Intel",            "Tech"),
    "CSCO": ("Cisco",            "Tech"),

    # --- HEALTHCARE (10 companies) ---
    "JNJ":  ("Johnson & Johnson","Healthcare"),
    "UNH":  ("UnitedHealth",     "Healthcare"),
    "PFE":  ("Pfizer",           "Healthcare"),
    "ABBV": ("AbbVie",           "Healthcare"),
    "MRK":  ("Merck",            "Healthcare"),
    "TMO":  ("Thermo Fisher",    "Healthcare"),
    "ABT":  ("Abbott Labs",      "Healthcare"),
    "CVS":  ("CVS Health",       "Healthcare"),
    "CI":   ("Cigna",            "Healthcare"),
    "HUM":  ("Humana",           "Healthcare"),
}

# The 5 fiscal years we want (most recent 5 full years)
TARGET_YEARS = [2020, 2021, 2022, 2023, 2024]

# ============================================================
# SECTION 3: DATABASE HELPERS
# ============================================================

def get_connection():
    """Create and return a MySQL connection."""
    return mysql.connector.connect(**DB_CONFIG)


def insert_companies(cursor):
    """Insert all 30 companies into the companies table."""
    sql = """
        INSERT IGNORE INTO companies (ticker, company_name, sector)
        VALUES (%s, %s, %s)
    """
    rows = [(ticker, name, sector) for ticker, (name, sector) in COMPANIES.items()]
    cursor.executemany(sql, rows)
    print(f"  ✓ Inserted/confirmed {len(rows)} companies in master table.")


# ============================================================
# SECTION 4: DATA EXTRACTION HELPERS
# ============================================================

def safe_get(df, field):
    """
    Safely extract a row from a yfinance financial DataFrame.
    Returns the Series for that field, or None if not found.
    """
    if df is None or df.empty:
        return None
    if field in df.index:
        result = df.loc[field]
        # Return None if all values are NaN
        if result.isna().all():
            return None
        return result
    return None


def safe_get_first(df, fields):
    """
    Try multiple field names in order, return the first one found.
    Fixes the ambiguous 'or' issue with pandas Series.
    """
    for field in fields:
        result = safe_get(df, field)
        if result is not None:
            return result
    return None


def extract_annual_value(series, year):
    """
    Given a pandas Series indexed by datetime (one value per year),
    extract the value closest to the given fiscal year.
    Returns None if no data found for that year.
    """
    if series is None:
        return None
    for date, value in series.items():
        if date.year == year:
            # Convert to Python int, handle NaN gracefully
            try:
                val = int(value)
                return val if val != 0 else None
            except (ValueError, TypeError):
                return None
    return None


# ============================================================
# SECTION 5: MAIN DATA PULL FUNCTION
# ============================================================

def pull_company_data(ticker, company_name, sector):
    """
    Pull 5 years of financial data for one company using yfinance.
    Returns three lists of row-dicts: income, balance, cashflow.
    """
    print(f"  Pulling data for {ticker} ({company_name})...")

    try:
        stock = yf.Ticker(ticker)

        # yfinance returns annual financials as DataFrames
        # .financials       = Income Statement
        # .balance_sheet    = Balance Sheet
        # .cashflow         = Cash Flow Statement
        income_df  = stock.financials      # rows: line items, cols: dates
        balance_df = stock.balance_sheet
        cashflow_df = stock.cashflow

    except Exception as e:
        print(f"    ✗ Failed to fetch {ticker}: {e}")
        return [], [], []

    income_rows   = []
    balance_rows  = []
    cashflow_rows = []

    for year in TARGET_YEARS:
        # --- Income Statement fields ---
        # Try both common naming conventions yfinance uses
        revenue    = safe_get_first(income_df, ["Total Revenue", "TotalRevenue"])
        net_income = safe_get_first(income_df, ["Net Income", "NetIncome"])
        op_income  = safe_get_first(income_df, ["Operating Income", "OperatingIncome", "EBIT"])

        income_rows.append({
            "ticker":           ticker,
            "fiscal_year":      year,
            "total_revenue":    extract_annual_value(revenue,    year),
            "net_income":       extract_annual_value(net_income, year),
            "operating_income": extract_annual_value(op_income,  year),
        })

        # --- Balance Sheet fields ---
        assets = safe_get_first(balance_df, ["Total Assets", "TotalAssets"])
        debt   = safe_get_first(balance_df, ["Total Debt", "TotalDebt", "Long Term Debt"])
        equity = safe_get_first(balance_df, ["Stockholders Equity", "StockholdersEquity", "Total Stockholder Equity"])

        balance_rows.append({
            "ticker":               ticker,
            "fiscal_year":          year,
            "total_assets":         extract_annual_value(assets, year),
            "total_debt":           extract_annual_value(debt,   year),
            "stockholders_equity":  extract_annual_value(equity, year),
        })

        # --- Cash Flow fields ---
        ocf = safe_get_first(cashflow_df, ["Operating Cash Flow", "Total Cash From Operating Activities"])

        cashflow_rows.append({
            "ticker":              ticker,
            "fiscal_year":         year,
            "operating_cash_flow": extract_annual_value(ocf, year),
        })

    return income_rows, balance_rows, cashflow_rows


# ============================================================
# SECTION 6: DATABASE WRITE FUNCTIONS
# ============================================================

def upsert_rows(engine, table_name, rows):
    """
    Write a list of row-dicts to MySQL.
    Uses INSERT IGNORE logic via pandas + SQLAlchemy.
    'if_exists=append' adds rows without dropping the table.
    """
    if not rows:
        return
    df = pd.DataFrame(rows)
    # Drop rows where ALL financial values are None (no data at all)
    value_cols = [c for c in df.columns if c not in ("ticker", "fiscal_year")]
    df = df.dropna(subset=value_cols, how="all")

    if df.empty:
        return

    df.to_sql(
        name=table_name,
        con=engine,
        if_exists="append",   # append to existing table
        index=False,
        method="multi"        # batch insert for speed
    )


# ============================================================
# SECTION 7: RUN EVERYTHING
# ============================================================

def main():
    print("=" * 60)
    print("S&P 500 Business Health Analyzer — Day 1: Data Collection")
    print("=" * 60)

    # --- Connect to MySQL ---
    print("\n[1/4] Connecting to MySQL...")
    conn = get_connection()
    cursor = conn.cursor()
    print("  ✓ Connected.")

    # --- Insert company master list ---
    print("\n[2/4] Inserting company master list...")
    insert_companies(cursor)
    conn.commit()
    cursor.close()
    conn.close()

    # --- Pull financial data for all 30 companies ---
    print("\n[3/4] Pulling financial data (this takes ~2-3 minutes)...")
    engine = create_engine(ENGINE_URL)

    all_income   = []
    all_balance  = []
    all_cashflow = []

    for ticker, (name, sector) in COMPANIES.items():
        inc, bal, cf = pull_company_data(ticker, name, sector)
        all_income.extend(inc)
        all_balance.extend(bal)
        all_cashflow.extend(cf)
        time.sleep(0.5)  # Be polite to the yfinance API — avoid rate limits

    # --- Write to MySQL ---
    print("\n[4/4] Writing data to MySQL...")
    upsert_rows(engine, "income_statement", all_income)
    print("  ✓ Income statement data saved.")
    upsert_rows(engine, "balance_sheet",    all_balance)
    print("  ✓ Balance sheet data saved.")
    upsert_rows(engine, "cash_flow",        all_cashflow)
    print("  ✓ Cash flow data saved.")

    print("\n" + "=" * 60)
    print("✅ Day 1 Complete! Database is populated.")
    print("   Run the SQL queries below to verify your data.")
    print("=" * 60)


if __name__ == "__main__":
    main()