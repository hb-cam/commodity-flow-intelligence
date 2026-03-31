"""Daily signal check — run via GitHub Actions or locally.

Fetches all data, validates, computes signals, and writes signal_result.json.
GitHub Actions workflow reads this file to decide whether to open an issue.

Usage:
    uv run python scripts/signal_check.py
"""

from __future__ import annotations

import json
import sys

from commodity_flow import analysis, charts, config, inventory
from commodity_flow.refresh import RefreshPipeline


def main() -> None:
    print("Running signal check...")
    print(f"  Live API: {config.USE_LIVE_API}")
    print(f"  EIA key: {'set' if config.EIA_API_KEY else 'missing'}")
    print()

    # Run full data pipeline with validation
    pipeline = RefreshPipeline()
    data = pipeline.run()

    if not pipeline.all_passed:
        failures = [v for v in pipeline.validations if not v.passed]
        print(f"WARNING: {len(failures)} validation failure(s):")
        for v in failures:
            print(f"  {v.name}: {v.detail}")
        print()

    # Build derived datasets
    scorecard = analysis.build_scorecard(data["imports"], data["natgas"], data["steo"])
    actual = scorecard[~scorecard["is_forecast"]]

    df_breakevens = data["breakevens"]

    # Get current WTI from live market; fall back to trailing average of offline data
    try:
        from commodity_flow import futures

        _fut = futures.fetch_futures_curves()
        current_wti = round(
            float(_fut[_fut["symbol"] == "CL=F"].sort_values("date").iloc[-1]["close"]), 2
        )
    except Exception:
        current_wti = round(float(df_breakevens["wti_price_usd_bbl"].tail(4).mean()), 2)

    status = analysis.compute_breakeven_status(df_breakevens, current_wti)

    # Inventory
    if config.USE_LIVE_API and config.EIA_API_KEY:
        try:
            df_prod_stocks = inventory.fetch_product_stocks(config.EIA_API_KEY)
            df_prod_supplied = inventory.fetch_product_supplied(config.EIA_API_KEY)
        except Exception as e:
            print(f"Inventory fetch failed: {e}. Using offline data.")
            inv_data = inventory.generate_offline_inventory()
            df_prod_stocks = inv_data["stocks"]
            df_prod_supplied = inv_data["supplied"]
    else:
        inv_data = inventory.generate_offline_inventory()
        df_prod_stocks = inv_data["stocks"]
        df_prod_supplied = inv_data["supplied"]

    df_dos = inventory.compute_days_of_supply(df_prod_stocks, df_prod_supplied)
    df_spr = inventory.compute_spr_status(df_prod_stocks)

    # Build signal table
    signal_table = charts.build_signal_table(
        scorecard, data["imports"], df_dos, df_spr, status, data["dpr"]
    )

    # Classify signals
    alerts = signal_table[signal_table["Status"].str.contains("\U0001f534")]
    warnings = signal_table[
        signal_table["Status"].str.contains("\u26a0\ufe0f")
    ]

    latest_z = actual["composite_gap_score"].iloc[-1] if not actual.empty else 0.0

    # Write result
    result = {
        "has_alerts": len(alerts) > 0,
        "has_warnings": len(warnings) > 0,
        "n_alerts": len(alerts),
        "n_warnings": len(warnings),
        "composite_z": round(float(latest_z), 2),
        "signals": signal_table.to_dict("records"),
    }

    with open("signal_result.json", "w") as f:
        json.dump(result, f, indent=2)

    # Summary
    print("SIGNAL CHECK RESULTS")
    print("=" * 50)
    for _, row in signal_table.iterrows():
        print(f"  {row['Status']:15s} {row['Signal']:25s} {row['Current']}")
    print()
    print(f"Composite gap score: {latest_z:.2f}\u03c3")
    print(f"Alerts: {len(alerts)} | Warnings: {len(warnings)}")
    print("Result written to signal_result.json")

    if len(alerts) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
