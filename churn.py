"""Churn-cost analyzer.

Answers, per instrument: did your high-frequency in-and-out trading actually
beat simply buying once and holding? Uses ONLY your own executed trade prices
(from the pytr export) — no external market data required.

Method per instrument, over its executed trades sorted oldest-first:
  * actual_pnl  = real FIFO realized P&L from all your round trips (what you got)
  * hold_pnl    = counterfactual of a single position: take the TOTAL shares you
                  ever bought, "buy" them all at your *first* buy price, and
                  "sell" the shares you actually closed at your *last* sell
                  price. This approximates "buy once at the start, sell at the
                  end" using prices you really transacted at.
  * churn_cost  = actual_pnl - hold_pnl
                  (negative => churning LOST money vs holding)

The number of trades is also reported, so you can see whether the names you
trade most are the ones the churn hurts most.
"""
import sys
from collections import defaultdict

from pytr_fifo import (load_events, _classify, _extract)


def analyze(path):
    events = load_events(path)
    events.sort(key=lambda e: e.get("timestamp") or e.get("date") or "")

    # Per instrument, collect executed buys and sells in time order.
    buys = defaultdict(list)   # key -> [(shares, price)]
    sells = defaultdict(list)
    names = {}

    for ev in events:
        side = _classify(ev)
        if side is None:
            continue
        name, isin, shares, price, fee, tax, cash = _extract(ev)
        if shares <= 0 or price <= 0:
            continue
        key = isin or name
        names[key] = name
        (buys if side == "buy" else sells)[key].append((shares, price))

    rows = []
    for key in names:
        b, s = buys[key], sells[key]
        if not b or not s:
            continue  # need both sides to compare churn vs hold
        n_trades = len(b) + len(s)
        bought_sh = sum(x[0] for x in b)
        sold_sh = sum(x[0] for x in s)
        closed_sh = min(bought_sh, sold_sh)

        # Actual realized P&L via simple FIFO (fees omitted here; we compare
        # like-for-like against the hold scenario which also omits fees).
        actual = _fifo_realized(b, s)

        # Hold counterfactual: buy all-at-first-price, sell closed_sh at last price.
        first_buy_px = b[0][1]
        last_sell_px = s[-1][1]
        hold = closed_sh * (last_sell_px - first_buy_px)

        churn = actual - hold
        rows.append({
            "name": names[key],
            "trades": n_trades,
            "actual": round(actual, 2),
            "hold": round(hold, 2),
            "churn_cost": round(churn, 2),
            "verdict": "churn helped" if churn > 0 else "churn hurt",
        })

    rows.sort(key=lambda r: r["churn_cost"])
    total_actual = round(sum(r["actual"] for r in rows), 2)
    total_hold = round(sum(r["hold"] for r in rows), 2)
    return {
        "instruments": rows,
        "total_actual": total_actual,
        "total_hold": total_hold,
        "total_churn_cost": round(total_actual - total_hold, 2),
    }


def _fifo_realized(buys, sells):
    """FIFO realized P&L from ordered (shares, price) lists, fees excluded."""
    from collections import deque
    lots = deque([list(x) for x in buys])
    pnl = 0.0
    for shares, price in sells:
        remaining = shares
        while remaining > 1e-9 and lots:
            lot = lots[0]
            take = min(remaining, lot[0])
            pnl += take * (price - lot[1])
            lot[0] -= take
            remaining -= take
            if lot[0] <= 1e-9:
                lots.popleft()
    return pnl


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "tr_docs/events_with_documents.json"
    res = analyze(path)
    print(f"{'Instrument':<28}{'Trades':>7}{'Churned':>11}{'Held':>11}{'ChurnCost':>12}")
    print("-" * 69)
    for r in res["instruments"]:
        print(f"{r['name']:<28}{r['trades']:>7}{r['actual']:>11.2f}"
              f"{r['hold']:>11.2f}{r['churn_cost']:>12.2f}")
    print("-" * 69)
    print(f"{'TOTAL':<28}{'':>7}{res['total_actual']:>11.2f}"
          f"{res['total_hold']:>11.2f}{res['total_churn_cost']:>12.2f}")
    print(f"\nIf churn cost is NEGATIVE, your trading did worse than simply "
          f"buying at the start and selling at the end.")
