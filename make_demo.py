"""Generate synthetic demo data so the product runs out-of-the-box.

Writes tr_docs_demo/events_with_documents.json and portfolio.csv in the exact
pytr schema, with fictional-but-realistic trades for a handful of well-known
tickers. No real account data. Re-run to regenerate.

    python3 make_demo.py
"""
import csv
import json
import os

OUT_DIR = "tr_docs_demo"

# Fictional instruments: (name, isin, behaviour). ISINs are the real public
# ISINs for these tickers so the ISIN->ticker auto-resolver works in the demo.
INSTRUMENTS = {
    "NVIDIA":            "US67066G1040",
    "Apple":             "US0378331005",
    "Micron Technology": "US5951121038",
    "Rivian Automotive": "US76954A1034",
    "Core MSCI World USD (Acc)": "IE00B4L5Y983",
}

# A deterministic, hand-built trade script: (date, name, side, shares, price).
# Tells a realistic story: NVIDIA held = winner; Rivian churned = loser;
# Micron round-tripped flat; Apple a clean win; the ETF partly held (open).
TRADES = [
    ("2026-03-02", "NVIDIA", "buy", 5.0, 110.00),
    ("2026-03-02", "Apple", "buy", 4.0, 168.00),
    ("2026-03-05", "Rivian Automotive", "buy", 60.0, 12.50),
    ("2026-03-06", "Rivian Automotive", "sell", 60.0, 11.80),   # panic sell -42
    ("2026-03-09", "Rivian Automotive", "buy", 70.0, 12.10),
    ("2026-03-10", "Rivian Automotive", "sell", 70.0, 11.40),   # churn -49
    ("2026-03-12", "Micron Technology", "buy", 8.0, 95.00),
    ("2026-03-18", "Micron Technology", "sell", 8.0, 96.20),    # +9.6
    ("2026-03-20", "Rivian Automotive", "buy", 80.0, 13.00),
    ("2026-03-23", "Rivian Automotive", "sell", 80.0, 12.20),   # churn -64
    ("2026-04-01", "Apple", "sell", 4.0, 182.50),               # +58 clean win
    ("2026-04-06", "Core MSCI World USD (Acc)", "buy", 20.0, 100.00),
    ("2026-04-15", "NVIDIA", "buy", 3.0, 118.00),
    ("2026-05-02", "Core MSCI World USD (Acc)", "sell", 6.0, 104.00),  # partial
    ("2026-05-20", "NVIDIA", "sell", 4.0, 152.00),              # big win, still holds 4
]

# Current holdings (open positions) with a "live" price for the demo.
HOLDINGS = [
    ("NVIDIA", "US67066G1040", 4.0, 158.00),
    ("Core MSCI World USD (Acc)", "IE00B4L5Y983", 14.0, 103.50),
]


def _event(date, name, side, shares, price):
    isin = INSTRUMENTS[name]
    total = shares * price
    is_buy = side == "buy"
    return {
        "id": f"demo-{date}-{name}-{side}".replace(" ", "_"),
        "timestamp": f"{date}T10:30:00.000+0000",
        "title": name,
        "icon": f"logos/{isin}/v2",
        "avatar": {"asset": f"logos/{isin}/v2", "badge": None},
        "subtitle": "Kauforder" if is_buy else "Verkaufsorder",
        "amount": {"currency": "EUR", "value": round(-total if is_buy else total, 2),
                   "fractionDigits": 2},
        "status": "EXECUTED",
        "eventType": "TRADING_TRADE_EXECUTED",
        "details": {
            "sections": [
                {"title": f"Du hast {total:.2f} € {'gezahlt' if is_buy else 'erhalten'}",
                 "type": "header"},
                {"title": "Übersicht", "data": [
                    {"title": "Kaufen" if is_buy else "Verkaufen",
                     "detail": {"text": "Ausgeführt", "type": "status"}},
                    {"title": "Asset", "detail": {"text": name, "type": "text"}},
                    {"title": "Transaktion",
                     "detail": {"text": f"{shares:.6f} ×  {price:.2f} €".replace(".", ","),
                                "type": "text"}},
                ]},
            ]
        },
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    events = [_event(*t) for t in TRADES]
    # newest-first, like a real pytr export
    events.sort(key=lambda e: e["timestamp"], reverse=True)
    with open(os.path.join(OUT_DIR, "events_with_documents.json"), "w",
              encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)

    with open(os.path.join(OUT_DIR, "portfolio.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Name", "ISIN", "quantity", "price", "netValue"])
        w.writeheader()
        for name, isin, qty, price in HOLDINGS:
            w.writerow({"Name": name, "ISIN": isin, "quantity": qty,
                        "price": price, "netValue": round(qty * price, 2)})

    # Fake available cash so the demo shows the headline / cash card too.
    with open(os.path.join(OUT_DIR, "cash.json"), "w", encoding="utf-8") as f:
        json.dump({"available_cash": 1842.55}, f)

    print(f"Wrote {len(events)} demo events + {len(HOLDINGS)} holdings to {OUT_DIR}/")


if __name__ == "__main__":
    main()
