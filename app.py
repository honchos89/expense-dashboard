from datetime import date

import requests
import streamlit as st
import pandas as pd

API_BASE = "http://localhost:8000"


# ── API helpers ───────────────────────────────────────────────────────────────

def api_get(path: str, **params):
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=5)
        r.raise_for_status()
        return r.json()
    except requests.ConnectionError:
        st.error("Cannot reach the API — is `uvicorn api:app` running on port 8000?")
        st.stop()


def api_post(path: str, body: dict):
    try:
        r = requests.post(f"{API_BASE}{path}", json=body, timeout=5)
        r.raise_for_status()
        return r.json()
    except requests.ConnectionError:
        st.error("Cannot reach the API — is `uvicorn api:app` running on port 8000?")
        st.stop()
    except requests.HTTPError:
        detail = r.json().get("detail", r.text)
        raise ValueError(detail)


def api_delete(path: str):
    try:
        r = requests.delete(f"{API_BASE}{path}", timeout=5)
        r.raise_for_status()
        return r.json()
    except requests.ConnectionError:
        st.error("Cannot reach the API — is `uvicorn api:app` running on port 8000?")
        st.stop()
    except requests.HTTPError:
        detail = r.json().get("detail", r.text)
        raise ValueError(detail)


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Expense Tracker",
    page_icon="💰",
    layout="wide",
)

# ── Navigation ────────────────────────────────────────────────────────────────

page = st.sidebar.radio("Navigate", ["Dashboard", "Settings"], label_visibility="collapsed")

# ── Sidebar: Add Expense form (shown on Dashboard) ───────────────────────────

if page == "Dashboard":
    st.sidebar.header("Add Expense")

    with st.sidebar.form("add_expense_form", clear_on_submit=True):
        category_input = st.text_input("Category", placeholder="e.g. food")
        amount_input = st.number_input("Amount ($)", min_value=0.01, step=0.01, format="%.2f")
        date_input = st.date_input("Date", value=date.today())
        notes_input = st.text_input("Notes (optional)", placeholder="optional description")
        submitted = st.form_submit_button("Add Expense", use_container_width=True)

    if submitted:
        try:
            body = {
                "category": category_input,
                "amount": amount_input,
                "date": str(date_input),
                "notes": notes_input.strip() or None,
            }
            entry = api_post("/expenses", body)
            st.sidebar.success(f"Added ${entry['amount']:.2f} to '{entry['category']}'")
            st.rerun()
        except ValueError as e:
            st.sidebar.error(str(e))

# ═════════════════════════════════════════════════════════════════════════════
# DASHBOARD PAGE
# ═════════════════════════════════════════════════════════════════════════════

if page == "Dashboard":
    st.title("💰 Expense Dashboard")

    expenses = api_get("/expenses")
    budgets = api_get("/budgets")

    if not expenses:
        st.info("No expenses yet. Add your first expense using the sidebar form.")
        st.stop()

    df = pd.DataFrame(expenses)
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].astype(float)

    # Current month filter
    today = date.today()
    month_str = today.strftime("%Y-%m")
    df_month = df[df["date"].dt.strftime("%Y-%m") == month_str]

    # ── Top metrics ──────────────────────────────────────────────────────────

    total_this_month = df_month["amount"].sum()
    total_all_time = df["amount"].sum()
    num_transactions = len(df_month)
    total_budget = sum(budgets.values()) if budgets else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("This Month", f"${total_this_month:,.2f}")
    col2.metric("All-time Total", f"${total_all_time:,.2f}")
    col3.metric("Transactions (month)", num_transactions)
    if total_budget:
        pct = total_this_month / total_budget * 100
        col4.metric("Budget Used", f"{pct:.1f}%", delta=f"${total_budget - total_this_month:,.2f} left")
    else:
        col4.metric("Budget", "No budgets set")

    st.divider()

    # ── Charts row ───────────────────────────────────────────────────────────

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("Spend by Category (this month)")
        if df_month.empty:
            st.info("No expenses this month.")
        else:
            by_cat = (
                df_month.groupby("category")["amount"]
                .sum()
                .reset_index()
                .sort_values("amount", ascending=False)
            )
            st.bar_chart(by_cat.set_index("category")["amount"])

    with chart_col2:
        st.subheader("Daily Spend (this month)")
        if df_month.empty:
            st.info("No expenses this month.")
        else:
            daily = df_month.groupby(df_month["date"].dt.date)["amount"].sum()
            month_start = today.replace(day=1)
            full_range = pd.date_range(month_start, today, freq="D").date
            daily = daily.reindex(full_range, fill_value=0)
            daily.index = [str(d) for d in daily.index]
            st.line_chart(daily)

    st.divider()

    # ── Budget vs Actual table (from /monthly-report) ─────────────────────────

    st.subheader(f"Budget vs Actual — {month_str}")

    report_rows = api_get("/monthly-report", month=month_str)

    if not report_rows:
        st.info("No data for this month.")
    else:
        rows = []
        for r in report_rows:
            spent = r["spent"]
            budget = r["budget"]
            remaining = r["remaining"]
            status_key = r["status"]

            if budget is not None:
                pct_used = spent / budget * 100 if budget else 0
                if status_key == "OVER":
                    status = "🔴 OVER"
                elif status_key == "WARNING":
                    status = "🟡 WARNING"
                else:
                    status = "🟢 OK"
            else:
                pct_used = None
                status = "—"

            rows.append({
                "Category": r["category"].title(),
                "Spent ($)": f"{spent:.2f}",
                "Budget ($)": f"{budget:.2f}" if budget is not None else "N/A",
                "Remaining ($)": f"{remaining:.2f}" if remaining is not None else "N/A",
                "% Used": f"{pct_used:.1f}%" if pct_used is not None else "N/A",
                "Status": status,
            })

        table_df = pd.DataFrame(rows)

        def row_style(row):
            s = row["Status"]
            if "OVER" in s:
                bg = "background-color: #fde8e8"
            elif "WARNING" in s:
                bg = "background-color: #fef9e7"
            else:
                bg = ""
            return [bg] * len(row)

        styled = table_df.style.apply(row_style, axis=1)
        st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Recent expenses ───────────────────────────────────────────────────────

    st.divider()
    st.subheader("Recent Expenses")

    recent = df.sort_values("date", ascending=False).head(20).copy()
    recent["date"] = recent["date"].dt.strftime("%Y-%m-%d")
    recent["amount"] = recent["amount"].map("${:.2f}".format)
    recent["category"] = recent["category"].str.title()
    display_cols = ["date", "category", "amount"] + (["notes"] if "notes" in recent.columns else [])
    st.dataframe(recent[display_cols], use_container_width=True, hide_index=True)

# ═════════════════════════════════════════════════════════════════════════════
# SETTINGS PAGE
# ═════════════════════════════════════════════════════════════════════════════

elif page == "Settings":
    st.title("⚙️ Budget Settings")
    st.caption("Set monthly spending limits per category.")

    budgets = api_get("/budgets")
    expenses = api_get("/expenses")

    known_categories = sorted(
        {e["category"] for e in expenses} | set(budgets.keys())
    )

    st.subheader("Current Budgets")

    if not budgets:
        st.info("No budgets set yet. Use the form below to add one.")
    else:
        budget_rows = [
            {"Category": cat.title(), "Monthly Budget ($)": f"{amt:.2f}"}
            for cat, amt in sorted(budgets.items())
        ]
        st.dataframe(pd.DataFrame(budget_rows), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Set / Update a Budget")

    with st.form("set_budget_form", clear_on_submit=True):
        category_options = known_categories + ["+ New category..."]
        selected = st.selectbox("Category", options=category_options)
        new_cat = ""
        if selected == "+ New category...":
            new_cat = st.text_input("New category name")
        budget_amount = st.number_input(
            "Monthly limit ($)", min_value=0.01, step=1.0, format="%.2f"
        )
        save_btn = st.form_submit_button("Save Budget", use_container_width=True)

    if save_btn:
        raw_cat = new_cat if selected == "+ New category..." else selected
        try:
            entry = api_post("/budgets", {"category": raw_cat, "amount": budget_amount})
            st.success(f"Budget for '{entry['category']}' set to ${entry['amount']:.2f}/month")
            st.rerun()
        except ValueError as e:
            st.error(str(e))

    # ── Delete a budget ───────────────────────────────────────────────────────

    if budgets:
        st.divider()
        st.subheader("Remove a Budget")
        with st.form("delete_budget_form", clear_on_submit=True):
            del_cat = st.selectbox("Select category to remove", options=sorted(budgets.keys()))
            del_btn = st.form_submit_button("Remove Budget", use_container_width=True)
        if del_btn:
            try:
                api_delete(f"/budgets/{del_cat}")
                st.success(f"Removed budget for '{del_cat}'")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
