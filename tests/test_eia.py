"""Tests for EIA API client — URL construction and response parsing."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from commodity_flow import eia


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
