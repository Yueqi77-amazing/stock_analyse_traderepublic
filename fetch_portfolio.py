"""Fetch current Trade Republic holdings + live prices -> tr_docs/portfolio.csv.

As of June 2026 TR retired both the `compactPortfolio` and `portfolio`
websocket topics (pytr issue #361); the working topic is now
`compactPortfolioByType`, which nests positions under `categories`. Each
position has `isin`, `netSize` (shares), and `averageBuyIn` (cost). We then
pull a live price per ISIN via the `ticker` topic to value each holding at
market.

Everything runs inside ONE asyncio event loop on a single websocket. (The
earlier bug used pytr's run_blocking(), which calls asyncio.run() per call and
closes the loop/socket between calls -> "Event loop is closed".)

READ-ONLY: subscribes only to compactPortfolioByType and ticker. Never creates,
modifies, or cancels an order.

Run on your laptop (uses your stored pytr session):
    python3 fetch_portfolio.py
    python3 total_return.py
"""
import asyncio
import csv
import json
import os

from pytr.account import login

OUT = os.path.join("tr_docs", "portfolio.csv")
# Exchanges to try for a live price, in order. LSX (Lang & Schwarz) is TR's
# default venue and quotes nearly everything during extended hours.
EXCHANGES = ["LSX", "TDG", "EUWAX"]


async def _one(tr, sub_coro, want_type, timeout=8):
    """Await a single answer for a freshly created subscription."""
    sub_id = await sub_coro
    try:
        while True:
            rid, sub, payload = await asyncio.wait_for(tr.recv(), timeout)
            if rid == sub_id:
                return payload
    except asyncio.TimeoutError:
        return None
    finally:
        try:
            await tr.unsubscribe(sub_id)
        except Exception:  # noqa: BLE001
            pass


async def _price(tr, isin):
    """Try each exchange until one returns a last price."""
    for ex in EXCHANGES:
        try:
            resp = await _one(tr, tr.ticker(isin, exchange=ex), "ticker", timeout=6)
        except Exception:  # noqa: BLE001
            resp = None
        if resp and isinstance(resp.get("last"), dict):
            p = resp["last"].get("price")
            if p:
                return float(p)
    return 0.0


async def main():
    tr = login(store_credentials=True)  # resumes stored session, no SMS
    await tr._get_ws()

    pf = await _one(tr, tr.subscribe({"type": "compactPortfolioByType"}),
                    "compactPortfolioByType", timeout=12)
    if not pf or "categories" not in pf:
        raise SystemExit("compactPortfolioByType returned no categories. "
                         f"Got: {str(pf)[:300]}")

    positions = []
    for cat in pf["categories"]:
        positions.extend(cat.get("positions", []))
    print(f"Got {len(positions)} positions. Fetching live prices...")

    rows = []
    for pos in positions:
        isin = pos.get("isin", "")
        qty = float(pos.get("netSize") or 0)
        avg = float(pos.get("averageBuyIn") or 0)
        name = pos.get("name") or isin
        price = await _price(tr, isin)
        # Fall back to average buy-in if no live price (keeps row usable).
        value = qty * (price or avg)
        rows.append({"Name": name, "ISIN": isin, "quantity": qty,
                     "price": round(price, 4), "netValue": round(value, 2)})
        flag = "" if price else "  (no live price; valued at cost)"
        print(f"  {name:<30} qty={qty:<11.4f} price={price:<9.2f} value={value:>10.2f}{flag}")

    os.makedirs("tr_docs", exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Name", "ISIN", "quantity", "price", "netValue"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} holdings to {OUT}")

    # Live available cash (uninvested EUR) from the `cash` topic. This is the
    # authoritative balance; the export-summed figure can drift if the export
    # doesn't cover full history.
    cash_val = None
    cash_resp = await _one(tr, tr.subscribe({"type": "cash"}), "cash", timeout=10)
    if isinstance(cash_resp, list) and cash_resp:
        # Returns a list of currency balances; take the EUR one.
        for c in cash_resp:
            if c.get("currencyId") == "EUR" or len(cash_resp) == 1:
                cash_val = float(c.get("amount") or 0)
                break
    elif isinstance(cash_resp, dict):
        cash_val = float(cash_resp.get("amount") or 0)
    if cash_val is not None:
        with open(os.path.join("tr_docs", "cash.json"), "w", encoding="utf-8") as f:
            json.dump({"available_cash": round(cash_val, 2)}, f)
        print(f"Available cash: €{cash_val:,.2f}  (written to tr_docs/cash.json)")
    else:
        print(f"Could not read available cash. Raw: {str(cash_resp)[:200]}")
    print("Now run:  python3 total_return.py")


if __name__ == "__main__":
    asyncio.run(main())
