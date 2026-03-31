"""Inventory analytics — days of supply, seasonal comparisons, SPR tracking."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

# Key product codes for inventory tracking.
# EPM0 = Total Gasoline (finished + blending components) — the market metric.
# EPM0F = Finished Motor Gasoline only (~14K MBBL vs ~241K for total).
PRODUCTS: dict[str, str] = {
    "EPC0": "Crude Oil",
    "EPM0": "Total Gasoline",
    "EPD0": "Distillate Fuel Oil",
    "EPJK": "Jet Fuel",
    "EPLLPZ": "Propane/Propylene",
    "EPPR": "Residual Fuel Oil",
}

# For days-of-supply, map stock products to their consumption counterparts.
# EPM0 stocks / EPM0F consumption = gasoline DoS (you consume finished, stock total).
STOCK_TO_CONSUMPTION: dict[str, str] = {
    "EPM0": "EPM0F",
    "EPD0": "EPD0",
    "EPJK": "EPJK",
    "EPLLPZ": "EPLLPZ",
    "EPPR": "EPPR",
}

# Product supplied codes (consumption proxy) — subset available weekly
CONSUMPTION_PRODUCTS: dict[str, str] = {
    "EPM0F": "Finished Motor Gasoline",
    "EPD0": "Distillate Fuel Oil",
    "EPJK": "Jet Fuel",
    "EPLLPZ": "Propane/Propylene",
    "EPP0": "Total Petroleum Products",
    "EPPR": "Residual Fuel Oil",
}


def fetch_product_stocks(api_key: str, start: str = "2020-01") -> pd.DataFrame:
    """Fetch weekly ending stocks by product at national level.

    Returns stocks for crude oil (total, SPR, commercial), gasoline,
    distillate, jet fuel, propane, and residual fuel oil.
    """
    base = "https://api.eia.gov/v2"
    params = {
        "api_key": api_key,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[duoarea][]": ["NUS"],
        "facets[product][]": list(PRODUCTS.keys()),
        "start": start,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 5000,
    }
    resp = requests.get(f"{base}/petroleum/stoc/wstk/data/", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "response" not in data or not data["response"]["data"]:
        return pd.DataFrame()

    df = pd.DataFrame(data["response"]["data"])
    df["date"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    n_nan = df["value"].isna().sum()
    if n_nan > 0:
        logger.warning("Product stocks: %d values coerced to NaN", n_nan)

    # Filter to MBBL only
    df = df[df["units"] == "MBBL"].copy()

    # Tag stock type from process-name.
    # EIA returns multiple process rows for crude:
    #   "Ending Stocks"              = total (SPR + commercial) — tag as "total"
    #   "Ending Stocks SPR"          = SPR only
    #   "Ending Stocks Excluding SPR" = commercial only
    #   "Stocks in Transit..."       = in-transit
    # For non-crude products, only "Ending Stocks" exists (no SPR split).
    # We must tag the crude total row as "total" to avoid double-counting.
    df["stock_type"] = "commercial"
    df.loc[df["process-name"].str.contains("Transit", na=False), "stock_type"] = "transit"
    # SPR rows (must check before "Excluding SPR" since both contain "SPR")
    is_spr = df["process-name"].str.contains("SPR", na=False)
    is_excl_spr = df["process-name"].str.contains("Excluding SPR", na=False)
    df.loc[is_spr & ~is_excl_spr, "stock_type"] = "spr"
    df.loc[is_excl_spr, "stock_type"] = "commercial"
    # The bare "Ending Stocks" row for crude is the total (SPR + commercial).
    # Tag it so downstream doesn't double-count.
    is_crude = df["product"] == "EPC0"
    is_bare_ending = df["process-name"] == "Ending Stocks"
    df.loc[is_crude & is_bare_ending, "stock_type"] = "total"

    # Map product codes to names
    df["product_name"] = df["product"].map(PRODUCTS)

    return df


def fetch_product_supplied(api_key: str, start: str = "2020-01") -> pd.DataFrame:
    """Fetch weekly product supplied (consumption proxy) at national level.

    Product supplied = domestic consumption, measured in MBBL/D.
    """
    base = "https://api.eia.gov/v2"
    params = {
        "api_key": api_key,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[product][]": list(CONSUMPTION_PRODUCTS.keys()),
        "start": start,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 5000,
    }
    resp = requests.get(f"{base}/petroleum/cons/wpsup/data/", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "response" not in data or not data["response"]["data"]:
        return pd.DataFrame()

    df = pd.DataFrame(data["response"]["data"])
    df["date"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["product_name"] = df["product"].map(CONSUMPTION_PRODUCTS)

    return df


def compute_days_of_supply(
    df_stocks: pd.DataFrame,
    df_supplied: pd.DataFrame,
) -> pd.DataFrame:
    """Compute days-of-supply for each product.

    Days of supply = ending stocks (MBBL) / (product supplied (MBBL/D)).
    Uses STOCK_TO_CONSUMPTION mapping for products where the stock code
    differs from the consumption code (e.g., EPM0 stocks / EPM0F consumption
    for gasoline — you stock total, you consume finished).
    """
    # Commercial stocks only (exclude SPR and transit)
    commercial = df_stocks[df_stocks["stock_type"] == "commercial"].copy()

    # Map stock products to their consumption counterparts
    commercial["consumption_product"] = commercial["product"].map(STOCK_TO_CONSUMPTION)
    # Fall back to same product code if not in mapping
    commercial["consumption_product"] = commercial["consumption_product"].fillna(
        commercial["product"]
    )

    # Aggregate stocks per product per week
    stocks_weekly = (
        commercial.groupby(["date", "product", "consumption_product"])
        .agg({"value": "sum", "product_name": "first"})
        .reset_index()
        .rename(columns={"value": "stocks_mbbl"})
    )

    # Consumption per product per week
    supplied_weekly = (
        df_supplied.groupby(["date", "product"])
        .agg({"value": "mean", "product_name": "first"})
        .reset_index()
        .rename(columns={"value": "supplied_mbbl_d", "product": "consumption_product"})
    )

    # Merge: stock product's consumption_product matches supplied's product code
    merged = stocks_weekly.merge(
        supplied_weekly,
        on=["date", "consumption_product"],
        how="inner",
        suffixes=("", "_supplied"),
    )
    merged["product_name"] = merged["product_name"].fillna(merged["product_name_supplied"])
    merged = merged.drop(columns=["product_name_supplied"], errors="ignore")

    # Days of supply
    merged["days_of_supply"] = merged["stocks_mbbl"] / merged["supplied_mbbl_d"]
    merged.loc[merged["supplied_mbbl_d"] <= 0, "days_of_supply"] = np.nan

    return merged


def compute_seasonal_comparison(
    df_stocks: pd.DataFrame,
    years_back: int = 5,
) -> pd.DataFrame:
    """Compare current stocks to the 5-year seasonal average and range.

    Returns DataFrame with: date, product, current, avg_5yr, min_5yr, max_5yr,
    deviation_pct (how far current is from the 5-year average as a percentage).
    """
    df = df_stocks[df_stocks["stock_type"] == "commercial"].copy()
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    df["year"] = df["date"].dt.year

    max_year = df["year"].max()
    historical = df[(df["year"] >= max_year - years_back) & (df["year"] < max_year)]
    current = df[df["year"] == max_year]

    # 5-year stats by week-of-year and product
    stats = (
        historical.groupby(["week_of_year", "product"])["value"]
        .agg(["mean", "min", "max", "std"])
        .reset_index()
        .rename(columns={"mean": "avg_5yr", "min": "min_5yr", "max": "max_5yr", "std": "std_5yr"})
    )

    # Merge current year with historical stats
    current_agg = (
        current.groupby(["date", "week_of_year", "product"])
        .agg({"value": "sum", "product_name": "first"})
        .reset_index()
        .rename(columns={"value": "current"})
    )

    result = current_agg.merge(stats, on=["week_of_year", "product"], how="left")
    result["deviation_pct"] = (result["current"] - result["avg_5yr"]) / result["avg_5yr"] * 100
    result["deviation_sigma"] = (result["current"] - result["avg_5yr"]) / result["std_5yr"].replace(
        0, np.nan
    )

    return result.sort_values(["product", "date"])


def compute_spr_status(df_stocks: pd.DataFrame) -> pd.DataFrame:
    """Extract SPR vs commercial crude oil stock levels over time."""
    crude = df_stocks[df_stocks["product"] == "EPC0"].copy()

    spr = crude[crude["stock_type"] == "spr"][["date", "value"]].rename(
        columns={"value": "spr_mbbl"}
    )
    commercial = crude[crude["stock_type"] == "commercial"][["date", "value"]].rename(
        columns={"value": "commercial_mbbl"}
    )

    merged = spr.merge(commercial, on="date", how="outer").sort_values("date")
    merged["total_mbbl"] = merged["spr_mbbl"].fillna(0) + merged["commercial_mbbl"].fillna(0)
    merged["spr_pct"] = merged["spr_mbbl"] / merged["total_mbbl"] * 100

    return merged


def generate_offline_inventory() -> dict[str, pd.DataFrame]:
    """Generate offline inventory data for analysis without API keys.

    Returns dict with keys: stocks, supplied, suitable for passing to
    compute_days_of_supply and compute_seasonal_comparison.
    """
    np.random.seed(44)
    dates = pd.date_range("2020-01-03", "2026-03-20", freq="W-FRI")

    # Stock baselines (MBBL) — calibrated to EIA weekly data 2026-03
    stock_bases = {
        "EPC0": {"commercial": 456_000, "spr": 415_000},
        "EPM0": {"commercial": 241_000},  # Total gasoline (finished + blending)
        "EPD0": {"commercial": 120_000},
        "EPJK": {"commercial": 44_000},
        "EPLLPZ": {"commercial": 73_000},
        "EPPR": {"commercial": 25_000},
    }

    # Consumption baselines (MBBL/D)
    supplied_bases = {
        "EPM0F": 8800,
        "EPD0": 3600,
        "EPJK": 1550,
        "EPLLPZ": 1100,
        "EPP0": 20000,
        "EPPR": 230,
    }

    stock_rows: list[dict] = []
    for product, types in stock_bases.items():
        for stock_type, base in types.items():
            level = float(base)
            for d in dates:
                # Seasonal pattern
                week = d.isocalendar().week
                seasonal = base * 0.05 * np.sin(2 * np.pi * week / 52)
                noise = np.random.normal(0, base * 0.008)

                # SPR drawdown trend (post-2022)
                if stock_type == "spr" and d >= pd.Timestamp("2022-03-01"):
                    level -= base * 0.0008

                level = max(level + seasonal * 0.01 + noise, base * 0.4)
                stock_rows.append(
                    {
                        "date": d,
                        "period": d.strftime("%Y-%m-%d"),
                        "product": product,
                        "product_name": PRODUCTS.get(product, product),
                        "value": round(level, 0),
                        "units": "MBBL",
                        "stock_type": stock_type,
                        "process-name": f"Ending Stocks{' SPR' if stock_type == 'spr' else ''}",
                    }
                )

    supplied_rows: list[dict] = []
    for product, base in supplied_bases.items():
        for d in dates:
            week = d.isocalendar().week
            seasonal = base * 0.08 * np.sin(2 * np.pi * (week - 26) / 52)
            noise = np.random.normal(0, base * 0.03)
            val = max(base + seasonal + noise, base * 0.5)
            supplied_rows.append(
                {
                    "date": d,
                    "period": d.strftime("%Y-%m-%d"),
                    "product": product,
                    "product_name": CONSUMPTION_PRODUCTS.get(product, product),
                    "value": round(val, 0),
                    "units": "MBBL/D",
                }
            )

    return {
        "stocks": pd.DataFrame(stock_rows),
        "supplied": pd.DataFrame(supplied_rows),
    }
