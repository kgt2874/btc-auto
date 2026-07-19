"""
솔라나 시세 자동 업데이트 스크립트 (증분 수집)
- data-api.binance.vision 공개 데이터 사용 (지역 차단 없음, API 키 불필요)
- 기존 sol_history.csv 에서 마지막으로 저장된 시각을 확인하고,
  그 이후에 새로 생긴 캔들만 받아와 이어붙인다.
- 최초 실행 시 파일이 없으면 최근 1000개(1시간봉 기준 약 41일치)만 받아온다.
  더 오래된 과거 데이터가 필요하면 binance_sol_backfill.py 를 먼저 실행할 것.

필요 패키지: requests, pandas
설치: pip install requests pandas
실행: python binance_sol_fetch.py
"""

import requests
import pandas as pd
import os

SYMBOL = "SOLUSDT"
INTERVAL = "1h"
KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "sol_history.csv")


def fetch_recent_klines():
    params = {"symbol": SYMBOL, "interval": INTERVAL, "limit": 1000}
    resp = requests.get(KLINES_URL, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def build_dataframe(raw):
    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "num_trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ]
    df = pd.DataFrame(raw, columns=cols)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df[["open_time", "open", "high", "low", "close", "volume"]]


def compute_indicators(df):
    close = df["close"]
    df["sma20"] = close.rolling(20).mean()
    df["sma50"] = close.rolling(50).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    df["rsi14"] = 100 - (100 / (1 + rs))

    df["volume_change_pct"] = df["volume"].pct_change() * 100
    return df


def main():
    last_open_time = None
    file_exists = os.path.exists(HISTORY_FILE)

    if file_exists:
        existing = pd.read_csv(HISTORY_FILE, parse_dates=["open_time"])
        if len(existing) > 0:
            last_open_time = existing["open_time"].max()

    raw = fetch_recent_klines()
    df = build_dataframe(raw)
    df = compute_indicators(df)

    if last_open_time is not None:
        new_rows = df[df["open_time"] > last_open_time]
    else:
        new_rows = df

    if len(new_rows) == 0:
        print("추가할 새 데이터가 없습니다 (이미 최신 상태입니다).")
        return

    new_rows.to_csv(HISTORY_FILE, mode="a", header=not file_exists, index=False)
    print(f"{len(new_rows)}개의 새 행을 추가했습니다.")
    print(new_rows.tail(3).to_string(index=False))


if __name__ == "__main__":
    main()
