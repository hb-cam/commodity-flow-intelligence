"""Tests for data provenance tracker."""

from datetime import datetime

from commodity_flow.provenance import DataSource, ProvenanceTracker


class TestProvenanceTracker:
    def test_empty_summary(self) -> None:
        prov = ProvenanceTracker()
        assert "No data sources recorded" in prov.summary()

    def test_single_live_source(self) -> None:
        prov = ProvenanceTracker()
        prov.record(DataSource("Imports", "EIA API v2", "petroleum/move/imp", True, rows=240))
        summary = prov.summary()
        assert "Imports" in summary
        assert "EIA API v2" in summary
        assert "240" in summary
        assert "Y" in summary  # live indicator

    def test_single_offline_source(self) -> None:
        prov = ProvenanceTracker()
        prov.record(DataSource("Helium", "Offline (published values)", "offline generator", False, rows=9))
        summary = prov.summary()
        assert "Offline" in summary
        assert "Helium" in summary

    def test_mixed_sources_footer(self) -> None:
        prov = ProvenanceTracker()
        prov.record(DataSource("A", "EIA", "route1", True, rows=100))
        prov.record(DataSource("B", "Offline (published values)", "offline generator", False, rows=50))
        prov.record(DataSource("C", "EIA", "route2", True, rows=200))
        summary = prov.summary()
        assert "**2 live**" in summary
        assert "**1 offline**" in summary
        assert "B" in summary  # offline name listed

    def test_all_live_no_offline_footer(self) -> None:
        prov = ProvenanceTracker()
        prov.record(DataSource("A", "EIA", "route1", True, rows=100))
        summary = prov.summary()
        # Should not have the offline warning
        assert "offline" not in summary.lower() or "0 offline" in summary

    def test_footnotes_live_tag(self) -> None:
        prov = ProvenanceTracker()
        prov.record(DataSource("Imports", "EIA API v2", "petroleum/move/imp", True))
        notes = prov.footnotes()
        assert len(notes) == 1
        assert "[LIVE]" in notes[0]
        assert "petroleum/move/imp" in notes[0]

    def test_footnotes_offline_tag(self) -> None:
        prov = ProvenanceTracker()
        prov.record(DataSource("Helium", "Offline (published values)", "offline generator", False))
        notes = prov.footnotes()
        assert "[OFFLINE]" in notes[0]
        # Offline generators should not show endpoint in parens
        assert "(offline generator)" not in notes[0]

    def test_timestamp_uses_latest_source(self) -> None:
        prov = ProvenanceTracker()
        early = datetime(2026, 1, 1, 10, 0)
        late = datetime(2026, 3, 25, 15, 30)
        prov.record(DataSource("A", "EIA", "r1", True, fetched_at=early, rows=1))
        prov.record(DataSource("B", "EIA", "r2", True, fetched_at=late, rows=1))
        summary = prov.summary()
        assert "2026-03-25" in summary

    def test_sources_property_returns_copy(self) -> None:
        prov = ProvenanceTracker()
        prov.record(DataSource("A", "EIA", "r1", True, rows=1))
        sources = prov.sources
        sources.clear()  # mutate the returned list
        assert len(prov.sources) == 1  # original should be unaffected

    def test_notes_included_in_summary(self) -> None:
        prov = ProvenanceTracker()
        prov.record(
            DataSource(
                "Stocks", "EIA", "stoc", True, rows=50, notes="Total petroleum, not crude-only"
            )
        )
        summary = prov.summary()
        assert "Total petroleum" in summary
