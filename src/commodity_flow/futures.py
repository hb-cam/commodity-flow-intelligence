"""Futures price overlay via yfinance."""

from __future__ import annotations

import pandas as pd
import yfinance as yf

# Default commodity futures tickers
DEFAULT_SYMBOLS: dict[str, str] = {
    "CL=F": "WTI Crude Oil",
    "NG=F": "Natural Gas",
    "RB=F": "RBOB Gasoline",
    "HO=F": "Heating Oil",
}


def fetch_futures_curves(
    symbols: list[str] | None = None,
    period: str = "2y",
) -> pd.DataFrame:
    """Fetch daily futures close prices for commodity tickers.

    Returns a DataFrame with columns: date, symbol, name, close, volume.
    """
    if symbols is None:
        symbols = list(DEFAULT_SYMBOLS.keys())

    frames: list[pd.DataFrame] = []
    for symbol in symbols:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        if hist.empty:
            continue
        df = pd.DataFrame(
            {
                "date": hist.index.tz_localize(None),
                "symbol": symbol,
                "name": DEFAULT_SYMBOLS.get(symbol, symbol),
                "close": hist["Close"].values,
                "volume": hist["Volume"].values,
            }
        )
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["date", "symbol", "name", "close", "volume"])

    return pd.concat(frames, ignore_index=True)


def compute_futures_z_scores(df_futures: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """Compute rolling z-scores for futures prices.

    Used to overlay on the physical gap scorecard — divergence between
    physical gap z-score and futures z-score = potential signal.
    """
    results: list[pd.DataFrame] = []
    for symbol in df_futures["symbol"].unique():
        sub = df_futures[df_futures["symbol"] == symbol].sort_values("date").copy()
        ma = sub["close"].rolling(window, min_periods=20).mean()
        std = sub["close"].rolling(window, min_periods=20).std()
        sub["futures_z"] = (sub["close"] - ma) / std.replace(0, float("nan"))
        results.append(sub)

    if not results:
        return df_futures.assign(futures_z=float("nan"))

    return pd.concat(results, ignore_index=True)
