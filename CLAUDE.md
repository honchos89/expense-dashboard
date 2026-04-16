# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
# Start the FastAPI backend (port 8000)
uvicorn api:app --reload

# Start the Streamlit dashboard (separate terminal)
streamlit run app.py

# Re-initialize Google Sheet tabs with sample data
python setup_sheet.py
```

## Legacy CLI (expense_tracker.py)

```bash
python expense_tracker.py add <category> <amount>
python expense_tracker.py set-budget <category> <amount>
python expense_tracker.py summary
python expense_tracker.py monthly [YYYY-MM]
```

## Architecture

### Data layer — Google Sheets

All data lives in spreadsheet `1pUOXBYP5O8vb8Tq8SBI_JJxLbP40O8ahPKx_MKBTBOM`.
Authentication uses a service account key at `google-credentials.json` (never committed — in .gitignore).

Three tabs:

| Tab | Columns |
|-----|---------|
| **Expenses** | Date, Category, Amount, Merchant, Person, Source, Type, Notes |
| **Budgets** | Category, MonthlyLimit, Person |
| **NetWorth** | Month, Stocks, MutualFunds, FD_PPF, Crypto, Cash, Total |

- `Person` values: `Saket`, `Wife`, or empty (shared/family)
- `Type` values: `expense` or `investment`
- `Source` values: `manual` or `auto`

### api.py — FastAPI backend (localhost:8000)

Connects to Google Sheets via gspread + service account at module load time.
All endpoints read/write directly to Sheets on each request.

Key endpoints:
- `GET /expenses?month=YYYY-MM&person=Family|Saket|Wife&type=expense|investment|all`
- `POST /expenses` — appends a row to Expenses tab
- `GET /budgets?person=...` — returns list of `{category, monthly_limit, person}`
- `POST /budgets` — upserts by category+person; `DELETE /budgets/{category}`
- `GET /monthly-report?month=YYYY-MM&person=...` — budget vs actual for expense-type transactions
- `GET /networth` — returns latest NetWorth row
- `POST /networth` — appends a new monthly snapshot; total is computed server-side
- `GET /monthly-history?person=...` — all months with `spending_ex_investment`, `invested`, `total_outflow`

### app.py — Streamlit dashboard

Personal finance dashboard at localhost:8501. Connects to API at `http://localhost:8000`.

Top bar controls (Person × View × Month) filter all data globally.
- **Person**: Family (no filter) / Saket / Wife
- **View**: This month (detailed) / History (aggregate table + chart)
- **Month**: current + last 12 months + Full year options

Sections: 4 metric cards → spending vs budget tables → net worth breakdown → daily spend chart → recent transactions → monthly history table.

Sidebar form adds expenses with full fields (category, amount, date, person, type, merchant, notes).

### setup_sheet.py

One-time setup script. Clears and re-creates all three tabs with headers and one sample row each.

## Make.com Gmail automation

The Make.com scenario routes bank alert emails to `/parse-email`. The Gmail trigger module's **"Has the words"** filter should be **left empty** — do not set it to "debited". The Router branches downstream handle filtering by transaction type (debit vs. reversal). If the filter is set to "debited", reversal emails (which contain "transaction reversal" or "reversal of Rs" but not "debited") will never reach the webhook.
