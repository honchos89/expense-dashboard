import json
import os
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

import gspread
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2.service_account import Credentials
from pydantic import BaseModel, field_validator

SPREADSHEET_ID = "1pUOXBYP5O8vb8Tq8SBI_JJxLbP40O8ahPKx_MKBTBOM"
SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

_creds_file = Path("google-credentials.json")
if _creds_file.exists():
    creds = Credentials.from_service_account_file(str(_creds_file), scopes=SCOPES)
else:
    _creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = Credentials.from_service_account_info(_creds_json, scopes=SCOPES)

gc = gspread.authorize(creds)
sh = gc.open_by_key(SPREADSHEET_ID)

app = FastAPI(title="Personal Finance API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Sheet helpers ─────────────────────────────────────────────────────────────

def load_expenses() -> list[dict]:
    ws = sh.worksheet("Expenses")
    records = ws.get_all_records()
    result = []
    for r in records:
        result.append({
            "date": str(r.get("Date", "")),
            "category": str(r.get("Category", "")).strip().lower(),
            "amount": float(r.get("Amount", 0) or 0),
            "merchant": str(r.get("Merchant", "")),
            "person": str(r.get("Person", "")),
            "source": str(r.get("Source", "manual")),
            "type": str(r.get("Type", "expense")),
            "notes": str(r.get("Notes", "")),
        })
    return [e for e in result if e["date"]]


def append_expense_row(entry: dict) -> None:
    ws = sh.worksheet("Expenses")
    ws.append_row([
        entry["date"],
        entry["category"],
        entry["amount"],
        entry.get("merchant", ""),
        entry.get("person", ""),
        entry.get("source", "manual"),
        entry.get("type", "expense"),
        entry.get("notes", ""),
    ])


def load_budgets_list() -> list[dict]:
    ws = sh.worksheet("Budgets")
    records = ws.get_all_records()
    result = []
    for r in records:
        cat = str(r.get("Category", "")).strip().lower()
        if not cat:
            continue
        result.append({
            "category": cat,
            "monthly_limit": float(r.get("MonthlyLimit", 0) or 0),
            "person": str(r.get("Person", "Family")),
        })
    return result


def load_networth_list() -> list[dict]:
    ws = sh.worksheet("NetWorth")
    records = ws.get_all_records()
    result = []
    for r in records:
        month = str(r.get("Month", ""))
        if not month:
            continue
        result.append({
            "month": month,
            "stocks": float(r.get("Stocks", 0) or 0),
            "mutual_funds": float(r.get("MutualFunds", 0) or 0),
            "fd_ppf": float(r.get("FD_PPF", 0) or 0),
            "crypto": float(r.get("Crypto", 0) or 0),
            "cash": float(r.get("Cash", 0) or 0),
            "total": float(r.get("Total", 0) or 0),
        })
    return result


# ── Request models ────────────────────────────────────────────────────────────

class ExpenseIn(BaseModel):
    category: str
    amount: float
    date: Optional[str] = None
    merchant: Optional[str] = None
    person: Optional[str] = None
    source: Optional[str] = "manual"
    type: Optional[str] = "expense"
    notes: Optional[str] = None

    @field_validator("category")
    @classmethod
    def category_not_empty(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("Category cannot be empty.")
        return v

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Amount must be a positive number.")
        return v


class BudgetIn(BaseModel):
    category: str
    amount: float
    person: Optional[str] = "Family"

    @field_validator("category")
    @classmethod
    def category_not_empty(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("Category cannot be empty.")
        return v

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Amount must be a positive number.")
        return v


class NetWorthIn(BaseModel):
    month: str  # YYYY-MM
    stocks: float
    mutual_funds: float
    fd_ppf: float
    crypto: float
    cash: float


class ParseEmailIn(BaseModel):
    email_body: str
    email_from: str
    person: Optional[str] = None


# ── Email parsing helpers ─────────────────────────────────────────────────────

def _detect_bank(email_from: str) -> str:
    sender = email_from.lower()
    if "hdfcbank" in sender:
        return "HDFC"
    if "icici" in sender:
        return "ICICI"
    return "UNKNOWN"


def _extract_amount(text: str) -> Optional[float]:
    # Primary: Rs.1200.00 / Rs.10,413.00 (no space after Rs.)
    m = re.search(r"Rs\.([0-9,]+\.?[0-9]*)", text)
    if m:
        return float(m.group(1).replace(",", ""))
    # Secondary: INR 100 / INR 10,413.00
    m = re.search(r"INR\s+([0-9,]+\.?[0-9]*)", text, re.IGNORECASE)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


def _extract_merchant_hdfc(text: str) -> str:
    # UPI: "to VPA zomato@okicici" — capture VPA, then check for a display name after it
    m = re.search(r"to\s+VPA\s+(\S+)(.*?)(?:\.|Ref|on\s+\d|\n|$)", text, re.IGNORECASE)
    if m:
        vpa = m.group(1).strip().rstrip(".,")
        after_vpa = m.group(2).strip()
        # Prefer display name that follows the VPA address
        if after_vpa and re.match(r"[A-Za-z]", after_vpa):
            return after_vpa.split()[0].strip(".,")
        # Fall back to handle before '@', strip trailing digits
        handle = vpa.split("@")[0]
        handle = re.sub(r"\d+$", "", handle).strip("._- ")
        return handle or vpa

    # Credit card: "towards Zomato on 15-Apr-26" — capture between towards and "on <date>"
    m = re.search(r"towards\s+(.+?)\s+on\s+\d", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # "at <merchant>" fallback
    m = re.search(
        r"\bat\s+([A-Za-z0-9 &.\-]+?)(?:\s+on\b|\s+for\b|\.|\n|$)",
        text, re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    return "Unknown"


def _extract_merchant_icici(text: str) -> str:
    # UPI: same VPA pattern as HDFC
    m = re.search(r"to\s+VPA\s+(\S+)(.*?)(?:\.|Ref|on\s+\d|\n|$)", text, re.IGNORECASE)
    if m:
        vpa = m.group(1).strip().rstrip(".,")
        after_vpa = m.group(2).strip()
        if after_vpa and re.match(r"[A-Za-z]", after_vpa):
            return after_vpa.split()[0].strip(".,")
        handle = vpa.split("@")[0]
        handle = re.sub(r"\d+$", "", handle).strip("._- ")
        return handle or vpa

    m = re.search(
        r"\bat\s+([A-Za-z0-9 &.\-]+?)(?:\s+on\b|\s+for\b|\.|\n|$)",
        text, re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    return "Unknown"


def _extract_date(text: str) -> str:
    # ISO: 2026-04-15
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if m:
        return m.group(1)

    # DD-MM-YYYY or DD/MM/YYYY
    m = re.search(r"\b(\d{2})[/-](\d{2})[/-](\d{4})\b", text)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    # "15 Apr 2026" or "15-Apr-2026"
    _MONTHS = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "may": "05", "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }
    m = re.search(
        r"\b(\d{1,2})[\s\-](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s\-,]+(\d{4})\b",
        text, re.IGNORECASE,
    )
    if m:
        day = m.group(1).zfill(2)
        mon = _MONTHS[m.group(2)[:3].lower()]
        return f"{m.group(3)}-{mon}-{day}"

    return str(date.today())


_MERCHANT_CATEGORIES: dict[str, list[str]] = {
    "food": ["zomato", "swiggy", "bigbasket", "blinkit", "dominos", "pizza",
             "mcdonalds", "kfc", "subway", "dunkin", "starbucks", "cafe",
             "restaurant", "foodpanda", "eatsure", "zepto"],
    "transport": ["ola", "uber", "rapido", "metro", "irctc", "railway",
                  "makemytrip", "goibibo", "indigo", "spicejet", "airindia"],
    "shopping": ["amazon", "flipkart", "myntra", "ajio", "nykaa", "meesho",
                 "snapdeal", "instamart"],
    "utilities": ["airtel", "jio", "bsnl", "vodafone", "electricity", "water",
                  "mahanagar", "tatapower", "bescom", "bses", "postpaid", "broadband"],
    "health": ["apollo", "pharmeasy", "1mg", "pharmacy", "medical", "hospital",
               "medplus", "practo", "netmeds", "clinic"],
    "entertainment": ["netflix", "hotstar", "spotify", "primevideo", "youtube",
                      "bookmyshow", "pvr", "inox", "jiocinema"],
}


def _categorize(merchant: str) -> str:
    m_lower = merchant.lower()
    if m_lower.startswith("refund"):
        return "refund"
    for category, keywords in _MERCHANT_CATEGORIES.items():
        if any(kw in m_lower for kw in keywords):
            return category
    return "general"


# Refund/reversal signal words
_REFUND_PATTERN = re.compile(
    r"\b(refund|reversal|reversed|cashback|chargeback|money\s+back|credited\s+back)\b",
    re.IGNORECASE,
)

# Known merchants to look for inside refund emails
_KNOWN_MERCHANTS = [
    "zomato", "swiggy", "bigbasket", "blinkit", "amazon", "flipkart", "myntra",
    "ola", "uber", "rapido", "netflix", "hotstar", "spotify", "airtel", "jio",
    "apollo", "pharmeasy", "1mg", "irctc", "makemytrip", "goibibo", "dominos",
    "mcdonalds", "kfc", "nykaa", "ajio", "meesho",
]


def _is_refund(text: str) -> bool:
    return bool(_REFUND_PATTERN.search(text))


def _extract_refund_merchant(text: str) -> str:
    """Return 'Refund - <Merchant>' if original merchant is detectable, else 'Refund'."""
    t_lower = text.lower()
    for name in _KNOWN_MERCHANTS:
        if name in t_lower:
            return f"Refund - {name.capitalize()}"
    # Try "refund from <name>" or "refund for <name>"
    m = re.search(
        r"refund\s+(?:from|for|of|by)\s+([A-Za-z0-9 &.\-]+?)(?:\s+on\b|\s+of\b|\.|\n|$)",
        text, re.IGNORECASE,
    )
    if m:
        return f"Refund - {m.group(1).strip().title()}"
    return "Refund"


def _is_credit_alert(text: str, bank: str) -> bool:
    """Return True only for non-refund credits (salary, deposit, etc.) on ICICI."""
    if bank != "ICICI":
        return False
    if _is_refund(text):
        return False  # Refunds are credits we do want to record
    t = text.lower()
    has_credit = bool(re.search(
        r"\bcredited\b|\bcredit of\b|\bdeposited\b|\breceived rs\b|\badded to\b", t
    ))
    has_debit = bool(re.search(r"\bdebited\b|\bdebit of\b|\bspent\b|\bpayment of\b", t))
    return has_credit and not has_debit


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/expenses", status_code=201)
def add_expense(expense: ExpenseIn):
    entry = {
        "date": expense.date or str(date.today()),
        "category": expense.category,
        "amount": expense.amount,
        "merchant": expense.merchant or "",
        "person": expense.person or "",
        "source": expense.source or "manual",
        "type": expense.type or "expense",
        "notes": expense.notes or "",
    }
    append_expense_row(entry)
    return entry


@app.get("/expenses")
def list_expenses(
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    person: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
):
    expenses = load_expenses()
    if month:
        expenses = [e for e in expenses if e["date"].startswith(month)]
    if person and person.lower() != "family":
        expenses = [e for e in expenses if e["person"].lower() == person.lower()]
    if type and type.lower() != "all":
        expenses = [e for e in expenses if e["type"].lower() == type.lower()]
    return expenses


@app.get("/summary")
def summary(person: Optional[str] = Query(None)):
    expenses = load_expenses()
    if person and person.lower() != "family":
        expenses = [e for e in expenses if e["person"].lower() == person.lower()]
    totals: dict[str, float] = {}
    for e in expenses:
        totals[e["category"]] = totals.get(e["category"], 0.0) + e["amount"]
    return totals


@app.get("/monthly-report")
def monthly_report(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    person: Optional[str] = Query(None),
):
    expenses = load_expenses()
    budgets_list = load_budgets_list()

    # Build budgets dict for this person
    budgets: dict[str, float] = {}
    for b in budgets_list:
        if person and person.lower() != "family":
            if b["person"].lower() in (person.lower(), "family"):
                budgets[b["category"]] = b["monthly_limit"]
        else:
            budgets[b["category"]] = b["monthly_limit"]

    # Filter expenses by month, person, and expense type only
    if person and person.lower() != "family":
        expenses = [e for e in expenses if e["person"].lower() == person.lower()]
    expenses = [e for e in expenses if e["date"].startswith(month) and e["type"] == "expense"]

    totals: dict[str, float] = {}
    for e in expenses:
        totals[e["category"]] = totals.get(e["category"], 0.0) + e["amount"]

    all_categories = sorted(set(totals) | set(budgets))
    rows = []
    for cat in all_categories:
        spent = totals.get(cat, 0.0)
        budget = budgets.get(cat)
        if budget is not None:
            remaining = budget - spent
            if spent > budget:
                status = "OVER"
            elif spent / budget >= 0.9:
                status = "WARNING"
            else:
                status = "OK"
        else:
            remaining = None
            status = "OK"

        rows.append({
            "category": cat,
            "spent": spent,
            "budget": budget,
            "remaining": remaining,
            "status": status,
        })

    return rows


@app.post("/budgets", status_code=201)
def set_budget(budget: BudgetIn):
    ws = sh.worksheet("Budgets")
    records = ws.get_all_records()
    person_val = budget.person or "Family"
    for i, r in enumerate(records, start=2):
        r_cat = str(r.get("Category", "")).strip().lower()
        r_person = str(r.get("Person", "Family")).lower()
        if r_cat == budget.category and r_person == person_val.lower():
            ws.update(f"B{i}", [[budget.amount]])
            return {"category": budget.category, "amount": budget.amount, "person": person_val}
    ws.append_row([budget.category, budget.amount, person_val])
    return {"category": budget.category, "amount": budget.amount, "person": person_val}


@app.get("/budgets")
def list_budgets(person: Optional[str] = Query(None)):
    budgets_list = load_budgets_list()
    if person and person.lower() != "family":
        budgets_list = [
            b for b in budgets_list
            if b["person"].lower() in (person.lower(), "family")
        ]
    return budgets_list


@app.delete("/budgets/{category}")
def delete_budget(category: str, person: Optional[str] = Query(None)):
    category = category.strip().lower()
    ws = sh.worksheet("Budgets")
    records = ws.get_all_records()
    for i, r in enumerate(records, start=2):
        r_cat = str(r.get("Category", "")).strip().lower()
        r_person = str(r.get("Person", "")).lower()
        if r_cat == category:
            if person is None or r_person == person.lower():
                ws.delete_rows(i)
                return {"removed": category}
    raise HTTPException(status_code=404, detail=f"No budget for '{category}'.")


@app.get("/networth")
def get_networth():
    records = load_networth_list()
    return records[-1] if records else None


@app.post("/networth", status_code=201)
def add_networth(nw: NetWorthIn):
    total = nw.stocks + nw.mutual_funds + nw.fd_ppf + nw.crypto + nw.cash
    ws = sh.worksheet("NetWorth")
    ws.append_row([nw.month, nw.stocks, nw.mutual_funds, nw.fd_ppf, nw.crypto, nw.cash, total])
    return {
        "month": nw.month,
        "stocks": nw.stocks,
        "mutual_funds": nw.mutual_funds,
        "fd_ppf": nw.fd_ppf,
        "crypto": nw.crypto,
        "cash": nw.cash,
        "total": total,
    }


@app.get("/monthly-history")
def monthly_history(person: Optional[str] = Query(None)):
    expenses = load_expenses()
    if person and person.lower() != "family":
        expenses = [e for e in expenses if e["person"].lower() == person.lower()]

    months: dict[str, dict] = defaultdict(lambda: {"spending_ex_investment": 0.0, "invested": 0.0})
    for e in expenses:
        month = e["date"][:7]
        if not month:
            continue
        if e["type"] == "investment":
            months[month]["invested"] += e["amount"]
        else:
            months[month]["spending_ex_investment"] += e["amount"]

    result = []
    for month in sorted(months.keys()):
        spending = months[month]["spending_ex_investment"]
        invested = months[month]["invested"]
        result.append({
            "month": month,
            "spending_ex_investment": spending,
            "invested": invested,
            "total_outflow": spending + invested,
        })
    return result


@app.post("/parse-email")
def parse_email(payload: ParseEmailIn):
    bank = _detect_bank(payload.email_from)
    body = payload.email_body

    # Skip non-refund credit alerts (salary deposits, etc.)
    if _is_credit_alert(body, bank):
        return {"status": "success", "transaction_type": "skipped", "amount": None,
                "merchant": None, "category": None}

    amount = _extract_amount(body)
    if amount is None:
        return {"status": "skipped", "reason": "Could not extract amount",
                "transaction_type": "unknown"}

    txn_date = _extract_date(body)
    is_refund = _is_refund(body)

    if is_refund:
        merchant = _extract_refund_merchant(body)
        category = "refund"
        txn_type = "refund"
        notes = f"{bank} refund"
    else:
        if bank == "HDFC":
            merchant = _extract_merchant_hdfc(body)
        elif bank == "ICICI":
            merchant = _extract_merchant_icici(body)
        else:
            merchant = _extract_merchant_hdfc(body) or _extract_merchant_icici(body) or "Unknown"
        category = _categorize(merchant)
        txn_type = "expense"
        notes = bank

    entry = {
        "date": txn_date,
        "category": category,
        "amount": amount,
        "merchant": merchant,
        "person": payload.person or "",
        "source": "auto",
        "type": txn_type,
        "notes": notes,
    }
    append_expense_row(entry)

    return {
        "status": "success",
        "transaction_type": txn_type,
        "amount": amount,
        "merchant": merchant,
        "category": category,
    }
