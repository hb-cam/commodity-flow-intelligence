"""Tests for EIA API client — URL construction and response parsing."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from commodity_flow import eia
from commodity_flow.eia import _normalize_padd_columns


class TestFetchEiaData:
    @patch("commodity_flow.eia.requests.get")
    def test_successful_response(self, mock_get: MagicMock) -> None:
        mock_get.return_value.json.return_value = {
            "response": {
                "data": [
                    {"period": "2024-01", "value": "100"},
                    {"period": "2024-02", "value": "105"},
                ]
            }
        }
        mock_get.return_value.raise_for_status = MagicMock()

        df = eia.fetch_eia_data("test/route", {}, "test-key")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    @patch("commodity_flow.eia.requests.get")
    def test_passes_api_key(self, mock_get: MagicMock) -> None:
        mock_get.return_value.json.return_value = {"response": {"data": []}}
        mock_get.return_value.raise_for_status = MagicMock()

        eia.fetch_eia_data("test/route", {"foo": "bar"}, "my-key")
        call_args = mock_get.call_args
        assert call_args[1]["params"]["api_key"] == "my-key"
        assert call_args[1]["params"]["foo"] == "bar"

    @patch("commodity_flow.eia.requests.get")
    def test_unexpected_response_raises(self, mock_get: MagicMock) -> None:
        mock_get.return_value.json.return_value = {"error": "bad request"}
        mock_get.return_value.raise_for_status = MagicMock()

        with pytest.raises(ValueError, match="Unexpected"):
            eia.fetch_eia_data("test/route", {}, "key")

    @patch("commodity_flow.eia.requests.get")
    def test_url_construction(self, mock_get: MagicMock) -> None:
        mock_get.return_value.json.return_value = {"response": {"data": []}}
        mock_get.return_value.raise_for_status = MagicMock()

        eia.fetch_eia_data("petroleum/move/imp", {}, "key")
        url = mock_get.call_args[0][0]
        assert url == "https://api.eia.gov/v2/petroleum/move/imp/data/"


class TestNormalizePaddColumns:
    def test_maps_region_name_to_padd(self) -> None:
        df = pd.DataFrame(
            {
                "area-name": ["Midwest", "Gulf Coast", "East Coast"],
                "period": ["2025-01", "2025-01", "2025-01"],
                "value": ["100", "200", "50"],
            }
        )
        result = _normalize_padd_columns(df)
        assert list(result["duoarea"]) == ["PADD 2", "PADD 3", "PADD 1"]

    def test_maps_padd_name_to_padd(self) -> None:
        df = pd.DataFrame(
            {
                "area-name": ["PADD 4", "PADD 5"],
                "period": ["2025-01", "2025-01"],
                "value": ["10", "20"],
            }
        )
        result = _normalize_padd_columns(df)
        assert list(result["duoarea"]) == ["PADD 4", "PADD 5"]

    def test_parses_dates_and_values(self) -> None:
        df = pd.DataFrame(
            {
                "period": ["2025-01-15", "2025-02-01"],
                "value": ["12345", "67890"],
            }
        )
        result = _normalize_padd_columns(df)
        assert pd.api.types.is_datetime64_any_dtype(result["date"])
        assert pd.api.types.is_numeric_dtype(result["value"])

    def test_unknown_area_name_preserved(self) -> None:
        """Unknown area-name should not silently disappear."""
        df = pd.DataFrame(
            {
                "area-name": ["Unknown Region"],
                "duoarea": ["X99"],
                "period": ["2025-01"],
                "value": ["100"],
            }
        )
        result = _normalize_padd_columns(df)
        # fillna falls back to original duoarea
        assert result["duoarea"].iloc[0] == "X99"


class TestSteoColumnRename:
    @patch("commodity_flow.eia.requests.get")
    def test_camel_case_renamed(self, mock_get: MagicMock) -> None:
        """Live EIA returns 'seriesId'; should be renamed to 'series_id'."""
        mock_get.return_value.json.return_value = {
            "response": {"data": [{"period": "2025-01", "seriesId": "CONIPUS", "value": "2.5"}]}
        }
        mock_get.return_value.raise_for_status = MagicMock()

        df = eia.fetch_steo_projections("key")
        assert "series_id" in df.columns
        assert "seriesId" not in df.columns


class TestDprNotImplemented:
    def test_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="not available"):
            eia.fetch_drilling_productivity("key")
