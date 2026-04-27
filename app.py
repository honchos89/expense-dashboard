import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import gspread
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1pUOXBYP5O8vb8Tq8SBI_JJxLbP40O8ahPKx_MKBTBOM"
SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

ASSET_COLORS = {
    "Stocks": "#3b82f6",
    "Mutual Funds": "#22c55e",
    "Insurance": "#f59e0b",
    "Annuity": "#a855f7",
    "Cash": "#6b7280",
}

BADGE_STYLES = {
    "Stocks": "background:#dbeafe;color:#1d4ed8",
    "Mutual Funds": "background:#dcfce7;color:#15803d",
    "Insurance": "background:#fef3c7;color:#b45309",
    "Annuity": "background:#f3e8ff;color:#7e22ce",
    "Cash": "background:#f3f4f6;color:#374151",
}

# Tab label → AssetClass value in sheet
TAB_TO_AC = {"Equity": "Stocks", "Mutual Funds": "Mutual Funds", "Insurance": "Insurance", "Annuity": "Annuity", "Cash": "Cash"}


# ── Google Sheets connection ───────────────────────────────────────────────────

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


# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
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


@st.cache_data(ttl=300)
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


@st.cache_data(ttl=300)
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


# ── Write helpers ──────────────────────────────────────────────────────────────

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


def update_portfolio_value(institution: str, new_value: float, updated_date: str) -> bool:
    ws = _get_sheet().worksheet("Portfolio")
    records = ws.get_all_records()
    for i, r in enumerate(records, start=2):
        if str(r.get("Institution", "")).strip().lower() == institution.strip().lower():
            ws.update([[new_value]], f"D{i}")
            ws.update([[updated_date]], f"E{i}")
            load_portfolio.clear()
            return True
    return False


# ── Utilities ──────────────────────────────────────────────────────────────────

def fmt_inr(amount: float) -> str:
    if amount >= 10_000_000:
        return f"₹{amount / 10_000_000:.2f}Cr"
    elif amount >= 100_000:
        return f"₹{amount / 100_000:.2f}L"
    elif amount >= 1_000:
        return f"₹{amount / 1_000:.1f}k"
    else:
        return f"₹{amount:,.0f}"


def date_range_from_filter(filt: str) -> tuple:
    today = date.today()
    if filt == "1W":
        return today - timedelta(days=7), today
    elif filt == "1M":
        return today - timedelta(days=30), today
    elif filt == "MTD":
        return today.replace(day=1), today
    elif filt == "3M":
        return today - timedelta(days=90), today
    elif filt == "YTD":
        return today.replace(month=1, day=1), today
    elif filt == "1Y":
        return today - timedelta(days=365), today
    else:
        return None, today


def filter_by_range(expenses: list[dict], start, end: date) -> list[dict]:
    result = []
    for e in expenses:
        try:
            d = date.fromisoformat(e["date"][:10])
        except ValueError:
            continue
        if start and d < start:
            continue
        if d > end:
            continue
        result.append(e)
    return result


# ═════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG + PASSWORD GATE
# ═════════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Personal Finance Dashboard", layout="wide")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    _, col_c, _ = st.columns([1, 1, 1])
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


# ═════════════════════════════════════════════════════════════════════════════
# TOP BAR
# ═════════════════════════════════════════════════════════════════════════════

st.title("Personal Finance Dashboard")

tb1, tb2, tb3 = st.columns([2, 3, 5])
with tb1:
    person = st.radio("Person", ["Family", "Saket", "Wife"], horizontal=True)
with tb2:
    view = st.radio("View", ["Portfolio", "Expenses", "History"], horizontal=True)
with tb3:
    st.caption("Date Range")
    date_filter_options = ["1W", "1M", "MTD", "3M", "YTD", "1Y", "All"]
    if "date_filter" not in st.session_state:
        st.session_state.date_filter = "MTD"
    df_btn_cols = st.columns(7)
    for i, opt in enumerate(date_filter_options):
        with df_btn_cols[i]:
            btn_type = "primary" if st.session_state.date_filter == opt else "secondary"
            if st.button(opt, key=f"dfbtn_{opt}", use_container_width=True, type=btn_type):
                st.session_state.date_filter = opt
                st.rerun()

date_filter = st.session_state.date_filter
start_date, end_date = date_range_from_filter(date_filter)
p = None if person == "Family" else person

st.divider()


# ═════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═════════════════════════════════════════════════════════════════════════════

st.sidebar.header("Add Entry")
with st.sidebar.form("add_expense_form", clear_on_submit=True):
    sb_date = st.date_input("Date", value=date.today())
    sb_category = st.text_input("Category", placeholder="e.g. food")
    sb_amount = st.number_input("Amount (₹)", min_value=0.01, step=1.0, format="%.0f")
    sb_merchant = st.text_input("Merchant", placeholder="e.g. Zomato")
    sb_person = st.selectbox("Person", ["Saket", "Wife"])
    sb_type = st.selectbox("Type", ["expense", "investment", "refund"])
    sb_source = st.selectbox("Source", ["manual", "auto"])
    sb_notes = st.text_input("Notes (optional)")
    sb_submitted = st.form_submit_button("Add Entry", use_container_width=True)

if sb_submitted:
    try:
        entry = add_expense({
            "category": sb_category,
            "amount": sb_amount,
            "date": str(sb_date),
            "person": sb_person,
            "type": sb_type,
            "merchant": sb_merchant.strip() or None,
            "source": sb_source,
            "notes": sb_notes.strip() or None,
        })
        st.sidebar.success(f"Added ₹{entry['amount']:,.0f} to '{entry['category']}'")
        st.rerun()
    except Exception as e:
        st.sidebar.error(str(e))

st.sidebar.divider()
st.sidebar.header("Update Portfolio")

_portfolio_assets = load_portfolio()
if _portfolio_assets:
    inst_options = [a["institution"] for a in _portfolio_assets if a["institution"]]
    with st.sidebar.form("update_portfolio_form", clear_on_submit=True):
        sel_inst = st.selectbox("Institution", inst_options)
        new_val = st.number_input("New Value (₹)", min_value=0.0, step=1000.0, format="%.0f")
        upd_date = st.date_input("Date", value=date.today(), key="upd_date")
        upd_submitted = st.form_submit_button("Update Portfolio", use_container_width=True)

    if upd_submitted:
        ok = update_portfolio_value(sel_inst, new_val, str(upd_date))
        if ok:
            st.sidebar.success(f"Updated {sel_inst} to {fmt_inr(new_val)}")
            st.rerun()
        else:
            st.sidebar.error(f"Could not find '{sel_inst}' in Portfolio sheet.")
else:
    st.sidebar.info("No portfolio data.")


# ═════════════════════════════════════════════════════════════════════════════
# PORTFOLIO VIEW
# ═════════════════════════════════════════════════════════════════════════════

if view == "Portfolio":
    assets = load_portfolio()

    total_stocks = sum(a["current_value"] for a in assets if a["asset_class"] == "Stocks")
    total_mf = sum(a["current_value"] for a in assets if a["asset_class"] == "Mutual Funds")
    total_insurance = sum(a["current_value"] for a in assets if a["asset_class"] == "Insurance")
    total_annuity = sum(a["current_value"] for a in assets if a["asset_class"] == "Annuity")
    total_nw = sum(a["current_value"] for a in assets)

    # 4 metric cards
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Net Worth", fmt_inr(total_nw))
    m2.metric("Equity", fmt_inr(total_stocks))
    m3.metric("Mutual Funds", fmt_inr(total_mf))
    m4.metric("Insurance + Annuity", fmt_inr(total_insurance + total_annuity))

    st.divider()

    # Aggregate by asset class
    ac_totals: dict[str, float] = {}
    for a in assets:
        ac_totals[a["asset_class"]] = ac_totals.get(a["asset_class"], 0) + a["current_value"]

    if "portfolio_filter" not in st.session_state:
        st.session_state.portfolio_filter = "All"

    left_col, right_col = st.columns([3, 2])

    with left_col:
        st.markdown("**Allocation Breakdown**")
        for ac, val in sorted(ac_totals.items(), key=lambda x: x[1], reverse=True):
            pct = (val / total_nw * 100) if total_nw > 0 else 0
            color = ASSET_COLORS.get(ac, "#6b7280")
            is_active = st.session_state.portfolio_filter == ac

            row_c1, row_c2, row_c3, row_c4, row_c5 = st.columns([0.4, 2.5, 3.5, 1.8, 1.2])
            with row_c1:
                st.markdown(
                    f'<div style="width:12px;height:12px;border-radius:50%;'
                    f'background:{color};margin-top:8px"></div>',
                    unsafe_allow_html=True,
                )
            with row_c2:
                if st.button(
                    ac,
                    key=f"alloc_{ac}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    st.session_state.portfolio_filter = "All" if is_active else ac
                    st.rerun()
            with row_c3:
                st.progress(pct / 100)
            with row_c4:
                st.markdown(f"**{fmt_inr(val)}**")
            with row_c5:
                st.markdown(f"{pct:.1f}%")

        st.markdown(f"**Total: {fmt_inr(total_nw)}**")

    with right_col:
        if ac_totals and total_nw > 0:
            labels = list(ac_totals.keys())
            values = list(ac_totals.values())
            colors = [ASSET_COLORS.get(l, "#6b7280") for l in labels]

            fig = go.Figure(data=[go.Pie(
                labels=labels,
                values=values,
                hole=0.5,
                marker=dict(colors=colors),
                textinfo="percent",
                hovertemplate="%{label}: ₹%{value:,.0f}<extra></extra>",
            )])
            fig.update_layout(
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=-0.35),
                margin=dict(t=20, b=90, l=10, r=10),
                height=360,
            )
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Holdings table
    st.markdown("**Holdings**")

    filter_tabs = ["All", "Equity", "Mutual Funds", "Insurance", "Annuity", "Cash"]
    ft_cols = st.columns(len(filter_tabs))
    for i, ft in enumerate(filter_tabs):
        mapped_ac = TAB_TO_AC.get(ft, ft)
        is_tab_active = (
            (ft == "All" and st.session_state.portfolio_filter == "All")
            or (ft != "All" and st.session_state.portfolio_filter == mapped_ac)
        )
        with ft_cols[i]:
            if st.button(ft, key=f"tab_{ft}", use_container_width=True,
                         type="primary" if is_tab_active else "secondary"):
                st.session_state.portfolio_filter = "All" if ft == "All" else mapped_ac
                st.rerun()

    search = st.text_input("Search institutions...", placeholder="Type to filter...", key="holdings_search")

    active_ac = st.session_state.portfolio_filter
    filtered_assets = assets if active_ac == "All" else [a for a in assets if a["asset_class"] == active_ac]
    if search:
        filtered_assets = [a for a in filtered_assets if search.lower() in a["institution"].lower()]

    if filtered_assets:
        rows = []
        for a in sorted(filtered_assets, key=lambda x: x["current_value"], reverse=True):
            weight = (a["current_value"] / total_nw * 100) if total_nw > 0 else 0
            rows.append({
                "Institution": a["institution"],
                "Category": a["asset_class"],
                "Value": fmt_inr(a["current_value"]),
                "Weight %": f"{weight:.1f}%",
                "Last Updated": a["last_updated"],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No holdings match the current filter.")


# ═════════════════════════════════════════════════════════════════════════════
# EXPENSES VIEW
# ═════════════════════════════════════════════════════════════════════════════

elif view == "Expenses":
    all_expenses = load_expenses()
    if p:
        all_expenses = [e for e in all_expenses if e["person"].lower() == p.lower()]

    filtered = filter_by_range(all_expenses, start_date, end_date)

    expenses = [e for e in filtered if e["type"] == "expense"]
    investments = [e for e in filtered if e["type"] == "investment"]
    refunds = [e for e in filtered if e["type"] == "refund"]

    spending_total = sum(e["amount"] for e in expenses)
    invested_total = sum(e["amount"] for e in investments)
    refund_total = sum(e["amount"] for e in refunds)
    net_spending = spending_total - refund_total
    total_outflow = net_spending + invested_total

    # 4 metric cards
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Net Spending", fmt_inr(net_spending), help="Expenses minus refunds")
    m2.metric("Total Invested", fmt_inr(invested_total))
    m3.metric("Total Refunds", fmt_inr(refund_total))
    m4.metric("Total Outflow", fmt_inr(total_outflow))

    st.divider()

    left_col, right_col = st.columns(2)

    with left_col:
        st.markdown("**Spending vs Budget**")
        budgets_list = load_budgets()
        budgets: dict[str, float] = {}
        for b in budgets_list:
            if p:
                if b["person"].lower() in (p.lower(), "family"):
                    budgets[b["category"]] = b["monthly_limit"]
            else:
                budgets[b["category"]] = b["monthly_limit"]

        totals: dict[str, float] = {}
        for e in expenses:
            totals[e["category"]] = totals.get(e["category"], 0.0) + e["amount"]

        report_rows = []
        for cat in sorted(set(totals) | set(budgets)):
            spent = totals.get(cat, 0.0)
            budget = budgets.get(cat)
            if budget is not None:
                remaining = budget - spent
                status = "OVER" if spent > budget else ("WARNING" if budget > 0 and spent / budget >= 0.9 else "OK")
            else:
                remaining = None
                status = "OK"
            report_rows.append({"category": cat, "spent": spent, "budget": budget, "remaining": remaining, "status": status})

        if report_rows:
            table_rows = []
            for r in report_rows:
                pill = "🔴 OVER" if r["status"] == "OVER" else ("🟡 WARNING" if r["status"] == "WARNING" else "🟢 OK")
                table_rows.append({
                    "Category": r["category"].title(),
                    "Spent": fmt_inr(r["spent"]),
                    "Budget": fmt_inr(r["budget"]) if r["budget"] else "—",
                    "Remaining": fmt_inr(r["remaining"]) if r.get("remaining") is not None else "—",
                    "Status": pill,
                })
            subtotal = sum(r["spent"] for r in report_rows)
            table_rows.append({"Category": "TOTAL", "Spent": fmt_inr(subtotal), "Budget": "", "Remaining": "", "Status": ""})

            df_report = pd.DataFrame(table_rows)

            def style_status(row):
                if "OVER" in str(row["Status"]):
                    return ["background-color:#fde8e8"] * len(row)
                elif "WARNING" in str(row["Status"]):
                    return ["background-color:#fef9e7"] * len(row)
                return [""] * len(row)

            st.dataframe(df_report.style.apply(style_status, axis=1), use_container_width=True, hide_index=True)
        else:
            st.info("No expense data for this period.")

    with right_col:
        st.markdown("**Investments**")
        if investments:
            inv_df = pd.DataFrame(investments)
            by_cat = inv_df.groupby("category")["amount"].sum().reset_index().sort_values("amount", ascending=False)
            inv_rows = [{"Category": r["category"].title(), "Invested": fmt_inr(r["amount"])} for _, r in by_cat.iterrows()]
            inv_rows.append({"Category": "TOTAL", "Invested": fmt_inr(invested_total)})
            st.dataframe(pd.DataFrame(inv_rows), use_container_width=True, hide_index=True)

            fig = go.Figure(go.Bar(
                x=by_cat["amount"].tolist(),
                y=by_cat["category"].tolist(),
                orientation="h",
                marker_color="#7c3aed",
                hovertemplate="%{y}: ₹%{x:,.0f}<extra></extra>",
            ))
            fig.update_layout(height=260, margin=dict(t=10, b=10, l=10, r=10), xaxis_title="Amount (₹)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No investments this period.")

    st.divider()

    st.markdown("**Daily Spend**")
    if expenses:
        df_exp = pd.DataFrame(expenses)
        df_exp["date"] = pd.to_datetime(df_exp["date"])
        daily = df_exp.groupby(df_exp["date"].dt.date)["amount"].sum().reset_index()
        daily.columns = ["date", "amount"]
        daily["date"] = daily["date"].astype(str)

        fig = go.Figure(go.Bar(
            x=daily["date"].tolist(),
            y=daily["amount"].tolist(),
            marker_color="#3b82f6",
            hovertemplate="%{x}: ₹%{y:,.0f}<extra></extra>",
        ))
        fig.update_layout(height=300, margin=dict(t=10, b=10, l=10, r=10), xaxis_title="Date", yaxis_title="Amount (₹)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No expenses to chart.")

    st.divider()

    st.markdown("**Recent Transactions**")
    if filtered:
        df_all = pd.DataFrame(filtered)
        df_all["date"] = pd.to_datetime(df_all["date"])
        df_all = df_all.sort_values("date", ascending=False).head(50)

        txn_rows = []
        for _, row in df_all.iterrows():
            txn_rows.append({
                "Date": row["date"].strftime("%d %b %Y"),
                "Merchant": row.get("merchant") or row.get("category", "").title(),
                "Category": row.get("category", "").title(),
                "Amount": fmt_inr(row.get("amount", 0)),
                "Person": row.get("person", ""),
                "Source": row.get("source", "manual"),
                "Type": row.get("type", "expense"),
            })
        st.dataframe(pd.DataFrame(txn_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No transactions for this period.")


# ═════════════════════════════════════════════════════════════════════════════
# HISTORY VIEW
# ═════════════════════════════════════════════════════════════════════════════

elif view == "History":
    all_expenses = load_expenses()
    if p:
        all_expenses = [e for e in all_expenses if e["person"].lower() == p.lower()]

    months: dict[str, dict] = defaultdict(lambda: {"spending": 0.0, "invested": 0.0, "refunds": 0.0})
    for e in all_expenses:
        month = e["date"][:7]
        if not month:
            continue
        if e["type"] == "investment":
            months[month]["invested"] += e["amount"]
        elif e["type"] == "refund":
            months[month]["refunds"] += e["amount"]
        else:
            months[month]["spending"] += e["amount"]

    history = []
    for month in sorted(months.keys()):
        sp = months[month]["spending"]
        inv = months[month]["invested"]
        ref = months[month]["refunds"]
        history.append({
            "month": month,
            "spending": sp,
            "invested": inv,
            "refunds": ref,
            "net_outflow": sp - ref + inv,
        })

    today_month = date.today().strftime("%Y-%m")

    if history:
        df_hist = pd.DataFrame(history).sort_values("month", ascending=False)

        display_rows = []
        for _, row in df_hist.iterrows():
            is_current = row["month"] == today_month
            display_rows.append({
                "Month": f"► {row['month']}" if is_current else row["month"],
                "Spending": fmt_inr(row["spending"]),
                "Invested": fmt_inr(row["invested"]),
                "Refunds": fmt_inr(row["refunds"]),
                "Net Outflow": fmt_inr(row["net_outflow"]),
            })

        def highlight_current(row):
            if str(row["Month"]).startswith("►"):
                return ["background-color:#fffbeb;font-weight:bold"] * len(row)
            return [""] * len(row)

        df_display = pd.DataFrame(display_rows)
        st.dataframe(df_display.style.apply(highlight_current, axis=1), use_container_width=True, hide_index=True)

        df_chart = pd.DataFrame(history).sort_values("month")
        fig = go.Figure()
        fig.add_trace(go.Bar(name="Spending", x=df_chart["month"].tolist(), y=df_chart["spending"].tolist(), marker_color="#3b82f6"))
        fig.add_trace(go.Bar(name="Invested", x=df_chart["month"].tolist(), y=df_chart["invested"].tolist(), marker_color="#7c3aed"))
        fig.update_layout(barmode="group", height=350, xaxis_title="Month", yaxis_title="Amount (₹)", margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No history data available yet.")
