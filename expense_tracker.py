import json
import sys
from datetime import date
from pathlib import Path

DATA_FILE = Path("expenses.json")
BUDGETS_FILE = Path("budgets.json")


def load_expenses():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return []


def save_expenses(expenses):
    DATA_FILE.write_text(json.dumps(expenses, indent=2))


def load_budgets():
    if BUDGETS_FILE.exists():
        return json.loads(BUDGETS_FILE.read_text())
    return {}


def save_budgets(budgets):
    BUDGETS_FILE.write_text(json.dumps(budgets, indent=2))


def parse_amount(raw):
    """Parse and validate a positive number from a string."""
    try:
        amount = float(raw)
    except ValueError:
        raise ValueError(f"'{raw}' is not a valid number.")
    if amount <= 0:
        raise ValueError(f"Amount must be a positive number, got {amount}.")
    return amount


def parse_category(raw):
    category = raw.strip().lower()
    if not category:
        raise ValueError("Category cannot be empty.")
    return category


def add_expense(category, raw_amount):
    category = parse_category(category)
    amount = parse_amount(raw_amount)
    expenses = load_expenses()
    expenses.append({
        "category": category,
        "amount": amount,
        "date": str(date.today()),
    })
    save_expenses(expenses)
    print(f"Added ${amount:.2f} to '{category}'")


def set_budget(category, raw_amount):
    category = parse_category(category)
    amount = parse_amount(raw_amount)
    budgets = load_budgets()
    budgets[category] = amount
    save_budgets(budgets)
    print(f"Budget for '{category}' set to ${amount:.2f}/month")


def print_summary():
    expenses = load_expenses()
    if not expenses:
        print("No expenses recorded.")
        return

    totals = {}
    for e in expenses:
        totals[e["category"]] = totals.get(e["category"], 0) + e["amount"]

    grand_total = sum(totals.values())
    col = max(len(c) for c in totals)

    print(f"\n{'Category':<{col}}   Amount")
    print("-" * (col + 12))
    for category, total in sorted(totals.items()):
        print(f"{category:<{col}}   ${total:.2f}")
    print("-" * (col + 12))
    print(f"{'TOTAL':<{col}}   ${grand_total:.2f}\n")


def print_monthly_report(year, month):
    expenses = load_expenses()
    budgets = load_budgets()

    month_str = f"{year}-{month:02d}"
    totals = {}
    for e in expenses:
        if e["date"].startswith(month_str):
            cat = e["category"]
            totals[cat] = totals.get(cat, 0) + e["amount"]

    # Include categories that have a budget even if no spending this month
    all_categories = sorted(set(totals) | set(budgets))

    if not all_categories:
        print(f"No expenses or budgets found for {month_str}.")
        return

    col = max(len(c) for c in all_categories)
    header = f"\n{'Category':<{col}}   {'Spent':>8}   {'Budget':>8}   {'Remaining':>10}   Status"
    print(f"Monthly Report — {month_str}")
    print(header)
    print("-" * len(header))

    grand_spent = 0
    grand_budget = 0

    for category in all_categories:
        spent = totals.get(category, 0.0)
        budget = budgets.get(category)
        grand_spent += spent

        if budget is not None:
            grand_budget += budget
            remaining = budget - spent
            if spent > budget:
                status = f"OVER by ${abs(remaining):.2f}"
            elif spent / budget >= 0.9:
                status = f"WARNING ({spent/budget:.0%} used)"
            else:
                status = "OK"
            print(f"{category:<{col}}   ${spent:>7.2f}   ${budget:>7.2f}   ${remaining:>9.2f}   {status}")
        else:
            print(f"{category:<{col}}   ${spent:>7.2f}   {'N/A':>8}   {'N/A':>10}   (no budget set)")

    print("-" * len(header))
    budget_str = f"${grand_budget:.2f}" if grand_budget else "N/A"
    print(f"{'TOTAL':<{col}}   ${grand_spent:>7.2f}   {budget_str:>8}\n")


def usage():
    print("Usage:")
    print("  python expense_tracker.py add <category> <amount>")
    print("  python expense_tracker.py set-budget <category> <amount>")
    print("  python expense_tracker.py summary")
    print("  python expense_tracker.py monthly [YYYY-MM]")
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        usage()

    command = sys.argv[1].lower()

    if command == "add":
        if len(sys.argv) != 4:
            print("Usage: python expense_tracker.py add <category> <amount>")
            sys.exit(1)
        try:
            add_expense(sys.argv[2], sys.argv[3])
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif command == "set-budget":
        if len(sys.argv) != 4:
            print("Usage: python expense_tracker.py set-budget <category> <amount>")
            sys.exit(1)
        try:
            set_budget(sys.argv[2], sys.argv[3])
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif command == "summary":
        print_summary()

    elif command == "monthly":
        if len(sys.argv) == 3:
            try:
                year_s, month_s = sys.argv[2].split("-")
                year, month = int(year_s), int(month_s)
                if not (1 <= month <= 12):
                    raise ValueError
            except ValueError:
                print("Error: Date must be in YYYY-MM format, e.g. 2026-04")
                sys.exit(1)
        else:
            today = date.today()
            year, month = today.year, today.month
        print_monthly_report(year, month)

    else:
        usage()
