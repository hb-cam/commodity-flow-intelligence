"""Tests for futures price module."""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from commodity_flow import futures


class TestFetchFuturesCurves:
    @patch("commodity_flow.futures.yf.Ticker")
    def test_returns_expected_columns(self, mock_ticker_cls: MagicMock) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame(
            {"Close": [89.0, 90.0], "Volume": [1000, 1100]},
            index=pd.DatetimeIndex(["2025-03-24", "2025-03-25"], tz="UTC"),
        )
        mock_ticker_cls.return_value = mock_ticker

        df = futures.fetch_futures_curves(symbols=["CL=F"], period="5d")
        assert set(df.columns) >= {"date", "symbol", "name", "close", "volume"}
        assert len(df) == 2
        assert df["symbol"].iloc[0] == "CL=F"

    @patch("commodity_flow.futures.yf.Ticker")
    def test_empty_ticker_returns_empty_df(self, mock_ticker_cls: MagicMock) -> None:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        df = futures.fetch_futures_curves(symbols=["FAKE=F"])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert "date" in df.columns

    @patch("commodity_flow.futures.yf.Ticker")
    def test_default_symbols_include_ho(self, mock_ticker_cls: MagicMock) -> None:
        """HO=F (Heating Oil) should be in default symbols."""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        futures.fetch_futures_curves()
        called_symbols = [call[0][0] for call in mock_ticker_cls.call_args_list]
        assert "HO=F" in called_symbols


class TestComputeFuturesZScores:
    def test_returns_futures_z_column(self) -> None:
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        df = pd.DataFrame(
            {
                "date": dates,
                "symbol": "CL=F",
                "name": "WTI",
                "close": np.random.normal(80, 5, 100),
                "volume": 1000,
            }
        )
        result = futures.compute_futures_z_scores(df, window=20)
        assert "futures_z" in result.columns
        # First 19 rows should be NaN (min_periods=20)
        assert result["futures_z"].iloc[:19].isna().all()
        # Later rows should have valid z-scores
        valid = result["futures_z"].dropna()
        assert len(valid) > 50

    def test_empty_input(self) -> None:
        df = pd.DataFrame(columns=["date", "symbol", "name", "close", "volume"])
        result = futures.compute_futures_z_scores(df)
        assert "futures_z" in result.columns
        assert len(result) == 0

    def test_z_scores_bounded(self) -> None:
        """Normal random data should produce z-scores mostly in [-3, 3]."""
        np.random.seed(0)
        dates = pd.date_range("2024-01-01", periods=200, freq="D")
        df = pd.DataFrame(
            {
                "date": dates,
                "symbol": "CL=F",
                "name": "WTI",
                "close": np.random.normal(80, 3, 200),
                "volume": 1000,
            }
        )
        result = futures.compute_futures_z_scores(df, window=60)
        valid = result["futures_z"].dropna()
        assert (valid.abs() < 5).all()
