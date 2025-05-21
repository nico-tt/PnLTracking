"""
Crypto Spot PnL Dashboard — MEXC edition
Author: ChatGPT assistant
Last updated: 2025-05-21

A lightweight **Streamlit** application that tracks the unrealised PnL of spot
crypto positions. Prices are pulled from **MEXC’s** public price ticker
(`GET /api/v3/ticker/price`); positions whose tickers *aren’t* listed on MEXC
(e.g. **HYPE**) can be priced manually so your PnL stays complete.:contentReference[oaicite:0]{index=0}

> **Bulk-loaded portfolio**
> The dashboard starts with your full portfolio pre-loaded, so you can jump
> straight to tracking without hand-entering each coin.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final, List, Dict, Union
import sys
import textwrap

import requests
import pandas as pd
import streamlit as st

Position = Dict[str, Union[str, float]]

# ── Pre-loaded portfolio -------------------------------------------------------
DEFAULT_POSITIONS: List[Position] = [
    {"symbol": "BTC", "entry_price": 102_930.0, "size": 2.0},
    {"symbol": "ETH", "entry_price": 2_484.068, "size": 5.38},
    {"symbol": "SOL", "entry_price": 164.987, "size": 80.99},
    {"symbol": "SUI", "entry_price": 3.785, "size": 3_530.34},
    {"symbol": "XRP", "entry_price": 2.357, "size": 5_670.03},
    {"symbol": "LINK", "entry_price": 15.601, "size": 285.51},
    {"symbol": "HYPE", "entry_price": 26.201, "size": 170.0},
    {"symbol": "DOGE", "entry_price": 0.223, "size": 19_978.46},
    {"symbol": "ONDO", "entry_price": 0.925, "size": 4_816.12},
    {"symbol": "BONK", "entry_price": 0.0000198104, "size": 224_835_941.0},
    {"symbol": "TAO", "entry_price": 409.384, "size": 10.88},
    {"symbol": "NEAR", "entry_price": 2.775, "size": 1_605.04},
    {"symbol": "RENDER", "entry_price": 4.578, "size": 972.91},
]

# ── Abort early if not run via `streamlit run` ---------------------------------
try:
    from streamlit.runtime.scriptrunner import get_script_run_ctx  # type: ignore

    if get_script_run_ctx() is None:  # Not running inside Streamlit
        sys.exit(
            textwrap.dedent(
                """
                ==========================================================
                This script must be executed with:

                    streamlit run crypto_pnl_dashboard.py

                Running it inside a notebook or with plain `python` will
                disable Streamlit features.  Aborting.
                ==========================================================
                """
            )
        )
except Exception:
    pass  # Older Streamlit versions – carry on.

# ── Optional auto-refresh ------------------------------------------------------
try:
    from streamlit_autorefresh import st_autorefresh  # type: ignore

    AUTOREFRESH_AVAILABLE: Final = True
except ModuleNotFoundError:
    st_autorefresh = None  # type: ignore
    AUTOREFRESH_AVAILABLE: Final = False

# ── Constants -----------------------------------------------------------------
API_BASE: Final = "https://api.mexc.com"  # ← switched from Binance to MEXC

# ── Page config ----------------------------------------------------------------
st.set_page_config(page_title="Crypto Spot PnL Dashboard", layout="wide")

st.title("📈 Crypto Spot PnL Dashboard (MEXC)")

# ────────────────────────────────────────────────────────────────────────────────
# Sidebar – manage user positions
# ────────────────────────────────────────────────────────────────────────────────

st.sidebar.header("Manage Positions")

# Initialise session state on first run
if "positions" not in st.session_state:
    # Use a copy so the constant remains immutable
    st.session_state["positions"] = [pos.copy() for pos in DEFAULT_POSITIONS]

if "manual_prices" not in st.session_state:
    st.session_state["manual_prices"] = {}

positions: List[Position] = st.session_state["positions"]
manual_prices: Dict[str, float] = st.session_state["manual_prices"]

# ── Add / update position form ────────────────────────────────────────────────
with st.sidebar.form("add_position", clear_on_submit=True):
    symbol = st.text_input("Symbol (e.g. BTC)", "").upper()
    entry_price = st.number_input(
        "Entry price (USDT)", min_value=0.0, step=0.01, format="%.6f"
    )
    size = st.number_input(
        "Size (units of the coin)", min_value=0.0, step=0.0001, format="%.6f"
    )
    submitted = st.form_submit_button("Add / Update")

    if submitted and symbol and entry_price > 0 and size > 0:
        existing = next((p for p in positions if p["symbol"] == symbol), None)
        if existing:
            existing.update(entry_price=entry_price, size=size)
        else:
            positions.append(
                {"symbol": symbol, "entry_price": entry_price, "size": size}
            )

# ── Remove positions ───────────────────────────────────────────────────────────
if positions:
    remove_symbol = st.sidebar.selectbox(
        "Remove position", ["-"] + [p["symbol"] for p in positions]
    )
    if st.sidebar.button("Remove") and remove_symbol != "-":
        positions[:] = [p for p in positions if p["symbol"] != remove_symbol]
        manual_prices.pop(remove_symbol, None)

# ── Refresh interval ───────────────────────────────────────────────────────────
refresh_interval = st.sidebar.slider("Refresh interval (seconds)", 1, 60, 5)

if AUTOREFRESH_AVAILABLE:
    st_autorefresh(interval=refresh_interval * 1000, limit=None, key="refresh")
else:
    st.sidebar.warning(
        "Automatic refresh disabled (missing **streamlit-autorefresh**). "
        "Press **R** or click the ⟳ button to rerun manually."
    )

# ────────────────────────────────────────────────────────────────────────────────
# Price fetching helpers
# ────────────────────────────────────────────────────────────────────────────────

symbols = [p["symbol"] for p in positions]
api_symbols = [f"{sym}USDT" for sym in symbols]


def fetch_prices(pairs: List[str]) -> Dict[str, Union[float, None]]:
    """Return {symbol: last_price} via MEXC’s price ticker."""
    prices: Dict[str, Union[float, None]] = {}
    for pair in pairs:
        base = pair[:-4]  # strip the ‘USDT’ suffix
        try:
            rsp = requests.get(
                f"{API_BASE}/api/v3/ticker/price",
                params={"symbol": pair},
                timeout=5,
            )
            rsp.raise_for_status()
            prices[base] = float(rsp.json()["price"])
        except Exception:
            prices[base] = None
    return prices


prices = fetch_prices(api_symbols)

# ── Manual price overrides -----------------------------------------------------
missing = [sym for sym, price in prices.items() if price is None]

if missing:
    with st.sidebar.expander("Missing prices (manual override)", expanded=True):
        st.write(
            "Tickers not on **MEXC**. Enter a manual USDT price to include them in the PnL calc."
        )
        for sym in missing:
            default = manual_prices.get(sym, 0.0)
            manual_price = st.number_input(
                f"{sym} price (USDT)",
                value=default,
                min_value=0.0,
                step=0.0001,
                format="%.6f",
            )
            if manual_price > 0:
                manual_prices[sym] = manual_price
                prices[sym] = manual_price
            elif sym in manual_prices:
                manual_prices.pop(sym)

# ────────────────────────────────────────────────────────────────────────────────
# PnL computation & display
# ────────────────────────────────────────────────────────────────────────────────

rows: List[Dict[str, Union[str, float, None]]] = []
net_pnl: float = 0.0

for pos in positions:
    sym = pos["symbol"]
    entry = pos["entry_price"]
    size = pos["size"]
    current = prices.get(sym)

    pnl = (current - entry) * size if current is not None else None
    if pnl is not None:
        net_pnl += pnl

    rows.append(
        {
            "Symbol": sym,
            "Entry Price": entry,
            "Current Price": current,
            "Size": size,
            "PnL (USDT)": pnl,
        }
    )

# ── Display --------------------------------------------------------------------

st.subheader("Current Positions")
st.dataframe(pd.DataFrame(rows), use_container_width=True, height=450)

st.metric(label="Total Unrealised PnL (USDT)", value=f"{net_pnl:,.2f}")

st.caption(f"Last update: {datetime.utcnow():%Y-%m-%d %H:%M:%S} UTC")
