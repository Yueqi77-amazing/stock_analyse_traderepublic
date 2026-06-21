"""Discover which websocket topic currently returns the portfolio.

TR retired both `compactPortfolio` and `portfolio` (pytr issue #361), so we
don't know the new topic name. This script opens ONE websocket connection
(inside a single asyncio event loop — the previous bug was calling
asyncio.run() per topic, which closed the loop each time) and tries a list of
candidate topics, printing the raw response of whichever succeeds.

READ-ONLY: only subscribes to read topics; never creates/cancels orders.

Run on your laptop (uses your stored pytr session):
    python3 discover_portfolio.py
Paste me the output — I'll wire the working topic into fetch_portfolio.py.
"""
import asyncio
import json

from pytr.account import login

CANDIDATES = [
    {"type": "compactPortfolio"},
    {"type": "portfolio"},
    {"type": "compactPortfolioByType"},
    {"type": "portfolioStatus"},
    {"type": "trading"},
    {"type": "currentPortfolio"},
    {"type": "investments"},
    {"type": "portfolioPositions"},
    {"type": "compactPortfolioPositions"},
]


async def try_topic(tr, topic, timeout=8):
    """Subscribe, await one answer, unsubscribe — all on the shared ws."""
    sub_id = await tr.subscribe(topic)
    try:
        while True:
            rid, sub, payload = await asyncio.wait_for(tr.recv(), timeout)
            if rid == sub_id:
                return ("OK", payload)
    except asyncio.TimeoutError:
        return ("TIMEOUT", None)
    except Exception as e:  # noqa: BLE001 - capture the TR error message
        return ("ERROR", str(e))
    finally:
        try:
            await tr.unsubscribe(sub_id)
        except Exception:  # noqa: BLE001
            pass


async def main():
    tr = login(store_credentials=True)  # default flow; resumes saved session
    # Force the websocket open once.
    await tr._get_ws()
    for topic in CANDIDATES:
        status, payload = await try_topic(tr, topic)
        if status == "OK":
            keys = list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
            print(f"\n✅ WORKS: {topic}   top-level keys: {keys}")
            print(json.dumps(payload, indent=2, ensure_ascii=False)[:1800])
            print("\n(Stopping at first working topic.)")
            return
        else:
            print(f"❌ {topic['type']:<28} -> {status}: {payload}")
    print("\nNo candidate worked. Paste this whole output to me.")


if __name__ == "__main__":
    asyncio.run(main())
