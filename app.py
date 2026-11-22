"""Step 4: interactive dashboard.   Run:  streamlit run app.py

Layout and styling live here and in style.css; all the maths is in inflation.py.
"""
import base64
import html
import math
import re
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
TRUTH = ROOT / "data" / "receipts_truth.csv"
RECEIPT_DIR = ROOT / "data" / "receipts"
REPO = "https://github.com/s1mmiud/personal-inflation-tracker"
INK, MUTED, LINE = "#26262b", "#8b8c94", "#e3e4e8"
ABOVE_CPI, BELOW_CPI = "#eb6834", "#b9bac2"
STORE_STRIPES = ["#e87ba4", "#0ca30c", "#6250d6", "#2a78d6"]


def svg_img(svg, w, h, alt=""):
    """st.html strips inline <svg>, so embed it as an image instead."""
    data = base64.b64encode(svg.encode()).decode()
    return f'<img src="data:image/svg+xml;base64,{data}" width="{w}" height="{h}" alt="{alt}" style="display:block">'


def mark(color):
    return svg_img(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke="{color}" '
                   'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                   '<path d="M2 12 L6 7 L9 10 L14 4"/></svg>', 14, 14)


MARK = mark(INK)

st.set_page_config(page_title="Personal Inflation Tracker", page_icon=":material/trending_up:", layout="wide")
st.html(f"<style>{(ROOT / 'style.css').read_text(encoding='utf-8')}</style>")


# ---------------- helpers ----------------
def pretty(name):
    """'TOOR DAL 1KG' -> 'Toor Dal 1kg'"""
    units = {"L": "L"}
    words = []
    for w in str(name).split():
        m = re.match(r"^(\d+)([A-Z]+)$", w)
        words.append(m[1] + units.get(m[2], m[2].lower()) if m else w.capitalize())
    return " ".join(words)


def mlabel(period):
    return period.strftime("%b %Y")


def esc(s):
    return html.escape(str(s))


def style_fig(fig, height=340):
    fig.update_layout(
        height=height, margin=dict(l=4, r=4, t=36, b=4),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color=INK, size=12),
        legend=dict(orientation="h", x=0, y=1.12, font=dict(color=MUTED, size=12)),
        hoverlabel=dict(bgcolor="white", bordercolor=LINE, font=dict(family="Inter, sans-serif", color=INK)),
    )
    fig.update_xaxes(showgrid=False, linecolor=LINE, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=LINE, zeroline=False, tickfont=dict(color=MUTED))
    return fig


def line_fig(df, series, ysuffix=""):
    fig = go.Figure()
    for col, name, color in series:
        if col in df:
            fig.add_scatter(x=df.index.to_timestamp(), y=df[col], name=name, mode="lines+markers",
                            line=dict(color=color, width=2), marker=dict(size=7, line=dict(color="white", width=1.5)),
                            hovertemplate="%{y:.1f}" + ysuffix + "<extra>" + name + "</extra>")
    fig.update_layout(hovermode="x unified")
    return style_fig(fig)


def ring(value, marker, scale):
    r, w = 66, 14
    c = 2 * math.pi * r
    frac = max(0.0, min(value / scale, 1.0))
    ang = 2 * math.pi * max(0.0, min(marker / scale, 1.0)) - math.pi / 2
    x1, y1 = 90 + (r - 11) * math.cos(ang), 90 + (r - 11) * math.sin(ang)
    x2, y2 = 90 + (r + 11) * math.cos(ang), 90 + (r + 11) * math.sin(ang)
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="180" height="180" viewBox="0 0 180 180">
      <circle cx="90" cy="90" r="{r}" fill="none" stroke="rgba(255,255,255,.35)" stroke-width="{w}"/>
      <circle cx="90" cy="90" r="{r}" fill="none" stroke="#fff" stroke-width="{w}" stroke-linecap="round"
              stroke-dasharray="{frac * c:.1f} {c:.1f}" transform="rotate(-90 90 90)"/>
      <line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{INK}" stroke-width="3" stroke-linecap="round"/>
      <text x="90" y="96" text-anchor="middle" fill="#fff" font-family="Inter, Segoe UI, sans-serif"
            font-size="34" font-weight="300">{value:.1f}%</text>
      <text x="90" y="118" text-anchor="middle" fill="#fff" font-family="Inter, Segoe UI, sans-serif"
            font-size="12" opacity=".9">/ {marker:.1f}% CPI</text>
    </svg>"""
    alt = f"My inflation {value:.1f}% against CPI {marker:.1f}% on a 0 to {scale:.0f}% scale"
    return f'<div class="ring">{svg_img(svg, 180, 180, alt)}</div>'


def ocr_accuracy(items):
    if not TRUTH.exists():
        return None
    truth = pd.read_csv(TRUTH)
    m = truth.merge(items, on=["receipt_id", "item"], how="left", suffixes=("_t", "_o"))
    return {"lines": m["rate_o"].notna().mean(), "rates": (m["rate_t"] == m["rate_o"]).mean()}


# ---------------- data ----------------
if not PARSED.exists():
    st.info("No receipts yet. Run `python generate_receipts.py` then `python ocr_parser.py`.")
    st.stop()

items = pd.read_csv(PARSED)
base_months = st.session_state.get("base_months", 12)
cpi_src = st.session_state.get("cpi_file") or ROOT / "data" / "cpi.csv"
if hasattr(cpi_src, "seek"):
    cpi_src.seek(0)

res = personal_index(clean(items), base_months)
table = comparison_table(res, load_cpi(cpi_src, base_months))
yoy = table.dropna(subset=["personal_yoy"])
if yoy.empty:
    st.warning("Need at least 13 months of receipts to compute year-on-year inflation.")
    st.stop()

months = [str(p) for p in yoy.index]
if st.session_state.get("month") not in months:
    st.session_state["month"] = months[-1]


def shift_month(step):
    i = months.index(st.session_state["month"])
    st.session_state["month"] = months[max(0, min(len(months) - 1, i + step))]


month = pd.Period(st.session_state["month"], "M")
row = yoy.loc[month]
mine, cpi_gen = row["personal_yoy"], row.get("cpi_general_yoy", float("nan"))
dated = items.assign(date=pd.to_datetime(items["date"]))
n_receipts = items["receipt_id"].nunique()
span = f"{dated['date'].min():%b %Y} – {dated['date'].max():%b %Y}"

# ---------------- layout ----------------
nav_col, main = st.columns([1, 4.4], gap="small")

with nav_col:
    with st.container(key="nav", gap="medium"):
        st.html(f'<div class="brand"><span class="brand-mark">{mark("#ffffff")}</span>Inflation tracker</div>')
        last = yoy.iloc[-1]
        st.html(f'<div class="status"><div><small>Latest · {mlabel(yoy.index[-1])}</small>'
                f'<b>{last["personal_yoy"]:.1f}% / yr</b></div><span class="sq">%</span></div>')
        pages = {"Overview": ":material/space_dashboard:", "Drivers": ":material/bar_chart:",
                 "Receipts": ":material/receipt_long:", "Method": ":material/menu_book:"}
        page = st.radio("Pages", list(pages), key="page", label_visibility="collapsed",
                        format_func=lambda p: f"{pages[p]}&nbsp;&nbsp;{p}")
        with st.container(key="navnote", gap="small"):
            st.html('<div class="note"><h4>Demo data</h4><p>The receipts are synthetic and the CPI series is a '
                    'placeholder until official MoSPI figures are added.</p></div>')
            st.link_button("View code on GitHub", REPO, icon=":material/code:")

with main:
    top, who = st.columns([3.3, 1.1], gap="small", vertical_alignment="center")
    with top:
        with st.container(key="topbar", horizontal=True, vertical_alignment="center", gap="small"):
            st.html('<div class="ask">Is my inflation higher than CPI?</div>')
            with st.popover("Upload receipts", icon=":material/upload:"):
                uploads = st.file_uploader("Receipt images", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
                if uploads and st.button("Scan with OCR", type="primary"):
                    rows = []
                    with st.spinner("Reading receipts..."):
                        for up in uploads:
                            with tempfile.TemporaryDirectory() as d:
                                p = Path(d) / up.name
                                p.write_bytes(up.getvalue())
                                rows += parse_receipt(p)
                    new = pd.DataFrame(rows)
                    if new.empty:
                        st.error("No item lines could be read from these images.")
                    else:
                        # Re-scanning a receipt replaces its old rows instead of adding them twice.
                        old = items[~items["receipt_id"].isin(new["receipt_id"])]
                        pd.concat([old, new]).to_csv(PARSED, index=False)
                        st.rerun()
            with st.popover("Settings", icon=":material/tune:"):
                st.slider("Base period (months)", 6, 12, 12, key="base_months",
                          help="Spending in these first months sets the basket weights.")
                st.file_uploader("Official CPI file (month, cpi_general, cpi_food)", type="csv", key="cpi_file")
                st.caption("Download real figures from cpi.mospi.gov.in")
            st.download_button("Export", table.round(2).to_csv().encode(), "inflation_vs_cpi.csv",
                               icon=":material/download:", help="Download the results as CSV")
    with who:
        with st.container(key="datacard"):
            st.html(f'<div class="who"><span class="av">{n_receipts}</span>'
                    f'<div><b>Receipts scanned</b><small>{span}</small></div></div>')

    # ---------- shared month control ----------
    def controls(with_view=True):
        if with_view:
            left, _, right = st.columns([1.5, 1.4, 1.7], vertical_alignment="center")
        else:
            left, _ = st.columns([1.5, 3.1], vertical_alignment="center")
        with left:
            with st.container(key="monthnav", horizontal=True, vertical_alignment="center", gap=None):
                st.button("", icon=":material/chevron_left:", key="prev", on_click=shift_month, args=(-1,))
                st.selectbox("Month", months, key="month", label_visibility="collapsed",
                             format_func=lambda m: mlabel(pd.Period(m, "M")))
                st.button("", icon=":material/chevron_right:", key="next", on_click=shift_month, args=(1,))
        if with_view:
            with right:
                with st.container(key="viewswitch"):
                    return st.segmented_control("View", ["Inflation", "Price level", "Spending"], default="Inflation",
                                                key="view", label_visibility="collapsed")

    # ================= OVERVIEW =================
    if page == "Overview":
        hero, blue = st.columns(2, gap="small")
        gap_pp = mine - cpi_gen
        word = "faster" if gap_pp > 0 else "slower"
        with hero:
            st.html(f"""
            <div class="hero">
              <div><h2>Past 12 months</h2>
                <div class="sub">My grocery basket cost {mine:.1f}% more in {mlabel(month)} than a year
                earlier, rising {abs(gap_pp):.1f} points {word} than official inflation.</div></div>
              {ring(mine, cpi_gen, max(10, math.ceil(max(mine, cpi_gen) / 5) * 5))}
              <div class="chips"><span class="glass">{mlabel(month)}</span>
                <span class="glass solid">{gap_pp:+.1f} pp vs CPI</span></div>
            </div>""")
        with blue:
            cc = category_contrib(res, month).sort_values(ascending=False)
            cat_w = (items.dropna(subset=["item"]).drop_duplicates("item").set_index("item")["category"])
            cat_share = res["weights"].groupby(cat_w).sum() * 100
            rows = ""
            for i, (cat, v) in enumerate(cc.head(4).items()):
                rows += (f'<div class="row{" fade" if i == 3 else ""}"><div class="bar"><span>{esc(cat)}</span>'
                         f'<span class="pill">{cat_share.get(cat, 0):.0f}% of basket</span></div>'
                         f'<div class="val">{v:+.2f}</div></div>')
            st.html(f"""
            <div class="blue"><div class="head"><h2>What pushed it</h2>
              <span class="plus">pp of inflation</span></div>{rows}</div>""")

        view = controls() or "Inflation"
        with st.container(key="card_main"):
            if view == "Inflation":
                st.html('<p class="card-title">Year-on-year inflation</p>'
                        '<p class="card-sub">% change in prices vs the same month a year earlier</p>')
                st.plotly_chart(line_fig(yoy, [("personal_yoy", "My basket", C_PERSONAL),
                                              ("cpi_general_yoy", "CPI general", C_CPI),
                                              ("cpi_food_yoy", "CPI food", C_FOOD)], "%"),
                                width="stretch", config={"displayModeBar": False})
            elif view == "Price level":
                st.html('<p class="card-title">Price level</p>'
                        f'<p class="card-sub">Index, average of the first {base_months} months = 100</p>')
                st.plotly_chart(line_fig(table, [("personal_index", "My basket", C_PERSONAL),
                                                ("cpi_general", "CPI general", C_CPI),
                                                ("cpi_food", "CPI food", C_FOOD)]),
                                width="stretch", config={"displayModeBar": False})
            else:
                spend = dated.groupby(dated["date"].dt.to_period("M"))["amount"].sum()
                st.html('<p class="card-title">Monthly grocery spending</p>'
                        '<p class="card-sub">Total of all scanned receipts, ₹</p>')
                fig = go.Figure(go.Bar(x=spend.index.to_timestamp(), y=spend.values, marker_color=C_PERSONAL,
                                       marker_cornerradius=4, hovertemplate="₹%{y:,.0f}<extra></extra>"))
                st.plotly_chart(style_fig(fig), width="stretch", config={"displayModeBar": False})

    # ================= DRIVERS =================
    elif page == "Drivers":
        st.html('<p class="page-title">What is driving my inflation</p>'
                '<p class="page-sub">Each category\'s contribution adds up to the headline rate.</p>')
        controls(with_view=False)
        cc = category_contrib(res, month).sort_values()
        with st.container(key="card_drivers"):
            st.html(f'<p class="card-title">Contribution by category, {mlabel(month)}</p>'
                    f'<p class="card-sub">Percentage points · total {mine:.2f}%</p>')
            fig = go.Figure(go.Bar(x=cc.values, y=cc.index, orientation="h", marker_color=C_PERSONAL,
                                   marker_cornerradius=4, text=[f"{v:+.2f}" for v in cc.values],
                                   textposition="outside", textfont=dict(color=MUTED),
                                   hovertemplate="%{y}: %{x:.2f} pp<extra></extra>"))
            fig.update_xaxes(range=[min(0, cc.min()) * 1.3, max(0, cc.max()) * 1.25], gridcolor=LINE, showgrid=True)
            fig.update_yaxes(showgrid=False)
            st.plotly_chart(style_fig(fig, 330), width="stretch", config={"displayModeBar": False})

        prices = res["prices"]
        prev = month - 12
        cat_of = items.dropna(subset=["item"]).drop_duplicates("item").set_index("item")["category"]
        movers = pd.DataFrame({"then": prices.loc[prev], "now": prices.loc[month],
                               "w": res["weights"] * 100}).dropna()
        movers["chg"] = (movers["now"] / movers["then"] - 1) * 100
        tiles = ""
        for item, r in movers.sort_values("chg", ascending=False).iterrows():
            above = r["chg"] > cpi_gen
            tiles += f"""
            <div class="tile" style="--stripe:{ABOVE_CPI if above else BELOW_CPI}">
              <div class="chips"><span class="pill grey">{esc(cat_of.get(item, ''))}</span>
                <span class="pill grey">{'above CPI' if above else 'below CPI'}</span></div>
              <span class="mark">{MARK}</span>
              <h5>{esc(pretty(item))}</h5><div class="meta">{r['w']:.1f}% of my basket</div>
              <div class="big">{r['chg']:+.1f}%</div>
              <div class="badge"><div>₹{r['then']:.0f}<small>to</small>₹{r['now']:.0f}</div></div>
            </div>"""
        st.html(f'<p class="card-title" style="margin-top:18px">Item prices vs a year earlier</p>'
                f'<p class="card-sub">Orange stripe: rose faster than CPI general ({cpi_gen:.1f}%)</p>'
                f'<div class="tiles">{tiles}</div>')

    # ================= RECEIPTS =================
    elif page == "Receipts":
        st.html('<p class="page-title">Receipts</p>'
                '<p class="page-sub">Every receipt is read with OCR and checked: qty × rate must equal the amount, '
                'and the lines must add up to the printed total.</p>')
        controls(with_view=False)
        rec = (dated.groupby("receipt_id")
               .agg(date=("date", "first"), store=("store", "first"), n=("item", "size"),
                    total=("amount", "sum"), ok=("total_ok", "all"))
               .sort_values("date"))
        upto = rec[rec["date"].dt.to_period("M") <= month].tail(8).iloc[::-1]
        stores = sorted(rec["store"].unique())
        tiles = ""
        for rid, r in upto.iterrows():
            stripe = STORE_STRIPES[stores.index(r["store"]) % len(STORE_STRIPES)]
            tiles += f"""
            <div class="tile" style="--stripe:{stripe}">
              <div class="chips"><span class="pill grey">{esc(str(r['store']).title())}</span>
                <span class="pill grey">{'total matches' if r['ok'] else 'check manually'}</span></div>
              <span class="mark">{MARK}</span>
              <h5>Bill {esc(rid)}</h5><div class="meta">{r['date']:%d %b %Y} · {r['n']} items</div>
              <div class="badge"><div><small>total</small>₹{r['total']:,.0f}</div></div>
            </div>"""
        st.html(f'<p class="card-title">Latest receipts up to {mlabel(month)}</p>'
                f'<p class="card-sub">Stripe colour = store</p><div class="tiles">{tiles}</div>')

        st.html('<p class="card-title" style="margin-top:22px">Inspect a receipt</p>'
                '<p class="card-sub">The original image next to what OCR read from it</p>')
        pick = st.selectbox("Receipt", list(rec.index[::-1]), label_visibility="collapsed",
                            format_func=lambda r: f"Bill {r} · {rec.loc[r, 'date']:%d %b %Y} · {str(rec.loc[r, 'store']).title()}")
        img_col, data_col = st.columns([1, 1.2], gap="medium")
        with img_col:
            imgs = sorted(RECEIPT_DIR.glob(f"{pick}_*.png"))
            if imgs:
                st.image(str(imgs[0]), width="stretch")
            else:
                st.caption("Original image not stored for this receipt.")
        with data_col:
            lines = items[items["receipt_id"] == pick][["item", "qty", "rate", "amount", "line_ok"]].copy()
            lines["item"] = lines["item"].map(pretty)
            st.dataframe(lines, hide_index=True, width="stretch",
                         column_config={"line_ok": st.column_config.CheckboxColumn("checked"),
                                        "rate": st.column_config.NumberColumn(format="₹%.2f"),
                                        "amount": st.column_config.NumberColumn(format="₹%.2f")})

        with st.expander(f"Fix OCR mistakes ({len(items)} rows)"):
            bad = ~items["line_ok"].astype(bool) | items["item"].isna()
            st.caption(f"{bad.sum()} rows are flagged and left out of the index. Edit a row and save to include it.")
            edited = st.data_editor(items, num_rows="dynamic", width="stretch", key="editor")
            if st.button("Save corrections"):
                edited.to_csv(PARSED, index=False)
                st.rerun()

    # ================= METHOD =================
    else:
        st.html('<p class="page-title">How it works</p>'
                '<p class="page-sub">Official CPI averages a national basket. This app builds the same kind of '
                'index from one person\'s receipts.</p>')
        st.html("""
        <div class="steps">
          <div class="step"><div class="n">01</div><h5>Receipts</h5><p>Two years of synthetic grocery receipts
            with known price trends, seasonal spikes and phone-photo noise.</p></div>
          <div class="step"><div class="n">02</div><h5>OCR</h5><p>RapidOCR reads each image. Text boxes are
            grouped into rows and parsed into item, quantity, rate and amount.</p></div>
          <div class="step"><div class="n">03</div><h5>Validation</h5><p>Lines must satisfy qty × rate = amount
            and add up to the printed total. Anything else is flagged, not used.</p></div>
          <div class="step"><div class="n">04</div><h5>Index</h5><p>A Laspeyres price index weighted by my own
            spending, compared with CPI year on year.</p></div>
        </div>""")
        acc = ocr_accuracy(items)
        if acc:
            true_yoy = personal_index(clean(pd.read_csv(TRUTH)), base_months)["yoy"].dropna()
            err = (yoy["personal_yoy"] - true_yoy).abs().mean()
            st.html(f"""
            <p class="card-title" style="margin-top:22px">How accurate is it?</p>
            <p class="card-sub">The receipts are synthetic, so the true answer is known.</p>
            <div class="stats">
              <div class="stat"><b>{acc['lines']:.1%}</b><span>of receipt lines recovered by OCR</span></div>
              <div class="stat"><b>{acc['rates']:.1%}</b><span>of prices read exactly right</span></div>
              <div class="stat"><b>{err:.2f} pp</b><span>average error in the final inflation rate</span></div>
            </div>""")
        with st.container(key="card_formula"):
            st.html('<p class="card-title">The formula</p>'
                    '<p class="card-sub">Weights w come from spending in the base period; p₀ is the base-period price.</p>')
            st.latex(r"I_t = 100 \sum_i w_i \frac{p_{i,t}}{p_{i,0}} \qquad \pi_t = \frac{I_t}{I_{t-12}} - 1")
