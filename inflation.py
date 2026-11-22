"""Step 3: compute your personal inflation rate and compare it with CPI.

Method (same idea the statistics office uses for CPI, applied to your own basket):

  1. Monthly price of each item  p[i,t] = median unit rate seen that month
     (median is robust to the odd OCR misread).
  2. Base year = first 12 months. Base price p0[i] = average of p[i,t] in the base year.
  3. Weights w[i] = your share of spending on item i in the base year.
  4. Laspeyres index   I[t] = 100 * sum_i  w[i] * p[i,t] / p0[i]
  5. Year-on-year inflation  pi[t] = I[t] / I[t-12] - 1
  6. Contribution of item i (percentage points) =
        100 * w[i] * (p[i,t] - p[i,t-12]) / p0[i] / (I[t-12] / 100)
     contributions add up exactly to the headline inflation number.

Run:  python inflation.py   -> prints a summary, writes charts to outputs/
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from catalog import CATEGORY_OF

ROOT = Path(__file__).parent
OUT = ROOT / "outputs"
# Validated categorical slots 1-3 (blue, orange, aqua), always in this order.
C_PERSONAL, C_CPI, C_FOOD = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def clean(items):
    df = items.copy()
    df["date"] = pd.to_datetime(df["date"])
    if "line_ok" in df:
        df = df[df["line_ok"].astype(bool)]
    df = df[df["item"].notna()]
    df["month"] = df["date"].dt.to_period("M")
    return df


def monthly_prices(df):
    prices = df.pivot_table(index="month", columns="item", values="rate", aggfunc="median")
    full = pd.period_range(prices.index.min(), prices.index.max(), freq="M")
    # Months where an item wasn't bought: carry the last seen price forward.
    return prices.reindex(full).ffill().bfill()


def personal_index(df, base_months=12):
    prices = monthly_prices(df)
    base = prices.index[:base_months]
    p0 = prices.loc[base].mean()
    spend = df[df["month"].isin(base)].groupby("item")["amount"].sum()
    w = (spend / spend.sum()).reindex(prices.columns).fillna(0)
    rel = prices / p0                      # price relatives
    index = 100 * (rel * w).sum(axis=1)
    yoy = index.pct_change(12) * 100

    contrib = 100 * (rel - rel.shift(12)).mul(w, axis=1).div(index.shift(12) / 100, axis=0)
    return {"prices": prices, "weights": w, "index": index, "yoy": yoy, "contrib": contrib}


def load_cpi(path=ROOT / "data" / "cpi.csv", base_months=12):
    cpi = pd.read_csv(path)
    cpi["month"] = pd.PeriodIndex(cpi["month"], freq="M")
    cpi = cpi.set_index("month").sort_index()
    out = pd.DataFrame(index=cpi.index)
    for col in [c for c in cpi.columns if c.startswith("cpi_")]:
        out[col] = cpi[col] / cpi[col].iloc[:base_months].mean() * 100  # rebase to base year = 100
        out[col + "_yoy"] = cpi[col].pct_change(12) * 100
    return out


def comparison_table(res, cpi):
    t = pd.DataFrame({"personal_index": res["index"], "personal_yoy": res["yoy"]}).join(cpi, how="left")
    if "cpi_general_yoy" in t:
        t["gap_vs_cpi_pp"] = t["personal_yoy"] - t["cpi_general_yoy"]
    return t


def category_contrib(res, month=None):
    c = res["contrib"].dropna(how="all")
    row = c.loc[month] if month is not None else c.iloc[-1]
    return row.groupby(row.index.map(CATEGORY_OF)).sum().sort_values()


def _style(ax, title, ylabel):
    ax.set_title(title, loc="left", fontsize=13, color=INK, pad=12)
    ax.set_ylabel(ylabel, color=INK2)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.tick_params(colors=INK2)
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)


def make_charts(res, table):
    OUT.mkdir(exist_ok=True)
    x = table.index.to_timestamp()

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(x, table["personal_index"], color=C_PERSONAL, lw=2, label="My grocery index")
    if "cpi_general" in table:
        ax.plot(x, table["cpi_general"], color=C_CPI, lw=2, label="CPI (general)")
    if "cpi_food" in table:
        ax.plot(x, table["cpi_food"], color=C_FOOD, lw=2, label="CPI (food)")
    _style(ax, "Price level, base year average = 100", "Index")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout(); fig.savefig(OUT / "1_price_index.png", dpi=150); plt.close(fig)

    t = table.dropna(subset=["personal_yoy"])
    xt = t.index.to_timestamp()
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(xt, t["personal_yoy"], color=C_PERSONAL, lw=2, marker="o", ms=4, label="My inflation")
    if "cpi_general_yoy" in t:
        ax.plot(xt, t["cpi_general_yoy"], color=C_CPI, lw=2, marker="o", ms=4, label="CPI (general)")
    if "cpi_food_yoy" in t:
        ax.plot(xt, t["cpi_food_yoy"], color=C_FOOD, lw=2, marker="o", ms=4, label="CPI (food)")
    ax.axhline(0, color=INK2, lw=0.8)
    _style(ax, "Year-on-year inflation", "% change vs same month last year")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout(); fig.savefig(OUT / "2_yoy_inflation.png", dpi=150); plt.close(fig)

    cc = category_contrib(res)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(cc.index, cc.values, color=C_PERSONAL, height=0.6)
    for y, v in enumerate(cc.values):
        ax.text(v + (0.03 if v >= 0 else -0.03), y, f"{v:+.2f}", va="center",
                ha="left" if v >= 0 else "right", color=INK2, fontsize=9)
    ax.axvline(0, color=INK2, lw=0.8)
    _style(ax, f"What drove my inflation in {res['contrib'].index[-1]} (pp)", "")
    ax.grid(axis="y", visible=False); ax.grid(axis="x", color=GRID, linewidth=0.8)
    fig.tight_layout(); fig.savefig(OUT / "3_category_contributions.png", dpi=150); plt.close(fig)


def main():
    items = pd.read_csv(ROOT / "data" / "parsed_items.csv")
    res = personal_index(clean(items))
    table = comparison_table(res, load_cpi())
    make_charts(res, table)
    table.round(2).to_csv(OUT / "inflation_vs_cpi.csv")

    last = table.dropna(subset=["personal_yoy"]).iloc[-1]
    print(f"Latest month: {table.dropna(subset=['personal_yoy']).index[-1]}")
    print(f"  My grocery inflation : {last['personal_yoy']:.2f}%")
    for col, label in [("cpi_general_yoy", "CPI general"), ("cpi_food_yoy", "CPI food")]:
        if col in last:
            print(f"  {label:<20} : {last[col]:.2f}%")
    yo = table["personal_yoy"].dropna()
    print(f"Average over last {len(yo)} months: mine {yo.mean():.2f}% vs CPI {table['cpi_general_yoy'].loc[yo.index].mean():.2f}%")

    print("\nBasket weights (base year):")
    print((res["weights"].sort_values(ascending=False) * 100).round(1).to_string())
    print("\nContribution to latest inflation by category (pp):")
    print(category_contrib(res).sort_values(ascending=False).round(2).to_string())

    truth = ROOT / "data" / "receipts_truth.csv"
    if truth.exists():  # sanity check: same calculation on the true printed data
        true_yoy = personal_index(clean(pd.read_csv(truth)))["yoy"].dropna()
        err = (yo - true_yoy).abs()
        print(f"\nOCR-vs-truth error in YoY inflation: mean {err.mean():.3f} pp, max {err.max():.3f} pp")
    print(f"\nCharts saved to {OUT}")


if __name__ == "__main__":
    main()
