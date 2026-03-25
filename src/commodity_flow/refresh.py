"""Data refresh pipeline — fetch, validate, and report on all data sources.

Provides a single entry point to refresh all live data, validate schemas
and magnitudes, and report any issues before downstream analysis runs.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from commodity_flow import config, eia, synthetic
from commodity_flow.provenance import DataSource, ProvenanceTracker


@dataclass
class ValidationResult:
    """Result of a single validation check."""

    name: str
    passed: bool
    detail: str = ""


class RefreshPipeline:
    """Fetch all data sources, validate schemas and magnitudes, track provenance."""

    def __init__(self) -> None:
        self.provenance = ProvenanceTracker()
        self.validations: list[ValidationResult] = []
        self.data: dict[str, pd.DataFrame] = {}

    def run(self) -> dict[str, pd.DataFrame]:
        """Execute the full refresh: fetch → validate → return data dict."""
        self._load_all()
        self._validate_all()
        return self.data

    def _load_all(self) -> None:
        """Load all datasets from live API or synthetic fallback."""
        live = config.USE_LIVE_API and config.EIA_API_KEY is not None

        # Crude imports
        if live:
            df = eia.fetch_crude_imports_by_padd(config.EIA_API_KEY)
            self.provenance.record(
                DataSource(
                    "Crude imports",
                    "EIA API v2",
                    "petroleum/move/imp",
                    True,
                    rows=len(df),
                    date_range=f"{df['date'].min().date()} to {df['date'].max().date()}"
                    if not df.empty
                    else "",
                )
            )
        else:
            df = synthetic.generate_synthetic_imports()
            self.provenance.record(
                DataSource(
                    "Crude imports",
                    "Simulated (published values)",
                    "synthetic generator",
                    False,
                    rows=len(df),
                )
            )
        self.data["imports"] = df

        # Weekly stocks
        if live:
            df = eia.fetch_weekly_stocks(config.EIA_API_KEY)
            self.provenance.record(
                DataSource(
                    "Weekly stocks",
                    "EIA API v2",
                    "petroleum/stoc/wstk",
                    True,
                    rows=len(df),
                    notes="Total petroleum by PADD (crude-only not available at PADD level)",
                )
            )
        else:
            df = synthetic.generate_synthetic_stocks()
            self.provenance.record(
                DataSource(
                    "Weekly stocks",
                    "Simulated (published values)",
                    "synthetic generator",
                    False,
                    rows=len(df),
                )
            )
        self.data["stocks"] = df

        # STEO
        if live:
            df = eia.fetch_steo_projections(config.EIA_API_KEY)
            self.provenance.record(
                DataSource(
                    "STEO projections",
                    "EIA API v2",
                    "steo",
                    True,
                    rows=len(df),
                )
            )
        else:
            df = synthetic.generate_synthetic_steo()
            self.provenance.record(
                DataSource(
                    "STEO projections",
                    "Simulated (published values)",
                    "synthetic generator",
                    False,
                    rows=len(df),
                )
            )
        self.data["steo"] = df

        # NatGas imports
        if live:
            df = eia.fetch_natgas_imports(config.EIA_API_KEY)
            self.provenance.record(
                DataSource(
                    "NatGas imports",
                    "EIA API v2",
                    "natural-gas/move/poe1",
                    True,
                    rows=len(df),
                    notes="Pipeline + LNG split (Bcf)",
                )
            )
        else:
            df = synthetic.generate_synthetic_natgas_imports()
            self.provenance.record(
                DataSource(
                    "NatGas imports",
                    "Simulated (published values)",
                    "synthetic generator",
                    False,
                    rows=len(df),
                )
            )
        self.data["natgas"] = df

        # Helium (always synthetic)
        df = synthetic.generate_synthetic_helium()
        self.provenance.record(
            DataSource(
                "Helium supply/demand",
                "USGS MCS (manual entry)",
                "synthetic generator",
                False,
                rows=len(df),
                notes="USGS publishes annual PDFs, no API",
            )
        )
        self.data["helium"] = df

        # Breakevens (always synthetic)
        df = synthetic.generate_synthetic_breakevens()
        self.provenance.record(
            DataSource(
                "Basin breakevens",
                "Dallas/KC Fed Surveys (manual entry)",
                "synthetic generator",
                False,
                rows=len(df),
                notes="Q4 2024 survey values; no public API",
            )
        )
        self.data["breakevens"] = df

        # DPR (always synthetic — not in EIA API)
        df = synthetic.generate_synthetic_dpr()
        self.provenance.record(
            DataSource(
                "Drilling productivity",
                "EIA DPR (manual entry)",
                "synthetic generator",
                False,
                rows=len(df),
                notes="DPR not in EIA API v2; baselined to Feb 2025 values",
            )
        )
        self.data["dpr"] = df

    def _check(self, name: str, condition: bool, detail: str = "") -> None:
        self.validations.append(ValidationResult(name, condition, detail))

    def _validate_all(self) -> None:
        """Run all validation checks against loaded data."""
        self._validate_imports()
        self._validate_stocks()
        self._validate_natgas()
        self._validate_steo()
        self._validate_helium()
        self._validate_breakevens()
        self._validate_dpr()

    def _validate_imports(self) -> None:
        df = self.data["imports"]

        # Schema
        required = {"date", "value", "duoarea"}
        self._check(
            "imports:schema",
            required.issubset(df.columns),
            f"Missing: {required - set(df.columns)}" if not required.issubset(df.columns) else "",
        )

        if df.empty:
            self._check("imports:not_empty", False, "Zero rows returned")
            return

        # All 5 PADDs
        padds = set(df["duoarea"].unique())
        self._check("imports:all_padds", padds == set(config.PADDS.keys()), f"Found: {padds}")

        # Monthly national total in range
        monthly = df.groupby("date")["value"].sum()
        avg = monthly.mean()
        self._check("imports:magnitude", 120_000 <= avg <= 280_000, f"{avg:,.0f} MBBL/mo")

        # PADD 2 dominant
        padd_avg = df.groupby("duoarea")["value"].mean()
        self._check(
            "imports:padd2_largest", padd_avg.idxmax() == "PADD 2", f"Largest: {padd_avg.idxmax()}"
        )

        # No negative values
        self._check("imports:non_negative", (df["value"] >= 0).all())

    def _validate_stocks(self) -> None:
        df = self.data["stocks"]
        if df.empty:
            self._check("stocks:not_empty", False)
            return

        required = {"date", "value", "duoarea"}
        self._check("stocks:schema", required.issubset(df.columns))

        latest = df.groupby("duoarea")["value"].last()
        total = latest.sum()
        self._check("stocks:magnitude", 500_000 <= total <= 2_000_000, f"{total:,.0f} MBBL total")

        self._check(
            "stocks:padd3_largest", latest.idxmax() == "PADD 3", f"Largest: {latest.idxmax()}"
        )

    def _validate_natgas(self) -> None:
        df = self.data["natgas"]
        if df.empty:
            self._check("natgas:not_empty", False)
            return

        modes = set(df["mode"].unique())
        self._check("natgas:modes", {"Pipeline", "LNG"}.issubset(modes), f"Found: {modes}")

        pipeline_avg = df[df["mode"] == "Pipeline"]["value_bcf"].mean()
        self._check(
            "natgas:pipeline_range", 150 <= pipeline_avg <= 400, f"{pipeline_avg:.0f} Bcf/mo"
        )

        lng_avg = df[df["mode"] == "LNG"]["value_bcf"].mean()
        self._check("natgas:lng_near_zero", lng_avg < 15, f"{lng_avg:.1f} Bcf/mo")

    def _validate_steo(self) -> None:
        df = self.data["steo"]
        if df.empty:
            self._check("steo:not_empty", False)
            return

        self._check("steo:has_series_id", "series_id" in df.columns)

        if "series_id" in df.columns:
            series = set(df["series_id"].unique())
            self._check("steo:has_conipus", "CONIPUS" in series, f"Found: {series}")

    def _validate_helium(self) -> None:
        df = self.data["helium"]
        self._check("helium:has_rows", len(df) > 0)
        if not df.empty:
            self._check("helium:production_range", df["us_production_Mcm"].between(30, 70).all())

    def _validate_breakevens(self) -> None:
        df = self.data["breakevens"]
        self._check("breakevens:has_rows", len(df) > 0)
        if not df.empty:
            basins = set(df["basin"].unique())
            self._check(
                "breakevens:all_basins", basins == set(config.BASINS.keys()), f"Found: {basins}"
            )
            self._check("breakevens:range", df["breakeven_usd_bbl"].between(15, 80).all())

    def _validate_dpr(self) -> None:
        df = self.data["dpr"]
        self._check("dpr:has_rows", len(df) > 0)
        if not df.empty:
            self._check("dpr:positive_rigs", (df["rig_count"] > 0).all())

    def report(self) -> str:
        """Generate a text report of all validation results."""
        lines = ["DATA REFRESH VALIDATION REPORT", "=" * 50]
        passed = sum(1 for v in self.validations if v.passed)
        total = len(self.validations)
        lines.append(f"Results: {passed}/{total} passed\n")

        for v in self.validations:
            status = "PASS" if v.passed else "FAIL"
            line = f"  [{status}] {v.name}"
            if v.detail:
                line += f" — {v.detail}"
            lines.append(line)

        lines.append("")
        lines.append("DATA PROVENANCE")
        lines.append("-" * 50)
        for fn in self.provenance.footnotes():
            lines.append(f"  {fn}")

        return "\n".join(lines)

    @property
    def all_passed(self) -> bool:
        return all(v.passed for v in self.validations)
