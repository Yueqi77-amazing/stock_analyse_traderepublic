"""Account-level cash summary computed from the real pytr export.

Replaces the legacy analyze.py cards (which summed the demo transactions.py).
Every pytr timeline event carries a signed `amount.value` (EUR cash change:
negative = money out, positive = money in) plus an `eventType` and `subtitle`.
We sum them by category to reconstruct deposits, interest, dividends, fees,
buys/sells, and the running cash balance.

Because pytr's eventType strings vary by version/locale, classification is
defensive and `--debug` lists every eventType seen so the mapping can be
verified against real data.

    python3 cashflow.py tr_docs/events_with_documents.json [--debug]
"""
import json
import sys
from collections import defaultdict

from pytr_fifo import load_events, _amount_value


# EXACT Trade Republic eventType -> category, taken from pytr's own
# tr_event_type_mapping (pytr/event.py). Matched case-insensitively against the
# full eventType string.
DEPOSIT_TYPES = {
    "account_transfer_incoming", "incoming_transfer",
    "incoming_transfer_delegation", "payment_inbound",
    "payment_inbound_apple_pay", "payment_inbound_google_pay",
    "payment_inbound_sepa_direct_debit", "payment_inbound_credit_card",
    "payment-service-in-payment-direct-debit", "card_refund",
    "card_successful_oct", "card_tr_refund",
}
WITHDRAWAL_TYPES = {
    "outgoing_transfer", "outgoing_transfer_delegation", "payment_outbound",
    "card_failed_transaction", "card_order_billed",
    "card_successful_atm_withdrawal", "card_successful_transaction",
    "junior_p2p_transfer",
}
INTEREST_TYPES = {"interest_payout", "interest_payout_created"}
DIVIDEND_TYPES = {"credit"}
TAX_TYPES = {"tax_correction", "tax_refund", "ssp_tax_correction_invoice"}
TRADE_TYPES = {
    "order_executed", "savings_plan_executed", "savings_plan_invoice_created",
    "trade_corrected", "trade_invoice", "benefits_spare_change_execution",
    "trading_savingsplan_executed", "trading_trade_executed",
    "benefits_saveback_execution", "acquisition_trade_perk",
}


def _category(ev):
    etype = str(ev.get("eventType", "")).strip().lower()
    if etype in DEPOSIT_TYPES:
        return "deposit"
    if etype in WITHDRAWAL_TYPES:
        return "withdrawal"
    if etype in INTEREST_TYPES:
        return "interest"
    if etype in DIVIDEND_TYPES:
        return "dividend"
    if etype in TAX_TYPES:
        return "tax"
    if etype in TRADE_TYPES:
        return "trade"
    # Fallbacks for legacy/migrated events that carry the info in title/subtitle.
    title = str(ev.get("title", "")).lower()
    sub = str(ev.get("subtitle", "")).lower()
    if "einzahlung" in title:
        return "deposit"
    if "zins" in title or "zins" in sub or "interest" in etype:
        return "interest"
    if "steuerkorrektur" in title:
        return "tax"
    if "dividend" in title or "dividend" in sub:
        return "dividend"
    if any(k in sub for k in ("kauforder", "verkaufsorder", "sparplan", "order")):
        return "trade"
    return "other"


def summarize(path, debug=False):
    events = load_events(path)
    cats = defaultdict(float)
    counts = defaultdict(int)
    cash = 0.0
    seen_types = defaultdict(int)

    for ev in events:
        amt = _amount_value(ev)          # signed: + in, - out
        cash += amt
        cat = _category(ev)
        cats[cat] += amt
        counts[cat] += 1
        seen_types[str(ev.get("eventType", "")) or "(none)"] += 1

    # Split trades into buys (cash out) and sells (cash in).
    buys = sum(_amount_value(e) for e in events
               if _category(e) == "trade" and _amount_value(e) < 0)
    sells = sum(_amount_value(e) for e in events
                if _category(e) == "trade" and _amount_value(e) > 0)

    result = {
        "cash_balance": round(cash, 2),
        "deposits": round(cats.get("deposit", 0), 2),
        "withdrawals": round(cats.get("withdrawal", 0), 2),
        "net_funded": round(cats.get("deposit", 0) + cats.get("withdrawal", 0), 2),
        "interest": round(cats.get("interest", 0), 2),
        "dividends": round(cats.get("dividend", 0), 2),
        "tax": round(cats.get("tax", 0), 2),
        "gross_buys": round(-buys, 2),
        "gross_sells": round(sells, 2),
        "n_events": len(events),
        "other_cash": round(cats.get("other", 0), 2),
    }
    if debug:
        result["_event_types"] = dict(sorted(seen_types.items(),
                                              key=lambda x: -x[1]))
        # Itemize the cash-funding events so we can see exactly what's counted.
        items = []
        for ev in events:
            cat = _category(ev)
            if cat in ("deposit", "withdrawal", "interest", "other"):
                items.append({
                    "time": (ev.get("timestamp") or "")[:10],
                    "cat": cat,
                    "amount": _amount_value(ev),
                    "eventType": ev.get("eventType"),
                    "title": ev.get("title"),
                    "subtitle": ev.get("subtitle"),
                })
        result["_funding_items"] = items
    return result


if __name__ == "__main__":
    path = next((a for a in sys.argv[1:] if not a.startswith("-")),
                "tr_docs/events_with_documents.json")
    debug = "--debug" in sys.argv
    res = summarize(path, debug=debug)
    if debug:
        print("=== eventType counts (verify the category mapping) ===")
        for t, n in res.pop("_event_types").items():
            print(f"  {n:>4}  {t}")
        print("\n=== funding events (deposit / withdrawal / interest / other) ===")
        for it in res.pop("_funding_items"):
            print(f"  {it['time']}  {it['cat']:<11}{it['amount']:>11.2f}  "
                  f"type={it['eventType']!r} title={it['title']!r}")
        print()
    for k, v in res.items():
        print(f"{k:<16} {v}")
    print(f"\nNOTE: cash_balance here is the SUM of all event cash flows. If TR "
          f"shows a different live balance, the difference is events outside the "
          f"export window. Use fetch_portfolio.py for the live figure.")
