"""Tests for plotly chart functions."""

import plotly.graph_objects as go

from commodity_flow import analysis, charts, offline
from commodity_flow.inventory import (
    compute_days_of_supply,
    compute_spr_status,
    generate_offline_inventory,
)


def _make_fixtures():
    """Build all data fixtures for chart tests."""
    df_imports = offline.generate_offline_imports()
    df_natgas = offline.generate_offline_natgas_imports()
    df_steo = offline.generate_offline_steo()
    df_breakevens = offline.generate_offline_breakevens()
    df_dpr = offline.generate_offline_dpr()
    scorecard = analysis.build_scorecard(df_imports, df_natgas, df_steo)
    current_wti = 70.0
    status = analysis.compute_breakeven_status(df_breakevens, current_wti)
    risk_curve = analysis.production_at_risk_curve(df_breakevens, df_dpr)
    inv = generate_offline_inventory()
    df_dos = compute_days_of_supply(inv["stocks"], inv["supplied"])
    df_spr = compute_spr_status(inv["stocks"])
    return {
        "scorecard": scorecard,
        "status": status,
        "risk_curve": risk_curve,
        "current_wti": current_wti,
        "df_dos": df_dos,
        "df_spr": df_spr,
        "df_imports": df_imports,
        "df_dpr": df_dpr,
    }


class TestPlotFunctionsReturnFigure:
    """Every plot function should return a plotly Figure."""

    def setup_method(self) -> None:
        self.f = _make_fixtures()

    def test_plot_scorecard(self) -> None:
        fig = charts.plot_scorecard(self.f["scorecard"])
        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 3  # oil, natgas, composite

    def test_plot_elasticity_curve(self) -> None:
        fig = charts.plot_elasticity_curve(self.f["risk_curve"], self.f["current_wti"])
        assert isinstance(fig, go.Figure)

    def test_plot_days_of_supply(self) -> None:
        fig = charts.plot_days_of_supply(self.f["df_dos"])
        assert isinstance(fig, go.Figure)

    def test_plot_spr_status(self) -> None:
        fig = charts.plot_spr_status(self.f["df_spr"])
        assert isinstance(fig, go.Figure)

    def test_plot_basin_breakevens(self) -> None:
        fig = charts.plot_basin_breakevens(self.f["status"], self.f["current_wti"])
        assert isinstance(fig, go.Figure)

    def test_plot_risk_dashboard(self) -> None:
        fig = charts.plot_risk_dashboard(
            self.f["scorecard"],
            self.f["status"],
            self.f["df_spr"],
            self.f["df_dos"],
            self.f["current_wti"],
        )
        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 3  # at least scorecard, basins, DoS


class TestSignalTable:
    def setup_method(self) -> None:
        self.f = _make_fixtures()

    def test_returns_dataframe(self) -> None:
        table = charts.build_signal_table(
            self.f["scorecard"],
            self.f["df_imports"],
            self.f["df_dos"],
            self.f["df_spr"],
            self.f["status"],
            self.f["df_dpr"],
        )
        assert "Signal" in table.columns
        assert "Status" in table.columns
        assert len(table) >= 4  # at least gap, DoS, SPR, basins

    def test_status_values_are_valid(self) -> None:
        table = charts.build_signal_table(
            self.f["scorecard"],
            self.f["df_imports"],
            self.f["df_dos"],
            self.f["df_spr"],
            self.f["status"],
            self.f["df_dpr"],
        )
        valid_prefixes = ["\U0001f534", "\u26a0\ufe0f", "\u2705"]
        for status_val in table["Status"]:
            assert any(status_val.startswith(p) for p in valid_prefixes), (
                f"Invalid status: {status_val}"
            )
