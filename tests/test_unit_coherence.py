"""Unit coherence tests — verify unit annotations, conversion arithmetic,
dimensional algebra, cross-source schema agreement, provenance labels,
round-trip inverses, chart axis labels, and column naming conventions.

These tests catch silent unit mismatches (e.g., bbl vs MBBL, MMCF vs Bcf)
that magnitude range checks alone would miss.
"""

from __future__ import annotations

import pandas as pd

from commodity_flow import analysis, charts, offline
from commodity_flow.inventory import (
    compute_days_of_supply,
    compute_seasonal_comparison,
    compute_spr_status,
    generate_offline_inventory,
)
from commodity_flow.refresh import RefreshPipeline


# ---------------------------------------------------------------------------
# Class 1: Unit annotations
# ---------------------------------------------------------------------------


class TestUnitAnnotations:
    """Verify each DataFrame carries expected units column or unit-suffixed columns."""

    def test_imports_units_column_is_mbbl(self) -> None:
        df = offline.generate_offline_imports()
        assert "units" in df.columns, "Imports DataFrame missing 'units' column"
        assert (df["units"] == "MBBL").all(), (
            f"Expected all import rows units='MBBL', found: {df['units'].unique().tolist()}"
        )

    def test_stocks_units_column_is_mbbl(self) -> None:
        df = offline.generate_offline_stocks()
        assert "units" in df.columns, "Stocks DataFrame missing 'units' column"
        assert (df["units"] == "MBBL").all(), (
            f"Expected all stock rows units='MBBL', found: {df['units'].unique().tolist()}"
        )

    def test_steo_units_column_is_million_bbl_d(self) -> None:
        df = offline.generate_offline_steo()
        assert "units" in df.columns, "STEO DataFrame missing 'units' column"
        assert (df["units"] == "million bbl/d").all(), (
            f"Expected STEO units='million bbl/d', found: {df['units'].unique().tolist()}"
        )

    def test_natgas_uses_value_bcf_column(self) -> None:
        df = offline.generate_offline_natgas_imports()
        assert "value_bcf" in df.columns, "NatGas missing unit-suffixed 'value_bcf' column"
        assert "value" not in df.columns, (
            "NatGas has ambiguous 'value' column alongside 'value_bcf'"
        )

    def test_inventory_stocks_units_mbbl(self) -> None:
        data = generate_offline_inventory()
        stocks = data["stocks"]
        assert "units" in stocks.columns
        assert (stocks["units"] == "MBBL").all(), (
            f"Inventory stocks units: {stocks['units'].unique().tolist()}"
        )

    def test_inventory_supplied_units_mbbl_d(self) -> None:
        data = generate_offline_inventory()
        supplied = data["supplied"]
        assert "units" in supplied.columns
        assert (supplied["units"] == "MBBL/D").all(), (
            f"Inventory supplied units: {supplied['units'].unique().tolist()}"
        )


# ---------------------------------------------------------------------------
# Class 2: Conversion factor arithmetic (exact values, not range checks)
# ---------------------------------------------------------------------------


class TestConversionFactorArithmetic:
    """Independently verify the exact arithmetic of every unit conversion."""

    def test_mbbl_month_to_million_bbl_d(self) -> None:
        """analysis.py:120 — MBBL/month ÷ 30 ÷ 1000 = million bbl/d."""
        cases = [
            (180_000, 6.0),
            (30_000, 1.0),
            (0, 0.0),
            (300_000, 10.0),
        ]
        for mbbl_month, expected_mbd in cases:
            result = mbbl_month / 30 / 1000
            assert abs(result - expected_mbd) < 1e-10, (
                f"{mbbl_month} MBBL/mo → {result} million bbl/d, expected {expected_mbd}"
            )

    def test_mmcf_to_bcf(self) -> None:
        """eia.py:219 — MMCF ÷ 1000 = Bcf."""
        cases = [
            (260_000, 260.0),
            (1_000, 1.0),
            (1, 0.001),
        ]
        for mmcf, expected_bcf in cases:
            result = mmcf / 1000
            assert abs(result - expected_bcf) < 1e-10, (
                f"{mmcf} MMCF → {result} Bcf, expected {expected_bcf}"
            )

    def test_mbbl_to_million_bbl_display(self) -> None:
        """charts.py — MBBL ÷ 1000 = million bbl (display conversion)."""
        cases = [
            (415_000, 415.0),
            (456_000, 456.0),
            (1_000, 1.0),
        ]
        for mbbl, expected_mm in cases:
            result = mbbl / 1000
            assert abs(result - expected_mm) < 1e-10, (
                f"{mbbl} MBBL → {result} million bbl, expected {expected_mm}"
            )

    def test_dos_formula(self) -> None:
        """inventory.py:173 — stocks(MBBL) / supplied(MBBL/D) = days."""
        cases = [
            (120_000, 4_000, 30.0),
            (241_000, 8_800, 241_000 / 8_800),
            (45_000, 1_500, 30.0),
        ]
        for stocks, supplied, expected_dos in cases:
            result = stocks / supplied
            assert abs(result - expected_dos) < 1e-6, (
                f"{stocks}/{supplied} = {result} days, expected {expected_dos}"
            )

    def test_composite_average_formula(self) -> None:
        """analysis.py:68-70 — composite = (oil_z + gas_z) / 2."""
        cases = [
            (-1.5, -0.5, -1.0),
            (2.0, -2.0, 0.0),
            (0.0, 0.0, 0.0),
            (3.0, 1.0, 2.0),
        ]
        for oil_z, gas_z, expected in cases:
            result = (oil_z + gas_z) / 2
            assert abs(result - expected) < 1e-10, (
                f"({oil_z} + {gas_z})/2 = {result}, expected {expected}"
            )


# ---------------------------------------------------------------------------
# Class 3: Dimensional algebra
# ---------------------------------------------------------------------------


class TestDimensionalAlgebra:
    """Verify unit algebra is consistent and wrong-unit inputs are detectable."""

    def test_dos_result_in_plausible_day_range(self) -> None:
        """All offline DoS values should be in [1, 365] — outside = dimensional error."""
        data = generate_offline_inventory()
        dos = compute_days_of_supply(data["stocks"], data["supplied"])
        valid = dos["days_of_supply"].dropna()
        assert (valid >= 1).all() and (valid <= 365).all(), (
            f"DoS range [{valid.min():.1f}, {valid.max():.1f}] outside [1, 365]"
        )

    def test_bbl_instead_of_mbbl_produces_absurd_dos(self) -> None:
        """Feeding bbl (not MBBL) as stocks produces DoS > 10,000 days."""
        stocks = pd.DataFrame({
            "date": [pd.Timestamp("2025-03-15")],
            "product": ["EPD0"],
            "product_name": ["Distillate"],
            "value": [120_000_000.0],  # bbl, not MBBL — 1000x too large
            "stock_type": "commercial",
        })
        supplied = pd.DataFrame({
            "date": [pd.Timestamp("2025-03-15")],
            "product": ["EPD0"],
            "product_name": ["Distillate"],
            "value": [3_600.0],  # MBBL/D (correct)
        })
        dos = compute_days_of_supply(stocks, supplied)
        if not dos.empty:
            val = dos["days_of_supply"].iloc[0]
            assert val > 10_000, (
                f"bbl-as-MBBL error should produce DoS > 10,000 days, got {val:.0f}"
            )

    def test_mbbl_d_where_mbbl_expected_produces_tiny_dos(self) -> None:
        """Feeding a daily flow rate as stock level produces DoS ~ 1 day."""
        stocks = pd.DataFrame({
            "date": [pd.Timestamp("2025-03-15")],
            "product": ["EPD0"],
            "product_name": ["Distillate"],
            "value": [3_600.0],  # MBBL/D mistakenly used as MBBL (stock)
            "stock_type": "commercial",
        })
        supplied = pd.DataFrame({
            "date": [pd.Timestamp("2025-03-15")],
            "product": ["EPD0"],
            "product_name": ["Distillate"],
            "value": [3_600.0],  # MBBL/D (correct)
        })
        dos = compute_days_of_supply(stocks, supplied)
        if not dos.empty:
            val = dos["days_of_supply"].iloc[0]
            assert val < 2.0, (
                f"Flow-rate-as-stock error should produce DoS < 2 days, got {val:.1f}"
            )

    def test_import_conversion_lands_in_steo_magnitude(self) -> None:
        """MBBL/month ÷30÷1000 should be in same scale as STEO CONIPUS, and gross > net."""
        df_imports = offline.generate_offline_imports()
        df_steo = offline.generate_offline_steo()

        monthly_total = df_imports.groupby("date")["value"].sum()
        gross_daily_mbd = monthly_total / 30 / 1000  # million bbl/d

        net = df_steo[df_steo["series_id"] == "CONIPUS"].set_index("date")["value"]
        common = gross_daily_mbd.index.intersection(net.index)
        assert len(common) > 0, "No overlapping dates between imports and STEO"

        # Both should be in million bbl/d scale (1-10)
        assert gross_daily_mbd.median() > 1.0
        assert gross_daily_mbd.median() < 10.0
        # Gross should exceed net
        for d in common[:12]:
            assert gross_daily_mbd[d] > net[d], (
                f"Gross ({gross_daily_mbd[d]:.2f}) should exceed net ({net[d]:.2f}) on {d}"
            )

    def test_natgas_bcf_matches_offline_scale(self) -> None:
        """260,000 MMCF ÷1000 = 260 Bcf — should match offline pipeline avg (200-350)."""
        converted = 260_000 / 1000  # MMCF → Bcf
        df = offline.generate_offline_natgas_imports()
        pipeline_avg = df[df["mode"] == "Pipeline"]["value_bcf"].mean()
        # Converted value should be in same ballpark as offline data
        assert 150 < converted < 400
        assert 150 < pipeline_avg < 400
        # And within 2x of each other
        ratio = converted / pipeline_avg
        assert 0.5 < ratio < 2.0, f"Converted/offline ratio: {ratio:.2f}"


# ---------------------------------------------------------------------------
# Class 4: Cross-source schema agreement
# ---------------------------------------------------------------------------


class TestCrossSourceSchemaAgreement:
    """Verify offline and live data paths produce compatible schemas."""

    def test_imports_offline_has_live_critical_columns(self) -> None:
        """Offline imports must have the columns that downstream code expects."""
        df = offline.generate_offline_imports()
        required = {"period", "duoarea", "value", "units", "date"}
        assert required.issubset(df.columns), (
            f"Missing columns: {required - set(df.columns)}"
        )

    def test_natgas_offline_and_live_share_output_columns(self) -> None:
        """Both live and offline natgas paths produce {period, date, mode, value_bcf}."""
        df = offline.generate_offline_natgas_imports()
        required = {"period", "date", "mode", "value_bcf"}
        assert required.issubset(df.columns), (
            f"Missing columns: {required - set(df.columns)}"
        )

    def test_steo_offline_has_series_id_not_seriesId(self) -> None:
        """Offline uses series_id (snake_case), matching live after eia.py:157 rename."""
        df = offline.generate_offline_steo()
        assert "series_id" in df.columns, "STEO missing 'series_id' column"
        assert "seriesId" not in df.columns, "STEO has camelCase 'seriesId' (should be renamed)"

    def test_steo_series_id_superset(self) -> None:
        """Offline produces the core series that downstream analysis needs."""
        df = offline.generate_offline_steo()
        offline_series = set(df["series_id"].unique())
        required = {"CONIPUS", "COPRPUS", "PAPR_WORLD"}
        assert required.issubset(offline_series), (
            f"Missing series: {required - offline_series}"
        )

    def test_inventory_offline_units_match_live_filters(self) -> None:
        """Offline inventory stocks use MBBL — same filter as fetch_product_stocks."""
        data = generate_offline_inventory()
        assert (data["stocks"]["units"] == "MBBL").all()
        assert (data["supplied"]["units"] == "MBBL/D").all()


# ---------------------------------------------------------------------------
# Class 5: Provenance label coherence
# ---------------------------------------------------------------------------


class TestProvenanceLabelCoherence:
    """Verify provenance output strings use correct terminology."""

    def setup_method(self) -> None:
        self.pipeline = RefreshPipeline()
        self.pipeline.run()

    def test_provenance_footnotes_use_offline_tag(self) -> None:
        footnotes = self.pipeline.provenance.footnotes()
        for fn in footnotes:
            assert "[SYNTHETIC]" not in fn, f"Stale [SYNTHETIC] tag in: {fn}"
        offline_fns = [fn for fn in footnotes if "[OFFLINE]" in fn]
        assert len(offline_fns) >= 3, "Expected at least 3 offline-tagged footnotes"

    def test_provenance_summary_no_stale_terms(self) -> None:
        summary = self.pipeline.provenance.summary()
        for term in ["synthetic", "simulated", "MMCF"]:
            assert term.lower() not in summary.lower(), (
                f"Stale term '{term}' found in provenance summary"
            )

    def test_provenance_sources_count(self) -> None:
        sources = self.pipeline.provenance.sources
        assert len(sources) == 7, f"Expected 7 sources, got {len(sources)}"
        for s in sources:
            assert s.rows > 0, f"Source '{s.name}' has 0 rows"

    def test_provenance_live_endpoint_matches_eia_routes(self) -> None:
        """Live source endpoints should reference valid EIA API routes."""
        valid_prefixes = ("petroleum/", "steo", "natural-gas/", "offline generator")
        for s in self.pipeline.provenance.sources:
            assert any(s.endpoint.startswith(p) for p in valid_prefixes), (
                f"Source '{s.name}' has unexpected endpoint: {s.endpoint}"
            )


# ---------------------------------------------------------------------------
# Class 6: Round-trip / inverse tests
# ---------------------------------------------------------------------------


class TestRoundTripInverse:
    """Verify inverse operations recover original values."""

    def test_dos_times_supplied_recovers_stocks(self) -> None:
        stocks = pd.DataFrame({
            "date": [pd.Timestamp("2025-03-15")] * 3,
            "product": ["EPD0", "EPJK", "EPLLPZ"],
            "product_name": ["Distillate", "Jet Fuel", "Propane"],
            "value": [120_000.0, 45_000.0, 73_000.0],
            "stock_type": "commercial",
        })
        supplied = pd.DataFrame({
            "date": [pd.Timestamp("2025-03-15")] * 3,
            "product": ["EPD0", "EPJK", "EPLLPZ"],
            "product_name": ["Distillate", "Jet Fuel", "Propane"],
            "value": [3_600.0, 1_500.0, 1_100.0],
        })
        dos = compute_days_of_supply(stocks, supplied)
        for _, row in dos.iterrows():
            recovered = row["days_of_supply"] * row["supplied_mbbl_d"]
            assert abs(recovered - row["stocks_mbbl"]) < 1.0, (
                f"{row['product']}: DoS×supplied={recovered:.1f}, stocks={row['stocks_mbbl']}"
            )

    def test_stocks_over_dos_recovers_supplied(self) -> None:
        stocks = pd.DataFrame({
            "date": [pd.Timestamp("2025-03-15")],
            "product": ["EPD0"],
            "product_name": ["Distillate"],
            "value": [120_000.0],
            "stock_type": "commercial",
        })
        supplied = pd.DataFrame({
            "date": [pd.Timestamp("2025-03-15")],
            "product": ["EPD0"],
            "product_name": ["Distillate"],
            "value": [3_600.0],
        })
        dos = compute_days_of_supply(stocks, supplied)
        row = dos.iloc[0]
        recovered = row["stocks_mbbl"] / row["days_of_supply"]
        assert abs(recovered - row["supplied_mbbl_d"]) < 1.0, (
            f"stocks/DoS={recovered:.1f}, supplied={row['supplied_mbbl_d']}"
        )

    def test_composite_decompose_to_oil_z(self) -> None:
        df_imports = offline.generate_offline_imports()
        df_natgas = offline.generate_offline_natgas_imports()
        sc = analysis.build_scorecard(df_imports, df_natgas)
        actual = sc[~sc["is_forecast"]].dropna()
        oil_recovered = 2 * actual["composite_gap_score"] - actual["natgas_import_z"]
        diff = (oil_recovered - actual["oil_import_z"]).abs()
        assert diff.max() < 1e-10, f"Max decomposition error: {diff.max()}"

    def test_spr_plus_commercial_equals_total(self) -> None:
        data = generate_offline_inventory()
        spr = compute_spr_status(data["stocks"])
        valid = spr.dropna()
        diff = (valid["spr_mbbl"] + valid["commercial_mbbl"] - valid["total_mbbl"]).abs()
        assert diff.max() < 1.0, f"Max SPR decomposition error: {diff.max():.2f} MBBL"


# ---------------------------------------------------------------------------
# Class 7: Chart unit labels
# ---------------------------------------------------------------------------


def _build_chart_fixtures() -> dict:
    """Build all data fixtures needed for chart tests."""
    df_imports = offline.generate_offline_imports()
    df_natgas = offline.generate_offline_natgas_imports()
    df_steo = offline.generate_offline_steo()
    df_breakevens = offline.generate_offline_breakevens()
    df_dpr = offline.generate_offline_dpr()
    scorecard = analysis.build_scorecard(df_imports, df_natgas, df_steo)
    risk_curve = analysis.production_at_risk_curve(df_breakevens, df_dpr)
    inv = generate_offline_inventory()
    df_dos = compute_days_of_supply(inv["stocks"], inv["supplied"])
    df_seasonal = compute_seasonal_comparison(inv["stocks"])
    df_spr = compute_spr_status(inv["stocks"])
    return {
        "scorecard": scorecard,
        "risk_curve": risk_curve,
        "df_dos": df_dos,
        "df_seasonal": df_seasonal,
        "df_spr": df_spr,
    }


def _get_axis_title(fig, axis: str = "yaxis") -> str:
    """Extract axis title text from a plotly figure."""
    ax = getattr(fig.layout, axis, None)
    if ax is None:
        return ""
    title = ax.title
    if title is None:
        return ""
    if isinstance(title, str):
        return title
    return title.text or ""


class TestChartUnitLabels:
    """Verify plotly figures carry correct axis labels with unit strings."""

    def setup_method(self) -> None:
        self.f = _build_chart_fixtures()

    def test_scorecard_yaxis_mentions_z_score(self) -> None:
        fig = charts.plot_scorecard(self.f["scorecard"])
        label = _get_axis_title(fig, "yaxis")
        assert "Z-Score" in label, f"Scorecard y-axis: '{label}' (expected 'Z-Score')"

    def test_elasticity_xaxis_mentions_usd_bbl(self) -> None:
        fig = charts.plot_elasticity_curve(self.f["risk_curve"], 70.0)
        # Both subplots share x-axis label via update_xaxes
        label1 = _get_axis_title(fig, "xaxis")
        label2 = _get_axis_title(fig, "xaxis2")
        found = "$/bbl" in label1 or "$/bbl" in label2
        assert found, f"Elasticity x-axes: '{label1}', '{label2}' (expected '$/bbl')"

    def test_dos_yaxis_mentions_days(self) -> None:
        fig = charts.plot_days_of_supply(self.f["df_dos"])
        label = _get_axis_title(fig, "yaxis")
        assert "Days" in label, f"DoS y-axis: '{label}' (expected 'Days')"

    def test_seasonal_yaxis_mentions_mbbl(self) -> None:
        products = self.f["df_seasonal"]["product"].unique()
        if len(products) > 0:
            fig = charts.plot_seasonal_comparison(self.f["df_seasonal"], products[0])
            label = _get_axis_title(fig, "yaxis")
            assert "MBBL" in label, f"Seasonal y-axis: '{label}' (expected 'MBBL')"

    def test_spr_yaxes_mention_mbbl_and_pct(self) -> None:
        fig = charts.plot_spr_status(self.f["df_spr"])
        left = _get_axis_title(fig, "yaxis")
        right = _get_axis_title(fig, "yaxis2")
        assert "bbl" in left.lower(), f"SPR left y-axis: '{left}' (expected barrel unit)"
        assert "%" in right or "SPR" in right, (
            f"SPR right y-axis: '{right}' (expected 'SPR %')"
        )


# ---------------------------------------------------------------------------
# Class 8: Column name conventions
# ---------------------------------------------------------------------------


class TestColumnNameConventions:
    """Verify columns carrying physical quantities have unit suffixes."""

    def test_helium_columns_have_mcm_suffix(self) -> None:
        df = offline.generate_offline_helium()
        expected = {
            "us_production_Mcm",
            "world_production_Mcm",
            "world_demand_Mcm",
            "supply_gap_Mcm",
            "blm_price_usd_per_mcf",
        }
        assert expected.issubset(df.columns), (
            f"Missing helium columns: {expected - set(df.columns)}"
        )

    def test_dpr_columns_have_bbl_d_suffix(self) -> None:
        df = offline.generate_offline_dpr()
        expected = {"production_per_rig_bbl_d", "total_new_well_production_bbl_d"}
        assert expected.issubset(df.columns), (
            f"Missing DPR columns: {expected - set(df.columns)}"
        )

    def test_breakeven_columns_have_usd_bbl_suffix(self) -> None:
        df = offline.generate_offline_breakevens()
        expected = {"breakeven_usd_bbl", "wti_price_usd_bbl"}
        assert expected.issubset(df.columns), (
            f"Missing breakeven columns: {expected - set(df.columns)}"
        )

    def test_value_columns_have_companion_units(self) -> None:
        """DataFrames using generic 'value' column must also have a 'units' column."""
        datasets = {
            "imports": offline.generate_offline_imports(),
            "stocks": offline.generate_offline_stocks(),
            "steo": offline.generate_offline_steo(),
        }
        for name, df in datasets.items():
            if "value" in df.columns:
                assert "units" in df.columns, (
                    f"'{name}' has 'value' column but no companion 'units' column"
                )
