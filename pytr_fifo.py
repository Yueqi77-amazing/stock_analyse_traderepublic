"""Exact FIFO P&L from pytr's events_with_documents.json.

pytr writes a list of timeline events. Each trade event carries the structured
amounts we need under nested sections. The schema drifts across pytr versions
and locales, so this parser is DEFENSIVE: it scans event sections for labelled
rows (shares / price / fee / tax) rather than hard-coding deep paths, and falls
back to the top-level amount when a section is missing.

Once you drop events_with_documents.json into ./tr_docs/, run:
    python3 pytr_fifo.py tr_docs/events_with_documents.json
or just start app.py — /api/fifo picks it up automatically if present.
"""
import json
import re
import sys
from collections import defaultdict, deque

# pytr event types we treat as buys / sells. Lowercased substring match.
# SELL is always tested before BUY because "verkauf" contains "kauf".
SELL_HINTS = ("verkauf", "sell", "sale", "disposal")
BUY_HINTS = ("kauf", "buy", "savingsplan", "sparplan", "purchase")


def _num(s):
    """Parse '1.234,56 €', '€1,234.56', '12.5 Stk.', '-51.99' -> float."""
    if s is None:
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)
    s = re.sub(r"[^\d,.\-]", "", str(s))
    if not s or s in ("-", ".", ","):
        return 0.0
    # Both separators -> the last one is the decimal separator.
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # Ambiguous: treat comma as decimal (German default).
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _walk_rows(node, found):
    """Recursively collect (label, text) pairs from any nested sections."""
    if isinstance(node, dict):
        title = node.get("title")
        detail = node.get("detail")
        if isinstance(title, str) and detail is not None:
            text = detail.get("text") if isinstance(detail, dict) else detail
            if text is not None:
                found.append((title.lower(), str(text)))
        for v in node.values():
            _walk_rows(v, found)
    elif isinstance(node, list):
        for v in node:
            _walk_rows(v, found)


def _classify(event):
    """Return 'buy' | 'sell' | None for a pytr event.

    pytr marks trades with eventType TRADING_TRADE_EXECUTED / SAVINGS_PLAN_*,
    and the direction lives in `subtitle`: "Kauforder" (buy) / "Verkaufsorder"
    (sell). NOTE: "Verkaufsorder" contains the substring "kauf", so SELL must
    be tested before BUY.
    """
    subtitle = str(event.get("subtitle", "")).lower()
    etype = str(event.get("eventType", "")).upper()
    # Ignore orders that never executed: rejected / cancelled / expired. These
    # carry €0 and no shares, so they are not trades at all.
    if ("REJECTED" in etype or "CANCEL" in etype or "EXPIRED" in etype
            or "abgelehnt" in subtitle or "storniert" in subtitle):
        return None
    blob = (subtitle + " " + etype.lower())
    if any(h in blob for h in SELL_HINTS):      # verkauf / sell
        return "sell"
    if any(h in blob for h in BUY_HINTS):       # kauf / buy / savingsplan
        return "buy"
    if "SAVINGS_PLAN" in etype:                 # savings-plan execution = buy
        return "buy"
    return None


# "0,501756 ×  971,70 €"  ->  (shares, price). Handles the × separator and
# German decimal commas. The × char is U+00D7; we also accept a plain 'x'.
_TXN_RE = re.compile(r"([\d.,]+)\s*[×x]\s*([\d.,]+)")


def _amount_value(event):
    """Top-level signed cash amount of the event in EUR."""
    amt = event.get("amount")
    if isinstance(amt, dict):
        return _num(amt.get("value"))
    return _num(amt or event.get("cashChangeAmount"))


def _extract(event):
    """Pull (name, isin, shares, price, fee, tax, cash) from one event."""
    name = event.get("title") or event.get("name") or "?"

    # ISIN is embedded in the icon/avatar asset path, e.g. "logos/US5951121038/v2".
    isin = ""
    asset = (event.get("avatar") or {}).get("asset") or event.get("icon") or ""
    m = re.search(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b", str(asset))
    if not m:
        m = re.search(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b", json.dumps(event))
    isin = m.group(1) if m else ""

    rows = []
    _walk_rows(event.get("details") or event.get("sections") or event, rows)

    shares = price = fee = tax = 0.0
    for label, text in rows:
        # The combined "Transaktion" row carries shares × price in one string.
        if ("transaktion" in label or "transaction" in label) and not shares:
            mt = _TXN_RE.search(text)
            if mt:
                shares = _num(mt.group(1))
                price = _num(mt.group(2))
        # Explicit share-price row ("Aktienkurs" / "Share price") as a fallback.
        elif not price and any(k in label for k in ("aktienkurs", "share price", "kurs", "preis")):
            price = _num(text)
        elif not shares and any(k in label for k in ("anteile", "stück", "shares", "quantity", "menge")):
            shares = _num(text)
        elif not fee and any(k in label for k in ("gebühr", "fee", "commission")):
            fee = _num(text)
        elif not tax and any(k in label for k in ("steuer", "tax")):
            tax = _num(text)

    cash = _amount_value(event)
    # Last-resort: derive shares from total cash / price when the txn row is absent.
    if shares == 0 and price > 0 and cash:
        shares = abs(cash) / price
    return name, isin, shares, price, fee, tax, cash


def load_events(path):
    # Force UTF-8: pytr writes UTF-8 (€ signs etc.), but Python on a
    # non-UTF-8 locale (e.g. GBK on Chinese Windows) would otherwise use the
    # system default codec and fail on byte 0xac (the tail of "€").
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # pytr may store a bare list or wrap it under a key.
    if isinstance(data, dict):
        for k in ("events", "data", "items"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
    return data if isinstance(data, list) else []


def trade_points(path):
    """Per instrument, the dated executed trades for plotting on a price chart.

    Returns {key: {"name", "isin", "trades": [{date, side, shares, price}]}}.
    """
    events = load_events(path)
    events.sort(key=lambda e: e.get("timestamp") or e.get("date") or "")
    out = {}
    for ev in events:
        side = _classify(ev)
        if side is None:
            continue
        name, isin, shares, price, fee, tax, cash = _extract(ev)
        if shares <= 0 or price <= 0:
            continue
        key = isin or name
        rec = out.setdefault(key, {"name": name, "isin": isin, "trades": []})
        rec["trades"].append({
            "date": (ev.get("timestamp") or "")[:10],
            "side": side, "shares": round(shares, 6), "price": round(price, 4),
        })
    return out


def daily_churn(path):
    """Gross EUR volume traded per day, from ALL real executed trades."""
    events = load_events(path)
    by_day = defaultdict(lambda: {"orders": 0, "volume": 0.0})
    for ev in events:
        if _classify(ev) is None:
            continue
        name, isin, shares, price, fee, tax, cash = _extract(ev)
        if shares <= 0 or price <= 0:
            continue
        day = (ev.get("timestamp") or "")[:10]
        by_day[day]["orders"] += 1
        by_day[day]["volume"] += shares * price
    return [{"date": d, "orders": v["orders"], "volume": round(v["volume"], 2)}
            for d, v in sorted(by_day.items())]


def recent_trades(path, limit=100):
    """Time-ordered list of executed trades with per-SELL realized P&L (FIFO).

    Buys show no P&L (a buy realizes nothing); sells show the FIFO gain/loss of
    that specific sell. Returns newest-first, capped at `limit`.
    """
    events = load_events(path)
    events.sort(key=lambda e: e.get("timestamp") or e.get("date") or "")
    lots = defaultdict(deque)
    out = []
    for ev in events:
        side = _classify(ev)
        if side is None:
            continue
        name, isin, shares, price, fee, tax, cash = _extract(ev)
        if shares <= 0 or price <= 0:
            continue
        key = isin or name
        ts = ev.get("timestamp") or ""
        if side == "buy":
            lots[key].append([shares, price + (fee / shares if shares else 0)])
            out.append({"time": ts, "name": name, "side": "buy",
                        "shares": round(shares, 6), "price": round(price, 4),
                        "value": round(shares * price, 2), "pnl": None})
        else:
            proceeds_ps = price - ((fee + tax) / shares if shares else 0)
            remaining, pnl, matched = shares, 0.0, False
            while remaining > 1e-9 and lots[key]:
                lot = lots[key][0]
                take = min(remaining, lot[0])
                pnl += take * (proceeds_ps - lot[1])
                lot[0] -= take
                remaining -= take
                matched = True
                if lot[0] <= 1e-9:
                    lots[key].popleft()
            out.append({"time": ts, "name": name, "side": "sell",
                        "shares": round(shares, 6), "price": round(price, 4),
                        "value": round(shares * price, 2),
                        # None if no matching buy in data (cost basis unknown).
                        "pnl": (round(pnl, 2) if matched and remaining < 1e-6 else None)})
    out.reverse()  # newest first
    return out[:limit]


def fifo(path):
    events = load_events(path)
    # Sort oldest-first by timestamp when available.
    events.sort(key=lambda e: e.get("timestamp") or e.get("date") or "")

    lots = defaultdict(deque)          # key -> deque[[shares, cost_per_share]]
    realized = defaultdict(float)
    names = {}
    trades = defaultdict(lambda: {"wins": 0, "losses": 0})
    no_basis_shares = defaultdict(float)  # sells with no buy in the export window
    skipped = 0
    skipped_detail = []

    for ev in events:
        side = _classify(ev)
        if side is None:
            continue
        name, isin, shares, price, fee, tax, cash = _extract(ev)
        key = isin or name
        names[key] = name
        if shares <= 0 or price <= 0:
            # Not enough structured data on this event; can't FIFO it.
            skipped += 1
            skipped_detail.append({
                "name": name, "side": side, "shares": shares, "price": price,
                "cash": cash, "eventType": ev.get("eventType"),
                "subtitle": ev.get("subtitle"), "timestamp": ev.get("timestamp"),
            })
            continue
        if side == "buy":
            lots[key].append([shares, price + (fee / shares if shares else 0)])
        else:
            proceeds_ps = price - ((fee + tax) / shares if shares else 0)
            remaining, pnl = shares, 0.0
            while remaining > 1e-9 and lots[key]:
                lot = lots[key][0]
                take = min(remaining, lot[0])
                pnl += take * (proceeds_ps - lot[1])
                lot[0] -= take
                remaining -= take
                if lot[0] <= 1e-9:
                    lots[key].popleft()
            if remaining > 1e-6:
                # Sold more shares than we have buy records for -> the matching
                # buy happened BEFORE the export window. Cost basis unknown, so
                # this instrument's realized P&L is unreliable. Flag it.
                no_basis_shares[key] += remaining
            realized[key] += pnl
            trades[key]["wins" if pnl >= 0 else "losses"] += 1

    rows = []
    # Include every instrument that has EITHER realized P&L (was sold) OR open
    # lots still held (buy-only positions, e.g. an ETF you've never sold). The
    # old code iterated realized.items() only, which silently dropped held
    # positions and lost their cost basis from total return.
    all_keys = set(realized) | {k for k, lt in lots.items() if lt}
    for key in all_keys:
        pnl = realized.get(key, 0.0)
        open_sh = sum(l[0] for l in lots[key])
        open_cost = sum(l[0] * l[1] for l in lots[key])  # remaining cost basis
        rows.append({
            "name": names.get(key, key),
            "isin": key if key.startswith(tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ")) and len(key) == 12 else "",
            "realized": round(pnl, 2),
            "open_shares": round(open_sh, 4),
            "open_cost_basis": round(open_cost, 2),  # what those open shares cost you
            "wins": trades[key]["wins"],
            "losses": trades[key]["losses"],
            # True if some sold shares had no buy record (bought before export
            # window) -> this instrument's realized P&L is unreliable.
            "no_basis": no_basis_shares.get(key, 0) > 1e-6,
            "no_basis_shares": round(no_basis_shares.get(key, 0), 4),
        })
    rows.sort(key=lambda r: r["realized"])
    total_trades = sum(r["wins"] + r["losses"] for r in rows)
    total_wins = sum(r["wins"] for r in rows)
    return {
        "instruments": rows,
        "total_realized": round(sum(r["realized"] for r in rows), 2),
        "win_rate": round(100 * total_wins / total_trades, 1) if total_trades else 0,
        "n_trades": total_trades,
        "skipped_events": skipped,
        "skipped_detail": skipped_detail,
        "no_basis_instruments": [r["name"] for r in rows if r["no_basis"]],
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "tr_docs/events_with_documents.json"
    res = fifo(path)
    print(f"{'Instrument':<32}{'Realized':>12}{'Open':>12}  W/L")
    for r in res["instruments"]:
        flag = "  ⚠ no buy in data" if r["no_basis"] else ""
        print(f"{r['name']:<32}{r['realized']:>12.2f}{r['open_shares']:>12.4f}"
              f"  {r['wins']}/{r['losses']}{flag}")
    print(f"\nTotal realized: €{res['total_realized']:,.2f}  |  "
          f"win rate {res['win_rate']}%  |  {res['n_trades']} closed trades  |  "
          f"{res['skipped_events']} events skipped (missing shares/price)")
    if res["no_basis_instruments"]:
        print(f"\n⚠️  Bought BEFORE the export window (cost basis unknown, "
              f"realized P&L unreliable): {', '.join(res['no_basis_instruments'])}")
        print("    Fix: export a longer history with pytr (more --last_days).")
    if res["skipped_detail"]:
        print("\n=== SKIPPED (classified as a trade but no shares/price found) ===")
        for s in res["skipped_detail"]:
            print(f"  {s['timestamp']}  {s['name']!r}  side={s['side']}  "
                  f"type={s['eventType']}  subtitle={s['subtitle']!r}  "
                  f"shares={s['shares']} price={s['price']} cash={s['cash']}")
