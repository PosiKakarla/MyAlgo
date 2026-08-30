"""
fetch_upstox_data.py

Pulls 5-min historical candles for a list of NSE stocks from Upstox V3 API
and saves one clean CSV per symbol.

RUN THIS ON YOUR OWN MACHINE (not in Claude's sandbox -- it has no network
access to financial APIs). Requires: pip install requests pandas

STEPS BEFORE RUNNING:
1. Generate today's access token from the Upstox Developer Console.
2. Download the instrument master file (see INSTRUMENT_MASTER_URL below) and
   find the instrument_key for each symbol you want -- paste them into
   SYMBOL_TO_INSTRUMENT_KEY below. This script does NOT auto-resolve them,
   because the instrument master format/URL can change and silently guessing
   wrong keys would corrupt the whole dataset.
"""
import os
import time
from datetime import date, timedelta
import requests
import pandas as pd

# ---- FILL THESE IN ----
ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")

# Instrument master file (download and inspect to get exact keys):
# https://assets.upstox.com/market-quote/instruments/exchange/NSE.csv.gz
INSTRUMENT_MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.csv.gz"

# Example only -- REPLACE with real instrument_keys you look up yourself.
# Format is "NSE_EQ|<ISIN>"
SYMBOL_TO_INSTRUMENT_KEY = {
    "RELIANCE": "NSE_EQ|INE002A01018",
    "SBIN": "NSE_EQ|INE062A01020",
    "TATAMOTORS": "NSE_EQ|INE155A01022",
    
    # "Nifty 50": "NSE_INDEX|Nifty 50",
    # ... add the rest of your chosen universe here
}

FROM_DATE = date(2024, 1, 1)   # adjust to how far back you want
TO_DATE = date.today()
INTERVAL_UNIT = "minutes"
INTERVAL_VALUE = "5"
MAX_CHUNK_DAYS = 28            # stay safely under the "1 month" limit for <=15 min bars

OUTPUT_DIR = "./upstox_data"
# ------------------------


def month_chunks(start: date, end: date, chunk_days: int = MAX_CHUNK_DAYS):
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=chunk_days - 1), end)
        yield cur, chunk_end
        cur = chunk_end + timedelta(days=1)


def fetch_chunk(instrument_key: str, from_d: date, to_d: date) -> list:
    url = (f"https://api.upstox.com/v3/historical-candle/{instrument_key}/"
           f"{INTERVAL_UNIT}/{INTERVAL_VALUE}/{to_d.isoformat()}/{from_d.isoformat()}")
    headers = {"Accept": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        print(f"  ERROR {resp.status_code} for {instrument_key} {from_d}->{to_d}: {resp.text[:200]}")
        return []
    payload = resp.json()
    return payload.get("data", {}).get("candles", [])


def fetch_symbol(symbol: str, instrument_key: str) -> pd.DataFrame:
    all_candles = []
    for chunk_start, chunk_end in month_chunks(FROM_DATE, TO_DATE):
        candles = fetch_chunk(instrument_key, chunk_start, chunk_end)
        all_candles.extend(candles)
        time.sleep(0.5)  # be polite to the API, avoid rate-limit errors

    if not all_candles:
        print(f"  WARNING: no data returned for {symbol}")
        return pd.DataFrame()

    df = pd.DataFrame(all_candles,
                       columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.drop(columns=["oi"]).sort_values("timestamp").drop_duplicates("timestamp")
    df = df.set_index("timestamp")
    return df


def main():
    import os
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for symbol, instrument_key in SYMBOL_TO_INSTRUMENT_KEY.items():
        print(f"Fetching {symbol} ({instrument_key}) ...")
        df = fetch_symbol(symbol, instrument_key)
        if df.empty:
            continue
        out_path = f"{OUTPUT_DIR}/{symbol}_5min.csv"
        df.to_csv(out_path)
        print(f"  Saved {len(df)} bars -> {out_path}")

    print("\nDone. Upload these CSVs (or their folder) back to continue with backtesting.")


if __name__ == "__main__":
    main()