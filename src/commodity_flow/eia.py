"""EIA API v2 client — crude imports, stocks, STEO, drilling productivity."""

from __future__ import annotations

import pandas as pd
import requests


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


def fetch_crude_imports_by_padd(
    api_key: str, start: str = "2022-01", end: str = "2026-03"
) -> pd.DataFrame:
    """Pull monthly crude oil imports by PADD via tanker/barge."""
    params = {
        "frequency": "monthly",
        "data[0]": "value",
        "facets[duoarea][]": ["R10", "R20", "R30", "R40", "R50"],
        "start": start,
        "end": end,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 5000,
    }
    df = fetch_eia_data("petroleum/move/imp", params, api_key)
    df["date"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def fetch_weekly_stocks(api_key: str, start: str = "2024-01") -> pd.DataFrame:
    """Pull weekly crude oil stocks by PADD."""
    params = {
        "frequency": "weekly",
        "data[0]": "value",
        "start": start,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 5000,
    }
    df = fetch_eia_data("petroleum/stoc/wstk", params, api_key)
    df["date"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
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
    df["date"] = pd.to_datetime(df["period"])
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
    df["date"] = pd.to_datetime(df["period"])
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
    df["date"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df
