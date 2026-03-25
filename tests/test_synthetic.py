"""Tests for synthetic data generators."""

import pandas as pd
from commodity_flow import synthetic


class TestGenerateSyntheticImports:
    def test_returns_dataframe(self) -> None:
        df = synthetic.generate_synthetic_imports()
        assert isinstance(df, pd.DataFrame)

    def test_has_required_columns(self) -> None:
        df = synthetic.generate_synthetic_imports()
        required = {"period", "duoarea", "value", "date", "units"}
        assert required.issubset(df.columns)

    def test_covers_all_padds(self) -> None:
        df = synthetic.generate_synthetic_imports()
        padds = set(df["duoarea"].unique())
        assert padds == {"PADD 1", "PADD 2", "PADD 3", "PADD 4", "PADD 5"}

    def test_values_are_non_negative(self) -> None:
        df = synthetic.generate_synthetic_imports()
        assert (df["value"] >= 0).all()

    def test_delivery_gap_injected(self) -> None:
        df = synthetic.generate_synthetic_imports()
        # PADD 3 should show a notable dip in late 2025
        padd3 = df[df["duoarea"] == "PADD 3"].sort_values("date")
        pre_gap = padd3[(padd3["date"] >= "2025-06-01") & (padd3["date"] < "2025-10-01")]
        in_gap = padd3[(padd3["date"] >= "2025-10-01") & (padd3["date"] <= "2026-02-01")]
        assert in_gap["value"].mean() < pre_gap["value"].mean()

    def test_deterministic(self) -> None:
        df1 = synthetic.generate_synthetic_imports()
        df2 = synthetic.generate_synthetic_imports()
        pd.testing.assert_frame_equal(df1, df2)


class TestGenerateSyntheticStocks:
    def test_returns_dataframe(self) -> None:
        df = synthetic.generate_synthetic_stocks()
        assert isinstance(df, pd.DataFrame)

    def test_has_date_and_value(self) -> None:
        df = synthetic.generate_synthetic_stocks()
        assert "date" in df.columns
        assert "value" in df.columns

    def test_weekly_frequency(self) -> None:
        df = synthetic.generate_synthetic_stocks()
        padd1 = df[df["duoarea"] == "PADD 1"].sort_values("date")
        # Check roughly weekly spacing
        diffs = padd1["date"].diff().dropna()
        assert diffs.median().days == 7


class TestGenerateSyntheticHelium:
    def test_shape(self) -> None:
        df = synthetic.generate_synthetic_helium()
        assert len(df) == 9  # 2018-2026
        assert "year" in df.columns
        assert "supply_gap_Mcm" in df.columns

    def test_deficit_years_exist(self) -> None:
        df = synthetic.generate_synthetic_helium()
        assert (df["supply_gap_Mcm"] < 0).any()


class TestGenerateSyntheticNatgas:
    def test_two_modes(self) -> None:
        df = synthetic.generate_synthetic_natgas_imports()
        assert set(df["mode"].unique()) == {"Pipeline", "LNG"}

    def test_pipeline_larger_than_lng(self) -> None:
        df = synthetic.generate_synthetic_natgas_imports()
        pipeline_avg = df[df["mode"] == "Pipeline"]["value_bcf"].mean()
        lng_avg = df[df["mode"] == "LNG"]["value_bcf"].mean()
        assert pipeline_avg > lng_avg


class TestGenerateSyntheticBreakevens:
    def test_all_basins_present(self) -> None:
        df = synthetic.generate_synthetic_breakevens()
        from commodity_flow.config import BASINS

        assert set(df["basin"].unique()) == set(BASINS.keys())

    def test_breakevens_positive(self) -> None:
        df = synthetic.generate_synthetic_breakevens()
        assert (df["breakeven_usd_bbl"] > 0).all()


class TestGenerateSyntheticDpr:
    def test_has_production_and_rigs(self) -> None:
        df = synthetic.generate_synthetic_dpr()
        assert "production_per_rig_bbl_d" in df.columns
        assert "rig_count" in df.columns

    def test_rig_counts_positive(self) -> None:
        df = synthetic.generate_synthetic_dpr()
        assert (df["rig_count"] > 0).all()


class TestGenerateSyntheticSteo:
    def test_has_forecast_flag(self) -> None:
        df = synthetic.generate_synthetic_steo()
        assert "is_forecast" in df.columns
        assert df["is_forecast"].any()
        assert (~df["is_forecast"]).any()

    def test_series_ids(self) -> None:
        df = synthetic.generate_synthetic_steo()
        assert "CONIPUS" in df["series_id"].values
        assert "PAPR_WORLD" in df["series_id"].values
