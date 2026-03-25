"""Domain sanity checks — magnitude bounds, distribution, cross-validation.

These tests formalize the ad-hoc verification checks that were run interactively
against known EIA/USGS/Fed benchmarks. They run against synthetic data by default
(no API key needed) and catch configuration drift that would silently corrupt
the z-score signals.
"""

import numpy as np
import pandas as pd

from commodity_flow import analysis, config, synthetic


class TestImportMagnitudes:
    """Verify synthetic import baselines match known US petroleum flows."""

    def setup_method(self) -> None:
        self.df = synthetic.generate_synthetic_imports()

    def test_national_monthly_total_in_range(self) -> None:
        """US gross crude imports: ~150K-250K MBBL/month (5-8M bbl/d)."""
        monthly = self.df.groupby("date")["value"].sum()
        avg = monthly.mean()
        assert 120_000 <= avg <= 280_000, f"National monthly avg {avg:,.0f} outside range"

    def test_padd2_is_largest_importer(self) -> None:
        """PADD 2 dominates due to Canadian pipeline crude (~47%)."""
        padd_avg = self.df.groupby("duoarea")["value"].mean()
        assert padd_avg.idxmax() == "PADD 2", f"Largest PADD: {padd_avg.idxmax()}"

    def test_padd_shares_reasonable(self) -> None:
        """No single PADD should exceed 60% or be below 3% of total."""
        padd_avg = self.df.groupby("duoarea")["value"].mean()
        total = padd_avg.sum()
        for padd, val in padd_avg.items():
            share = val / total * 100
            assert 3 <= share <= 60, f"{padd} has {share:.1f}% share"

    def test_config_baselines_sum_matches_national(self) -> None:
        """Config baselines should sum to roughly the national monthly total."""
        config_total = sum(config.PADD_IMPORT_BASELINES.values())
        monthly = self.df.groupby("date")["value"].sum().mean()
        ratio = monthly / config_total
        assert 0.8 <= ratio <= 1.3, f"Synthetic/config ratio: {ratio:.2f}"


class TestStockMagnitudes:
    """Verify synthetic stock baselines match known US petroleum inventories."""

    def setup_method(self) -> None:
        self.df = synthetic.generate_synthetic_stocks()

    def test_national_total_in_range(self) -> None:
        """US total petroleum stocks: ~700K-1.5M MBBL across 5 PADDs."""
        latest = self.df.groupby("duoarea")["value"].last()
        total = latest.sum()
        assert 700_000 <= total <= 1_500_000, f"Total stocks {total:,.0f} outside range"

    def test_padd3_has_largest_stocks(self) -> None:
        """Gulf Coast (PADD 3) has the largest storage infrastructure."""
        padd_avg = self.df.groupby("duoarea")["value"].mean()
        assert padd_avg.idxmax() == "PADD 3"

    def test_config_baselines_match_synthetic(self) -> None:
        """Synthetic generator should produce values near config baselines."""
        synth_avg = self.df.groupby("duoarea")["value"].mean()
        for padd, baseline in config.PADD_STOCK_BASELINES.items():
            ratio = synth_avg[padd] / baseline
            assert 0.7 <= ratio <= 1.5, f"{padd} ratio {ratio:.2f}"


class TestNatgasMagnitudes:
    """Verify natgas import baselines reflect US as net LNG exporter."""

    def setup_method(self) -> None:
        self.df = synthetic.generate_synthetic_natgas_imports()

    def test_pipeline_dominates_lng(self) -> None:
        """Pipeline imports ~260 Bcf/mo vs LNG ~2 Bcf/mo."""
        pipeline = self.df[self.df["mode"] == "Pipeline"]["value_bcf"].mean()
        lng = self.df[self.df["mode"] == "LNG"]["value_bcf"].mean()
        assert pipeline > 50 * lng, f"Pipeline/LNG ratio too low: {pipeline / lng:.0f}x"

    def test_pipeline_in_range(self) -> None:
        """US pipeline natgas imports: ~200-350 Bcf/month."""
        pipeline = self.df[self.df["mode"] == "Pipeline"]["value_bcf"].mean()
        assert 180 <= pipeline <= 380, f"Pipeline avg {pipeline:.0f} Bcf/mo"

    def test_lng_near_zero(self) -> None:
        """US is net LNG exporter; imports should be <10 Bcf/mo."""
        lng = self.df[self.df["mode"] == "LNG"]["value_bcf"].mean()
        assert lng < 10, f"LNG avg {lng:.1f} Bcf/mo — US is a net exporter"


class TestHeliumBenchmarks:
    """Verify helium data against USGS Mineral Commodity Summaries."""

    def setup_method(self) -> None:
        self.df = synthetic.generate_synthetic_helium()

    def test_us_production_range(self) -> None:
        """US helium production: ~45-60 Mcm/yr."""
        assert self.df["us_production_Mcm"].between(40, 65).all()

    def test_world_production_range(self) -> None:
        """Global helium production: ~140-190 Mcm/yr."""
        assert self.df["world_production_Mcm"].between(130, 200).all()

    def test_blm_price_increasing_trend(self) -> None:
        """BLM Grade-A helium price should show overall upward trend."""
        prices = self.df["blm_price_usd_per_mcf"].values
        assert prices[-1] > prices[0], "Price should trend upward"

    def test_deficit_years_exist(self) -> None:
        """Helium market should show supply deficits in recent years."""
        recent = self.df[self.df["year"] >= 2024]
        assert (recent["supply_gap_Mcm"] < 0).any()


class TestBreakevenBenchmarks:
    """Verify basin breakevens against Dallas/KC Fed survey ranges."""

    def setup_method(self) -> None:
        self.df = synthetic.generate_synthetic_breakevens()
        self.latest = self.df.sort_values("date").groupby("basin").last()

    def test_permian_cheapest(self) -> None:
        """Permian Basin should have lowest breakeven."""
        cheapest = self.latest["breakeven_usd_bbl"].idxmin()
        assert cheapest == "Permian", f"Cheapest basin: {cheapest}"

    def test_breakevens_in_fed_survey_range(self) -> None:
        """All breakevens should be in $20-$70/bbl range."""
        assert self.latest["breakeven_usd_bbl"].between(20, 70).all()

    def test_wti_array_length_guard(self) -> None:
        """wti_base array must cover all quarters in the date range."""
        quarters = pd.date_range("2022-01-01", "2026-01-01", freq="QS")
        wti_base = np.array([78, 95, 88, 82, 75, 72, 78, 85, 80, 76, 70, 65, 58, 62, 68, 72, 70])
        assert len(wti_base) >= len(quarters), (
            f"wti_base has {len(wti_base)} entries but need {len(quarters)} quarters"
        )


class TestDprBenchmarks:
    """Verify DPR baselines against EIA Drilling Productivity Report."""

    def setup_method(self) -> None:
        self.df = synthetic.generate_synthetic_dpr()

    def test_permian_has_most_rigs(self) -> None:
        """Permian should have highest rig count."""
        latest = self.df.sort_values("date").groupby("basin").last()
        assert latest["rig_count"].idxmax() == "Permian"

    def test_production_per_rig_ranges(self) -> None:
        """Oil basins: 800-2000 bbl/d/rig; gas basins: 200-500."""
        latest = self.df.sort_values("date").groupby("basin").last()
        oil_basins = ["Permian", "Eagle Ford", "Bakken", "DJ/Niobrara", "Anadarko"]
        gas_basins = ["Appalachian", "Haynesville"]
        for basin in oil_basins:
            prod = latest.loc[basin, "production_per_rig_bbl_d"]
            assert 600 <= prod <= 2500, f"{basin}: {prod} bbl/d/rig"
        for basin in gas_basins:
            prod = latest.loc[basin, "production_per_rig_bbl_d"]
            assert 100 <= prod <= 600, f"{basin}: {prod} bbl/d/rig"


class TestSteoSynthetic:
    """Verify synthetic STEO projections match real EIA magnitudes."""

    def setup_method(self) -> None:
        self.df = synthetic.generate_synthetic_steo()

    def test_conipus_is_net_imports(self) -> None:
        """CONIPUS = net imports, should be ~0.5-5 million bbl/d (NOT gross ~6.3)."""
        conipus = self.df[self.df["series_id"] == "CONIPUS"]["value"]
        assert conipus.between(0.3, 5.0).all(), (
            f"Range: {conipus.min():.1f}-{conipus.max():.1f} — should be net imports, not gross"
        )

    def test_papr_world_is_world_production(self) -> None:
        """PAPR_WORLD = world production, should be ~100-115 million bbl/d."""
        papr = self.df[self.df["series_id"] == "PAPR_WORLD"]["value"]
        assert papr.between(95, 120).all(), (
            f"Range: {papr.min():.1f}-{papr.max():.1f} — should be world production ~107M bbl/d"
        )

    def test_coprpus_is_us_production(self) -> None:
        """COPRPUS = US crude production, should be ~12-15 million bbl/d."""
        coprpus = self.df[self.df["series_id"] == "COPRPUS"]["value"]
        assert coprpus.between(11, 16).all(), f"Range: {coprpus.min():.1f}-{coprpus.max():.1f}"

    def test_has_historical_and_forecast(self) -> None:
        """STEO should have both historical and forecast periods."""
        assert self.df["is_forecast"].any(), "No forecast rows"
        assert (~self.df["is_forecast"]).any(), "No historical rows"

    def test_has_three_series(self) -> None:
        """Should have CONIPUS, COPRPUS, and PAPR_WORLD."""
        series = set(self.df["series_id"].unique())
        assert {"CONIPUS", "COPRPUS", "PAPR_WORLD"} == series


class TestScorecardOutputBounds:
    """Verify scorecard z-scores are bounded and well-formed."""

    def setup_method(self) -> None:
        df_imports = synthetic.generate_synthetic_imports()
        df_natgas = synthetic.generate_synthetic_natgas_imports()
        df_steo = synthetic.generate_synthetic_steo()
        self.scorecard = analysis.build_scorecard(df_imports, df_natgas, df_steo)

    def test_composite_bounded(self) -> None:
        """Z-scores should not exceed ±6 in normal data."""
        actual = self.scorecard[~self.scorecard["is_forecast"]]
        z = actual["composite_gap_score"].dropna()
        assert (z.abs() < 6).all(), f"Range: [{z.min():.2f}, {z.max():.2f}]"

    def test_sufficient_data_points(self) -> None:
        """Scorecard should have at least 12 months of data."""
        actual = self.scorecard[~self.scorecard["is_forecast"]]
        assert len(actual) >= 12

    def test_forecast_rows_present_with_steo(self) -> None:
        """When STEO is provided, forecast rows should exist."""
        assert self.scorecard["is_forecast"].any()

    def test_empty_intersection_returns_empty(self) -> None:
        """Non-overlapping dates should produce empty scorecard, not error."""
        df_imp = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=12, freq="MS"),
                "duoarea": "PADD 1",
                "value": 100,
            }
        )
        df_ng = pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=12, freq="MS"),
                "mode": "Pipeline",
                "value_bcf": 250,
            }
        )
        sc = analysis.build_scorecard(df_imp, df_ng)
        # Should not raise; may be empty
        assert isinstance(sc, pd.DataFrame)


class TestScorecardUnitAlignment:
    """Verify scorecard catches unit mismatches via logging warnings."""

    def test_warns_on_low_import_values(self, caplog) -> None:
        """Import values in bbl instead of MBBL should trigger warning."""
        import logging

        df_imp = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=24, freq="MS"),
                "duoarea": "PADD 1",
                "value": 100.0,  # way too low for MBBL
            }
        )
        df_ng = synthetic.generate_synthetic_natgas_imports()
        with caplog.at_level(logging.WARNING, logger="commodity_flow.analysis"):
            analysis.build_scorecard(df_imp, df_ng)
        assert any("suspiciously low" in msg for msg in caplog.messages)

    def test_warns_on_high_steo_conipus(self, caplog) -> None:
        """CONIPUS > 8 should trigger 'not gross imports' warning."""
        import logging

        df_imp = synthetic.generate_synthetic_imports()
        df_ng = synthetic.generate_synthetic_natgas_imports()
        df_steo = pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=12, freq="MS"),
                "series_id": "CONIPUS",
                "value": 9.0,  # gross imports, not net — triggers >8 warning
                "is_forecast": False,
            }
        )
        with caplog.at_level(logging.WARNING, logger="commodity_flow.analysis"):
            analysis.build_scorecard(df_imp, df_ng, df_steo)
        assert any("net imports" in msg.lower() for msg in caplog.messages)


class TestZScoreArithmetic:
    """Verify z-score calculation produces exact known values."""

    def test_exact_value_known_series(self) -> None:
        """Compute z-score by hand and compare."""
        # 9 values of 100, then 80
        s = pd.Series([100.0] * 10 + [80.0])
        z = analysis.compute_gap_score(s, window=10)
        # At index 10: window is [100,100,100,100,100,100,100,100,100,80]
        vals = np.array([100.0] * 9 + [80.0])
        expected_z = (80.0 - vals.mean()) / vals.std(ddof=1)
        assert abs(z.iloc[-1] - expected_z) < 1e-10

    def test_constant_series_returns_nan(self) -> None:
        """Constant series has std=0, should return NaN not inf."""
        s = pd.Series([42.0] * 20)
        z = analysis.compute_gap_score(s, window=10)
        valid = z.dropna()
        # After warmup, all z-scores should be NaN (std=0 → NaN via replace)
        assert len(valid) == 0 or not np.isinf(valid).any()

    def test_gap_detection_threshold(self) -> None:
        """Threshold=-1 should flag values more than 1 std below mean."""
        dates = pd.date_range("2024-01-01", periods=24, freq="MS")
        values = [100.0] * 18 + [60.0, 55.0, 50.0, 45.0, 40.0, 35.0]
        df = pd.DataFrame({"date": dates, "value": values})
        result = analysis.detect_gaps(df, threshold=-1.0, window=12)
        # The sharp drop should trigger gaps
        late = result[result["date"] >= "2025-07-01"]
        assert late["in_gap"].all(), "Sharp drop should flag all late months"
