"""Gap detection, z-score analysis, and composite scorecard."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_gap_score(series: pd.Series, window: int = 6) -> pd.Series:
    """Z-score relative to trailing window. Negative = below-normal deliveries."""
    ma = series.rolling(window, min_periods=3).mean()
    std = series.rolling(window, min_periods=3).std()
    return (series - ma) / std.replace(0, np.nan)


def detect_gaps(
    df: pd.DataFrame,
    column: str = "value",
    date_column: str = "date",
    window: int = 12,
    threshold: float = -1.0,
) -> pd.DataFrame:
    """Detect delivery gaps in a time series.

    Returns rows where the z-score falls below the threshold.
    """
    sorted_df = df.sort_values(date_column).copy()
    sorted_df["z_score"] = compute_gap_score(sorted_df[column], window)
    sorted_df["in_gap"] = sorted_df["z_score"] < threshold
    return sorted_df


def build_scorecard(
    df_imports: pd.DataFrame,
    df_natgas: pd.DataFrame,
    df_steo: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build composite gap scorecard from oil imports + natgas imports.

    Optionally includes STEO forward projections to extend the scorecard
    into forecast territory.
    """
    # --- Input validation ---
    _validate_scorecard_inputs(df_imports, df_natgas, df_steo)

    # Monthly crude imports — national total
    national_imports = df_imports.groupby("date")["value"].sum().sort_index()
    oil_z = compute_gap_score(national_imports, 12)

    # Natural gas total
    natgas_total = df_natgas.groupby("date")["value_bcf"].sum().sort_index()
    gas_z = compute_gap_score(natgas_total, 6)

    # Align on common monthly index
    common_idx = oil_z.index.intersection(gas_z.index)
    scorecard = pd.DataFrame(
        {
            "oil_import_z": oil_z.loc[common_idx],
            "natgas_import_z": gas_z.loc[common_idx],
        }
    ).dropna()

    # Composite score (equal weight)
    scorecard["composite_gap_score"] = (
        scorecard["oil_import_z"] + scorecard["natgas_import_z"]
    ) / 2

    # STEO forward overlay
    if df_steo is not None:
        steo_imports = df_steo[df_steo["series_id"] == "CONIPUS"].copy()
        # Infer forecast flag if not present (live STEO includes future periods)
        if "is_forecast" not in steo_imports.columns:
            steo_imports["is_forecast"] = steo_imports["date"] > pd.Timestamp.now()
        steo_forecast = steo_imports[steo_imports["is_forecast"]].set_index("date")["value"]
        if not steo_forecast.empty:
            steo_z = compute_gap_score(
                pd.concat([national_imports, steo_forecast]).sort_index(), 12
            )
            forecast_idx = steo_forecast.index
            scorecard_forecast = pd.DataFrame(
                {
                    "oil_import_z": steo_z.loc[forecast_idx],
                    "natgas_import_z": np.nan,
                    "composite_gap_score": steo_z.loc[forecast_idx],
                    "is_forecast": True,
                }
            )
            scorecard["is_forecast"] = False
            scorecard = pd.concat([scorecard, scorecard_forecast]).sort_index()

    if "is_forecast" not in scorecard.columns:
        scorecard["is_forecast"] = False

    return scorecard


def _validate_scorecard_inputs(
    df_imports: pd.DataFrame,
    df_natgas: pd.DataFrame,
    df_steo: pd.DataFrame | None,
) -> None:
    """Validate data quality and unit alignment before building scorecard."""
    # Imports: should have date + value columns, values in MBBL range
    if not df_imports.empty:
        monthly_total = df_imports.groupby("date")["value"].sum()
        avg = monthly_total.mean()
        if avg < 1000:
            logger.warning(
                "Import values avg %.0f — suspiciously low. "
                "Expected ~150K-250K MBBL/month for national total. "
                "Check units (MBBL vs bbl vs MBBL/D).",
                avg,
            )
        if avg > 1_000_000:
            logger.warning(
                "Import values avg %.0f — suspiciously high. "
                "Expected ~150K-250K MBBL/month. Check for double-counting.",
                avg,
            )

    # NatGas: should have date + value_bcf, pipeline ~200-350 Bcf/mo
    if not df_natgas.empty and "value_bcf" in df_natgas.columns:
        ng_total = df_natgas.groupby("date")["value_bcf"].sum()
        ng_avg = ng_total.mean()
        if ng_avg < 50:
            logger.warning(
                "NatGas total avg %.1f Bcf — suspiciously low. "
                "Expected ~200-350 Bcf/month. Check units (MMCF vs Bcf).",
                ng_avg,
            )

    # STEO: CONIPUS should be net imports ~1-5 million bbl/d
    if df_steo is not None and not df_steo.empty and "series_id" in df_steo.columns:
        conipus = df_steo[df_steo["series_id"] == "CONIPUS"]["value"]
        if not conipus.empty:
            avg_conipus = conipus.mean()
            if avg_conipus > 8:
                logger.warning(
                    "STEO CONIPUS avg %.2f — too high for net imports. "
                    "CONIPUS is NET imports (imports - exports), not gross. "
                    "Expected ~1-5 million bbl/d.",
                    avg_conipus,
                )

        papr = df_steo[df_steo["series_id"] == "PAPR_WORLD"]["value"]
        if not papr.empty:
            avg_papr = papr.mean()
            if avg_papr < 50:
                logger.warning(
                    "STEO PAPR_WORLD avg %.2f — too low for world production. "
                    "Expected ~100-115 million bbl/d.",
                    avg_papr,
                )


def compute_breakeven_status(df_breakevens: pd.DataFrame, wti_price: float) -> pd.DataFrame:
    """Classify basins as profitable/at-risk at a given WTI price.

    Returns DataFrame with profitability status and margin for each basin.
    """
    # Get most recent quarter for each basin
    latest = df_breakevens.sort_values("date").groupby("basin").last().reset_index()
    latest["margin_usd_bbl"] = wti_price - latest["breakeven_usd_bbl"]
    latest["profitable"] = latest["margin_usd_bbl"] > 0
    latest["status"] = latest["margin_usd_bbl"].apply(
        lambda m: "profitable" if m > 10 else ("marginal" if m > 0 else "at risk")
    )
    latest["wti_reference"] = wti_price
    return latest.sort_values("breakeven_usd_bbl")


def production_at_risk_curve(
    df_breakevens: pd.DataFrame,
    df_dpr: pd.DataFrame,
    wti_range: tuple[float, float] = (30.0, 100.0),
    step: float = 5.0,
) -> pd.DataFrame:
    """Sweep WTI prices and compute cumulative production at risk.

    Returns a DataFrame with WTI price, production at risk (bbl/d),
    and percentage of total production at risk.
    """
    # Latest breakevens and production by basin
    latest_be = df_breakevens.sort_values("date").groupby("basin").last().reset_index()
    latest_prod = df_dpr.sort_values("date").groupby("basin").last().reset_index()

    merged = latest_be.merge(
        latest_prod[["basin", "total_new_well_production_bbl_d"]], on="basin", how="inner"
    )
    total_production = merged["total_new_well_production_bbl_d"].sum()

    prices = np.arange(wti_range[0], wti_range[1] + step, step)
    rows: list[dict] = []

    for price in prices:
        at_risk = merged[merged["breakeven_usd_bbl"] > price]
        risk_prod = at_risk["total_new_well_production_bbl_d"].sum()
        rows.append(
            {
                "wti_price": price,
                "production_at_risk_bbl_d": risk_prod,
                "pct_at_risk": (risk_prod / total_production * 100) if total_production > 0 else 0,
                "basins_at_risk": len(at_risk),
            }
        )

    return pd.DataFrame(rows)
