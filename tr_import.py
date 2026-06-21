"""Read-only Trade Republic timeline exporter.

Pulls your transaction timeline (with share quantities, prices, and fees) via
the UNOFFICIAL pytr / TradeRepublicApi library and writes it to a CSV that
fifo.py can turn into exact FIFO P&L.

==============================  SAFETY RAILS  ==============================
This module is deliberately constrained:
  * It ONLY reads: login + timeline + timelineDetail. It NEVER calls any
    order/trade/cancel endpoint. There is no code path here that can place,
    modify, or cancel an order.
  * It does NOT store your PIN. The PIN is read interactively at runtime
    (getpass) and kept only in memory for the session.
  * Logging in via the unofficial API will LOG YOU OUT of the Trade Republic
    phone app (TR allows one active device). This is expected behaviour of
    the API, not a bug.
  * Because this is an unofficial API hitting a live account, treat output as
    sensitive and review before trusting. Prefer the official statement
    export if one is available to you.
===========================================================================

Install (one of these unofficial libs):
    pip install pytr            # actively maintained fork, recommended
    # or the original: pip install TradeRepublicApi

Usage:
    python3 tr_import.py +49XXXXXXXXXX     # phone number; PIN prompted securely
    -> writes timeline.csv
Then:
    python3 fifo.py timeline.csv           # exact FIFO P&L
"""
import csv
import getpass
import sys


CSV_FIELDS = ["timestamp", "type", "name", "isin", "shares", "price",
              "amount", "fee", "tax"]

# Hard denylist: if any of these substrings appear in a method we intend to
# call, refuse. Defense-in-depth so this module can never mutate the account.
_FORBIDDEN = ("order", "buy", "sell", "trade", "cancel", "savingsplan_create",
              "withdraw", "transfer", "limit", "market")


def _assert_read_only(method_name: str) -> None:
    low = method_name.lower()
    for bad in _FORBIDDEN:
        if bad in low:
            raise RuntimeError(
                f"Refusing to call '{method_name}': this exporter is read-only "
                f"and must never touch trading endpoints.")


def _connect(phone: str):
    """Return a logged-in blocking client, or exit with guidance."""
    try:
        from pytr.account import login  # pytr fork
    except ImportError:
        try:
            from trapi.api import TrBlockingApi as _Api  # original lib name varies
        except ImportError:
            sys.exit("No TR library found. Install with:  pip install pytr")
        pin = getpass.getpass("Trade Republic PIN (not stored): ")
        api = _Api(phone, pin)
        _assert_read_only("login")
        api.login()
        return api
    # pytr path
    pin = getpass.getpass("Trade Republic PIN (not stored): ")
    print("Logging in (this logs you out of the TR phone app)...")
    return login(phone_no=phone, pin=pin)


def _extract(detail: dict) -> dict:
    """Best-effort pull of structured fields from a timelineDetail payload.

    TR's schema is nested and changes over time, so we scan defensively for
    the sections that carry shares / price / fee rather than hard-coding paths.
    """
    out = {k: "" for k in CSV_FIELDS}
    out["timestamp"] = detail.get("timestamp", "")
    out["type"] = detail.get("type", "")
    out["name"] = detail.get("title", "") or detail.get("name", "")
    out["isin"] = detail.get("isin", "")
    out["amount"] = (detail.get("cashChangeAmount")
                     or detail.get("amount", {}).get("value", "") if isinstance(
                         detail.get("amount"), dict) else detail.get("amount", ""))
    # Walk any "sections" / "details" looking for labelled numeric rows.
    sections = detail.get("sections") or detail.get("details") or []
    for sec in sections:
        for row in (sec.get("data") or sec.get("rows") or []):
            label = str(row.get("title", "")).lower()
            val = row.get("detail", {})
            text = val.get("text", "") if isinstance(val, dict) else str(val)
            if "shares" in label or "anteile" in label or "stück" in label:
                out["shares"] = text
            elif "price" in label or "kurs" in label:
                out["price"] = text
            elif "fee" in label or "gebühr" in label:
                out["fee"] = text
            elif "tax" in label or "steuer" in label:
                out["tax"] = text
    return out


def export(phone: str, out_path: str = "timeline.csv", max_events: int = 5000):
    api = _connect(phone)
    _assert_read_only("timeline")

    rows, cursor, fetched = [], None, 0
    while fetched < max_events:
        page = api.timeline(cursor) if cursor else api.timeline()
        events = page.get("data", page) if isinstance(page, dict) else page
        if not events:
            break
        for ev in events:
            ev_id = ev.get("id") or ev.get("data", {}).get("id")
            if not ev_id:
                continue
            _assert_read_only("timeline_detail")
            try:
                detail = api.timeline_detail(ev_id)
            except Exception as e:  # noqa: BLE001 - keep exporting on a bad row
                print(f"  skip {ev_id}: {e}")
                continue
            rows.append(_extract(detail))
            fetched += 1
        cursor = page.get("cursor") if isinstance(page, dict) else None
        if not cursor:
            break

    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} events to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python3 tr_import.py +49XXXXXXXXXX")
    export(sys.argv[1])
