"""True total return = realized P&L + unrealized P&L of positions still held.

The cash-flow and FIFO views only show REALIZED profit (closed trades). For
positions you still hold (e.g. FTSE All-World), the money you "spent and didn't
get back" is not a loss — it's shares you still own. To value them we need your
CURRENT portfolio from Trade Republic:

    python3 -m pytr portfolio -o tr_docs/portfolio.csv

That CSV has columns: Name, ISIN, quantity, price (current), avgCost, netValue.
We combine it with the FIFO open-position cost basis:

    total_return = realized_pnl + (current_market_value - open_cost_basis)

Run:  python3 total_return.py
"""
import csv
import os
import sys

from pytr_fifo import fifo


def _num(s):
    if s is None or s == "":
        return 0.0
    s = str(s).replace("€", "").replace("$", "").strip()
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def load_portfolio(path):
    """Return {isin or name: {'qty','price','value','name'}} from pytr CSV."""
    holdings = {}
    if not os.path.exists(path):
        return holdings
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # pytr column names vary in case; normalize.
            r = {k.strip().lower(): v for k, v in row.items()}
            isin = (r.get("isin") or "").strip()
            name = (r.get("name") or "").strip()
            qty = _num(r.get("quantity"))
            price = _num(r.get("price"))
            value = _num(r.get("netvalue")) or qty * price
            key = isin or name
            if key:
                holdings[key] = {"qty": qty, "price": price,
                                 "value": value, "name": name}
    return holdings


def analyze(events_path, portfolio_path):
    fi = fifo(events_path)
    holdings = load_portfolio(portfolio_path)
    have_portfolio = bool(holdings)
    used_holdings = set()  # which portfolio keys we matched to a FIFO row

    rows = []
    for r in fi["instruments"]:
        key = r["isin"] or r["name"]
        # Match this FIFO instrument to a current holding by ISIN then name.
        h = holdings.get(key) or holdings.get(r["name"])
        h_key = key if key in holdings else (r["name"] if r["name"] in holdings else None)
        if h_key:
            used_holdings.add(h_key)
        market_value = h["value"] if h else 0.0
        open_cost = r.get("open_cost_basis", 0.0)
        # If TR still reports a holding, value it at market even when FIFO's
        # open_shares rounds to ~0 (the data's sells matched all its buys but
        # you actually still hold shares). Use the holding as source of truth.
        held = bool(h) and market_value > 0
        unrealized = (market_value - open_cost) if held else 0.0
        total = r["realized"] + unrealized
        rows.append({
            "name": r["name"],
            "realized": r["realized"],
            "open_shares": r["open_shares"],
            "open_cost_basis": round(open_cost, 2),
            "market_value": round(market_value, 2),
            "unrealized": round(unrealized, 2),
            "total": round(total, 2),
            "wins": r["wins"], "losses": r["losses"],
            "no_basis": r.get("no_basis", False),
        })

    # Add any current holding that never matched a FIFO instrument (e.g. its
    # buys are before the export window). Without this, its market value would
    # vanish from the total — the bug that made holdings under-report.
    for hkey, h in holdings.items():
        if hkey in used_holdings:
            continue
        rows.append({
            "name": h["name"] or hkey,
            "realized": 0.0,
            "open_shares": round(h["qty"], 4),
            "open_cost_basis": 0.0,
            "market_value": round(h["value"], 2),
            "unrealized": 0.0,  # cost basis unknown -> can't compute P&L
            "total": 0.0,
            "wins": 0, "losses": 0,
            "no_basis": True,
        })

    rows.sort(key=lambda r: r["total"])
    holdings_value = round(sum(h["value"] for h in holdings.values()), 2)

    return {
        "instruments": rows,
        "realized_total": round(sum(r["realized"] for r in rows), 2),
        "unrealized_total": round(sum(r["unrealized"] for r in rows), 2),
        "total_return": round(sum(r["total"] for r in rows), 2),
        "holdings_value": holdings_value,   # current market value of all stock
        "have_portfolio": have_portfolio,
    }


if __name__ == "__main__":
    events = sys.argv[1] if len(sys.argv) > 1 else "tr_docs/events_with_documents.json"
    pf = sys.argv[2] if len(sys.argv) > 2 else "tr_docs/portfolio.csv"
    res = analyze(events, pf)
    if not res["have_portfolio"]:
        print("⚠️  No portfolio.csv found. Run:")
        print("    python3 -m pytr portfolio -o tr_docs/portfolio.csv")
        print("Showing realized P&L only (unrealized = 0).\n")
    print(f"{'Instrument':<26}{'Realized':>11}{'Unrealized':>12}{'Total':>11}")
    print("-" * 60)
    for r in res["instruments"]:
        print(f"{r['name']:<26}{r['realized']:>11.2f}{r['unrealized']:>12.2f}"
              f"{r['total']:>11.2f}")
    print("-" * 60)
    print(f"{'TOTAL':<26}{res['realized_total']:>11.2f}"
          f"{res['unrealized_total']:>12.2f}{res['total_return']:>11.2f}")
    print(f"\nCurrent stock holdings value: €{res['holdings_value']:,.2f}")
    print(f"Realized P&L (closed trades):  €{res['realized_total']:,.2f}")
    print(f"True total return (realized + unrealized): €{res['total_return']:,.2f}")
