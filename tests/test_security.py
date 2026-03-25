"""Security tests — input validation, credential hygiene, malformed data handling."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from commodity_flow.ais import _parse_position_report


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestCredentialHygiene:
    """Verify no secrets leak into tracked files."""

    def test_env_example_has_no_real_values(self) -> None:
        env_example = PROJECT_ROOT / ".env.example"
        content = env_example.read_text()
        for line in content.strip().splitlines():
            if "=" in line:
                key, val = line.split("=", 1)
                assert val.strip() in ("", "false"), f".env.example has non-empty value for {key}"

    def test_gitignore_covers_secrets(self) -> None:
        gitignore = (PROJECT_ROOT / ".gitignore").read_text()
        for pattern in [".env", "*.key", "*.pem", "*.token", "*.secret"]:
            assert pattern in gitignore, f".gitignore missing {pattern}"

    def test_no_api_keys_in_source(self) -> None:
        """Scan all .py files for patterns that look like hardcoded API keys."""
        import re

        key_pattern = re.compile(r'["\'][a-zA-Z0-9]{32,}["\']')
        for py_file in PROJECT_ROOT.rglob("src/**/*.py"):
            content = py_file.read_text()
            matches = key_pattern.findall(content)
            # Filter out legitimate strings (docstrings, format specs)
            real_matches = [m for m in matches if "YOUR_" not in m and "test" not in m.lower()]
            assert not real_matches, f"Possible API key in {py_file.name}: {real_matches}"

    def test_no_keys_in_notebook_source(self) -> None:
        """Verify notebook cells don't contain hardcoded credentials."""
        import json
        import re

        key_pattern = re.compile(r'["\'][a-zA-Z0-9]{32,}["\']')
        for nb_file in (PROJECT_ROOT / "notebooks").glob("*.ipynb"):
            with open(nb_file) as f:
                nb = json.load(f)
            for i, cell in enumerate(nb["cells"]):
                if cell["cell_type"] == "code":
                    source = "".join(cell["source"])
                    matches = key_pattern.findall(source)
                    real = [m for m in matches if "YOUR_" not in m]
                    assert not real, f"Possible key in {nb_file.name} cell {i}: {real}"


class TestEiaInputValidation:
    """Verify EIA client handles malformed responses safely."""

    @patch("commodity_flow.eia.requests.get")
    def test_natgas_missing_process_name_raises(self, mock_get: MagicMock) -> None:
        """Missing process-name column should raise ValueError, not KeyError."""
        from commodity_flow import eia

        mock_get.return_value.json.return_value = {
            "response": {
                "data": [
                    {"period": "2025-01", "value": "100", "units": "MMCF", "duoarea": "NUS-Z00"}
                ]
            }
        }
        mock_get.return_value.raise_for_status = MagicMock()

        with pytest.raises(ValueError, match="process-name"):
            eia.fetch_natgas_imports("key")

    @patch("commodity_flow.eia.requests.get")
    def test_coerced_nan_logged(self, mock_get: MagicMock) -> None:
        """Non-numeric values should be coerced to NaN with a warning."""
        from commodity_flow.eia import _normalize_padd_columns

        df = pd.DataFrame(
            {
                "area-name": ["PADD 3", "PADD 3"],
                "period": ["2025-01", "2025-02"],
                "value": ["12345", "W"],  # "W" = withheld
            }
        )
        with patch("commodity_flow.eia.logger") as mock_logger:
            result = _normalize_padd_columns(df)
            # One value should be NaN
            assert result["value"].isna().sum() == 1
            mock_logger.warning.assert_called_once()


class TestAisCoordinateValidation:
    """Verify AIS parser rejects invalid coordinates."""

    def test_rejects_missing_latitude(self) -> None:
        data = {
            "MessageType": "PositionReport",
            "Message": {"PositionReport": {"Longitude": -90.0}},
            "MetaData": {"MMSI": 123},
        }
        assert _parse_position_report(data) is None

    def test_rejects_missing_longitude(self) -> None:
        data = {
            "MessageType": "PositionReport",
            "Message": {"PositionReport": {"Latitude": 30.0}},
            "MetaData": {"MMSI": 123},
        }
        assert _parse_position_report(data) is None

    def test_rejects_out_of_range_latitude(self) -> None:
        data = {
            "MessageType": "PositionReport",
            "Message": {"PositionReport": {"Latitude": 95.0, "Longitude": -90.0}},
            "MetaData": {"MMSI": 123},
        }
        assert _parse_position_report(data) is None

    def test_rejects_out_of_range_longitude(self) -> None:
        data = {
            "MessageType": "PositionReport",
            "Message": {"PositionReport": {"Latitude": 30.0, "Longitude": -200.0}},
            "MetaData": {"MMSI": 123},
        }
        assert _parse_position_report(data) is None

    def test_rejects_non_numeric_coordinates(self) -> None:
        data = {
            "MessageType": "PositionReport",
            "Message": {"PositionReport": {"Latitude": "bad", "Longitude": -90.0}},
            "MetaData": {"MMSI": 123},
        }
        assert _parse_position_report(data) is None

    def test_accepts_valid_coordinates(self) -> None:
        data = {
            "MessageType": "PositionReport",
            "Message": {"PositionReport": {"Latitude": 29.5, "Longitude": -89.5}},
            "MetaData": {"MMSI": 123},
        }
        result = _parse_position_report(data)
        assert result is not None
        assert result["lat"] == 29.5
        assert result["lon"] == -89.5

    def test_accepts_boundary_coordinates(self) -> None:
        """Poles and dateline should be valid."""
        for lat, lon in [(90, 180), (-90, -180), (0, 0)]:
            data = {
                "MessageType": "PositionReport",
                "Message": {"PositionReport": {"Latitude": lat, "Longitude": lon}},
                "MetaData": {"MMSI": 1},
            }
            assert _parse_position_report(data) is not None


class TestNetworkSecurity:
    """Verify all external connections use secure protocols."""

    def test_eia_uses_https(self) -> None:
        from commodity_flow.eia import fetch_eia_data

        import inspect

        source = inspect.getsource(fetch_eia_data)
        assert "https://" in source
        assert "http://" not in source.replace("https://", "")

    def test_ais_uses_wss(self) -> None:
        from commodity_flow.ais import WEBSOCKET_URL

        assert WEBSOCKET_URL.startswith("wss://")
