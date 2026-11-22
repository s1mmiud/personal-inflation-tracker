"""Step 2: OCR the receipt images and turn them into a clean table.

Pipeline per image:
  1. RapidOCR finds text boxes (pip-installable, no Tesseract needed).
  2. Boxes are grouped into rows by their vertical position.
  3. Regexes pull out the date, store name and item lines (name qty rate amount).
  4. OCR'd item names are fuzzy-matched to the catalog (fixes typos like "T0MATO").
  5. Each line is validated (qty x rate == amount), and the receipt against its TOTAL.

Outputs
  data/parsed_items.csv   one row per purchased item
  prints OCR accuracy against data/receipts_truth.csv when that file exists
"""
import difflib
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from catalog import CATEGORY_OF, ITEM_NAMES, STORES

ROOT = Path(__file__).parent
DATE_RE = re.compile(r"(\d{2})[/\-.](\d{2})[/\-.](\d{4})")
LINE_RE = re.compile(r"^(?P<name>[A-Z][A-Z0-9 .]*?)(?:\s+(?P<qty>\d{1,2}))?\s+(?P<rate>\d+[.,]\d{2})\s+(?P<amt>\d+[.,]\d{2})$")
TOTAL_RE = re.compile(r"TOTAL\D*(\d+[.,]\d{2})")

_engine = None


def ocr_rows(image_path):
    """Return the receipt as a list of text rows, top to bottom."""
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    result, _ = _engine(str(image_path))
    boxes = []
    for box, text, score in result or []:
        ys = [p[1] for p in box]
        boxes.append({"y": sum(ys) / 4, "x": min(p[0] for p in box), "h": max(ys) - min(ys), "text": text})
    boxes.sort(key=lambda b: b["y"])

    rows, current = [], []
    for b in boxes:  # boxes whose centres are within half a line height belong to the same row
        if current and abs(b["y"] - current[-1]["y"]) > max(b["h"], 10) * 0.5:
            rows.append(current)
            current = []
        current.append(b)
    if current:
        rows.append(current)
    return [" ".join(b["text"] for b in sorted(r, key=lambda b: b["x"])) for r in rows]


def to_num(s):
    return float(s.replace(",", "."))


def match_item(raw):
    hit = difflib.get_close_matches(raw.upper().strip(), ITEM_NAMES, n=1, cutoff=0.6)
    return hit[0] if hit else None


def parse_receipt(image_path):
    rows = ocr_rows(image_path)
    text = "\n".join(rows)
    store = (difflib.get_close_matches(rows[0].upper(), STORES, n=1, cutoff=0.5) or [rows[0]])[0] if rows else "?"

    m = DATE_RE.search(text)
    try:
        when = datetime(int(m[3]), int(m[2]), int(m[1])).date()
    except (TypeError, ValueError):  # not found or misread: use the date in the file name, and flag it
        m = None
        when = datetime.strptime(re.search(r"(\d{8})", image_path.stem)[1], "%Y%m%d").date()

    items = []
    for row in rows:
        row = re.sub(r"\s+", " ", row.upper()).strip()
        lm = LINE_RE.match(row)
        if not lm:
            continue
        name = match_item(lm["name"])
        rate, amt = to_num(lm["rate"]), to_num(lm["amt"])
        # OCR often misses the lone qty digit, or misreads it: recover it from amount / rate.
        qty = int(lm["qty"]) if lm["qty"] else 0
        if rate and abs(qty * rate - amt) > 0.5 and abs(amt / rate - round(amt / rate)) < 0.01:
            qty = max(1, round(amt / rate))
        qty = qty or 1  # amount/rate wasn't a whole number -> a digit was misread; line_ok flags it
        items.append({
            "receipt_id": image_path.stem.split("_")[0], "date": when, "store": store,
            "raw_name": lm["name"], "item": name, "category": CATEGORY_OF.get(name, "Unknown"),
            "qty": qty, "rate": rate, "amount": amt,
            "line_ok": abs(qty * rate - amt) <= 0.5, "date_from_ocr": bool(m),
        })

    tm = TOTAL_RE.search(text.upper())
    total_ok = bool(tm) and abs(to_num(tm[1]) - sum(i["amount"] for i in items)) < 1
    for i in items:
        i["total_ok"] = total_ok
    return items


def accuracy_report(parsed, truth_path):
    if not truth_path.exists():
        return
    truth = pd.read_csv(truth_path)
    merged = truth.merge(parsed, on=["receipt_id", "item"], how="left", suffixes=("_true", "_ocr"))
    found = merged["rate_ocr"].notna()
    print("\nOCR accuracy vs ground truth")
    print(f"  item lines recovered : {found.mean():.1%} ({found.sum()}/{len(merged)})")
    print(f"  rate exactly correct : {(merged['rate_true'] == merged['rate_ocr']).mean():.1%}")
    print(f"  qty exactly correct  : {(merged['qty_true'] == merged['qty_ocr']).mean():.1%}")
    extra = len(parsed) - found.sum()
    print(f"  spurious lines       : {extra}")


def main(folder=ROOT / "data" / "receipts"):
    images = sorted(Path(folder).glob("*.png")) + sorted(Path(folder).glob("*.jpg"))
    all_items = []
    for n, img in enumerate(images, 1):
        items = parse_receipt(img)
        all_items += items
        flag = "" if items and items[0]["total_ok"] else "  <-- total mismatch, check manually"
        print(f"[{n}/{len(images)}] {img.name}: {len(items)} items{flag}")
    df = pd.DataFrame(all_items)
    df.to_csv(ROOT / "data" / "parsed_items.csv", index=False)
    print(f"\nSaved {len(df)} item rows to data/parsed_items.csv")
    print(f"Unmatched item names: {df['item'].isna().sum()}")
    accuracy_report(df, ROOT / "data" / "receipts_truth.csv")


if __name__ == "__main__":
    main(*sys.argv[1:])
