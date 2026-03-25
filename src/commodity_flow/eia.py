"""EIA API v2 client — crude imports, stocks, STEO, drilling productivity."""

from __future__ import annotations

import pandas as pd
import requests

from commodity_flow.config import PADDS

# EIA duoarea codes use "-Z00" suffix for PADD regions
_PADD_DUOAREA = ["R10-Z00", "R20-Z00", "R30-Z00", "R40-Z00", "R50-Z00"]

# Map EIA area-name back to our PADD keys
_AREA_TO_PADD = {
    "PADD 1": "PADD 1",
    "PADD 2": "PADD 2",
    "PADD 3": "PADD 3",
    "PADD 4": "PADD 4",
    "PADD 5": "PADD 5",
    "East Coast": "PADD 1",
    "Midwest": "PADD 2",
    "Gulf Coast": "PADD 3",
    "Rocky Mountain": "PADD 4",
    "West Coast": "PADD 5",
}


def fetch_eia_data(route: str, params: dict, api_key: str) -> pd.DataFrame:
    """Generic EIA API v2 fetcher. Returns DataFrame."""
    base = "https://api.eia.gov/v2"
    url = f"{base}/{route}/data/"
    params["api_key"] = api_key
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "response" in data and "data" in data["response"]:
        return pd.DataFrame(data["response"]["data"])
    raise ValueError(f"Unexpected EIA response structure: {list(data.keys())}")


def _normalize_padd_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize EIA response columns to match synthetic data schema."""
    df = df.copy()

    # Map area-name to duoarea PADD key
    if "area-name" in df.columns:
        df["duoarea"] = df["area-name"].map(_AREA_TO_PADD).fillna(df.get("duoarea", ""))
        df["duoarea-name"] = df["area-name"]

    # Parse dates and values
    if "period" in df.columns:
        df["date"] = pd.to_datetime(df["period"])
    if "value" in df.columns:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")

    return df


def fetch_crude_imports_by_padd(
    api_key: str, start: str = "2022-01", end: str = "2026-12"
) -> pd.DataFrame:
    """Pull monthly crude oil imports by PADD (thousand barrels)."""
    params = {
        "frequency": "monthly",
        "data[0]": "value",
        "facets[duoarea][]": _PADD_DUOAREA,
        "facets[product][]": ["EPC0"],  # Crude Oil
        "facets[process][]": ["IM0"],  # Imports
        "start": start,
        "end": end,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 5000,
    }
    df = fetch_eia_data("petroleum/move/imp", params, api_key)
    df = _normalize_padd_columns(df)

    # Filter to MBBL (absolute, not per-day) to match synthetic schema
    if "units" in df.columns:
        df = df[df["units"] == "MBBL"]

    return df


def fetch_weekly_stocks(api_key: str, start: str = "2024-01") -> pd.DataFrame:
    """Pull weekly petroleum ending stocks by PADD (thousand barrels).

    Note: EIA weekly stocks at PADD level cover total petroleum products (EP00),
    distillates, jet fuel, etc. — crude-specific stocks (EPC0) are only available
    at national level. We pull total petroleum (EP00) by PADD for regional analysis.
    """
    # Stocks use bare PADD codes (R10, not R10-Z00).
    # PADD-level weekly data doesn't have EP00 (total petroleum) — only
    # individual products. We pull all products at PADD level and aggregate
    # per period+PADD for a total stocks figure.
    padd_codes = ["R10", "R20", "R30", "R40", "R50"]
    params = {
        "frequency": "weekly",
        "data[0]": "value",
        "facets[duoarea][]": padd_codes,
        "facets[process][]": ["SAE"],  # Ending Stocks
        "start": start,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 5000,
    }
    df = fetch_eia_data("petroleum/stoc/wstk", params, api_key)
    df = _normalize_padd_columns(df)

    if "units" in df.columns:
        df = df[df["units"] == "MBBL"]

    # Aggregate all products per period+PADD to get total stocks
    if not df.empty and "duoarea" in df.columns:
        df = (
            df.groupby(["period", "duoarea", "date"], as_index=False)
            .agg({"value": "sum"})
        )
        # Restore duoarea-name
        df["duoarea-name"] = df["duoarea"].map(PADDS)
        df["units"] = "MBBL"

    return df


def fetch_steo_projections(api_key: str) -> pd.DataFrame:
    """Pull Short Term Energy Outlook — crude oil production & imports forecasts."""
    series_ids = ["PAPR_WORLD", "COIMPUS", "COPS_SPR", "COSTPUS"]
    params = {
        "frequency": "monthly",
        "data[0]": "value",
        "facets[seriesId][]": series_ids,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 5000,
    }
    df = fetch_eia_data("steo", params, api_key)
    if "period" in df.columns:
        df["date"] = pd.to_datetime(df["period"])
    if "value" in df.columns:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def fetch_drilling_productivity(api_key: str) -> pd.DataFrame:
    """Pull Drilling Productivity Report — production per rig by basin."""
    params = {
        "frequency": "monthly",
        "data[0]": "value",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 5000,
    }
    df = fetch_eia_data("petroleum/dril/data", params, api_key)
    if "period" in df.columns:
        df["date"] = pd.to_datetime(df["period"])
    if "value" in df.columns:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def fetch_eia_914_production(api_key: str) -> pd.DataFrame:
    """Pull EIA-914 monthly crude + gas production by state."""
    params = {
        "frequency": "monthly",
        "data[0]": "value",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 5000,
    }
    df = fetch_eia_data("petroleum/crd/crpdn", params, api_key)
    if "period" in df.columns:
        df["date"] = pd.to_datetime(df["period"])
    if "value" in df.columns:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df
