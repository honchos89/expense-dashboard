import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1pUOXBYP5O8vb8Tq8SBI_JJxLbP40O8ahPKx_MKBTBOM"
SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

creds = Credentials.from_service_account_file("google-credentials.json", scopes=SCOPES)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SPREADSHEET_ID)


def get_or_create_worksheet(name: str, rows: int = 1000, cols: int = 20):
    try:
        ws = sh.worksheet(name)
        ws.clear()
        return ws
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(title=name, rows=rows, cols=cols)


# ── Expenses tab ──────────────────────────────────────────────────────────────

expenses_headers = ["Date", "Category", "Amount", "Merchant", "Person", "Source", "Type", "Notes"]
ws_expenses = get_or_create_worksheet("Expenses")
ws_expenses.append_row(expenses_headers)
ws_expenses.append_row(["2026-04-14", "Food", 450, "Zomato", "Saket", "manual", "expense", "test entry"])
print("Expenses tab ready.")

# ── Budgets tab ───────────────────────────────────────────────────────────────

budgets_headers = ["Category", "MonthlyLimit", "Person"]
ws_budgets = get_or_create_worksheet("Budgets")
ws_budgets.append_row(budgets_headers)
ws_budgets.append_row(["Food", 5000, "Family"])
print("Budgets tab ready.")

# ── NetWorth tab ──────────────────────────────────────────────────────────────

networth_headers = ["Month", "Stocks", "MutualFunds", "FD_PPF", "Crypto", "Cash", "Total"]
ws_networth = get_or_create_worksheet("NetWorth")
ws_networth.append_row(networth_headers)
ws_networth.append_row(["2026-04", 1240000, 780000, 420000, 140000, 260000, 2840000])
print("NetWorth tab ready.")

print("Sheet setup complete")
