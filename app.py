"""Step 4: interactive dashboard.   Run:  streamlit run app.py"""
import tempfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from inflation import (C_CPI, C_FOOD, C_PERSONAL, category_contrib, clean, comparison_table,
                       load_cpi, personal_index)
from ocr_parser import parse_receipt

ROOT = Path(__file__).parent
PARSED = ROOT / "data" / "parsed_items.csv"

st.set_page_config(page_title="Personal Inflation Tracker", layout="wide")
st.title("Personal Inflation Tracker")
st.caption("Scan grocery receipts, build your own price index, compare it with CPI.")

# ---------------- Sidebar: data in ----------------
with st.sidebar:
    st.header("1. Receipts")
    uploads = st.file_uploader("Add receipt images", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    if uploads and st.button("Scan with OCR"):
        rows = []
        with st.spinner("Reading receipts..."):
            for up in uploads:
                with tempfile.TemporaryDirectory() as d:
                    p = Path(d) / up.name
                    p.write_bytes(up.getvalue())
                    rows += parse_receipt(p)
        new = pd.DataFrame(rows)
        old = pd.read_csv(PARSED) if PARSED.exists() else pd.DataFrame()
        pd.concat([old, new]).drop_duplicates(["receipt_id", "item", "date"], keep="last").to_csv(PARSED, index=False)
        st.success(f"Added {len(new)} items from {len(uploads)} receipts")

    st.header("2. CPI data")
    cpi_up = st.file_uploader("Official CPI CSV (month, cpi_general, cpi_food)", type="csv")
    st.caption("The bundled cpi.csv is a placeholder. Download real figures from cpi.mospi.gov.in.")
    base_months = st.slider("Base period (months)", 6, 12, 12)

if not PARSED.exists():
    st.info("No receipts yet. Run `python generate_receipts.py` then `python ocr_parser.py`, or upload images.")
    st.stop()

items = pd.read_csv(PARSED)

# ---------------- Review OCR output ----------------
with st.expander(f"Review scanned items ({len(items)} rows), fix OCR mistakes here"):
    bad = ~items["line_ok"].astype(bool) | items["item"].isna()
    st.write(f"{bad.sum()} rows flagged (qty × rate ≠ amount, or unknown item); they're excluded from the index.")
    items = st.data_editor(items, num_rows="dynamic", width="stretch")
    if st.button("Save corrections"):
        items.to_csv(PARSED, index=False)
        st.success("Saved")

res = personal_index(clean(items), base_months)
cpi = load_cpi(cpi_up if cpi_up else ROOT / "data" / "cpi.csv", base_months)
table = comparison_table(res, cpi)
yoy = table.dropna(subset=["personal_yoy"])

if yoy.empty:
    st.warning("Need at least 13 months of receipts to compute year-on-year inflation.")
    st.stop()

# ---------------- Headline numbers ----------------
last, month = yoy.iloc[-1], yoy.index[-1]
c1, c2, c3, c4 = st.columns(4)
c1.metric(f"My inflation ({month})", f"{last['personal_yoy']:.1f}%")
c2.metric("CPI general", f"{last.get('cpi_general_yoy', float('nan')):.1f}%",
          f"{last['personal_yoy'] - last.get('cpi_general_yoy', 0):+.1f} pp gap", delta_color="inverse")
c3.metric("CPI food", f"{last.get('cpi_food_yoy', float('nan')):.1f}%")
c4.metric(f"My average, last {len(yoy)} months", f"{yoy['personal_yoy'].mean():.1f}%")


def line_chart(df, cols, title, ytitle):
    fig = go.Figure()
    for col, name, color in cols:
        if col in df:
            fig.add_scatter(x=df.index.to_timestamp(), y=df[col], name=name, mode="lines+markers",
                            line=dict(color=color, width=2), marker=dict(size=6),
                            hovertemplate="%{y:.2f}<extra>" + name + "</extra>")
    fig.update_layout(title=title, yaxis_title=ytitle, hovermode="x unified", height=380,
                      legend=dict(orientation="h", y=1.12), margin=dict(t=70, l=10, r=10, b=10))
    return fig


series = [("personal_yoy", "My inflation", C_PERSONAL), ("cpi_general_yoy", "CPI general", C_CPI),
          ("cpi_food_yoy", "CPI food", C_FOOD)]
st.plotly_chart(line_chart(yoy, series, "Year-on-year inflation", "%"), width="stretch")

left, right = st.columns(2)
with left:
    idx = [("personal_index", "My grocery index", C_PERSONAL), ("cpi_general", "CPI general", C_CPI),
           ("cpi_food", "CPI food", C_FOOD)]
    st.plotly_chart(line_chart(table, idx, "Price level (base period = 100)", "Index"), width="stretch")
with right:
    pick = st.selectbox("Month to explain", list(yoy.index.astype(str))[::-1])
    cc = category_contrib(res, pd.Period(pick, "M"))
    fig = go.Figure(go.Bar(x=cc.values, y=cc.index, orientation="h", marker_color=C_PERSONAL,
                           text=[f"{v:+.2f}" for v in cc.values], textposition="outside",
                           hovertemplate="%{y}: %{x:.2f} pp<extra></extra>"))
    fig.update_layout(title=f"Drivers of inflation, {pick} (pp)", height=380,
                      xaxis=dict(range=[min(0, cc.min()) * 1.25, max(0, cc.max()) * 1.25]),
                      margin=dict(t=70, l=10, r=10, b=10))
    st.plotly_chart(fig, width="stretch")

st.subheader("Item-level price changes")
p = res["prices"]
movers = pd.DataFrame({
    "weight %": res["weights"] * 100,
    "price then": p.shift(12).iloc[-1],
    "price now": p.iloc[-1],
}).dropna()
movers["change %"] = (movers["price now"] / movers["price then"] - 1) * 100
st.dataframe(movers.sort_values("change %", ascending=False).round(1), width="stretch")

st.subheader("Data table")
st.dataframe(table.round(2), width="stretch")
