"""
fix_refunds_and_backfill.py

1. Fix refund rows in Google Sheet: make positive amounts negative.
2. Log 8 missing HDFC reversal emails via /parse-email (skip if already present).
"""

import json
import os
import re
from collections import Counter
from pathlib import Path

import gspread
import requests
from google.oauth2.service_account import Credentials

# ── Setup ──────────────────────────────────────────────────────────────────────

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
ws = gc.open_by_key(SPREADSHEET_ID).worksheet("Expenses")

# Column indices (0-based): Date=0, Category=1, Amount=2, Merchant=3,
#                            Person=4, Source=5, Type=6, Notes=7

# ── Part 1: Make refund amounts negative ──────────────────────────────────────

print("=" * 60)
print("PART 1 -- Fix refund amounts to negative")
print("=" * 60)

all_values = ws.get_all_values()
fixed_count = 0

for i, row in enumerate(all_values[1:], start=2):
    row_type = row[6].strip().lower() if len(row) > 6 else ""
    if row_type != "refund":
        continue
    try:
        amount = float(str(row[2]).replace(",", ""))
    except ValueError:
        continue
    if amount <= 0:
        continue  # already negative, skip

    negative_amount = -amount
    ws.update([[negative_amount]], f"C{i}")
    merchant = row[3] if len(row) > 3 else "Unknown"
    print(f"  Fixed refund: {merchant!r} -> -{amount}")
    fixed_count += 1

print(f"\nTotal fixed: {fixed_count} rows")

# ── Part 2: Log 8 missing reversal emails ─────────────────────────────────────

print()
print("=" * 60)
print("PART 2 -- Logging 8 missing reversal emails")
print("=" * 60)

REVERSALS = [
    {
        "label": "CONFIRMTKT Rs.815.36  (14 Apr)",
        "payload": {
            "email_body": (
                "Dear Customer, Greetings from HDFC Bank! "
                "Transaction reversal of Rs.815.36 has been initiated to your "
                "HDFC Bank Credit Card ending 0175. "
                "From Merchant:A CONFIRMTKT SMART BUY Date Time: 14 Apr, 2026 at"
            ),
            "email_from": "alerts@hdfcbank.bank.in",
            "person": "Saket",
        },
        "keyword": "confirmtkt",
        "amount": 815.36,
        "max_count": 1,
    },
    {
        "label": "MYNTRA Rs.697.00  (14 Apr)",
        "payload": {
            "email_body": (
                "Dear Customer, Greetings from HDFC Bank! "
                "Transaction reversal of Rs.697.00 has been initiated to your "
                "HDFC Bank Credit Card ending 0175. "
                "From Merchant:A MYNTRA VIA SMARTBUY Date Time: 14 Apr, 2026 at"
            ),
            "email_from": "alerts@hdfcbank.bank.in",
            "person": "Saket",
        },
        "keyword": "myntra",
        "amount": 697.00,
        "max_count": 1,
    },
    {
        "label": "MYNTRA Rs.271.00  (09 Apr)",
        "payload": {
            "email_body": (
                "Dear Customer, Greetings from HDFC Bank! "
                "Transaction reversal of Rs.271.00 has been initiated to your "
                "HDFC Bank Credit Card ending 0175. "
                "From Merchant:A MYNTRA VIA SMARTBUY Date Time: 09 Apr, 2026 at"
            ),
            "email_from": "alerts@hdfcbank.bank.in",
            "person": "Saket",
        },
        "keyword": "myntra",
        "amount": 271.00,
        "max_count": 1,
    },
    {
        "label": "MYNTRA Rs.872.00  (06 Apr)",
        "payload": {
            "email_body": (
                "Dear Customer, Greetings from HDFC Bank! "
                "Transaction reversal of Rs.872.00 has been initiated to your "
                "HDFC Bank Credit Card ending 0175. "
                "From Merchant:A MYNTRA VIA SMARTBUY Date Time: 06 Apr, 2026 at"
            ),
            "email_from": "alerts@hdfcbank.bank.in",
            "person": "Saket",
        },
        "keyword": "myntra",
        "amount": 872.00,
        "max_count": 1,
    },
    {
        "label": "MYNTRA Rs.1397.00  (06 Apr)",
        "payload": {
            "email_body": (
                "Dear Customer, Greetings from HDFC Bank! "
                "Transaction reversal of Rs.1397.00 has been initiated to your "
                "HDFC Bank Credit Card ending 0175. "
                "From Merchant:A MYNTRA VIA SMARTBUY Date Time: 06 Apr, 2026 at"
            ),
            "email_from": "alerts@hdfcbank.bank.in",
            "person": "Saket",
        },
        "keyword": "myntra",
        "amount": 1397.00,
        "max_count": 1,
    },
    {
        "label": "MYNTRA Rs.255.00 #1  (06 Apr)",
        "payload": {
            "email_body": (
                "Dear Customer, Greetings from HDFC Bank! "
                "Transaction reversal of Rs.255.00 has been initiated to your "
                "HDFC Bank Credit Card ending 0175. "
                "From Merchant:A MYNTRA VIA SMARTBUY Date Time: 06 Apr, 2026 at"
            ),
            "email_from": "alerts@hdfcbank.bank.in",
            "person": "Saket",
        },
        "keyword": "myntra",
        "amount": 255.00,
        "max_count": 2,  # two identical reversals exist
    },
    {
        "label": "MYNTRA Rs.255.00 #2  (06 Apr)",
        "payload": {
            "email_body": (
                "Dear Customer, Greetings from HDFC Bank! "
                "Transaction reversal of Rs.255.00 has been initiated to your "
                "HDFC Bank Credit Card ending 0175. "
                "From Merchant:A MYNTRA VIA SMARTBUY Date Time: 06 Apr, 2026 at"
            ),
            "email_from": "alerts@hdfcbank.bank.in",
            "person": "Saket",
        },
        "keyword": "myntra",
        "amount": 255.00,
        "max_count": 2,
    },
    {
        "label": "MYNTRA Rs.494.00  (06 Apr)",
        "payload": {
            "email_body": (
                "Dear Customer, Greetings from HDFC Bank! "
                "Transaction reversal of Rs.494.00 has been initiated to your "
                "HDFC Bank Credit Card ending 0175. "
                "From Merchant:A MYNTRA VIA SMARTBUY Date Time: 06 Apr, 2026 at"
            ),
            "email_from": "alerts@hdfcbank.bank.in",
            "person": "Saket",
        },
        "keyword": "myntra",
        "amount": 494.00,
        "max_count": 1,
    },
]

# Reload sheet after Part 1 changes
all_values = ws.get_all_values()

# Build counter of existing refund rows: (keyword, rounded_amount) -> count
existing_counter = Counter()
for row in all_values[1:]:
    if len(row) > 6 and row[6].strip().lower() == "refund":
        merchant_lower = row[3].strip().lower() if len(row) > 3 else ""
        try:
            amt = round(abs(float(str(row[2]).replace(",", ""))), 2)
        except ValueError:
            continue
        for kw in ("confirmtkt", "myntra"):
            if kw in merchant_lower:
                existing_counter[(kw, amt)] += 1
                break

# Track what we add in this run so we don't double-count the two Rs.255 entries
added_this_run = Counter()

for rev in REVERSALS:
    kw = rev["keyword"]
    amt = round(rev["amount"], 2)
    key = (kw, amt)

    already = existing_counter[key] + added_this_run[key]
    if already >= rev["max_count"]:
        print(f"\n{rev['label']}")
        print("  Already logged -- skipping.")
        continue

    print(f"\n{rev['label']}")
    resp = requests.post(f"{API_BASE}/parse-email", json=rev["payload"], timeout=30)
    print(f"  HTTP {resp.status_code}")
    try:
        print(f"  Result: {resp.json()}")
    except Exception:
        print(f"  Response text: {resp.text}")

    if resp.status_code == 200:
        added_this_run[key] += 1

# ── Part 1b: Fix amounts for any refunds just added by Part 2 ─────────────────

print()
print("=" * 60)
print("PART 1b -- Fix amounts for newly added refund rows")
print("=" * 60)

all_values = ws.get_all_values()
fixed2 = 0
for i, row in enumerate(all_values[1:], start=2):
    row_type = row[6].strip().lower() if len(row) > 6 else ""
    if row_type != "refund":
        continue
    try:
        amount = float(str(row[2]).replace(",", ""))
    except ValueError:
        continue
    if amount <= 0:
        continue
    ws.update([[- amount]], f"C{i}")
    merchant = row[3] if len(row) > 3 else "Unknown"
    print(f"  Fixed refund: {merchant!r} -> -{amount}")
    fixed2 += 1

if fixed2 == 0:
    print("  All refund amounts already negative -- nothing to fix.")
