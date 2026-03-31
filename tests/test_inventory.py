"""Tests for inventory analytics module."""

from commodity_flow.inventory import (
    compute_days_of_supply,
    compute_seasonal_comparison,
    compute_spr_status,
    generate_offline_inventory,
)


class TestOfflineInventory:
    def setup_method(self) -> None:
        self.data = generate_offline_inventory()

    def test_returns_stocks_and_supplied(self) -> None:
        assert "stocks" in self.data
        assert "supplied" in self.data

    def test_stocks_has_products(self) -> None:
        products = set(self.data["stocks"]["product"].unique())
        assert "EPC0" in products  # crude
        assert "EPM0" in products  # total gasoline
        assert "EPD0" in products  # distillate

    def test_stocks_has_spr(self) -> None:
        types = set(self.data["stocks"]["stock_type"].unique())
        assert "spr" in types
        assert "commercial" in types

    def test_supplied_has_products(self) -> None:
        products = set(self.data["supplied"]["product"].unique())
        assert "EPM0F" in products
        assert "EPP0" in products  # total petroleum

    def test_stocks_values_positive(self) -> None:
        assert (self.data["stocks"]["value"] > 0).all()

    def test_supplied_values_positive(self) -> None:
        assert (self.data["supplied"]["value"] > 0).all()


class TestDaysOfSupply:
    def setup_method(self) -> None:
        data = generate_offline_inventory()
        self.dos = compute_days_of_supply(data["stocks"], data["supplied"])

    def test_returns_days_column(self) -> None:
        assert "days_of_supply" in self.dos.columns

    def test_days_in_reasonable_range(self) -> None:
        """Days of supply should be 10-120 for most products."""
        valid = self.dos["days_of_supply"].dropna()
        assert valid.between(5, 200).mean() > 0.9

    def test_has_multiple_products(self) -> None:
        assert self.dos["product"].nunique() >= 3


class TestSeasonalComparison:
    def setup_method(self) -> None:
        data = generate_offline_inventory()
        self.seasonal = compute_seasonal_comparison(data["stocks"])

    def test_has_deviation_columns(self) -> None:
        assert "deviation_pct" in self.seasonal.columns
        assert "avg_5yr" in self.seasonal.columns
        assert "current" in self.seasonal.columns

    def test_deviation_bounded(self) -> None:
        """Deviations should be within +-50% for offline data."""
        valid = self.seasonal["deviation_pct"].dropna()
        if not valid.empty:
            assert valid.abs().mean() < 50


class TestSprStatus:
    def setup_method(self) -> None:
        data = generate_offline_inventory()
        self.spr = compute_spr_status(data["stocks"])

    def test_has_spr_and_commercial(self) -> None:
        assert "spr_mbbl" in self.spr.columns
        assert "commercial_mbbl" in self.spr.columns
        assert "spr_pct" in self.spr.columns

    def test_spr_pct_bounded(self) -> None:
        valid = self.spr["spr_pct"].dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_spr_positive(self) -> None:
        assert (self.spr["spr_mbbl"].dropna() > 0).all()

    def test_no_duplicate_dates(self) -> None:
        """Each date should appear exactly once — no double-counting from total rows."""
        assert not self.spr["date"].duplicated().any(), "Duplicate dates in SPR status"

    def test_spr_plus_commercial_equals_total(self) -> None:
        valid = self.spr.dropna()
        diff = (valid["spr_mbbl"] + valid["commercial_mbbl"] - valid["total_mbbl"]).abs()
        assert diff.max() < 1.0, f"SPR + Commercial != Total (max diff: {diff.max()})"

    def test_spr_magnitude_is_mbbl(self) -> None:
        """SPR should be in MBBL (~300K-700K range), not barrels or millions."""
        median_spr = self.spr["spr_mbbl"].dropna().median()
        assert 200_000 < median_spr < 800_000, (
            f"SPR median {median_spr:,.0f} — expected 200K-800K MBBL"
        )
