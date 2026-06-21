"""Flask backend for the stock-analysis dashboard.

Serves the static frontend and JSON analytics computed in analyze.py.
Run:  python3 app.py   then open http://127.0.0.1:5000
"""
import os
from flask import Flask, jsonify, send_from_directory
import analyze

app = Flask(__name__, static_folder="static", static_url_path="")

# Data folder. Defaults to your real export in tr_docs/; override with the
# TR_DOCS env var for a one-off demo, e.g.  TR_DOCS=tr_docs_demo python3 app.py
TR_DOCS = os.environ.get("TR_DOCS", "tr_docs")


def events_path():
    return os.path.join(TR_DOCS, "events_with_documents.json")


def portfolio_path():
    return os.path.join(TR_DOCS, "portfolio.csv")


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/summary")
def api_summary():
    return jsonify({
        "account": analyze.account_summary(),
        "book": analyze.trading_vs_core(),
        "closed": analyze.fully_closed_pnl(),
    })


@app.route("/api/instruments")
def api_instruments():
    return jsonify(analyze.per_instrument())


@app.route("/api/daily")
def api_daily():
    # Prefer real export; fall back to the (demo) cash-flow approximation.
    path = events_path()
    if os.path.exists(path):
        try:
            import pytr_fifo
            return jsonify(pytr_fifo.daily_churn(path))
        except Exception:  # noqa: BLE001
            pass
    return jsonify(analyze.daily_activity())


@app.route("/api/fifo")
def api_fifo():
    """Exact FIFO P&L from a pytr export, if one has been dropped in tr_docs/.

    Returns {"available": false} when no export is present, so the frontend can
    fall back to the approximate cash-flow view.
    """
    path = events_path()
    if not os.path.exists(path):
        return jsonify({"available": False})
    try:
        import pytr_fifo
        result = pytr_fifo.fifo(path)
        result["available"] = True
        return jsonify(result)
    except Exception as e:  # noqa: BLE001 - surface parse issues to the UI
        return jsonify({"available": False, "error": str(e)})


@app.route("/api/total")
def api_total():
    """True total return = realized + unrealized (needs export + portfolio.csv)."""
    events = events_path()
    if not os.path.exists(events):
        return jsonify({"available": False})
    try:
        import total_return
        result = total_return.analyze(events, portfolio_path())
        result["available"] = True
        return jsonify(result)
    except Exception as e:  # noqa: BLE001
        return jsonify({"available": False, "error": str(e)})


@app.route("/api/prices")
def api_prices():
    """Cached historical prices + your trade points (built by prices.py)."""
    cache = os.path.join(TR_DOCS, "prices.json")
    if not os.path.exists(cache):
        return jsonify({"available": False})
    try:
        import json as _json
        with open(cache, encoding="utf-8") as f:
            return jsonify({"available": True, "data": _json.load(f)})
    except Exception as e:  # noqa: BLE001
        return jsonify({"available": False, "error": str(e)})


@app.route("/api/trades")
def api_trades():
    """Recent executed trades (newest first) with per-sell realized P&L."""
    path = events_path()
    if not os.path.exists(path):
        return jsonify({"available": False})
    try:
        import pytr_fifo
        return jsonify({"available": True, "trades": pytr_fifo.recent_trades(path, 100)})
    except Exception as e:  # noqa: BLE001
        return jsonify({"available": False, "error": str(e)})


@app.route("/api/cash")
def api_cash():
    """Live available cash fetched from TR (written by fetch_portfolio.py)."""
    path = os.path.join(TR_DOCS, "cash.json")
    if not os.path.exists(path):
        return jsonify({"available": False})
    try:
        import json as _json
        with open(path, encoding="utf-8") as f:
            d = _json.load(f)
        return jsonify({"available": True, "available_cash": d.get("available_cash")})
    except Exception as e:  # noqa: BLE001
        return jsonify({"available": False, "error": str(e)})


@app.route("/api/cashflow")
def api_cashflow():
    """Account cash summary from the real export (replaces demo-derived cards)."""
    path = events_path()
    if not os.path.exists(path):
        return jsonify({"available": False})
    try:
        import cashflow
        result = cashflow.summarize(path)
        result["available"] = True
        return jsonify(result)
    except Exception as e:  # noqa: BLE001
        return jsonify({"available": False, "error": str(e)})


@app.route("/api/churn")
def api_churn():
    """Churn-cost analysis: did trading beat holding? Needs the pytr export."""
    path = events_path()
    if not os.path.exists(path):
        return jsonify({"available": False})
    try:
        import churn
        result = churn.analyze(path)
        result["available"] = True
        return jsonify(result)
    except Exception as e:  # noqa: BLE001
        return jsonify({"available": False, "error": str(e)})


if __name__ == "__main__":
    import os as _os
    port = int(_os.environ.get("PORT", "8000"))
    app.run(debug=True, port=port)
