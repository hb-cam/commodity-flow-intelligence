"""Tests for analysis functions."""

import numpy as np
import pandas as pd
from commodity_flow import analysis, synthetic


class TestComputeGapScore:
    def test_returns_series(self) -> None:
        s = pd.Series([100, 102, 98, 101, 99, 97, 95, 90, 85, 80])
        result = analysis.compute_gap_score(s, window=5)
        assert isinstance(result, pd.Series)
        assert len(result) == len(s)

    def test_declining_series_goes_negative(self) -> None:
        s = pd.Series([100, 100, 100, 100, 100, 90, 80, 70, 60, 50])
        result = analysis.compute_gap_score(s, window=5)
        # Last values should be strongly negative
        assert result.iloc[-1] < -1

    def test_stable_series_near_zero(self) -> None:
        np.random.seed(0)
        s = pd.Series(np.random.normal(100, 1, 50))
        result = analysis.compute_gap_score(s, window=12)
        # Most z-scores should be between -2 and 2
        valid = result.dropna()
        assert (valid.abs() < 3).mean() > 0.9


class TestDetectGaps:
    def test_flags_gaps(self) -> None:
        dates = pd.date_range("2024-01-01", periods=20, freq="MS")
        values = [100] * 15 + [60, 55, 50, 45, 40]  # sharp drop
        df = pd.DataFrame({"date": dates, "value": values})
        result = analysis.detect_gaps(df, column="value", window=12, threshold=-1.0)
        assert "in_gap" in result.columns
        assert "z_score" in result.columns
        assert result["in_gap"].any()

    def test_no_gaps_in_stable_data(self) -> None:
        dates = pd.date_range("2024-01-01", periods=20, freq="MS")
        values = [100] * 20
        df = pd.DataFrame({"date": dates, "value": values})
        result = analysis.detect_gaps(df, column="value", window=6, threshold=-1.0)
        # Stable data shouldn't trigger gaps (z-scores are NaN or 0)
        assert not result["in_gap"].any()


class TestBuildScorecard:
    def test_returns_dataframe_with_composite(self) -> None:
        df_imports = synthetic.generate_synthetic_imports()
        df_natgas = synthetic.generate_synthetic_natgas_imports()
        result = analysis.build_scorecard(df_imports, df_natgas)
        assert "composite_gap_score" in result.columns
        assert "oil_import_z" in result.columns
        assert "natgas_import_z" in result.columns
        assert len(result) > 0

    def test_with_steo_adds_forecast(self) -> None:
        df_imports = synthetic.generate_synthetic_imports()
        df_natgas = synthetic.generate_synthetic_natgas_imports()
        df_steo = synthetic.generate_synthetic_steo()
        result = analysis.build_scorecard(df_imports, df_natgas, df_steo)
        assert "is_forecast" in result.columns
        assert result["is_forecast"].any()


class TestComputeBreakevenStatus:
    def test_classifies_basins(self) -> None:
        df = synthetic.generate_synthetic_breakevens()
        result = analysis.compute_breakeven_status(df, wti_price=70.0)
        assert "status" in result.columns
        assert "margin_usd_bbl" in result.columns
        assert set(result["status"].unique()).issubset({"profitable", "marginal", "at risk"})

    def test_high_price_all_profitable(self) -> None:
        df = synthetic.generate_synthetic_breakevens()
        result = analysis.compute_breakeven_status(df, wti_price=200.0)
        assert result["profitable"].all()

    def test_low_price_none_profitable(self) -> None:
        df = synthetic.generate_synthetic_breakevens()
        result = analysis.compute_breakeven_status(df, wti_price=10.0)
        assert not result["profitable"].any()


class TestProductionAtRiskCurve:
    def test_returns_sweep(self) -> None:
        df_be = synthetic.generate_synthetic_breakevens()
        df_dpr = synthetic.generate_synthetic_dpr()
        result = analysis.production_at_risk_curve(df_be, df_dpr)
        assert "wti_price" in result.columns
        assert "pct_at_risk" in result.columns
        assert len(result) > 10

    def test_monotonic_risk(self) -> None:
        """Lower prices should mean more production at risk."""
        df_be = synthetic.generate_synthetic_breakevens()
        df_dpr = synthetic.generate_synthetic_dpr()
        result = analysis.production_at_risk_curve(df_be, df_dpr)
        # pct_at_risk should be non-increasing as price rises
        pct = result.sort_values("wti_price")["pct_at_risk"].values
        assert all(pct[i] >= pct[i + 1] for i in range(len(pct) - 1))
