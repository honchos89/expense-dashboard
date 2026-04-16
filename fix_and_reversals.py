"""
fix_and_reversals.py

1. Fix wrong dates (2026-04-15) in the Expenses Google Sheet.
2. Log 2 HDFC reversal emails via the /parse-email API (skip if already logged).
"""

import json
import os
from pathlib import Path

import gspread
import requests
from google.oauth2.service_account import Credentials

# ── Google Sheets setup ────────────────────────────────────────────────────

SPREADSHEET_ID = "1pUOXBYP5O8vb8Tq8SBI_JJxLbP40O8ahPKx_MKBTBOM"
SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
API_BASE = "https://expense-api-5azs.onrender.com"

_creds_file = Path("google-credentials.json")
if _creds_file.exists():
    creds = Credentials.from_service_account_file(str(_creds_file), scopes=SCOPES)
else:
    _creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = Credentials.from_service_account_info(_creds_json, scopes=SCOPES)

gc = gspread.authorize(creds)
sh = gc.open_by_key(SPREADSHEET_ID)
ws = sh.worksheet("Expenses")

# ── Part 1: Fix wrong dates ────────────────────────────────────────────────

# Column indices (0-based): Date=0, Category=1, Amount=2, Merchant=3,
#                            Person=4, Source=5, Type=6, Notes=7

def get_correct_date(merchant, occurrence_counters):
    """
    Return the correct date string for a given merchant name.
    occurrence_counters tracks how many times each merchant has been seen,
    used to disambiguate duplicate merchants.
    """
    m = merchant.strip().lower()

    if "manak mewa" in m:
        return "2026-04-12"
    if "anshul arora" in m:
        return "2026-04-11"
    if "iccl zerodha" in m:
        return "2026-04-02"
    if "zerodha broking" in m:
        n = occurrence_counters.get("zerodha_broking", 0)
        occurrence_counters["zerodha_broking"] = n + 1
        # rows 5 & 6 (occurrences 0 and 1) → 2026-04-02; row 7 (occurrence 2) → 2026-04-01
        return "2026-04-02" if n < 2 else "2026-04-01"
    if "murali krishna" in m:
        return "2026-04-01"
    if "tarkeshwar tiwari" in m:
        return "2026-04-01"
    if "myntra via smartbuy" in m:
        return "2026-04-14"
    if "www swiggy in" in m:
        return "2026-04-12"
    if "firstcry" in m:
        n = occurrence_counters.get("firstcry", 0)
        occurrence_counters["firstcry"] = n + 1
        return "2026-04-12" if n == 0 else "2026-04-11"
    if "pyu" in m and "swiggy" in m:
        return None  # amount-based, handled below
    if "rsp" in m and "instamart" in m:
        return None  # amount-based, handled below
    if "gyftr via smartbuy" in m:
        return "2026-04-09"
    if "confirmtkt" in m:
        return "2026-04-06"
    if "sb emt flight" in m or "a sb emt" in m:
        return "2026-04-06"
    if "swiggy" in m:
        return None  # amount-based, handled below
    if "balmapp" in m:
        return "2026-04-05"
    if "www acko" in m:
        return "2026-04-03"
    return None


def get_correct_date_by_amount(merchant, amount):
    """For merchants that appear multiple times, use the amount to pick the date."""
    m = merchant.strip().lower()
    try:
        amt = float(str(amount).replace(",", ""))
    except ValueError:
        return None

    if "pyu" in m and "swiggy" in m:
        if abs(amt - 364) < 1:
            return "2026-04-12"
        if abs(amt - 336) < 1:
            return "2026-04-05"
        if abs(amt - 595) < 1:
            return "2026-04-04"

    if "rsp" in m and "instamart" in m:
        if abs(amt - 393) < 1:
            return "2026-04-10"
        if abs(amt - 553) < 1:
            return "2026-04-09"
        if abs(amt - 415) < 1:
            return "2026-04-04"

    # Plain "Swiggy" (not www swiggy, not pyu swiggy)
    if m == "swiggy" or (m.startswith("swiggy") and "www" not in m and "pyu" not in m):
        if abs(amt - 461) < 1:
            return "2026-04-05"
        if abs(amt - 630) < 1:
            return "2026-04-04"

    return None


print("=" * 60)
print("PART 1 — Fixing wrong dates in Expenses sheet")
print("=" * 60)

all_values = ws.get_all_values()  # row 0 = headers, rows 1..N = data
occurrence_counters = {}
fixed_count = 0

for i, row in enumerate(all_values[1:], start=2):  # i = actual sheet row number
    date_val = row[0]
    notes_val = row[7] if len(row) > 7 else ""
    merchant = row[3] if len(row) > 3 else ""
    amount = row[2] if len(row) > 2 else ""

    if date_val != "2026-04-15":
        continue
    if notes_val.strip().upper() != "HDFC":
        continue

    correct = get_correct_date(merchant, occurrence_counters)
    if correct is None:
        correct = get_correct_date_by_amount(merchant, amount)

    if correct is None:
        print(f"  SKIPPED (no mapping): Row {i} | {merchant!r} | amt={amount}")
        continue

    ws.update([[correct]], f"A{i}")
    print(f"  Fixed: {merchant!r} -> {correct}  (row {i})")
    fixed_count += 1

print(f"\nTotal fixed: {fixed_count} rows")

# ── Part 2: Log reversal emails ────────────────────────────────────────────

print()
print("=" * 60)
print("PART 2 — Logging reversal emails via /parse-email")
print("=" * 60)

REVERSALS = [
    {
        "label": "Reversal 1 — Rs.3357.00",
        "payload": {
            "email_body": (
                "Dear Customer, Greetings from HDFC Bank! "
                "Transaction reversal of Rs.3357.00 has been initiated to your "
                "HDFC Bank Credit Card ending 0175. "
                "From Merchant:A SB EMT FLIGHT Date Time: 15 Apr, 2026 at 18:30:"
            ),
            "email_from": "alerts@hdfcbank.bank.in",
            "person": "Saket",
        },
        "check_amount": 3357.0,
    },
    {
        "label": "Reversal 2 — Rs.3803.00",
        "payload": {
            "email_body": (
                "Dear Customer, Greetings from HDFC Bank! "
                "Transaction reversal of Rs.3803.00 has been initiated to your "
                "HDFC Bank Credit Card ending 0175. "
                "From Merchant:A SB EMT FLIGHT Date Time: 15 Apr, 2026 at 18:30:"
            ),
            "email_from": "alerts@hdfcbank.bank.in",
            "person": "Saket",
        },
        "check_amount": 3803.0,
    },
]

# Reload rows after the date fixes
all_values = ws.get_all_values()


def reversal_already_logged(rows, check_amount):
    """Return True if a refund entry for this amount already exists."""
    for row in rows[1:]:
        row_type = row[6].strip().lower() if len(row) > 6 else ""
        row_merchant = row[3].strip().lower() if len(row) > 3 else ""
        try:
            row_amount = float(str(row[2]).replace(",", ""))
        except ValueError:
            row_amount = 0
        if (
            row_type == "refund"
            and ("sb emt flight" in row_merchant or "a sb emt" in row_merchant)
            and abs(row_amount - check_amount) < 1
        ):
            return True
    return False


for rev in REVERSALS:
    print(f"\n{rev['label']}")
    if reversal_already_logged(all_values, rev["check_amount"]):
        print("  Already logged — skipping.")
        continue

    resp = requests.post(f"{API_BASE}/parse-email", json=rev["payload"], timeout=30)
    print(f"  HTTP {resp.status_code}")
    try:
        print(f"  Result: {resp.json()}")
    except Exception:
        print(f"  Response text: {resp.text}")
