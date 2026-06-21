"""Analytics over the Trade Republic transaction feed.

All P&L here is CASH-FLOW based (sold proceeds minus buy cost), because the
source feed has no share quantities. This is exact for fully-closed positions
and a lower bound (looks worse than reality) for positions still open.
"""
from collections import defaultdict
from transactions import TX, SIGN, CORE_ETFS, NON_INSTRUMENT


def per_instrument():
    """Aggregate buy/sell/dividend cash flows per instrument."""
    agg = defaultdict(lambda: {
        "bought": 0.0, "sold": 0.0, "dividends": 0.0,
        "n_buys": 0, "n_sells": 0, "first": None, "last": None,
    })
    for date, name, typ, amt in TX:
        if name in NON_INSTRUMENT:
            continue
        a = agg[name]
        if typ in ("buy", "saving", "ipo"):
            a["bought"] += amt
            a["n_buys"] += 1
        elif typ == "sell":
            a["sold"] += amt
            a["n_sells"] += 1
        elif typ == "dividend":
            a["dividends"] += amt
        else:
            continue
        a["first"] = date if a["first"] is None else min(a["first"], date)
        a["last"] = date if a["last"] is None else max(a["last"], date)

    rows = []
    for name, a in agg.items():
        # Heuristic: position considered closed if proceeds are within 3% of
        # cost (i.e. roughly the same euro size went out and came back).
        closed = a["bought"] > 0 and abs(a["sold"] - a["bought"]) / a["bought"] < 0.03
        realized = a["sold"] - a["bought"] + a["dividends"]
        rows.append({
            "name": name,
            "bought": round(a["bought"], 2),
            "sold": round(a["sold"], 2),
            "dividends": round(a["dividends"], 2),
            "net": round(realized, 2),
            "n_buys": a["n_buys"],
            "n_sells": a["n_sells"],
            "trips": min(a["n_buys"], a["n_sells"]),
            "first": a["first"],
            "last": a["last"],
            "core": name in CORE_ETFS,
            "likely_closed": closed,
            "still_open": a["bought"] - a["sold"] > 50 and not closed,
        })
    rows.sort(key=lambda r: r["net"])
    return rows


def account_summary():
    deposits = transfers_in = transfers_out = interest = tax = dividends = 0.0
    buys = sells = savings = 0.0
    cash = 0.0
    for _, name, typ, amt in TX:
        cash += SIGN.get(typ, 0) * amt
        if typ == "deposit":
            deposits += amt
        elif typ == "transfer_in":
            transfers_in += amt
        elif typ == "transfer_out":
            transfers_out += amt
        elif typ == "interest":
            interest += amt
        elif typ == "tax":
            tax += amt
        elif typ == "dividend":
            dividends += amt
        elif typ == "buy":
            buys += amt
        elif typ == "sell":
            sells += amt
        elif typ in ("saving", "ipo"):
            savings += amt
    return {
        "external_in": round(deposits + transfers_in, 2),
        "deposits": round(deposits, 2),
        "transfers_in": round(transfers_in, 2),
        "transfers_out": round(transfers_out, 2),
        "net_funded": round(deposits + transfers_in - transfers_out, 2),
        "interest": round(interest, 2),
        "tax_corrections": round(tax, 2),
        "dividends": round(dividends, 2),
        "gross_buys": round(buys + savings, 2),
        "gross_sells": round(sells, 2),
        "n_orders": sum(1 for _, _, t, _ in TX if t in ("buy", "sell", "saving")),
        "cash_balance": round(cash, 2),
    }


def trading_vs_core():
    """Split realized P&L between the high-churn trading book and the ETF core."""
    rows = per_instrument()
    book = {"trading": {"net": 0.0, "bought": 0.0, "sold": 0.0, "names": 0},
            "core": {"net": 0.0, "bought": 0.0, "sold": 0.0, "names": 0}}
    for r in rows:
        k = "core" if r["core"] else "trading"
        book[k]["net"] += r["net"]
        book[k]["bought"] += r["bought"]
        book[k]["sold"] += r["sold"]
        book[k]["names"] += 1
    for k in book:
        for f in ("net", "bought", "sold"):
            book[k][f] = round(book[k][f], 2)
    return book


def daily_activity():
    """Order count and gross volume traded per day."""
    by_day = defaultdict(lambda: {"orders": 0, "volume": 0.0})
    for date, name, typ, amt in TX:
        if typ in ("buy", "sell", "saving"):
            by_day[date]["orders"] += 1
            by_day[date]["volume"] += amt
    out = [{"date": d, "orders": v["orders"], "volume": round(v["volume"], 2)}
           for d, v in sorted(by_day.items())]
    return out


def fully_closed_pnl():
    """Sum of net P&L for positions that look fully round-tripped.

    This is the most trustworthy single number: real realized profit on
    trades that were opened AND closed, where cash-flow P&L is exact.
    """
    rows = per_instrument()
    closed = [r for r in rows if r["likely_closed"]]
    total = round(sum(r["net"] for r in closed), 2)
    wins = sum(1 for r in closed if r["net"] > 0)
    return {
        "instruments": len(closed),
        "total_net": total,
        "win_rate": round(100 * wins / len(closed), 1) if closed else 0,
        "winners": wins,
        "losers": len(closed) - wins,
    }


if __name__ == "__main__":
    import json
    print("=== ACCOUNT ===")
    print(json.dumps(account_summary(), indent=2))
    print("\n=== TRADING vs CORE ===")
    print(json.dumps(trading_vs_core(), indent=2))
    print("\n=== FULLY-CLOSED P&L (most trustworthy) ===")
    print(json.dumps(fully_closed_pnl(), indent=2))
    print("\n=== PER INSTRUMENT (worst to best) ===")
    for r in per_instrument():
        tag = "CORE" if r["core"] else ("OPEN" if r["still_open"] else "")
        print(f"{r['net']:>10.2f}  {r['name']:<42} buys={r['n_buys']:<2} "
              f"sells={r['n_sells']:<2} {tag}")
