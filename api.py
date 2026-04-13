import json
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

DATA_FILE = Path("expenses.json")
BUDGETS_FILE = Path("budgets.json")

app = FastAPI(title="Expense Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Data helpers ──────────────────────────────────────────────────────────────

def load_expenses() -> list[dict]:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return []


def save_expenses(expenses: list[dict]) -> None:
    DATA_FILE.write_text(json.dumps(expenses, indent=2))


def load_budgets() -> dict:
    if BUDGETS_FILE.exists():
        return json.loads(BUDGETS_FILE.read_text())
    return {}


def save_budgets(budgets: dict) -> None:
    BUDGETS_FILE.write_text(json.dumps(budgets, indent=2))


# ── Request models ────────────────────────────────────────────────────────────

class ExpenseIn(BaseModel):
    category: str
    amount: float
    date: Optional[str] = None   # YYYY-MM-DD; defaults to today
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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/expenses", status_code=201)
def add_expense(expense: ExpenseIn):
    entry = {
        "category": expense.category,
        "amount": expense.amount,
        "date": expense.date or str(date.today()),
    }
    if expense.notes and expense.notes.strip():
        entry["notes"] = expense.notes.strip()

    expenses = load_expenses()
    expenses.append(entry)
    save_expenses(expenses)
    return entry


@app.get("/expenses")
def list_expenses(
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
):
    expenses = load_expenses()
    if month:
        expenses = [e for e in expenses if e["date"].startswith(month)]
    return expenses


@app.get("/summary")
def summary():
    expenses = load_expenses()
    totals: dict[str, float] = {}
    for e in expenses:
        totals[e["category"]] = totals.get(e["category"], 0.0) + e["amount"]
    return totals


@app.get("/monthly-report")
def monthly_report(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
):
    expenses = load_expenses()
    budgets = load_budgets()

    totals: dict[str, float] = {}
    for e in expenses:
        if e["date"].startswith(month):
            cat = e["category"]
            totals[cat] = totals.get(cat, 0.0) + e["amount"]

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
    budgets = load_budgets()
    budgets[budget.category] = budget.amount
    save_budgets(budgets)
    return {"category": budget.category, "amount": budget.amount}


@app.get("/budgets")
def list_budgets():
    return load_budgets()


@app.delete("/budgets/{category}")
def delete_budget(category: str):
    category = category.strip().lower()
    budgets = load_budgets()
    if category not in budgets:
        raise HTTPException(status_code=404, detail=f"No budget for '{category}'.")
    del budgets[category]
    save_budgets(budgets)
    return {"removed": category}
