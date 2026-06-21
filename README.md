# 📈 TR Insight — Trade Republic Portfolio Analyzer

A local dashboard that turns your Trade Republic history into the numbers the
app doesn't show you: **exact realized P&L per stock, true total return
(including what you still hold), per-trade win rate, and a churn analysis that
reveals whether your trading actually beats buy-and-hold.**

Runs entirely on your machine. Your data never leaves your computer.

![dashboard](docs/screenshot.png)

---

## Why

Trade Republic shows you balances, not insight. It won't tell you:
- your **real profit per stock** (FIFO-matched, fees included),
- whether your **frequent trading earns or loses** vs just holding,
- your **win rate** and where your timing helped or hurt.

TR Insight computes all of that from your own exported data.

---

## Quick start

```bash
git clone https://github.com/Yueqi77-amazing/stock_analyse_traderepublic.git
cd stock_analyse_traderepublic
pip install flask pytr yfinance
python3 app.py            # or: ./run.sh   (Windows: run.bat)
```
Open **http://127.0.0.1:8000**.

On first run with no data it shows nothing useful — do the one-time export below.

---

## Load your real data (one time, ~2 min)

Run these on your **personal computer** (Trade Republic blocks logins from
cloud/data-center IPs). pytr is the unofficial-but-standard TR client; this flow
only **reads** your history and never places, modifies, or cancels orders.

```bash
# 1. Log in (prompts for phone, PIN, and a code via app/SMS).
python3 -m pytr login

# 2. Export full timeline (with share quantities, prices, fees).
python3 -m pytr dl_docs ./tr_docs --export-transactions --dump-raw-data --last_days 0

# 3. Fetch current holdings + live prices + available cash.
python3 fetch_portfolio.py

# 4. (optional) Historical price charts with your buy/sell points.
python3 prices.py
```
Then `python3 app.py` and refresh — the dashboard now shows your real portfolio.

> **Note:** P&L is exact for positions opened *within* your export window.
> Positions bought before it are flagged "⚠ no buy data" (cost basis unknown).
> `--last_days 0` exports everything TR still retains.

---

## What you get

- **Total account value** — cash + holdings at a glance.
- **True total return** — realized + unrealized, so held positions aren't
  mistaken for losses.
- **Per-instrument FIFO P&L** — exact, fees included, with open-position value.
- **Recent trades** — last 100, time-ordered, with per-sell realized P&L.
- **Churn cost** — did your trading beat holding, per stock?
- **Price charts** — historical price with your entries (▲) and exits (▼).

---

## Privacy & safety

- All processing is **local**. Nothing is uploaded anywhere.
- Your exported data lives in `tr_docs/` which is **git-ignored** — it is never
  committed. The repo ships **no real account data**.
- pytr stores its session in `~/.pytr/` on your machine only.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `405` on login | You're on a cloud/VPN IP — run on home internet. |
| `gbk codec` error (Windows) | `set PYTHONUTF8=1` then retry. |
| `pytr portfolio` crashes (`BAD_SUBSCRIPTION_TYPE`) | Known pytr bug — use `python3 fetch_portfolio.py` instead. |
| Numbers look off / "no buy data" | Re-export with `--last_days 0`. |

---

## Files

| File | Purpose |
|------|---------|
| `app.py` | Flask backend + dashboard server (port 8000, override with `PORT`) |
| `static/index.html` | Dashboard UI |
| `pytr_fifo.py` | Exact FIFO realized P&L, trades, daily churn |
| `total_return.py` | Realized + unrealized total return |
| `cashflow.py` | Deposits / interest / dividends / fees from the export |
| `fetch_portfolio.py` | Live holdings, prices, and available cash from TR |
| `prices.py` | Historical prices (auto-resolves ISIN→ticker via Yahoo) |
| `churn.py` | Trading-vs-holding churn analysis |
| `make_demo.py` | Generate throwaway synthetic data for screenshots |

Built with Flask + Chart.js. Unofficial; not affiliated with Trade Republic.
