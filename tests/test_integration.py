"""Integration tests — cross-dataset consistency, calculation verification,
unit alignment, and end-to-end pipeline behavior.

These tests verify that when datasets are combined, the outputs are
internally consistent and physically meaningful.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from commodity_flow import analysis, synthetic
from commodity_flow.inventory import (
    compute_days_of_supply,
    compute_seasonal_comparison,
    compute_spr_status,
    generate_synthetic_inventory,
)


# ---------------------------------------------------------------------------
# Section 1: Scorecard calculation verification
# ---------------------------------------------------------------------------


class TestScorecardDisruptionDetection:
    """Verify the scorecard actually detects the synthetic disruption.

    Synthetic data injects a delivery gap in Oct 2025 - Feb 2026.
    The scorecard should produce negative z-scores in that window.
    """

    def setup_method(self) -> None:
        self.df_imports = synthetic.generate_synthetic_imports()
        self.df_natgas = synthetic.generate_synthetic_natgas_imports()
        self.df_steo = synthetic.generate_synthetic_steo()
        self.scorecard = analysis.build_scorecard(self.df_imports, self.df_natgas, self.df_steo)
        self.actual = self.scorecard[~self.scorecard["is_forecast"]]

    def test_disruption_window_has_negative_composite(self) -> None:
        """Oct 2025 - Feb 2026 should show negative composite z-scores."""
        window = self.actual[
            (self.actual.index >= "2025-11-01") & (self.actual.index <= "2026-02-01")
        ]
        assert not window.empty, "No data in disruption window"
        avg_z = window["composite_gap_score"].mean()
        assert avg_z < 0, f"Disruption window avg z-score should be negative, got {avg_z:.2f}"

    def test_pre_disruption_near_zero(self) -> None:
        """Mid-2025 (before disruption) should have z-scores near zero."""
        pre = self.actual[(self.actual.index >= "2025-04-01") & (self.actual.index <= "2025-08-01")]
        if not pre.empty:
            avg_z = pre["composite_gap_score"].mean()
            assert abs(avg_z) < 1.5, f"Pre-disruption avg should be near zero, got {avg_z:.2f}"

    def test_composite_is_average_of_components(self) -> None:
        """Composite should equal (oil_z + natgas_z) / 2."""
        computed = (self.actual["oil_import_z"] + self.actual["natgas_import_z"]) / 2
        diff = (self.actual["composite_gap_score"] - computed).abs()
        assert diff.max() < 1e-10, "Composite doesn't match component average"

    def test_oil_and_natgas_have_overlapping_dates(self) -> None:
        """Both components should cover the same date range in the scorecard."""
        oil_dates = self.actual["oil_import_z"].dropna().index
        gas_dates = self.actual["natgas_import_z"].dropna().index
        assert oil_dates.equals(gas_dates), "Oil and natgas z-score dates don't align"


class TestScorecardSteoForecast:
    """Verify STEO forecast extension is physically sensible."""

    def setup_method(self) -> None:
        self.df_imports = synthetic.generate_synthetic_imports()
        self.df_natgas = synthetic.generate_synthetic_natgas_imports()
        self.df_steo = synthetic.generate_synthetic_steo()
        self.scorecard = analysis.build_scorecard(self.df_imports, self.df_natgas, self.df_steo)

    def test_forecast_dates_are_future(self) -> None:
        """All forecast rows should have dates after the last actual row."""
        actual = self.scorecard[~self.scorecard["is_forecast"]]
        forecast = self.scorecard[self.scorecard["is_forecast"]]
        if not forecast.empty and not actual.empty:
            assert forecast.index.min() > actual.index.max(), (
                "Forecast dates overlap with actual data"
            )

    def test_no_gap_between_actual_and_forecast(self) -> None:
        """Forecast should start within ~2 months of last actual date."""
        actual = self.scorecard[~self.scorecard["is_forecast"]]
        forecast = self.scorecard[self.scorecard["is_forecast"]]
        if not forecast.empty and not actual.empty:
            gap_days = (forecast.index.min() - actual.index.max()).days
            assert gap_days < 90, f"Gap between actual and forecast: {gap_days} days"

    def test_forecast_z_scores_bounded(self) -> None:
        """Forecast z-scores should not be extreme."""
        forecast = self.scorecard[self.scorecard["is_forecast"]]
        if not forecast.empty:
            z = forecast["composite_gap_score"].dropna()
            assert (z.abs() < 6).all(), f"Forecast z-scores extreme: [{z.min():.1f}, {z.max():.1f}]"


# ---------------------------------------------------------------------------
# Section 2: Days of supply arithmetic verification
# ---------------------------------------------------------------------------


class TestDaysOfSupplyArithmetic:
    """Verify DoS calculation produces correct arithmetic results."""

    def test_known_values(self) -> None:
        """Construct data where DoS = stocks / consumption is known exactly."""
        stocks = pd.DataFrame(
            {
                "date": [pd.Timestamp("2025-03-15")] * 2,
                "product": ["EPD0", "EPJK"],
                "product_name": ["Distillate", "Jet Fuel"],
                "value": [120_000.0, 45_000.0],
                "stock_type": "commercial",
            }
        )
        supplied = pd.DataFrame(
            {
                "date": [pd.Timestamp("2025-03-15")] * 2,
                "product": ["EPD0", "EPJK"],
                "product_name": ["Distillate", "Jet Fuel"],
                "value": [4000.0, 1500.0],  # MBBL/D
            }
        )
        dos = compute_days_of_supply(stocks, supplied)
        dist_dos = dos[dos["product"] == "EPD0"]["days_of_supply"].iloc[0]
        jet_dos = dos[dos["product"] == "EPJK"]["days_of_supply"].iloc[0]
        assert abs(dist_dos - 30.0) < 0.01, f"Distillate DoS: {dist_dos} (expected 30)"
        assert abs(jet_dos - 30.0) < 0.01, f"Jet DoS: {jet_dos} (expected 30)"

    def test_gasoline_mapping_works(self) -> None:
        """EPM0 stocks should be divided by EPM0F consumption."""
        stocks = pd.DataFrame(
            {
                "date": [pd.Timestamp("2025-03-15")],
                "product": ["EPM0"],
                "product_name": ["Total Gasoline"],
                "value": [240_000.0],
                "stock_type": "commercial",
            }
        )
        supplied = pd.DataFrame(
            {
                "date": [pd.Timestamp("2025-03-15")],
                "product": ["EPM0F"],
                "product_name": ["Finished Motor Gasoline"],
                "value": [8000.0],
            }
        )
        dos = compute_days_of_supply(stocks, supplied)
        assert not dos.empty, "Gasoline DoS should have data via EPM0→EPM0F mapping"
        gas_dos = dos[dos["product"] == "EPM0"]["days_of_supply"].iloc[0]
        assert abs(gas_dos - 30.0) < 0.01, f"Gasoline DoS: {gas_dos} (expected 30)"

    def test_zero_consumption_produces_nan(self) -> None:
        """Zero consumption should produce NaN, not inf."""
        stocks = pd.DataFrame(
            {
                "date": [pd.Timestamp("2025-03-15")],
                "product": ["EPD0"],
                "product_name": ["Distillate"],
                "value": [120_000.0],
                "stock_type": "commercial",
            }
        )
        supplied = pd.DataFrame(
            {
                "date": [pd.Timestamp("2025-03-15")],
                "product": ["EPD0"],
                "product_name": ["Distillate"],
                "value": [0.0],
            }
        )
        dos = compute_days_of_supply(stocks, supplied)
        if not dos.empty:
            assert dos["days_of_supply"].isna().all(), "Zero consumption should give NaN, not inf"

    def test_synthetic_dos_matches_manual(self) -> None:
        """Spot-check synthetic DoS against manual calculation."""
        data = generate_synthetic_inventory()
        dos = compute_days_of_supply(data["stocks"], data["supplied"])
        # Pick distillate — should be stocks ~120K / consumption ~3600 ≈ 33 days
        dist = dos[dos["product"] == "EPD0"]["days_of_supply"].median()
        assert 20 < dist < 50, f"Distillate DoS median {dist:.1f} outside [20, 50]"


# ---------------------------------------------------------------------------
# Section 3: Seasonal comparison edge cases
# ---------------------------------------------------------------------------


class TestSeasonalComparisonEdgeCases:
    """Test seasonal comparison with tricky data shapes."""

    def test_less_than_5_years_history(self) -> None:
        """Should still work with <5 years, just fewer comparison points."""
        data = generate_synthetic_inventory()
        # Trim to 2 years
        recent = data["stocks"][data["stocks"]["date"] >= "2024-01-01"]
        result = compute_seasonal_comparison(recent, years_back=5)
        # Should not crash; may have limited or NaN avg_5yr
        assert isinstance(result, pd.DataFrame)

    def test_deviation_sigma_distribution(self) -> None:
        """Deviation sigma should be roughly normally distributed for synthetic data."""
        data = generate_synthetic_inventory()
        result = compute_seasonal_comparison(data["stocks"])
        sigma = result["deviation_sigma"].dropna()
        if len(sigma) > 10:
            # Most values should be within ±3 sigma
            within_3 = (sigma.abs() < 3).mean()
            assert within_3 > 0.8, f"Only {within_3:.0%} within 3 sigma"


# ---------------------------------------------------------------------------
# Section 4: SPR consistency
# ---------------------------------------------------------------------------


class TestSprConsistency:
    """Verify SPR + commercial = total, and SPR share is derived correctly."""

    def test_spr_plus_commercial_equals_total(self) -> None:
        data = generate_synthetic_inventory()
        spr = compute_spr_status(data["stocks"])
        valid = spr.dropna()
        computed_total = valid["spr_mbbl"] + valid["commercial_mbbl"]
        diff = (computed_total - valid["total_mbbl"]).abs()
        assert diff.max() < 1.0, "SPR + Commercial != Total"

    def test_spr_share_matches_values(self) -> None:
        data = generate_synthetic_inventory()
        spr = compute_spr_status(data["stocks"])
        valid = spr.dropna()
        computed_pct = valid["spr_mbbl"] / valid["total_mbbl"] * 100
        diff = (computed_pct - valid["spr_pct"]).abs()
        assert diff.max() < 0.01, "SPR share doesn't match computed percentage"


# ---------------------------------------------------------------------------
# Section 5: Cross-dataset consistency
# ---------------------------------------------------------------------------


class TestCrossDatasetConsistency:
    """Verify relationships between different datasets hold."""

    def test_gross_imports_exceed_net(self) -> None:
        """Our gross imports should always exceed STEO net imports."""
        df_imports = synthetic.generate_synthetic_imports()
        df_steo = synthetic.generate_synthetic_steo()

        # Gross: monthly MBBL total → daily million bbl/d
        monthly = df_imports.groupby("date")["value"].sum()
        gross_daily = monthly / 30 / 1000  # MBBL/mo → million bbl/d

        # Net: STEO CONIPUS
        net = df_steo[df_steo["series_id"] == "CONIPUS"].set_index("date")["value"]

        # Compare on overlapping dates
        common = gross_daily.index.intersection(net.index)
        if len(common) > 0:
            for d in common:
                assert gross_daily[d] > net[d], (
                    f"Gross ({gross_daily[d]:.2f}) should exceed net ({net[d]:.2f}) on {d}"
                )

    def test_steo_production_exceeds_imports(self) -> None:
        """US production should exceed net imports (US is a net producer)."""
        df_steo = synthetic.generate_synthetic_steo()
        prod = df_steo[df_steo["series_id"] == "COPRPUS"]["value"]
        imports = df_steo[df_steo["series_id"] == "CONIPUS"]["value"]
        assert prod.mean() > imports.mean(), "US production should exceed net imports"

    def test_world_production_exceeds_us(self) -> None:
        """World production should be ~8x US production."""
        df_steo = synthetic.generate_synthetic_steo()
        world = df_steo[df_steo["series_id"] == "PAPR_WORLD"]["value"].mean()
        us = df_steo[df_steo["series_id"] == "COPRPUS"]["value"].mean()
        ratio = world / us
        assert 5 < ratio < 12, f"World/US production ratio {ratio:.1f} (expected 7-9x)"

    def test_stock_changes_bounded(self) -> None:
        """Week-over-week stock changes should not exceed 10% of total."""
        data = generate_synthetic_inventory()
        stocks = data["stocks"][data["stocks"]["stock_type"] == "commercial"]
        for product in stocks["product"].unique():
            sub = stocks[stocks["product"] == product].sort_values("date")
            if len(sub) < 2:
                continue
            pct_change = sub["value"].pct_change().dropna().abs()
            max_change = pct_change.max()
            assert max_change < 0.10, f"{product} has {max_change:.1%} week-over-week change (>10%)"


# ---------------------------------------------------------------------------
# Section 6: Input data robustness
# ---------------------------------------------------------------------------


class TestInputDataRobustness:
    """Test behavior with messy, incomplete, or edge-case input data."""

    def test_duplicate_rows_in_imports(self) -> None:
        """Duplicate rows should not cause scorecard to blow up."""
        df = synthetic.generate_synthetic_imports()
        # Double every row
        df_dup = pd.concat([df, df], ignore_index=True)
        df_ng = synthetic.generate_synthetic_natgas_imports()
        sc = analysis.build_scorecard(df_dup, df_ng)
        # Should still produce bounded z-scores (duplicates inflate groupby sum)
        assert isinstance(sc, pd.DataFrame)
        actual = sc[~sc["is_forecast"]]
        if not actual.empty:
            # Z-scores should still be finite
            z = actual["composite_gap_score"].dropna()
            assert not z.isin([np.inf, -np.inf]).any()

    def test_missing_padd_in_one_period(self) -> None:
        """Missing a PADD in one month should not crash the scorecard."""
        df = synthetic.generate_synthetic_imports()
        # Drop all PADD 4 data for one month
        mask = (df["duoarea"] == "PADD 4") & (df["date"] == df["date"].min())
        df_gap = df[~mask]
        df_ng = synthetic.generate_synthetic_natgas_imports()
        sc = analysis.build_scorecard(df_gap, df_ng)
        assert isinstance(sc, pd.DataFrame)

    def test_out_of_order_dates(self) -> None:
        """Shuffled date order should produce same scorecard."""
        df = synthetic.generate_synthetic_imports()
        df_shuffled = df.sample(frac=1, random_state=42)
        df_ng = synthetic.generate_synthetic_natgas_imports()
        sc_normal = analysis.build_scorecard(df, df_ng)
        sc_shuffled = analysis.build_scorecard(df_shuffled, df_ng)
        actual_n = sc_normal[~sc_normal["is_forecast"]]
        actual_s = sc_shuffled[~sc_shuffled["is_forecast"]]
        pd.testing.assert_frame_equal(actual_n, actual_s)

    def test_negative_stock_values_dont_crash(self) -> None:
        """Negative values (data error) should not cause DoS to crash."""
        stocks = pd.DataFrame(
            {
                "date": [pd.Timestamp("2025-03-15")],
                "product": ["EPD0"],
                "product_name": ["Distillate"],
                "value": [-5000.0],  # bad data
                "stock_type": "commercial",
            }
        )
        supplied = pd.DataFrame(
            {
                "date": [pd.Timestamp("2025-03-15")],
                "product": ["EPD0"],
                "product_name": ["Distillate"],
                "value": [3600.0],
            }
        )
        dos = compute_days_of_supply(stocks, supplied)
        # Should not crash; may produce negative DoS
        assert isinstance(dos, pd.DataFrame)

    def test_empty_imports_returns_empty_scorecard(self) -> None:
        """Empty imports should not crash."""
        df_empty = pd.DataFrame(columns=["date", "duoarea", "value"])
        df_ng = synthetic.generate_synthetic_natgas_imports()
        sc = analysis.build_scorecard(df_empty, df_ng)
        assert isinstance(sc, pd.DataFrame)


# ---------------------------------------------------------------------------
# Section 7: Order of magnitude dimensional analysis
# ---------------------------------------------------------------------------


class TestDimensionalAnalysis:
    """Verify unit conversions and dimensional consistency across the pipeline."""

    def test_import_mbbl_to_daily_mbd(self) -> None:
        """Monthly MBBL / 30 / 1000 should give reasonable million bbl/d."""
        df = synthetic.generate_synthetic_imports()
        monthly = df.groupby("date")["value"].sum()
        daily_mbd = monthly / 30 / 1000
        assert daily_mbd.between(4.0, 9.0).all(), (
            f"Daily rate [{daily_mbd.min():.1f}, {daily_mbd.max():.1f}] outside [4, 9] M bbl/d"
        )

    def test_natgas_bcf_in_range(self) -> None:
        """Total natgas imports should be 200-400 Bcf/month."""
        df = synthetic.generate_synthetic_natgas_imports()
        monthly = df.groupby("date")["value_bcf"].sum()
        assert monthly.between(150, 450).all(), (
            f"NatGas total [{monthly.min():.0f}, {monthly.max():.0f}] outside [150, 450] Bcf"
        )

    def test_steo_units_are_million_bbl_d(self) -> None:
        """All STEO values should be in million bbl/d scale."""
        df = synthetic.generate_synthetic_steo()
        for sid, (lo, hi) in {
            "CONIPUS": (0.3, 5),
            "COPRPUS": (11, 16),
            "PAPR_WORLD": (95, 120),
        }.items():
            vals = df[df["series_id"] == sid]["value"]
            assert vals.between(lo, hi).all(), (
                f"{sid} [{vals.min():.1f}, {vals.max():.1f}] outside [{lo}, {hi}]"
            )

    def test_dos_range_by_product(self) -> None:
        """Days of supply should be in product-specific ranges."""
        data = generate_synthetic_inventory()
        dos = compute_days_of_supply(data["stocks"], data["supplied"])
        expected_ranges = {
            "EPM0": (15, 40),  # total gasoline
            "EPD0": (20, 50),  # distillate
            "EPJK": (18, 45),  # jet fuel
            "EPLLPZ": (30, 120),  # propane (highly seasonal)
        }
        for prod, (lo, hi) in expected_ranges.items():
            sub = dos[dos["product"] == prod]["days_of_supply"].dropna()
            if not sub.empty:
                median = sub.median()
                assert lo <= median <= hi, f"{prod} median DoS {median:.1f} outside [{lo}, {hi}]"

    def test_breakeven_plus_margin_equals_wti(self) -> None:
        """Breakeven + margin should equal the WTI reference price."""
        df_be = synthetic.generate_synthetic_breakevens()
        status = analysis.compute_breakeven_status(df_be, wti_price=70.0)
        for _, row in status.iterrows():
            computed_wti = row["breakeven_usd_bbl"] + row["margin_usd_bbl"]
            assert abs(computed_wti - 70.0) < 0.01, (
                f"{row['basin']}: breakeven + margin = {computed_wti}, expected 70.0"
            )

    def test_production_at_risk_sums_correctly(self) -> None:
        """At extreme prices, production at risk should match expectations."""
        df_be = synthetic.generate_synthetic_breakevens()
        df_dpr = synthetic.generate_synthetic_dpr()
        curve = analysis.production_at_risk_curve(df_be, df_dpr, wti_range=(20, 120))

        # At $120, all basins profitable → 0% at risk
        at_120 = curve[curve["wti_price"] == 120.0]
        if not at_120.empty:
            assert at_120.iloc[0]["pct_at_risk"] == 0, "At $120 WTI, no basins should be at risk"

        # At $20, most basins at risk → >50% at risk
        at_20 = curve[curve["wti_price"] == 20.0]
        if not at_20.empty:
            assert at_20.iloc[0]["pct_at_risk"] > 50, (
                "At $20 WTI, most production should be at risk"
            )
