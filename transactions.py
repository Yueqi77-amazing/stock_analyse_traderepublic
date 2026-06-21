# SYNTHETIC DEMO DATA — not a real account.
#
# This file feeds the legacy cash-flow approximation (analyze.py), which is only
# used as a fallback when no exact pytr export is present. Real per-account data
# never lives here; users drop their own pytr export in tr_docs/ and the app
# computes exact FIFO P&L from that instead.
#
# The trades below mirror tr_docs_demo/ so the approximate and exact views tell
# a consistent demo story. Amounts are fictional.

# (date_iso, name, type, amount_eur)
TX = [
    ("2026-05-20", "NVIDIA", "sell", 608.00),
    ("2026-05-02", "Core MSCI World USD (Acc)", "sell", 624.00),
    ("2026-04-15", "NVIDIA", "buy", 354.00),
    ("2026-04-06", "Core MSCI World USD (Acc)", "buy", 2000.00),
    ("2026-04-01", "Apple", "sell", 730.00),
    ("2026-03-23", "Rivian Automotive", "sell", 976.00),
    ("2026-03-20", "Rivian Automotive", "buy", 1040.00),
    ("2026-03-18", "Micron Technology", "sell", 769.60),
    ("2026-03-12", "Micron Technology", "buy", 760.00),
    ("2026-03-10", "Rivian Automotive", "sell", 798.00),
    ("2026-03-09", "Rivian Automotive", "buy", 847.00),
    ("2026-03-06", "Rivian Automotive", "sell", 708.00),
    ("2026-03-05", "Rivian Automotive", "buy", 750.00),
    ("2026-03-02", "Apple", "buy", 672.00),
    ("2026-03-02", "NVIDIA", "buy", 550.00),
    ("2026-03-01", "Cash In", "deposit", 5000.00),
]


# Cash-flow sign per type: + means money into the account, - means money out.
SIGN = {
    "buy": -1, "saving": -1, "ipo": -1, "transfer_out": -1,
    "sell": +1, "dividend": +1, "tax": +1, "interest": +1,
    "deposit": +1, "transfer_in": +1,
}

# Types that represent a position in a tradable instrument.
INVEST_OUT = {"buy", "saving", "ipo"}   # money used to acquire the instrument
INVEST_IN = {"sell"}                    # money returned from the instrument
NON_INSTRUMENT = {"Tax correction", "Interest", "Cash In"}

# Long-term "core" instruments (savings-plan / broad ETFs) vs the trading book.
CORE_ETFS = {
    "Core MSCI World USD (Acc)",
    "Core S&P 500 USD (Acc)",
    "FTSE All-World USD (Acc)",
    "FTSE Korea USD (Acc)",
    "Artificial Intelligence & Robotics USD (Acc)",
    "Semiconductor USD (Acc)",
}
