"""Tests for AIS tanker tracking module."""

from commodity_flow.ais import US_PORT_BOXES, _parse_position_report


class TestParsePositionReport:
    def test_valid_position_report(self) -> None:
        data = {
            "MessageType": "PositionReport",
            "Message": {
                "PositionReport": {
                    "Latitude": 29.5,
                    "Longitude": -89.5,
                    "Sog": 12.5,
                    "TrueHeading": 180,
                }
            },
            "MetaData": {
                "MMSI": 123456789,
                "ShipName": "ATLANTIC STAR  ",
                "Destination": "LOOP  ",
                "ETA": "2025-04-01T12:00:00Z",
                "time_utc": "2025-03-25T10:30:00Z",
            },
        }
        result = _parse_position_report(data)
        assert result is not None
        assert result["mmsi"] == 123456789
        assert result["name"] == "ATLANTIC STAR"  # stripped
        assert result["destination"] == "LOOP"  # stripped
        assert result["lat"] == 29.5
        assert result["lon"] == -89.5
        assert result["speed_kn"] == 12.5

    def test_non_position_report_returns_none(self) -> None:
        data = {"MessageType": "ShipStaticData", "Message": {}}
        assert _parse_position_report(data) is None

    def test_missing_metadata_fields(self) -> None:
        data = {
            "MessageType": "PositionReport",
            "Message": {"PositionReport": {"Latitude": 30.0, "Longitude": -90.0}},
            "MetaData": {"MMSI": 999},
        }
        result = _parse_position_report(data)
        assert result is not None
        assert result["name"] == ""
        assert result["destination"] == ""
        assert result["speed_kn"] is None

    def test_empty_message_type(self) -> None:
        data = {"MessageType": "", "Message": {}}
        assert _parse_position_report(data) is None


class TestPortBoundingBoxes:
    def test_four_regions_defined(self) -> None:
        assert len(US_PORT_BOXES) == 4

    def test_boxes_are_valid_coordinates(self) -> None:
        for box in US_PORT_BOXES:
            sw, ne = box
            assert -90 <= sw[0] <= 90  # latitude
            assert -180 <= sw[1] <= 180  # longitude
            assert sw[0] < ne[0]  # SW lat < NE lat
            assert sw[1] < ne[1]  # SW lon < NE lon
