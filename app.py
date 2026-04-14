import os
from datetime import date

import altair as alt
import pandas as pd
import requests
import streamlit as st

API_BASE = os.environ.get("API_URL", "http://localhost:8000")


# ── API helpers ───────────────────────────────────────────────────────────────

def api_get(path: str, **params):
    params = {k: v for k, v in params.items() if v is not None}
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.ConnectionError:
        st.error("Cannot reach the API at localhost:8000 — start the server with: uvicorn api:app --reload")
        st.stop()
    except requests.HTTPError:
        st.error(f"API error: {r.text}")
        return None


def api_post(path: str, body: dict):
    try:
        r = requests.post(f"{API_BASE}{path}", json=body, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.ConnectionError:
        st.error("Cannot reach the API at localhost:8000")
        st.stop()
    except requests.HTTPError:
        detail = r.json().get("detail", r.text)
        raise ValueError(detail)


# ── Utilities ─────────────────────────────────────────────────────────────────

def fmt_inr(amount: float) -> str:
    if amount >= 10_000_000:
        return f"₹{amount / 10_000_000:.2f}Cr"
    elif amount >= 100_000:
        return f"₹{amount / 100_000:.2f}L"
    else:
        return f"₹{amount:,.0f}"


def get_month_options() -> list[str]:
    today = date.today()
    year, month = today.year, today.month
    options = []
    for _ in range(13):
        options.append(f"{year}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    options.append(f"Full year {today.year}")
    options.append(f"Full year {today.year - 1}")
    return options


def person_param(person: str):
    return None if person == "Family" else person


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Personal Finance Dashboard", layout="wide")
st.title("Personal Finance Dashboard")

# ── Top bar ───────────────────────────────────────────────────────────────────

tb1, tb2, tb3, _ = st.columns([2, 2, 3, 3])
with tb1:
    person = st.radio("Person", ["Family", "Saket", "Wife"], horizontal=True)
with tb2:
    view = st.radio("View", ["This month", "History"], horizontal=True)
with tb3:
    month_options = get_month_options()
    selected_month = st.selectbox("Month", month_options)

is_full_year = selected_month.startswith("Full year")
if is_full_year:
    year_str = selected_month.split()[-1]
    month_filter = None
    year_filter = year_str
else:
    month_filter = selected_month
    year_filter = None

st.divider()

# ── Sidebar: Add Expense form ─────────────────────────────────────────────────

st.sidebar.header("Add Expense")

with st.sidebar.form("add_expense_form", clear_on_submit=True):
    sb_category = st.text_input("Category", placeholder="e.g. food")
    sb_amount = st.number_input("Amount (₹)", min_value=0.01, step=1.0, format="%.0f")
    sb_date = st.date_input("Date", value=date.today())
    sb_person = st.selectbox("Person", ["Saket", "Wife"])
    sb_type = st.selectbox("Type", ["expense", "investment"])
    sb_merchant = st.text_input("Merchant", placeholder="e.g. Zomato")
    sb_notes = st.text_input("Notes (optional)")
    sb_submitted = st.form_submit_button("Add Expense", use_container_width=True)

if sb_submitted:
    try:
        body = {
            "category": sb_category,
            "amount": sb_amount,
            "date": str(sb_date),
            "person": sb_person,
            "type": sb_type,
            "merchant": sb_merchant.strip() or None,
            "source": "manual",
            "notes": sb_notes.strip() or None,
        }
        entry = api_post("/expenses", body)
        st.sidebar.success(f"Added ₹{entry['amount']:,.0f} to '{entry['category']}'")
        st.rerun()
    except ValueError as e:
        st.sidebar.error(str(e))

# ── Fetch data ────────────────────────────────────────────────────────────────

p = person_param(person)

# Expenses for the selected period
if month_filter:
    all_expenses = api_get("/expenses", month=month_filter, person=p) or []
    month_expenses = api_get("/expenses", month=month_filter, person=p, type="expense") or []
    month_investments = api_get("/expenses", month=month_filter, person=p, type="investment") or []
else:
    all_expenses_raw = api_get("/expenses", person=p) or []
    all_expenses = [e for e in all_expenses_raw if e["date"].startswith(year_filter)]
    month_expenses = [e for e in all_expenses if e["type"] == "expense"]
    month_investments = [e for e in all_expenses if e["type"] == "investment"]

networth = api_get("/networth")

# ── 4 Metric cards ────────────────────────────────────────────────────────────

spending_total = sum(e["amount"] for e in month_expenses)
invested_total = sum(e["amount"] for e in month_investments)
total_outflow = spending_total + invested_total
nw_total = networth["total"] if networth else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Net Worth", fmt_inr(nw_total))
m2.metric("Spending (ex-investment)", fmt_inr(spending_total))
m3.metric("Invested", fmt_inr(invested_total))
m4.metric("Total Outflow", fmt_inr(total_outflow))

st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# THIS MONTH VIEW
# ═════════════════════════════════════════════════════════════════════════════

if view == "This month":

    # ── Spending vs budget ────────────────────────────────────────────────────

    st.subheader("Spending vs Budget")

    report_rows = []
    if month_filter:
        report_rows = api_get("/monthly-report", month=month_filter, person=p) or []

    left_col, right_col = st.columns(2)

    with left_col:
        st.markdown("**Daily Expenses**")
        if report_rows:
            rows = []
            subtotal = 0.0
            for r in report_rows:
                spent = r["spent"]
                budget = r.get("budget")
                status = r["status"]
                if status == "OVER":
                    pill = "🔴 OVER"
                elif status == "WARNING":
                    pill = "🟡 WARNING"
                else:
                    pill = "🟢 OK"
                rows.append({
                    "Category": r["category"].title(),
                    "Spent": fmt_inr(spent),
                    "Budget": fmt_inr(budget) if budget else "—",
                    "Remaining": fmt_inr(r["remaining"]) if r.get("remaining") is not None else "—",
                    "Status": pill,
                })
                subtotal += spent
            rows.append({
                "Category": "**SUBTOTAL**",
                "Spent": fmt_inr(subtotal),
                "Budget": "",
                "Remaining": "",
                "Status": "",
            })
            df_report = pd.DataFrame(rows)

            def style_status(row):
                if "OVER" in str(row["Status"]):
                    return ["background-color: #fde8e8"] * len(row)
                elif "WARNING" in str(row["Status"]):
                    return ["background-color: #fef9e7"] * len(row)
                return [""] * len(row)

            st.dataframe(
                df_report.style.apply(style_status, axis=1),
                use_container_width=True,
                hide_index=True,
            )

            if month_expenses:
                by_cat = (
                    pd.DataFrame(month_expenses)
                    .groupby("category")["amount"]
                    .sum()
                    .reset_index()
                    .sort_values("amount", ascending=False)
                )
                st.bar_chart(by_cat.set_index("category")["amount"])
        else:
            st.info("No expense data for this period.")

    with right_col:
        st.markdown("**Investments This Month**")
        if month_investments:
            inv_df = pd.DataFrame(month_investments)
            by_type = inv_df.groupby("category")["amount"].sum().reset_index().sort_values("amount", ascending=False)
            inv_subtotal = by_type["amount"].sum()

            inv_rows = [
                {"Category": row["category"].title(), "Invested": fmt_inr(row["amount"])}
                for _, row in by_type.iterrows()
            ]
            inv_rows.append({"Category": "**SUBTOTAL**", "Invested": fmt_inr(inv_subtotal)})
            st.dataframe(pd.DataFrame(inv_rows), use_container_width=True, hide_index=True)

            chart = (
                alt.Chart(by_type)
                .mark_bar(color="#7c3aed")
                .encode(
                    x=alt.X("amount:Q", title="Amount (₹)"),
                    y=alt.Y("category:N", sort="-x", title=""),
                    tooltip=["category", "amount"],
                )
                .properties(height=250)
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No investments this period.")

    st.markdown(f"**Grand Total Outflow: {fmt_inr(total_outflow)}**")

    st.divider()

    # ── Net worth breakdown ───────────────────────────────────────────────────

    st.subheader("Net Worth Breakdown")
    if networth:
        nw_items = [
            ("Stocks", networth["stocks"]),
            ("Mutual Funds", networth["mutual_funds"]),
            ("FD / PPF", networth["fd_ppf"]),
            ("Crypto", networth["crypto"]),
            ("Cash", networth["cash"]),
        ]
        nw_cols = st.columns(len(nw_items))
        for col, (label, val) in zip(nw_cols, nw_items):
            col.metric(label, fmt_inr(val))
    else:
        st.info("No net worth data available.")

    st.divider()

    # ── Daily spend bar chart ─────────────────────────────────────────────────

    st.subheader(f"Daily Spend — {selected_month}")
    if month_expenses:
        df_exp = pd.DataFrame(month_expenses)
        df_exp["date"] = pd.to_datetime(df_exp["date"])
        daily = df_exp.groupby(df_exp["date"].dt.date)["amount"].sum().reset_index()
        daily.columns = ["date", "amount"]
        daily["date"] = daily["date"].astype(str)
        st.bar_chart(daily.set_index("date")["amount"])
    else:
        st.info("No expenses to chart.")

    st.divider()

    # ── Recent transactions ───────────────────────────────────────────────────

    st.subheader("Recent Transactions")
    if all_expenses:
        df_all = pd.DataFrame(all_expenses)
        df_all["date"] = pd.to_datetime(df_all["date"])
        df_all = df_all.sort_values("date", ascending=False).head(30)

        for _, row in df_all.iterrows():
            c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
            merchant = row.get("merchant") or row.get("category", "").title()
            category = row.get("category", "").title()
            amount = row.get("amount", 0)
            txn_date = row["date"].strftime("%d %b")
            source = row.get("source", "manual")
            txn_person = row.get("person", "")
            txn_type = row.get("type", "expense")

            amount_color = "#7c3aed" if txn_type == "investment" else "#111"
            source_badge = (
                '<span style="background:#e2e8f0;padding:1px 6px;border-radius:9px;font-size:11px">auto</span>'
                if source == "auto"
                else '<span style="background:#fef9c3;padding:1px 6px;border-radius:9px;font-size:11px">manual</span>'
            )
            if txn_person.lower() == "saket":
                person_badge = '<span style="background:#dbeafe;color:#1d4ed8;padding:1px 6px;border-radius:9px;font-size:11px">Saket</span>'
            elif txn_person.lower() == "wife":
                person_badge = '<span style="background:#fce7f3;color:#be185d;padding:1px 6px;border-radius:9px;font-size:11px">Wife</span>'
            else:
                person_badge = ""

            c1.markdown(f"**{merchant}** &nbsp; {source_badge} {person_badge}", unsafe_allow_html=True)
            c2.markdown(category)
            c3.markdown(f'<span style="color:{amount_color};font-weight:600">{fmt_inr(amount)}</span>', unsafe_allow_html=True)
            c4.markdown(txn_date)
    else:
        st.info("No transactions for this period.")

# ═════════════════════════════════════════════════════════════════════════════
# HISTORY VIEW
# ═════════════════════════════════════════════════════════════════════════════

elif view == "History":

    st.subheader("Monthly History")

    history = api_get("/monthly-history", person=p) or []

    if history:
        today_month = date.today().strftime("%Y-%m")

        df_hist = pd.DataFrame(history)
        df_hist = df_hist.sort_values("month", ascending=False)

        # Compute previous year average
        prev_year = str(date.today().year - 1)
        prev_year_rows = df_hist[df_hist["month"].str.startswith(prev_year)]
        if not prev_year_rows.empty:
            avg_spending = prev_year_rows["spending_ex_investment"].mean()
            avg_invested = prev_year_rows["invested"].mean()
            avg_total = prev_year_rows["total_outflow"].mean()
            avg_row = pd.DataFrame([{
                "month": f"Avg {prev_year}",
                "spending_ex_investment": avg_spending,
                "invested": avg_invested,
                "total_outflow": avg_total,
            }])
            df_hist = pd.concat([df_hist, avg_row], ignore_index=True)

        display_rows = []
        for _, row in df_hist.iterrows():
            is_current = row["month"] == today_month
            display_rows.append({
                "Month": f"► {row['month']}" if is_current else row["month"],
                "Spending (ex-investment)": fmt_inr(row["spending_ex_investment"]),
                "Invested": fmt_inr(row["invested"]),
                "Total Outflow": fmt_inr(row["total_outflow"]),
            })

        def highlight_current(row):
            if row["Month"].startswith("►"):
                return ["background-color: #fffbeb; font-weight: bold"] * len(row)
            elif "Avg" in str(row["Month"]):
                return ["background-color: #f0fdf4"] * len(row)
            return [""] * len(row)

        df_display = pd.DataFrame(display_rows)
        st.dataframe(
            df_display.style.apply(highlight_current, axis=1),
            use_container_width=True,
            hide_index=True,
        )

        # History chart (raw data, no avg row)
        df_chart = pd.DataFrame(history).sort_values("month")
        if not df_chart.empty:
            chart_data = df_chart[["month", "spending_ex_investment", "invested"]].melt(
                id_vars="month", var_name="type", value_name="amount"
            )
            chart_data["type"] = chart_data["type"].replace({
                "spending_ex_investment": "Spending",
                "invested": "Invested",
            })
            chart = (
                alt.Chart(chart_data)
                .mark_bar()
                .encode(
                    x=alt.X("month:N", title="Month", sort=None),
                    y=alt.Y("amount:Q", title="Amount (₹)"),
                    color=alt.Color(
                        "type:N",
                        scale=alt.Scale(
                            domain=["Spending", "Invested"],
                            range=["#3b82f6", "#7c3aed"],
                        ),
                    ),
                    tooltip=["month", "type", "amount"],
                )
                .properties(height=350)
            )
            st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No history data available yet.")
