"""
바이낸스 BTC 가격/거래량 자동 수집 스크립트
- API 키 불필요 (공개 마켓 데이터 엔드포인트만 사용)
- 실행할 때마다 최신 일봉 데이터를 받아 지표를 계산하고
  history CSV에 한 줄(오늘자 스냅샷)을 누적 저장한다.

필요 패키지: requests, pandas
설치: pip install requests pandas
실행: python binance_btc_fetch.py
"""

import requests
import pandas as pd
from datetime import datetime, timezone
import os

SYMBOL = "BTCUSDT"
INTERVAL = "1h"          # 1시간봉. 1d(일봉), 4h(4시간봉) 등으로도 변경 가능
KLINES_LIMIT = 100       # 지표 계산에 필요한 캔들 수
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "btc_history.csv")

# 참고: api.binance.com은 미국 소재 클라우드(GitHub Actions 등)의 접속을
# 지역 규제상 차단(HTTP 451)한다. data-api.binance.vision은 바이낸스가
# 공식 제공하는 차단되지 않는 공개 시세 데이터 미러 주소.
KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
TICKER_URL = "https://data-api.binance.vision/api/v3/ticker/24hr"


def fetch_klines():
    """캔들(시가/고가/저가/종가/거래량) 데이터 조회"""
    params = {"symbol": SYMBOL, "interval": INTERVAL, "limit": KLINES_LIMIT}
    resp = requests.get(KLINES_URL, params=params, timeout=10)
    resp.raise_for_status()
    raw = resp.json()

    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "num_trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ]
    df = pd.DataFrame(raw, columns=cols)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df


def fetch_24h_ticker():
    """24시간 변동률/거래량 요약"""
    params = {"symbol": SYMBOL}
    resp = requests.get(TICKER_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def compute_indicators(df: pd.DataFrame) -> dict:
    """이동평균선, RSI, 거래량 변화율 계산"""
    close = df["close"]
    volume = df["volume"]

    sma20 = close.rolling(20).mean().iloc[-1]
    sma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    rsi14 = (100 - (100 / (1 + rs))).iloc[-1]

    vol_change_pct = (
        (volume.iloc[-1] - volume.iloc[-2]) / volume.iloc[-2] * 100
        if len(volume) >= 2 and volume.iloc[-2] != 0 else None
    )

    golden_cross = None
    if sma50 is not None:
        golden_cross = bool(sma20 > sma50)

    return {
        "close": close.iloc[-1],
        "sma20": round(sma20, 2) if pd.notna(sma20) else None,
        "sma50": round(sma50, 2) if sma50 is not None and pd.notna(sma50) else None,
        "rsi14": round(rsi14, 2) if pd.notna(rsi14) else None,
        "volume_change_pct": round(vol_change_pct, 2) if vol_change_pct is not None else None,
        "golden_cross_sma20_over_sma50": golden_cross,
    }


def append_history(snapshot: dict):
    """오늘자 스냅샷을 history csv에 누적. 파일 없으면 생성."""
    row = pd.DataFrame([snapshot])
    if os.path.exists(HISTORY_FILE):
        row.to_csv(HISTORY_FILE, mode="a", header=False, index=False)
    else:
        row.to_csv(HISTORY_FILE, mode="w", header=True, index=False)


def main():
    df = fetch_klines()
    ticker = fetch_24h_ticker()
    indicators = compute_indicators(df)

    snapshot = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "symbol": SYMBOL,
        "last_price": float(ticker["lastPrice"]),
        "price_change_pct_24h": float(ticker["priceChangePercent"]),
        "volume_24h_btc": float(ticker["volume"]),
        "quote_volume_24h_usdt": float(ticker["quoteVolume"]),
        **indicators,
    }

    append_history(snapshot)

    print("=== BTC 스냅샷 저장 완료 ===")
    for k, v in snapshot.items():
        print(f"{k}: {v}")

    # 간단한 신호 코멘트 (참고용, 투자 자문 아님)
    if indicators.get("rsi14") is not None:
        if indicators["rsi14"] >= 70:
            print("\n[참고] RSI 70 이상 → 단기 과매수 구간")
        elif indicators["rsi14"] <= 30:
            print("\n[참고] RSI 30 이하 → 단기 과매도 구간")

    if indicators.get("golden_cross_sma20_over_sma50") is True:
        print("[참고] SMA20 > SMA50 → 단기 추세 상승 우위")
    elif indicators.get("golden_cross_sma20_over_sma50") is False:
        print("[참고] SMA20 < SMA50 → 단기 추세 하락 우위")


if __name__ == "__main__":
    main()
