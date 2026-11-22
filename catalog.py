"""Item catalog shared by the receipt generator and the OCR parser.

Prices are in INR. `yearly` is the underlying yearly price trend for the item,
`vol` is month-to-month noise, and `season` is an optional {month: multiplier}
map for items with seasonal price spikes (e.g. tomatoes in the monsoon).
"""

CATALOG = [
    # name,               category,     base price, yearly trend, noise, typical qty
    {"name": "BASMATI RICE 1KG",   "category": "Cereals",    "price": 110, "yearly": 0.06, "vol": 0.01, "qty": (1, 3)},
    {"name": "WHEAT ATTA 5KG",     "category": "Cereals",    "price": 260, "yearly": 0.07, "vol": 0.01, "qty": (1, 1)},
    {"name": "TOOR DAL 1KG",       "category": "Pulses",     "price": 160, "yearly": 0.12, "vol": 0.02, "qty": (1, 2)},
    {"name": "MOONG DAL 500G",     "category": "Pulses",     "price": 75,  "yearly": 0.09, "vol": 0.02, "qty": (1, 2)},
    {"name": "TONED MILK 1L",      "category": "Dairy",      "price": 62,  "yearly": 0.05, "vol": 0.00, "qty": (2, 6)},
    {"name": "PANEER 200G",        "category": "Dairy",      "price": 90,  "yearly": 0.06, "vol": 0.01, "qty": (1, 2)},
    {"name": "CURD 400G",          "category": "Dairy",      "price": 45,  "yearly": 0.05, "vol": 0.01, "qty": (1, 2)},
    {"name": "EGGS 12PC",          "category": "Eggs & Meat", "price": 84, "yearly": 0.04, "vol": 0.04, "qty": (1, 2)},
    {"name": "TOMATO 1KG",         "category": "Vegetables", "price": 40,  "yearly": 0.08, "vol": 0.06, "qty": (1, 2),
     "season": {6: 1.4, 7: 2.0, 8: 1.7, 9: 1.2}},
    {"name": "ONION 1KG",          "category": "Vegetables", "price": 35,  "yearly": 0.10, "vol": 0.05, "qty": (1, 3),
     "season": {9: 1.3, 10: 1.6, 11: 1.4}},
    {"name": "POTATO 1KG",         "category": "Vegetables", "price": 30,  "yearly": 0.05, "vol": 0.03, "qty": (1, 3)},
    {"name": "BANANA 1DOZ",        "category": "Fruits",     "price": 60,  "yearly": 0.05, "vol": 0.03, "qty": (1, 1)},
    {"name": "SUNFLOWER OIL 1L",   "category": "Oils",       "price": 140, "yearly": 0.03, "vol": 0.02, "qty": (1, 1)},
    {"name": "SUGAR 1KG",          "category": "Sugar & Tea", "price": 45, "yearly": 0.03, "vol": 0.01, "qty": (1, 2)},
    {"name": "TEA LEAVES 250G",    "category": "Sugar & Tea", "price": 140, "yearly": 0.04, "vol": 0.01, "qty": (1, 1)},
    {"name": "BREAD 400G",         "category": "Bakery",     "price": 45,  "yearly": 0.05, "vol": 0.00, "qty": (1, 2)},
    {"name": "BISCUITS 200G",      "category": "Bakery",     "price": 30,  "yearly": 0.03, "vol": 0.00, "qty": (1, 3)},
]

ITEM_NAMES = [c["name"] for c in CATALOG]
CATEGORY_OF = {c["name"]: c["category"] for c in CATALOG}

STORES = ["FRESHMART SUPERSTORE", "DAILY NEEDS KIRANA", "GREEN BASKET MARKET"]
