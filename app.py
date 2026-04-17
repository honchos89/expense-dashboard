import json
from collections import defaultdict
from datetime import date
from pathlib import Path

import altair as alt
import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1pUOXBYP5O8vb8Tq8SBI_JJxLbP40O8ahPKx_MKBTBOM"
SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


@st.cache_resource
def _get_sheet():
    _creds_file = Path("google-credentials.json")
    if _creds_file.exists():
        creds = Credentials.from_service_account_file(str(_creds_file), scopes=SCOPES)
    else:
        _creds_json = json.loads(st.secrets["GOOGLE_CREDENTIALS_JSON"])
        creds = Credentials.from_service_account_info(_creds_json, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SPREADSHEET_ID)


# ── Sheet helpers ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_expenses() -> list[dict]:
    ws = _get_sheet().worksheet("Expenses")
    result = []
    for r in ws.get_all_records():
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


@st.cache_data(ttl=60)
def load_budgets() -> list[dict]:
    ws = _get_sheet().worksheet("Budgets")
    result = []
    for r in ws.get_all_records():
        cat = str(r.get("Category", "")).strip().lower()
        if not cat:
            continue
        result.append({
            "category": cat,
            "monthly_limit": float(r.get("MonthlyLimit", 0) or 0),
            "person": str(r.get("Person", "Family")),
        })
    return result


@st.cache_data(ttl=60)
def load_portfolio() -> list[dict]:
    ws = _get_sheet().worksheet("Portfolio")
    result = []
    for r in ws.get_all_records():
        asset_class = str(r.get("AssetClass", "")).strip()
        if not asset_class:
            continue
        result.append({
            "asset_class": asset_class,
            "sub_category": str(r.get("SubCategory", "")),
            "institution": str(r.get("Institution", "")),
            "current_value": float(r.get("CurrentValue", 0) or 0),
            "last_updated": str(r.get("LastUpdated", "")),
            "notes": str(r.get("Notes", "")),
        })
    return result


# ── Computed data functions ───────────────────────────────────────────────────

def get_portfolio_data() -> dict:
    assets = load_portfolio()
    total_stocks = sum(a["current_value"] for a in assets if a["asset_class"].lower() == "stocks")
    total_mutual_funds = sum(a["current_value"] for a in assets if a["asset_class"].lower() == "mutual funds")
    total_insurance = sum(a["current_value"] for a in assets if a["asset_class"].lower() == "insurance")
    total_annuity = sum(a["current_value"] for a in assets if a["asset_class"].lower() == "annuity")
    total_cash = sum(a["current_value"] for a in assets if a["asset_class"].lower() == "cash")
    total_net_worth = total_stocks + total_mutual_funds + total_insurance + total_annuity + total_cash
    return {
        "assets": assets,
        "summary": {
            "total_stocks": total_stocks,
            "total_mutual_funds": total_mutual_funds,
            "total_insurance": total_insurance,
            "total_annuity": total_annuity,
            "total_cash": total_cash,
            "total_net_worth": total_net_worth,
        },
    }


def get_monthly_report(month: str, person: str | None) -> list[dict]:
    expenses = load_expenses()
    budgets_list = load_budgets()

    budgets: dict[str, float] = {}
    for b in budgets_list:
        if person and person.lower() != "family":
            if b["person"].lower() in (person.lower(), "family"):
                budgets[b["category"]] = b["monthly_limit"]
        else:
            budgets[b["category"]] = b["monthly_limit"]

    if person and person.lower() != "family":
        expenses = [e for e in expenses if e["person"].lower() == person.lower()]
    expenses = [e for e in expenses if e["date"].startswith(month) and e["type"] == "expense"]

    totals: dict[str, float] = {}
    for e in expenses:
        totals[e["category"]] = totals.get(e["category"], 0.0) + e["amount"]

    rows = []
    for cat in sorted(set(totals) | set(budgets)):
        spent = totals.get(cat, 0.0)
        budget = budgets.get(cat)
        if budget is not None:
            remaining = budget - spent
            status = "OVER" if spent > budget else ("WARNING" if spent / budget >= 0.9 else "OK")
        else:
            remaining = None
            status = "OK"
        rows.append({"category": cat, "spent": spent, "budget": budget, "remaining": remaining, "status": status})
    return rows


def get_monthly_history(person: str | None) -> list[dict]:
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
        result.append({"month": month, "spending_ex_investment": spending, "invested": invested, "total_outflow": spending + invested})
    return result


def add_expense(body: dict) -> dict:
    entry = {
        "date": body.get("date") or str(date.today()),
        "category": body["category"].strip().lower(),
        "amount": body["amount"],
        "merchant": body.get("merchant") or "",
        "person": body.get("person") or "",
        "source": body.get("source") or "manual",
        "type": body.get("type") or "expense",
        "notes": body.get("notes") or "",
    }
    ws = _get_sheet().worksheet("Expenses")
    ws.append_row([
        entry["date"], entry["category"], entry["amount"],
        entry["merchant"], entry["person"], entry["source"],
        entry["type"], entry["notes"],
    ])
    load_expenses.clear()
    return entry


def update_portfolio(asset_class: str, institution: str, current_value: float) -> bool:
    ws = _get_sheet().worksheet("Portfolio")
    records = ws.get_all_records()
    for i, r in enumerate(records, start=2):
        if (str(r.get("AssetClass", "")).strip().lower() == asset_class.strip().lower()
                and str(r.get("Institution", "")).strip().lower() == institution.strip().lower()):
            ws.update([[current_value]], f"D{i}")
            ws.update([[str(date.today())]], f"E{i}")
            load_portfolio.clear()
            return True
    return False


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

# ── Password gate ─────────────────────────────────────────────────────────────

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    col_l, col_c, col_r = st.columns([1, 1, 1])
    with col_c:
        st.markdown("## Personal Finance Dashboard")
        st.markdown("Enter password to continue.")
        pwd = st.text_input("Password", type="password", key="login_pwd")
        if st.button("Login", use_container_width=True):
            if pwd == st.secrets["APP_PASSWORD"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    st.stop()

st.title("Personal Finance Dashboard")

# ── Top bar ───────────────────────────────────────────────────────────────────

tb1, tb2, tb3, _ = st.columns([2, 2, 3, 3])
with tb1:
    person = st.radio("Person", ["Family", "Saket", "Wife"], horizontal=True)
with tb2:
    view = st.radio("View", ["This month", "History", "Portfolio"], horizontal=True)
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
        entry = add_expense(body)
        st.sidebar.success(f"Added ₹{entry['amount']:,.0f} to '{entry['category']}'")
        st.rerun()
    except Exception as e:
        st.sidebar.error(str(e))

# ── Fetch data ────────────────────────────────────────────────────────────────

p = person_param(person)

all_expenses_raw = load_expenses()
if p:
    all_expenses_raw = [e for e in all_expenses_raw if e["person"].lower() == p.lower()]

if month_filter:
    all_expenses = [e for e in all_expenses_raw if e["date"].startswith(month_filter)]
else:
    all_expenses = [e for e in all_expenses_raw if e["date"].startswith(year_filter)]

month_expenses = [e for e in all_expenses if e["type"] == "expense"]
month_investments = [e for e in all_expenses if e["type"] == "investment"]

portfolio_data = get_portfolio_data()
portfolio_summary = portfolio_data.get("summary", {})

# ── 4 Metric cards ────────────────────────────────────────────────────────────

spending_total = sum(e["amount"] for e in month_expenses if e["amount"] > 0)
invested_total = sum(e["amount"] for e in month_investments)
month_refunds = [e for e in all_expenses if e.get("type") == "refund"]
total_refunds = sum(abs(e["amount"]) for e in month_refunds if e["amount"] < 0)
net_spending = spending_total - total_refunds
total_outflow = net_spending + invested_total
nw_total = portfolio_summary.get("total_net_worth", 0)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Net Worth", fmt_inr(nw_total))
with m2:
    st.metric("Net Spending (after refunds)", fmt_inr(net_spending))
    if total_refunds > 0:
        st.caption(f"Refunds: {fmt_inr(total_refunds)}")
m3.metric("Invested This Month", fmt_inr(invested_total))
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
        report_rows = get_monthly_report(month_filter, p)

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

    st.markdown(f"**Grand Total Outflow: {fmt_inr(total_outflow)}** &nbsp; (Spending {fmt_inr(spending_total)} − Refunds {fmt_inr(total_refunds)} + Invested {fmt_inr(invested_total)})", unsafe_allow_html=True)

    st.divider()

    # ── Net worth breakdown ───────────────────────────────────────────────────

    st.subheader("Net Worth Breakdown")
    if portfolio_summary:
        nw_items = [
            ("Stocks", portfolio_summary.get("total_stocks", 0)),
            ("Mutual Funds", portfolio_summary.get("total_mutual_funds", 0)),
            ("Insurance", portfolio_summary.get("total_insurance", 0)),
            ("Annuity", portfolio_summary.get("total_annuity", 0)),
            ("Cash", portfolio_summary.get("total_cash", 0)),
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

    history = get_monthly_history(p)

    if history:
        today_month = date.today().strftime("%Y-%m")

        df_hist = pd.DataFrame(history)
        df_hist = df_hist.sort_values("month", ascending=False)

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

# ═════════════════════════════════════════════════════════════════════════════
# PORTFOLIO VIEW
# ═════════════════════════════════════════════════════════════════════════════

elif view == "Portfolio":

    st.subheader("Portfolio")

    # ── Summary cards ─────────────────────────────────────────────────────────

    p1, p2, p3, p4, p5, p6 = st.columns(6)
    p1.metric("Stocks", fmt_inr(portfolio_summary.get("total_stocks", 0)))
    p2.metric("Mutual Funds", fmt_inr(portfolio_summary.get("total_mutual_funds", 0)))
    p3.metric("Insurance", fmt_inr(portfolio_summary.get("total_insurance", 0)))
    p4.metric("Annuity", fmt_inr(portfolio_summary.get("total_annuity", 0)))
    p5.metric("Cash", fmt_inr(portfolio_summary.get("total_cash", 0)))
    p6.metric("Total Net Worth", fmt_inr(portfolio_summary.get("total_net_worth", 0)))

    st.divider()

    # ── Assets table grouped by AssetClass ────────────────────────────────────

    assets = portfolio_data.get("assets", [])
    if assets:
        df_assets = pd.DataFrame(assets)
        for asset_class in df_assets["asset_class"].unique():
            st.markdown(f"**{asset_class}**")
            group = df_assets[df_assets["asset_class"] == asset_class][
                ["institution", "current_value", "last_updated"]
            ].copy()
            group.columns = ["Institution", "Current Value (₹)", "Last Updated"]
            group["Current Value (₹)"] = group["Current Value (₹)"].apply(fmt_inr)
            st.dataframe(group, use_container_width=True, hide_index=True)
    else:
        st.info("No portfolio data available.")

    st.divider()

    # ── Edit Values ───────────────────────────────────────────────────────────

    st.markdown("**Edit Values**")

    if assets:
        asset_options = [
            f"{a['asset_class']} — {a['institution']}" for a in assets
        ]
        with st.form("edit_portfolio_form", clear_on_submit=True):
            selected = st.selectbox("Select asset", asset_options)
            new_value = st.number_input("New value (₹)", min_value=0.0, step=1000.0, format="%.0f")
            submitted = st.form_submit_button("Update", use_container_width=False)

        if submitted:
            idx = asset_options.index(selected)
            chosen = assets[idx]
            ok = update_portfolio(chosen["asset_class"], chosen["institution"], new_value)
            if ok:
                st.success(f"Updated {chosen['institution']} ({chosen['asset_class']}) to {fmt_inr(new_value)}")
                st.rerun()
            else:
                st.error(f"Could not find '{chosen['institution']}' in Portfolio sheet.")
