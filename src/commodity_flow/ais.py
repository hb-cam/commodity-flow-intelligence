"""AISstream.io websocket client for real-time tanker tracking."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp
import pandas as pd

logger = logging.getLogger(__name__)

# Bounding boxes for major US port regions [SW corner, NE corner]
US_PORT_BOXES: list[list[list[float]]] = [
    [[24.5, -98.0], [30.5, -87.0]],  # Gulf Coast (Houston, LOOP, New Orleans)
    [[37.5, -76.5], [40.7, -73.5]],  # East Coast (NY/NJ, Philadelphia, Delaware)
    [[33.5, -119.0], [34.5, -117.5]],  # West Coast (Los Angeles/Long Beach)
    [[47.0, -123.0], [48.5, -122.0]],  # Pacific NW (Puget Sound)
]

WEBSOCKET_URL = "wss://stream.aisstream.io/v0/stream"


async def track_tankers(
    api_key: str,
    duration_seconds: int = 300,
    max_positions: int = 500,
    bounding_boxes: list[list[list[float]]] | None = None,
) -> pd.DataFrame:
    """Connect to AISstream.io and collect tanker position reports.

    Args:
        api_key: AISstream.io API key.
        duration_seconds: Max seconds to collect data.
        max_positions: Stop after this many position reports.
        bounding_boxes: Override default US port bounding boxes.

    Returns:
        DataFrame with tanker positions (mmsi, name, lat, lon, speed, heading,
        destination, eta, timestamp).
    """
    boxes = bounding_boxes or US_PORT_BOXES
    subscribe_msg = {
        "APIKey": api_key,
        "BoundingBoxes": boxes,
        "FilterShipType": list(range(80, 90)),  # Tankers only
    }

    tanker_log: list[dict[str, Any]] = []

    try:
        async with asyncio.timeout(duration_seconds):
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(WEBSOCKET_URL) as ws:
                    await ws.send_json(subscribe_msg)
                    logger.info("Connected to AISstream.io, tracking tankers...")

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            entry = _parse_position_report(data)
                            if entry:
                                tanker_log.append(entry)
                                if len(tanker_log) % 50 == 0:
                                    logger.info("Tracked %d tanker positions...", len(tanker_log))
                                if len(tanker_log) >= max_positions:
                                    break
                        elif msg.type in (
                            aiohttp.WSMsgType.ERROR,
                            aiohttp.WSMsgType.CLOSED,
                        ):
                            logger.warning("WebSocket closed: %s", msg.type)
                            break

    except TimeoutError:
        logger.info(
            "Collection period ended (%ds). Collected %d positions.",
            duration_seconds,
            len(tanker_log),
        )

    if not tanker_log:
        return pd.DataFrame(
            columns=[
                "mmsi",
                "name",
                "lat",
                "lon",
                "speed_kn",
                "heading",
                "destination",
                "eta",
                "timestamp",
            ]
        )

    return pd.DataFrame(tanker_log)


def _parse_position_report(data: dict) -> dict[str, Any] | None:
    """Extract position data from an AIS message."""
    msg_type = data.get("MessageType", "")
    if msg_type != "PositionReport":
        return None

    pos = data.get("Message", {}).get("PositionReport", {})
    meta = data.get("MetaData", {})

    return {
        "mmsi": meta.get("MMSI"),
        "name": (meta.get("ShipName") or "").strip(),
        "lat": pos.get("Latitude"),
        "lon": pos.get("Longitude"),
        "speed_kn": pos.get("Sog"),
        "heading": pos.get("TrueHeading"),
        "destination": (meta.get("Destination") or "").strip(),
        "eta": meta.get("ETA", ""),
        "timestamp": meta.get("time_utc"),
    }
