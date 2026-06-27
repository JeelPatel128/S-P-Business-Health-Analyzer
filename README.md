# S-P-Business-Health-Analyzer
Automated financial health scoring system for 30 S&amp;P 500 companies using Python, MySQL, K-Means clustering, and Tableau


---

## How to Run

### 1. Install dependencies
```bash
pip3 install yfinance pandas numpy mysql-connector-python sqlalchemy scikit-learn
```

### 2. Set up MySQL
```sql
CREATE DATABASE sp500_analyzer;
```

### 3. Create config.py
```python
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "your_password",
    "database": "sp500_analyzer"
}
ENGINE_URL = (
    f"mysql+mysqlconnector://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}/{DB_CONFIG['database']}"
)
```

### 4. Run the pipeline
```bash
python3 day1_data_collection.py
python3 day2_metrics.py
python3 day3_clustering.py
python3 day4_export.py
```

---

## Dashboard
Built in Tableau Public with 4 interactive pages:
- Health Score Leaderboard — all 30 companies ranked and color coded by tier
- Sector Comparison — average scores and tier distribution by sector
- Tier Distribution — K-Means cluster breakdown across sectors
- Outlier Analysis — Revenue vs Health Score scatter plot


---

## Business Value
This tool replaces days of manual financial benchmarking with a 5-minute interactive review. Designed for analysts, investors, and business development teams who need a fast, rigorous starting point for competitive landscape analysis.

---

## Author
**Jeel Patel**
MS Business Analytics and Artificial Intelligence
Stevens Institute of Technology
