"""Data provenance tracking — records source, freshness, and limitations for each dataset."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DataSource:
    """Metadata about a loaded dataset."""

    name: str
    source: str  # "EIA API v2", "Offline (published values)", "Yahoo Finance", etc.
    endpoint: str  # API route or "offline generator"
    live: bool
    fetched_at: datetime = field(default_factory=datetime.now)
    rows: int = 0
    date_range: str = ""
    notes: str = ""


class ProvenanceTracker:
    """Collects provenance records for all datasets in a session."""

    def __init__(self) -> None:
        self._sources: list[DataSource] = []

    def record(self, source: DataSource) -> None:
        self._sources.append(source)

    @property
    def sources(self) -> list[DataSource]:
        return list(self._sources)

    def summary(self) -> str:
        """Markdown-formatted provenance summary for notebook footnotes."""
        if not self._sources:
            return "_No data sources recorded._"

        lines = ["| Dataset | Source | Live? | Rows | Date Range | Notes |"]
        lines.append("|---------|--------|-------|------|------------|-------|")

        for s in self._sources:
            live_icon = "Y" if s.live else "Offline"
            lines.append(
                f"| {s.name} | {s.source} | {live_icon} | {s.rows:,} | {s.date_range} | {s.notes} |"
            )

        ts = max(s.fetched_at for s in self._sources).strftime("%Y-%m-%d %H:%M")
        lines.append("")
        lines.append(f"_Data loaded at {ts}._")

        live_count = sum(1 for s in self._sources if s.live)
        offline_count = sum(1 for s in self._sources if not s.live)
        if offline_count > 0:
            lines.append("")
            lines.append(
                f"_**{live_count} live** and **{offline_count} offline** data sources in this run._"
            )
            offline_names = [s.name for s in self._sources if not s.live]
            lines.append(
                f"_Offline: {', '.join(offline_names)}. "
                "Offline data calibrated from published values. "
                "Set `USE_LIVE_API=true` and configure API keys to use live data._"
            )

        return "\n".join(lines)

    def footnotes(self) -> list[str]:
        """Return per-dataset footnote strings for chart annotations."""
        notes = []
        for s in self._sources:
            tag = "LIVE" if s.live else "OFFLINE"
            note = f"[{tag}] {s.name}: {s.source}"
            if s.endpoint != "offline generator":
                note += f" ({s.endpoint})"
            if s.notes:
                note += f" — {s.notes}"
            notes.append(note)
        return notes
