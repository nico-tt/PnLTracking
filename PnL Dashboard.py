"""
Crypto Spot PnL Dashboard
Author: ChatGPT assistant
Last updated: 2025-05-21

### Patch • Streamlit compatibility
`streamlit.experimental_rerun()` was renamed to the public `st.rerun()` around
v1.26. If you’re running an older or newer build, the attribute may be missing,
triggering the `AttributeError` you saw when setting the **HYPE** price.

A small helper now picks whichever API exists, so the dashboard works across the
version range shipped by Streamlit Cloud *and* local Python installs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final, List, Dict, Union
import sys
import textwrap
import time

import requests
import pandas as pd
import streamlit as st

Position = Dict[str, Union[str, float]]
PriceMap = Dict[str, Union[float, None]]

# ── Pre‑loaded portfolio -------------------------------------------------------
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
    if get_script_run_ctx() is None:
        sys.exit("Run this script with:  streamlit run crypto_pnl_dashboard.py")
except Exception:
    pass

# ── Helper for version‑agnostic rerun -----------------------------------------

def safe_rerun() -> None:  # noqa: D401 – imperative mood
    """Force a rerun using whichever Streamlit API exists."""
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()  # type: ignore[attr-defined]

# ── Optional auto‑refresh ------------------------------------------------------
try:
    from streamlit_autorefresh import st_autorefresh  # type: ignore
    AUTOREFRESH_AVAILABLE: Final = True
except ModuleNotFoundError:
    AUTOREFRESH_AVAILABLE = False  # type: ignore[assignment]

# ── Page config ----------------------------------------------------------------
st.set_page_config(page_title="Crypto Spot PnL Dashboard", layout="wide")

st.title("📈 Crypto Spot PnL Dashboard")

# ── Sidebar – positions --------------------------------------------------------
st.sidebar.header("Manage Positions")
if "positions" not in st.session_state:
    st.session_state["positions"] = [pos.copy() for pos in DEFAULT_POSITIONS]
if "manual_prices" not in st.session_state:
    st.session_state["manual_prices"] = {}

positions: List[Position] = st.session_state["positions"]
manual_prices: Dict[str, float] = st.session_state["manual_prices"]

with st.sidebar.form("add_position", clear_on_submit=True):
    symbol = st.text_input("Symbol (e.g. BTC)", "").upper()
    entry_price = st.number_input("Entry price (USDT)", min_value=0.0, step=0.01, format="%.6f")
    size = st.number_input("Size", min_value=0.0, step=0.0001, format="%.6f")
    if st.form_submit_button("Add / Update") and symbol and entry_price > 0 and size > 0:
        existing = next((p for p in positions if p["symbol"] == symbol), None)
        if existing:
            existing.update(entry_price=entry_price, size=size)
        else:
            positions.append({"symbol": symbol, "entry_price": entry_price, "size": size})
        safe_rerun()

if positions:
    remove_symbol = st.sidebar.selectbox("Remove position", ["-"] + [p["symbol"] for p in positions])
    if st.sidebar.button("Remove") and remove_symbol != "-":
        positions[:] = [p for p in positions if p["symbol"] != remove_symbol]
        manual_prices.pop(remove_symbol, None)
        safe_rerun()

# ── Refresh interval -----------------------------------------------------------
refresh_interval = st.sidebar.slider("Refresh interval (seconds)", 1, 60, 10)
if AUTOREFRESH_AVAILABLE:
    from streamlit_autorefresh import st_autorefresh  # type: ignore
    st_autorefresh(interval=refresh_interval * 1000, limit=None, key="refresh")
else:
    if "_last_refresh" not in st.session_state:
        st.session_state["_last_refresh"] = time.time()
    if time.time() - st.session_state["_last_refresh"] > refresh_interval:
        st.session_state["_last_refresh"] = time.time()
        safe_rerun()

# ── Price fetching (Binance + CoinGecko fallback) -----------------------------
CG_ID_MAP: Dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "SUI": "sui",
    "XRP": "ripple",
    "LINK": "chainlink",
    "DOGE": "dogecoin",
    "ONDO": "ondo-finance",
    "BONK": "bonk",
    "TAO": "bittensor",
    "NEAR": "near",
    "RENDER": "render-token",
}

def fetch_binance(symbols: List[str]) -> PriceMap:
    prices: PriceMap = {}
    for sym in symbols:
        try:
            r = requests.get("https://api.binance.com/api/v3/ticker/price", params={"symbol": f"{sym}USDT"}, timeout=3)
            r.raise_for_status()
            prices[sym] = float(r.json()["price"])
        except Exception:
            prices[sym] = None
    return prices

def fetch_coingecko(symbols: List[str]) -> PriceMap:
    ids = [CG_ID_MAP[s] for s in symbols if s in CG_ID_MAP]
    if not ids:
        return {s: None for s in symbols}
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price", params={"ids": ",".join(ids), "vs_currencies": "usd"}, timeout=5)
        r.raise_for_status()
        data = r.json()
        return {s: float(data[CG_ID_MAP[s]]["usd"]) if s in CG_ID_MAP and data.get(CG_ID_MAP[s]) else None for s in symbols}
    except Exception:
        return {s: None for s in symbols}

symbols = [p["symbol"] for p in positions]
prices = fetch_binance(symbols)
missing = [s for s, p in prices.items() if p is None]
if missing:
    prices.update(fetch_coingecko(missing))

# ── Manual overrides -----------------------------------------------------------
missing_final = [s for s, p in prices.items() if p is None]
if missing_final:
    with st.sidebar.expander("Missing prices (manual override)", expanded=True):
        st.info("Enter manual USDT price for tokens not found on Binance/CoinGecko.")
        for sym in missing_final:
            val = st.number_input(f"{sym} price", value=manual_prices.get(sym, 0.0), min_value=0.0, step=0.0001)
            if val > 0:
                manual_prices[sym] = val
                prices[sym] = val
                safe_rerun()
            elif sym in manual_prices and val == 0:
                manual_prices.pop(sym)
                safe_rerun()

# ── PnL computation & display --------------------------------------------------
rows: List[Dict[str, Union[str, float, None]]] = []
net_pnl = 0.0
for pos in positions:
    sym, entry, size = pos["symbol"], pos["entry_price"], pos["size"]
    current = prices.get(sym)
    pnl = (current - entry) * size if current is not None else None
    if pnl is not None:
        net_pnl += pnl
    rows.append({"Symbol": sym, "Entry Price": entry, "Current Price": current, "Size": size, "PnL (USDT)": pnl})

st.subheader("Current Positions")
st.dataframe(pd.DataFrame(rows), use_container_width=True, height=460)

st.metric("Total Unrealised PnL (USDT)", f"{net_pnl:,.2f}")

st.caption(f"Last update: {datetime.utcnow():%Y-%m-%d %H:%M:%S} UTC")
