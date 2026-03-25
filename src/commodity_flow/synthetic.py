"""Synthetic data generators mirroring EIA/USGS/Fed survey schemas."""

from __future__ import annotations

import numpy as np
import pandas as pd

from commodity_flow.config import (
    BASINS,
    PADD_IMPORT_BASELINES,
    PADD_STOCK_BASELINES,
    PADDS,
)


def generate_synthetic_imports() -> pd.DataFrame:
    """Generate synthetic monthly crude imports by PADD (thousand barrels).

    Shapes based on actual EIA magnitudes. Injects a delivery gap in
    late 2025 / early 2026 simulating a disruption.
    """
    np.random.seed(42)
    dates = pd.date_range("2022-01-01", "2026-03-01", freq="MS")
    rows: list[dict] = []

    for padd, base in PADD_IMPORT_BASELINES.items():
        n = len(dates)
        seasonal = base * 0.08 * np.sin(2 * np.pi * np.arange(n) / 12)
        trend = np.linspace(0, base * 0.05, n)
        noise = np.random.normal(0, base * 0.06, n)

        # Inject delivery gap in late 2025 / early 2026
        gap_mask = (dates >= "2025-10-01") & (dates <= "2026-02-01")
        disruption = np.where(gap_mask, -base * 0.25, 0)

        values = np.maximum(base + seasonal + trend + noise + disruption, 0)

        for d, v in zip(dates, values):
            rows.append(
                {
                    "period": d.strftime("%Y-%m"),
                    "duoarea": padd,
                    "duoarea-name": PADDS[padd],
                    "product": "EPC0",
                    "product-name": "Crude Oil",
                    "process": "IM0",
                    "process-name": "Imports",
                    "value": round(v, 0),
                    "units": "MBBL",
                }
            )

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def generate_synthetic_stocks() -> pd.DataFrame:
    """Generate synthetic weekly crude stocks by PADD (thousand barrels)."""
    np.random.seed(99)
    dates = pd.date_range("2024-01-05", "2026-03-21", freq="W-FRI")
    rows: list[dict] = []

    for padd, base in PADD_STOCK_BASELINES.items():
        level = float(base)
        for d in dates:
            draw = np.random.normal(0, base * 0.01)
            if pd.Timestamp("2025-10-01") <= d <= pd.Timestamp("2026-02-01"):
                draw -= base * 0.008
            level = max(level + draw, base * 0.6)
            rows.append(
                {
                    "period": d.strftime("%Y-%m-%d"),
                    "duoarea": padd,
                    "duoarea-name": PADDS[padd],
                    "value": round(level, 0),
                    "units": "MBBL",
                }
            )

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def generate_synthetic_helium() -> pd.DataFrame:
    """Generate annual helium supply/demand data (million cubic meters).

    Based on USGS Mineral Commodity Summaries structure.
    """
    years = list(range(2018, 2027))
    return pd.DataFrame(
        {
            "year": years,
            "us_production_Mcm": [56, 55, 50, 48, 52, 54, 56, 53, 50],
            "world_production_Mcm": [160, 158, 150, 155, 170, 175, 180, 172, 168],
            "world_demand_Mcm": [155, 160, 148, 153, 165, 172, 180, 185, 190],
            "supply_gap_Mcm": [5, -2, 2, 2, 5, 3, 0, -13, -22],
            "blm_price_usd_per_mcf": [7.5, 8.0, 10.0, 19.0, 20.5, 22.0, 35.0, 40.0, 42.0],
        }
    )


def generate_synthetic_natgas_imports() -> pd.DataFrame:
    """Generate monthly natural gas imports by pipeline + LNG (Bcf).

    Helium co-production proxy — disruptions cascade to helium supply.
    """
    np.random.seed(77)
    dates = pd.date_range("2022-01-01", "2026-03-01", freq="MS")
    rows: list[dict] = []

    for mode, base in [("Pipeline", 250), ("LNG", 35)]:
        n = len(dates)
        seasonal = base * 0.15 * np.sin(2 * np.pi * np.arange(n) / 12 + np.pi)
        trend = np.linspace(0, base * 0.08, n)
        noise = np.random.normal(0, base * 0.04, n)
        gap = np.where(
            (dates >= pd.Timestamp("2025-11-01")) & (dates <= pd.Timestamp("2026-01-01")),
            -base * 0.20,
            0,
        )
        values = base + seasonal + trend + noise + gap

        for d, v in zip(dates, values):
            rows.append(
                {
                    "period": d.strftime("%Y-%m"),
                    "mode": mode,
                    "value_bcf": round(max(v, 0), 1),
                }
            )

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["period"])
    return df


def generate_synthetic_breakevens() -> pd.DataFrame:
    """Generate synthetic basin-level breakeven data mirroring Dallas/KC Fed surveys.

    Returns quarterly breakeven estimates by basin with WTI reference price.
    """
    np.random.seed(55)
    quarters = pd.date_range("2022-01-01", "2026-01-01", freq="QS")

    # Baseline breakevens ($/bbl) — approximate Dallas/KC Fed survey values
    basin_breakevens: dict[str, float] = {
        "Permian": 38.0,
        "Eagle Ford": 42.0,
        "Bakken": 48.0,
        "DJ/Niobrara": 45.0,
        "Appalachian": 55.0,  # gas-weighted, higher oil breakeven
        "Haynesville": 52.0,  # gas-focused
        "Anadarko": 47.0,
    }

    # Synthetic WTI prices (quarterly avg)
    wti_base = np.array([78, 95, 88, 82, 75, 72, 78, 85, 80, 76, 70, 65, 58, 62, 68, 72, 70])
    wti_prices = wti_base[: len(quarters)]

    rows: list[dict] = []
    for i, q in enumerate(quarters):
        for basin, base_be in basin_breakevens.items():
            # Breakevens drift slightly with inflation + efficiency gains
            drift = np.random.normal(0, 1.5)
            efficiency = -0.3 * i  # costs decline over time with technology
            be = base_be + drift + efficiency
            rows.append(
                {
                    "date": q,
                    "quarter": q.strftime("%Y-Q%q").replace("%q", str((q.month - 1) // 3 + 1)),
                    "basin": basin,
                    "play": BASINS[basin]["play"],
                    "state": BASINS[basin]["state"],
                    "breakeven_usd_bbl": round(max(be, 20), 1),
                    "wti_price_usd_bbl": wti_prices[i],
                    "profitable": be < wti_prices[i],
                }
            )

    return pd.DataFrame(rows)


def generate_synthetic_dpr() -> pd.DataFrame:
    """Generate synthetic Drilling Productivity Report data.

    Monthly production per rig and rig counts by basin.
    """
    np.random.seed(33)
    dates = pd.date_range("2022-01-01", "2026-03-01", freq="MS")

    # Baseline production per rig (bbl/d) and rig counts
    basin_params: dict[str, dict[str, float]] = {
        "Permian": {"prod_per_rig": 1200, "rig_count": 340},
        "Eagle Ford": {"prod_per_rig": 1400, "rig_count": 65},
        "Bakken": {"prod_per_rig": 1100, "rig_count": 35},
        "DJ/Niobrara": {"prod_per_rig": 900, "rig_count": 15},
        "Appalachian": {"prod_per_rig": 300, "rig_count": 45},  # gas-weighted
        "Haynesville": {"prod_per_rig": 250, "rig_count": 50},  # gas basin
        "Anadarko": {"prod_per_rig": 800, "rig_count": 40},
    }

    rows: list[dict] = []
    for basin, params in basin_params.items():
        base_prod = params["prod_per_rig"]
        base_rigs = params["rig_count"]

        for i, d in enumerate(dates):
            # Productivity improves ~5%/yr
            prod_trend = base_prod * (1 + 0.004 * i)
            prod = prod_trend + np.random.normal(0, base_prod * 0.03)

            # Rig count responds to price (use synthetic WTI proxy)
            price_effect = np.sin(2 * np.pi * i / 24) * base_rigs * 0.15
            rig_noise = np.random.normal(0, base_rigs * 0.05)
            # Rigs drop in late 2025 (price decline)
            rig_drop = -base_rigs * 0.2 if d >= pd.Timestamp("2025-09-01") else 0
            rigs = max(base_rigs + price_effect + rig_noise + rig_drop, 1)

            total_production = prod * rigs  # bbl/d for basin

            rows.append(
                {
                    "date": d,
                    "period": d.strftime("%Y-%m"),
                    "basin": basin,
                    "production_per_rig_bbl_d": round(prod, 0),
                    "rig_count": round(rigs, 0),
                    "total_new_well_production_bbl_d": round(total_production, 0),
                }
            )

    return pd.DataFrame(rows)


def generate_synthetic_steo() -> pd.DataFrame:
    """Generate synthetic STEO (Short Term Energy Outlook) projections.

    Forward-looking monthly forecasts for crude imports and production.
    """
    np.random.seed(88)
    # Historical + forecast dates
    dates = pd.date_range("2024-01-01", "2027-06-01", freq="MS")

    rows: list[dict] = []
    for d in dates:
        is_forecast = d >= pd.Timestamp("2026-04-01")
        # US crude imports (million bbl/d) — declining trend
        imports_base = 6.5 - 0.02 * ((d - pd.Timestamp("2024-01-01")).days / 30)
        imports_noise = np.random.normal(0, 0.15) if not is_forecast else 0
        imports_val = max(imports_base + imports_noise, 4.0)

        # US crude production (million bbl/d) — rising
        prod_base = 13.0 + 0.03 * ((d - pd.Timestamp("2024-01-01")).days / 30)
        prod_noise = np.random.normal(0, 0.1) if not is_forecast else 0
        prod_val = prod_base + prod_noise

        rows.append(
            {
                "date": d,
                "period": d.strftime("%Y-%m"),
                "series_id": "COIMPUS",
                "series_name": "US Crude Oil Imports",
                "value": round(imports_val, 2),
                "units": "million bbl/d",
                "is_forecast": is_forecast,
            }
        )
        rows.append(
            {
                "date": d,
                "period": d.strftime("%Y-%m"),
                "series_id": "PAPR_WORLD",
                "series_name": "World Crude Oil Production",
                "value": round(prod_val, 2),
                "units": "million bbl/d",
                "is_forecast": is_forecast,
            }
        )

    return pd.DataFrame(rows)
