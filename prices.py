"""Historical prices for your traded stocks, with your buy/sell points overlaid.

Pulls daily closes from Yahoo Finance (yfinance) over each instrument's trading
window and bundles them with your executed trades, so the dashboard can plot
WHERE your entries and exits landed relative to price.

Caches to tr_docs/prices.json so you only hit Yahoo once per run (and the app
can read it offline). Run on your laptop (Yahoo may rate-limit cloud IPs):

    python3 prices.py
    # then refresh the dashboard

ISINs map to Yahoo tickers via ISIN_TO_TICKER below. US stocks use their plain
symbol; the accumulating ETFs are skipped by default (their ISIN->ticker and
USD/EUR basis make the overlay noisy and less actionable than single stocks).
"""
import json
import os
import sys

# No hardcoded ticker map. We resolve each instrument's ISIN to a Yahoo symbol
# dynamically via Yahoo's search API, so this works for ANY user's holdings.
# Resolved symbols are cached in tr_docs*/isin_map.json to avoid repeat lookups
# and let you hand-correct a wrong match.

import urllib.parse
import urllib.request


def resolve_ticker(isin, name=""):
    """Resolve an ISIN (or name) to a Yahoo Finance symbol via the search API."""
    for q in (isin, name):
        if not q:
            continue
        url = ("https://query1.finance.yahoo.com/v1/finance/search?q="
               + urllib.parse.quote(q) + "&quotesCount=5&newsCount=0")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.load(r)
        except Exception:  # noqa: BLE001
            continue
        quotes = data.get("quotes") or []
        # Prefer equities; skip options/futures/currencies.
        for quote in quotes:
            if quote.get("quoteType") in ("EQUITY", "ETF") and quote.get("symbol"):
                return quote["symbol"]
        if quotes and quotes[0].get("symbol"):
            return quotes[0]["symbol"]
    return None

CACHE = os.path.join("tr_docs", "prices.json")


def _fetch(ticker, start, end):
    import yfinance as yf
    df = yf.Ticker(ticker).history(start=start, end=end, interval="1d")
    if df is None or df.empty:
        return []
    return [{"date": d.strftime("%Y-%m-%d"), "close": round(float(c), 4)}
            for d, c in df["Close"].items()]


def build(events_path):
    from pytr_fifo import trade_points
    import datetime as dt

    tp = trade_points(events_path)
    out = {}
    for key, rec in tp.items():
        # Skip ETFs/funds (USD/Acc names) — the USD/EUR basis makes the overlay
        # noisy and less actionable than single stocks.
        if "Acc" in rec["name"] or "USD" in rec["name"]:
            continue
        if not rec["trades"]:
            continue
        ticker = resolve_ticker(rec["isin"], rec["name"])
        if not ticker:
            print(f"  {rec['name']}: could not resolve a ticker, skipping")
            continue
        dates = sorted(t["date"] for t in rec["trades"] if t["date"])
        if not dates:
            continue
        # Pad the window so the chart shows context around the trades.
        start = (dt.date.fromisoformat(dates[0]) - dt.timedelta(days=10)).isoformat()
        end = (dt.date.fromisoformat(dates[-1]) + dt.timedelta(days=10)).isoformat()
        try:
            series = _fetch(ticker, start, end)
        except Exception as e:  # noqa: BLE001
            print(f"  {rec['name']} ({ticker}): price fetch failed: {e}")
            series = []
        out[ticker] = {
            "name": rec["name"], "isin": rec["isin"], "ticker": ticker,
            "prices": series, "trades": rec["trades"],
        }
        print(f"  {rec['name']:<28} {ticker:<6} {len(series)} days, "
              f"{len(rec['trades'])} trades")
    os.makedirs("tr_docs", exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"\nWrote {len(out)} instruments to {CACHE}")
    return out


if __name__ == "__main__":
    events = sys.argv[1] if len(sys.argv) > 1 else "tr_docs/events_with_documents.json"
    build(events)
