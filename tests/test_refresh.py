"""Tests for the data refresh pipeline."""

from commodity_flow.refresh import RefreshPipeline


class TestRefreshPipelineOffline:
    """Run refresh pipeline in offline mode (no API key needed)."""

    def setup_method(self) -> None:
        self.pipeline = RefreshPipeline()
        self.data = self.pipeline.run()

    def test_all_datasets_loaded(self) -> None:
        expected = {"imports", "stocks", "steo", "natgas", "helium", "breakevens", "dpr"}
        assert expected == set(self.data.keys())

    def test_all_validations_pass(self) -> None:
        failures = [v for v in self.pipeline.validations if not v.passed]
        if failures:
            details = "\n".join(f"  {v.name}: {v.detail}" for v in failures)
            raise AssertionError(f"Validation failures:\n{details}")

    def test_provenance_records_all_sources(self) -> None:
        assert len(self.pipeline.provenance.sources) == 7

    def test_report_generates_text(self) -> None:
        report = self.pipeline.report()
        assert "VALIDATION REPORT" in report
        assert "PROVENANCE" in report

    def test_all_passed_property(self) -> None:
        assert self.pipeline.all_passed
