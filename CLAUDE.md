# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Add an expense
python expense_tracker.py add <category> <amount>

# Set a monthly budget for a category
python expense_tracker.py set-budget <category> <amount>

# All-time totals by category
python expense_tracker.py summary

# Monthly report vs budgets (defaults to current month)
python expense_tracker.py monthly [YYYY-MM]
```

No dependencies beyond the Python standard library.

## Architecture

Single-file CLI (`expense_tracker.py`). All logic is flat functions — no classes.

**Data layer** — two JSON files, read and written in full on every operation:
- `expenses.json` — list of `{category, amount, date}` objects (date is `YYYY-MM-DD` string)
- `budgets.json` — dict of `{category: monthly_limit}` (categories are the keys)

**Validation** — `parse_amount()` and `parse_category()` raise `ValueError` with descriptive messages; callers in `__main__` catch and print them, then exit with code 1.

**Monthly report logic** (`print_monthly_report`) — filters expenses by `date.startswith("YYYY-MM")`, then unions the resulting category set with all budgeted categories so budgeted-but-unspent categories always appear. Status thresholds: ≥90% of budget → WARNING, >100% → OVER.

Categories are always normalized to lowercase at write time, so lookups are case-insensitive by construction.
