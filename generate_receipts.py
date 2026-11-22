"""Step 1: generate dummy grocery receipts as PNG images.

Creates ~2 years of shopping trips. Each item's price follows its own trend,
seasonality and noise (see catalog.py), so the "true" personal inflation is
known and we can check how well OCR + analysis recovers it.

Outputs
  data/receipts/*.png         receipt images (the input to the OCR step)
  data/receipts_truth.csv     what was actually printed (ground truth, for OCR accuracy)
  data/cpi.csv                PLACEHOLDER CPI series - replace with official data
"""
import argparse
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from catalog import CATALOG, STORES

ROOT = Path(__file__).parent
STORE_MARKUP = {STORES[0]: 1.00, STORES[1]: 0.97, STORES[2]: 1.04}


def load_font(size):
    for name in ["consola.ttf", "cour.ttf", "DejaVuSansMono.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def item_price(item, months_since_start, month, store, rng):
    p = item["price"] * (1 + item["yearly"]) ** (months_since_start / 12)
    p *= item.get("season", {}).get(month, 1.0)
    p *= 1 + rng.normal(0, item["vol"])
    p *= STORE_MARKUP[store]
    return round(p)  # shops usually print whole-rupee prices


def render_receipt(store, bill_no, when, lines, path, rng):
    font, big = load_font(20), load_font(24)
    W, row = 620, 30
    H = 310 + row * len(lines)
    img = Image.new("L", (W, H), 250)
    d = ImageDraw.Draw(img)

    y = 20
    d.text((W // 2, y), store, font=big, fill=0, anchor="mt"); y += 40
    d.text((30, y), f"Bill No: {bill_no:05d}", font=font, fill=0); y += row
    d.text((30, y), f"Date: {when:%d/%m/%Y}   Time: {rng.integers(9, 21):02d}:{rng.integers(0, 60):02d}", font=font, fill=0); y += row
    d.text((30, y), "-" * 46, font=font, fill=0); y += row
    d.text((30, y), f"{'ITEM':<20}{'QTY':>5}{'RATE':>10}{'AMT':>11}", font=font, fill=0); y += row
    for name, qty, rate, amt in lines:
        d.text((30, y), f"{name:<20}{qty:>5}{rate:>10.2f}{amt:>11.2f}", font=font, fill=0); y += row
    d.text((30, y), "-" * 46, font=font, fill=0); y += row
    total = sum(l[3] for l in lines)
    d.text((30, y), f"{'TOTAL':<25}{total:>21.2f}", font=font, fill=0); y += row + 10
    d.text((W // 2, y), "THANK YOU! VISIT AGAIN", font=font, fill=0, anchor="mt")

    # Make it look a bit like a phone photo: slight tilt, blur and sensor noise.
    img = img.rotate(rng.uniform(-1.2, 1.2), expand=True, fillcolor=235)
    img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0, 0.8)))
    arr = np.asarray(img, dtype=np.float32) + rng.normal(0, 8, (img.height, img.width))
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(path)


def make_cpi(months, rng):
    """Placeholder CPI so the project runs out of the box.

    !!! These are NOT official numbers. For your report, replace data/cpi.csv with
    the real All-India CPI from MoSPI (https://cpi.mospi.gov.in) keeping the
    same columns: month (YYYY-MM), cpi_general, cpi_food.
    """
    t = np.arange(len(months))
    general = 100 * 1.048 ** (t / 12) * (1 + rng.normal(0, 0.002, len(t)))
    food = 100 * 1.07 ** (t / 12) * (1 + rng.normal(0, 0.006, len(t)))
    return pd.DataFrame({"month": [m.strftime("%Y-%m") for m in months],
                         "cpi_general": general.round(1), "cpi_food": food.round(1)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--months", type=int, default=24)
    ap.add_argument("--trips-per-month", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    random.seed(args.seed)
    out = ROOT / "data" / "receipts"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.png"):
        f.unlink()

    start = date.fromisoformat(args.start)
    months = pd.date_range(start, periods=args.months, freq="MS")
    truth, bill_no = [], 1
    for t, m in enumerate(months):
        for _ in range(args.trips_per_month):
            when = m.date() + timedelta(days=int(rng.integers(0, 28)))
            store = random.choice(STORES)
            # Staples are bought almost every trip, other items sometimes.
            basket = [c for c in CATALOG if rng.random() < (0.9 if c["category"] in ("Dairy", "Vegetables") else 0.55)]
            lines = []
            for item in basket:
                qty = int(rng.integers(item["qty"][0], item["qty"][1] + 1))
                rate = item_price(item, t, m.month, store, rng)
                lines.append((item["name"], qty, float(rate), float(qty * rate)))
            rid = f"R{bill_no:04d}"
            render_receipt(store, bill_no, when, lines, out / f"{rid}_{when:%Y%m%d}.png", rng)
            truth += [{"receipt_id": rid, "date": when, "store": store, "item": n, "qty": q, "rate": r, "amount": a}
                      for n, q, r, a in lines]
            bill_no += 1

    pd.DataFrame(truth).to_csv(ROOT / "data" / "receipts_truth.csv", index=False)
    cpi_path = ROOT / "data" / "cpi.csv"
    if not cpi_path.exists():  # never overwrite real CPI data you've put there
        make_cpi(months, rng).to_csv(cpi_path, index=False)
    print(f"Generated {bill_no - 1} receipts in {out}")


if __name__ == "__main__":
    main()
