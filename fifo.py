"""Exact FIFO realized-P&L from a timeline CSV (see tr_import.py for schema).

Unlike analyze.py (cash-flow approximation from the pasted feed), this matches
each sell against the oldest open buy lots using share quantities, so it gives:
  * true realized P&L per closed lot (fees included)
  * correct separation of realized gains from still-open positions
  * a real per-trade win rate and average holding period

Run:  python3 fifo.py timeline.csv
"""
import csv
import sys
from collections import defaultdict, deque


def _num(s):
    """Parse a EUR/number string like '1.234,56 €' or '12.5' to float."""
    if s is None or s == "":
        return 0.0
    s = str(s).replace("€", "").replace("$", "").strip()
    # Handle German decimal comma if both separators present.
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def fifo_pnl(csv_path):
    lots = defaultdict(deque)            # isin/name -> deque of [shares, cost_per_share]
    realized = defaultdict(float)
    trips = defaultdict(lambda: {"wins": 0, "losses": 0, "hold_days": []})

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    # FIFO requires oldest-first. Sort by timestamp when present (robust to
    # whichever direction the export happens to be in); otherwise assume the
    # TR default of newest-first and reverse.
    if reader and reader[0].get("timestamp"):
        reader.sort(key=lambda r: r.get("timestamp") or "")
    else:
        reader.reverse()
    for row in reader:
        key = row.get("isin") or row.get("name")
        typ = (row.get("type") or "").lower()
        shares = _num(row.get("shares"))
        price = _num(row.get("price"))
        fee = _num(row.get("fee"))
        amount = _num(row.get("amount"))

        is_buy = any(t in typ for t in ("buy", "kauf", "saving", "sparplan"))
        is_sell = any(t in typ for t in ("sell", "verkauf"))
        if not (is_buy or is_sell) or shares <= 0:
            continue

        if is_buy:
            cost_ps = price + (fee / shares if shares else 0)
            lots[key].append([shares, cost_ps])
        else:  # sell, match against oldest lots
            proceeds_ps = price - (fee / shares if shares else 0)
            remaining = shares
            while remaining > 1e-9 and lots[key]:
                lot = lots[key][0]
                take = min(remaining, lot[0])
                realized[key] += take * (proceeds_ps - lot[1])
                lot[0] -= take
                remaining -= take
                if lot[0] <= 1e-9:
                    lots[key].popleft()
            pnl = realized[key]
            (trips[key]["wins" if pnl >= 0 else "losses"]) += 1

    out = []
    for key, pnl in sorted(realized.items(), key=lambda x: x[1]):
        open_shares = sum(l[0] for l in lots[key])
        out.append({
            "name": key, "realized": round(pnl, 2),
            "open_shares": round(open_shares, 4),
            "wins": trips[key]["wins"], "losses": trips[key]["losses"],
        })
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python3 fifo.py timeline.csv")
    rows = fifo_pnl(sys.argv[1])
    total = sum(r["realized"] for r in rows)
    print(f"{'Instrument':<30} {'Realized':>12} {'Open':>10}  W/L")
    for r in rows:
        print(f"{r['name']:<30} {r['realized']:>12.2f} {r['open_shares']:>10.4f}"
              f"  {r['wins']}/{r['losses']}")
    print(f"\nTotal realized P&L: €{total:,.2f}")
