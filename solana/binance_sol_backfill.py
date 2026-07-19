"""
솔라나 과거 시세 전체 히스토리 백필(backfill) 스크립트
- data-api.binance.vision 공개 데이터 사용 (지역 차단 없음, API 키 불필요)
- SOLUSDT 상장일(2017-08-17)부터 현재까지 1시간봉 전체를 받아와
  sol_history.csv 를 새로 생성한다 (기존 파일이 있으면 덮어씀).
- 이 스크립트는 "딱 한 번" 수동으로 실행하면 된다. 이후 매시간 자동 실행되는
  binance_sol_fetch.py 가 이 파일 뒤에 새 데이터를 이어붙인다.

필요 패키지: requests, pandas
설치: pip install requests pandas
실행: python binance_sol_backfill.py
"""

import requests
import pandas as pd
from datetime import datetime, timezone
import os

SYMBOL = "SOLUSDT"
INTERVAL = "1h"
START_DATE = "2017-08-17"  # SOLUSDT 상장일. 필요시 "2022-01-01" 등으로 조정 가능
KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "sol_history.csv")


def to_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def fetch_all_klines():
    """1000개씩 끊어서 과거~현재까지 전체 캔들 수집"""
    all_rows = []
    start_ts = to_ms(START_DATE)
    now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)

    while start_ts < now_ts:
        params = {
            "symbol": SYMBOL,
            "interval": INTERVAL,
            "startTime": start_ts,
            "limit": 1000,
        }
        resp = requests.get(KLINES_URL, params=params, timeout=15)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            # 아직 상장 전이라 데이터가 없는 구간일 수 있음 -> 30일씩 건너뛰며 탐색
            start_ts += 30 * 24 * 60 * 60 * 1000
            continue

        all_rows.extend(batch)
        last_close_time = batch[-1][6]
        start_ts = last_close_time + 1

        progress_time = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc)
        print(f"수집 중... {progress_time} 까지 진행 (누적 {len(all_rows)}개)")

        if len(batch) < 1000:
            break

    return all_rows


def build_dataframe(raw: list) -> pd.DataFrame:
    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "num_trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ]
    df = pd.DataFrame(raw, columns=cols)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)

    df = (
        df[["open_time", "open", "high", "low", "close", "volume"]]
        .drop_duplicates(subset="open_time")
        .sort_values("open_time")
        .reset_index(drop=True)
    )
    return df


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
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
    print(f"{START_DATE} 부터 현재까지 {SYMBOL} {INTERVAL} 데이터 수집을 시작합니다.")
    raw = fetch_all_klines()
    df = build_dataframe(raw)
    df = compute_indicators(df)
    df.to_csv(HISTORY_FILE, index=False)
    print(f"완료: 총 {len(df)}개 행을 {HISTORY_FILE} 에 저장했습니다.")


if __name__ == "__main__":
    main()
