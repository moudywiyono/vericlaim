"""
Phase 4 — LLMOps tests.

Covers:
  - PromptRegistry: register, get, hash, dedup
  - TraceStore: record_generation writes correct fields, record_node carries new metadata
  - SuiteResult: to_dict / save / load roundtrip
  - SystemHealthReport: computed from synthetic JSONL traces
  - CostLatencyReport: per-node and per-model aggregation
  - ExperimentsReport: delta computation and Markdown rendering
  - QualityTrendsReport: trend aggregation from result files
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# PromptRegistry
# ---------------------------------------------------------------------------

class TestPromptRegistry:
    def test_register_and_get(self) -> None:
        from orchestration.llmops.prompt_registry import PromptRegistry
        r = PromptRegistry()
        vp = r.register("test_prompt", "v1", "Hello, {name}!")
        assert vp.name == "test_prompt"
        assert vp.version == "v1"
        assert vp.template == "Hello, {name}!"
        assert len(vp.hash) == 16

        fetched = r.get("test_prompt")
        assert fetched == vp

    def test_hash_is_deterministic(self) -> None:
        from orchestration.llmops.prompt_registry import hash_text
        h1 = hash_text("same text")
        h2 = hash_text("same text")
        assert h1 == h2

    def test_different_texts_have_different_hashes(self) -> None:
        from orchestration.llmops.prompt_registry import hash_text
        assert hash_text("text A") != hash_text("text B")

    def test_get_missing_raises_keyerror(self) -> None:
        from orchestration.llmops.prompt_registry import PromptRegistry
        r = PromptRegistry()
        with pytest.raises(KeyError):
            r.get("nonexistent")

    def test_register_overwrites_existing(self) -> None:
        from orchestration.llmops.prompt_registry import PromptRegistry
        r = PromptRegistry()
        r.register("p", "v1", "original")
        r.register("p", "v2", "updated")
        assert r.get("p").version == "v2"
        assert r.get("p").template == "updated"

    def test_list_names(self) -> None:
        from orchestration.llmops.prompt_registry import PromptRegistry
        r = PromptRegistry()
        r.register("b", "v1", "B")
        r.register("a", "v1", "A")
        assert r.list_names() == ["a", "b"]

    def test_len(self) -> None:
        from orchestration.llmops.prompt_registry import PromptRegistry
        r = PromptRegistry()
        r.register("x", "v1", "X")
        r.register("y", "v1", "Y")
        assert len(r) == 2

    def test_module_level_register_and_get(self) -> None:
        import orchestration.llmops.prompt_registry as pr
        pr.register("_test_module_level", "v1", "module level template")
        vp = pr.get("_test_module_level")
        assert vp.template == "module level template"


# ---------------------------------------------------------------------------
# TraceStore — record_generation
# ---------------------------------------------------------------------------

class TestTraceStoreGeneration:
    def test_record_generation_writes_correct_fields(self, tmp_path: Path) -> None:
        from orchestration.persistence.trace_store import TraceStore
        ts = TraceStore(trace_dir=tmp_path)
        ts.record_generation(
            claim_id="claim_gen_001",
            node_name="adjudicator",
            model="claude-haiku-4-5-20251001",
            prompt_hash="abc123def456",
            input_tokens=512,
            output_tokens=256,
            cost_usd=0.00045,
            claim_type="auto",
            severity_bucket="moderate",
        )
        events = ts.read_trace("claim_gen_001")
        assert len(events) == 1
        e = events[0]
        assert e["event"] == "llm_generation"
        assert e["node_name"] == "adjudicator"
        assert e["model"] == "claude-haiku-4-5-20251001"
        assert e["prompt_hash"] == "abc123def456"
        assert e["input_tokens"] == 512
        assert e["output_tokens"] == 256
        assert e["cost_usd"] == pytest.approx(0.00045)
        assert e["claim_type"] == "auto"
        assert e["severity_bucket"] == "moderate"

    def test_record_generation_omits_optional_fields_when_absent(self, tmp_path: Path) -> None:
        from orchestration.persistence.trace_store import TraceStore
        ts = TraceStore(trace_dir=tmp_path)
        ts.record_generation(
            claim_id="claim_gen_002",
            node_name="policy_reasoner",
            model="claude-haiku-4-5-20251001",
            prompt_hash="deadbeef1234",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.0001,
        )
        events = ts.read_trace("claim_gen_002")
        assert "claim_type" not in events[0]
        assert "severity_bucket" not in events[0]

    def test_record_node_carries_model_and_prompt_hash(self, tmp_path: Path) -> None:
        from orchestration.persistence.trace_store import TraceStore
        ts = TraceStore(trace_dir=tmp_path)
        ts.record_node(
            claim_id="claim_node_001",
            node_name="adjudicator",
            attempt=1,
            status="success",
            elapsed_ms=1200,
            cost_usd=0.002,
            model_used="claude-sonnet-4-6",
            prompt_hash="ff00aa11bb22",
            claim_type="property",
            severity_bucket="severe",
        )
        events = ts.read_trace("claim_node_001")
        assert events[0]["model_used"] == "claude-sonnet-4-6"
        assert events[0]["prompt_hash"] == "ff00aa11bb22"
        assert events[0]["claim_type"] == "property"
        assert events[0]["severity_bucket"] == "severe"



# ---------------------------------------------------------------------------
# SuiteResult — serialization roundtrip
# ---------------------------------------------------------------------------

class TestSuiteResultSerialization:
    def _make_result(self) -> object:
        from evals.runners.base import SuiteResult
        return SuiteResult(
            suite_name="damage_assessor_component_eval",
            dataset_path=Path("evals/datasets/component/damage_assessor"),
            metrics={"macro_f1_severity": 0.82, "mape_cost": 0.15},
            cost_usd=0.0034,
            latency_p50_ms=450,
            latency_p95_ms=900,
            n_samples=10,
            n_failures=1,
            prompt_hashes={"damage_system": "abc123"},
            timestamp=datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc),
            notes="Phase 4 test run",
        )

    def test_to_dict_has_required_keys(self) -> None:
        result = self._make_result()
        d = result.to_dict()  # type: ignore[union-attr]
        for key in ("suite_name", "metrics", "cost_usd", "latency_p50_ms",
                    "n_samples", "n_failures", "prompt_hashes", "timestamp"):
            assert key in d

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        from evals.runners.base import SuiteResult
        result = self._make_result()
        path = tmp_path / "result.json"
        result.save(path)  # type: ignore[union-attr]

        loaded = SuiteResult.load(path)
        assert loaded.suite_name == result.suite_name  # type: ignore[union-attr]
        assert loaded.metrics == result.metrics  # type: ignore[union-attr]
        assert loaded.cost_usd == pytest.approx(result.cost_usd)  # type: ignore[union-attr]
        assert loaded.n_samples == result.n_samples  # type: ignore[union-attr]
        assert loaded.prompt_hashes == result.prompt_hashes  # type: ignore[union-attr]

    def test_load_creates_parent_dirs(self, tmp_path: Path) -> None:
        result = self._make_result()
        deep_path = tmp_path / "nested" / "dir" / "result.json"
        result.save(deep_path)  # type: ignore[union-attr]
        assert deep_path.exists()


# ---------------------------------------------------------------------------
# SystemHealthReport
# ---------------------------------------------------------------------------

def _write_trace(trace_dir: Path, claim_id: str, events: list[dict]) -> None:
    path = trace_dir / f"{claim_id}.jsonl"
    with path.open("w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


class TestSystemHealth:
    def test_empty_trace_dir_returns_zero_report(self, tmp_path: Path) -> None:
        from evals.dashboards.system_health import system_health
        report = system_health(tmp_path)
        assert report.n_claims == 0
        assert report.auto_approve_rate == 0.0

    def test_nonexistent_dir_returns_zero_report(self, tmp_path: Path) -> None:
        from evals.dashboards.system_health import system_health
        report = system_health(tmp_path / "missing")
        assert report.n_claims == 0

    def test_single_claim_auto_approve(self, tmp_path: Path) -> None:
        from evals.dashboards.system_health import system_health
        _write_trace(tmp_path, "claim_001", [
            {"event": "node_execution", "claim_id": "claim_001", "node_name": "adjudicator",
             "status": "success", "elapsed_ms": 800, "cost_usd": 0.002},
            {"event": "claim_state_transition", "claim_id": "claim_001", "state": "complete"},
        ])
        report = system_health(tmp_path)
        assert report.n_claims == 1
        assert report.auto_approve_rate == pytest.approx(1.0)
        assert report.human_review_rate == pytest.approx(0.0)
        assert report.e2e_latency_p50_ms == pytest.approx(800.0)
        assert report.cost_per_claim_mean_usd == pytest.approx(0.002)

    def test_mixed_outcomes(self, tmp_path: Path) -> None:
        from evals.dashboards.system_health import system_health
        _write_trace(tmp_path, "claim_A", [
            {"event": "node_execution", "claim_id": "claim_A", "node_name": "adjudicator",
             "status": "success", "elapsed_ms": 1000, "cost_usd": 0.003},
            {"event": "claim_state_transition", "claim_id": "claim_A", "state": "complete"},
        ])
        _write_trace(tmp_path, "claim_B", [
            {"event": "node_execution", "claim_id": "claim_B", "node_name": "adjudicator",
             "status": "partial", "elapsed_ms": 500, "cost_usd": 0.001},
            {"event": "claim_state_transition", "claim_id": "claim_B", "state": "human_review"},
        ])
        report = system_health(tmp_path)
        assert report.n_claims == 2
        assert report.auto_approve_rate == pytest.approx(0.5)
        assert report.human_review_rate == pytest.approx(0.5)

    def test_error_rate_counts_failed_and_timeout(self, tmp_path: Path) -> None:
        from evals.dashboards.system_health import system_health
        _write_trace(tmp_path, "claim_ok", [
            {"event": "node_execution", "claim_id": "claim_ok", "node_name": "damage_assessor",
             "status": "success", "elapsed_ms": 200, "cost_usd": 0.0},
        ])
        _write_trace(tmp_path, "claim_fail", [
            {"event": "node_execution", "claim_id": "claim_fail", "node_name": "damage_assessor",
             "status": "failed", "elapsed_ms": 50, "cost_usd": 0.0},
        ])
        report = system_health(tmp_path)
        assert report.error_rate == pytest.approx(0.5)

    def test_per_node_latency_populated(self, tmp_path: Path) -> None:
        from evals.dashboards.system_health import system_health
        _write_trace(tmp_path, "claim_multi", [
            {"event": "node_execution", "claim_id": "claim_multi", "node_name": "damage_assessor",
             "status": "success", "elapsed_ms": 300, "cost_usd": 0.0},
            {"event": "node_execution", "claim_id": "claim_multi", "node_name": "adjudicator",
             "status": "success", "elapsed_ms": 700, "cost_usd": 0.001},
        ])
        report = system_health(tmp_path)
        assert "damage_assessor" in report.per_node_latency_p50_ms
        assert "adjudicator" in report.per_node_latency_p50_ms
        assert report.per_node_latency_p50_ms["damage_assessor"] == pytest.approx(300.0)

    def test_llm_generation_cost_aggregated(self, tmp_path: Path) -> None:
        from evals.dashboards.system_health import system_health
        _write_trace(tmp_path, "claim_gen", [
            {"event": "node_execution", "claim_id": "claim_gen", "node_name": "adjudicator",
             "status": "success", "elapsed_ms": 500, "cost_usd": 0.001},
            {"event": "llm_generation", "claim_id": "claim_gen", "node_name": "adjudicator",
             "model": "claude-haiku-4-5-20251001", "cost_usd": 0.0005,
             "input_tokens": 100, "output_tokens": 50},
        ])
        report = system_health(tmp_path)
        # node_execution cost (0.001) + llm_generation cost (0.0005) = 0.0015
        assert report.cost_per_claim_mean_usd == pytest.approx(0.0015)

    def test_to_dict_is_json_serializable(self, tmp_path: Path) -> None:
        from evals.dashboards.system_health import system_health
        _write_trace(tmp_path, "claim_s", [
            {"event": "node_execution", "claim_id": "claim_s", "node_name": "adjudicator",
             "status": "success", "elapsed_ms": 100, "cost_usd": 0.001},
        ])
        report = system_health(tmp_path)
        serialized = json.dumps(report.to_dict())
        assert isinstance(serialized, str)


# ---------------------------------------------------------------------------
# CostLatencyReport
# ---------------------------------------------------------------------------

class TestCostLatency:
    def test_empty_dir(self, tmp_path: Path) -> None:
        from evals.dashboards.cost_latency import cost_latency
        report = cost_latency(tmp_path)
        assert report.total_claims == 0
        assert report.total_cost_usd == pytest.approx(0.0)

    def test_per_node_aggregation(self, tmp_path: Path) -> None:
        from evals.dashboards.cost_latency import cost_latency
        _write_trace(tmp_path, "cla", [
            {"event": "node_execution", "claim_id": "cla", "node_name": "damage_assessor",
             "status": "success", "elapsed_ms": 400, "cost_usd": 0.001},
            {"event": "node_execution", "claim_id": "cla", "node_name": "adjudicator",
             "status": "success", "elapsed_ms": 800, "cost_usd": 0.005},
        ])
        report = cost_latency(tmp_path)
        node_names = {n.node_name for n in report.per_node}
        assert "damage_assessor" in node_names
        assert "adjudicator" in node_names
        adj = next(n for n in report.per_node if n.node_name == "adjudicator")
        assert adj.total_cost_usd == pytest.approx(0.005)
        assert adj.latency_p50_ms == pytest.approx(800.0)

    def test_per_model_from_generation_events(self, tmp_path: Path) -> None:
        from evals.dashboards.cost_latency import cost_latency
        _write_trace(tmp_path, "clm", [
            {"event": "llm_generation", "claim_id": "clm", "node_name": "adjudicator",
             "model": "claude-haiku-4-5-20251001", "cost_usd": 0.002,
             "input_tokens": 200, "output_tokens": 100},
            {"event": "llm_generation", "claim_id": "clm", "node_name": "policy_reasoner",
             "model": "claude-haiku-4-5-20251001", "cost_usd": 0.003,
             "input_tokens": 300, "output_tokens": 150},
        ])
        report = cost_latency(tmp_path)
        assert len(report.per_model) == 1
        m = report.per_model[0]
        assert m.model == "claude-haiku-4-5-20251001"
        assert m.n_calls == 2
        assert m.total_cost_usd == pytest.approx(0.005)
        assert m.total_input_tokens == 500
        assert m.total_output_tokens == 250

    def test_to_dict_caps_scatter(self, tmp_path: Path) -> None:
        from evals.dashboards.cost_latency import cost_latency
        # write 300 claims
        for i in range(300):
            _write_trace(tmp_path, f"claim_{i:04d}", [
                {"event": "node_execution", "claim_id": f"claim_{i:04d}", "node_name": "adjudicator",
                 "status": "success", "elapsed_ms": 100, "cost_usd": 0.001},
            ])
        report = cost_latency(tmp_path)
        assert len(report.to_dict()["claim_scatter"]) <= 200


# ---------------------------------------------------------------------------
# ExperimentsReport
# ---------------------------------------------------------------------------

class TestExperimentsDelta:
    def _baseline(self) -> dict:
        return {
            "suite_name": "damage_assessor_component_eval",
            "metrics": {"macro_f1_severity": 0.80, "mape_cost": 0.20},
            "cost_usd": 0.010,
            "latency_p50_ms": 500,
            "latency_p95_ms": 900,
            "n_samples": 20,
            "timestamp": "2026-05-01T00:00:00+00:00",
            "prompt_hashes": {"damage_system": "old_hash_abc"},
        }

    def _candidate(self) -> dict:
        return {
            "suite_name": "damage_assessor_component_eval",
            "metrics": {"macro_f1_severity": 0.85, "mape_cost": 0.18},
            "cost_usd": 0.012,
            "latency_p50_ms": 480,
            "latency_p95_ms": 850,
            "n_samples": 20,
            "timestamp": "2026-05-09T00:00:00+00:00",
            "prompt_hashes": {"damage_system": "new_hash_xyz"},
        }

    def test_positive_deltas_detected(self) -> None:
        from evals.dashboards.experiments import experiments_delta
        report = experiments_delta(self._baseline(), self._candidate())
        f1_delta = next(d for d in report.metric_deltas if d.metric == "macro_f1_severity")
        assert f1_delta.delta == pytest.approx(0.05)
        assert f1_delta.pct_change == pytest.approx(6.25)

    def test_cost_delta_positive_when_candidate_costs_more(self) -> None:
        from evals.dashboards.experiments import experiments_delta
        report = experiments_delta(self._baseline(), self._candidate())
        assert report.cost_delta_usd == pytest.approx(0.002)

    def test_changed_prompt_hashes_detected(self) -> None:
        from evals.dashboards.experiments import experiments_delta
        report = experiments_delta(self._baseline(), self._candidate())
        assert "damage_system" in report.changed_prompt_hashes
        assert report.changed_prompt_hashes["damage_system"] == ("old_hash_abc", "new_hash_xyz")

    def test_unchanged_prompts_not_in_changed(self) -> None:
        from evals.dashboards.experiments import experiments_delta
        b = self._baseline()
        c = self._candidate()
        b["prompt_hashes"]["shared"] = "same"
        c["prompt_hashes"]["shared"] = "same"
        report = experiments_delta(b, c)
        assert "shared" not in report.changed_prompt_hashes

    def test_regression_count(self) -> None:
        from evals.dashboards.experiments import experiments_delta
        c = self._candidate()
        c["metrics"]["macro_f1_severity"] = 0.70  # regression
        report = experiments_delta(self._baseline(), c)
        assert report.regression_count >= 1

    def test_improvement_count(self) -> None:
        from evals.dashboards.experiments import experiments_delta
        report = experiments_delta(self._baseline(), self._candidate())
        assert report.improvement_count >= 1

    def test_to_dict_is_json_serializable(self) -> None:
        from evals.dashboards.experiments import experiments_delta
        report = experiments_delta(self._baseline(), self._candidate())
        serialized = json.dumps(report.to_dict())
        assert isinstance(serialized, str)

    def test_to_markdown_contains_suite_name(self) -> None:
        from evals.dashboards.experiments import experiments_delta
        report = experiments_delta(self._baseline(), self._candidate())
        md = report.to_markdown()
        assert "damage_assessor_component_eval" in md


# ---------------------------------------------------------------------------
# QualityTrendsReport
# ---------------------------------------------------------------------------

class TestQualityTrends:
    def test_empty_dir(self, tmp_path: Path) -> None:
        from evals.dashboards.quality_trends import quality_trends
        report = quality_trends(tmp_path)
        assert report.trends == {}
        assert report.latest == {}

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        from evals.dashboards.quality_trends import quality_trends
        report = quality_trends(tmp_path / "missing")
        assert report.trends == {}

    def test_reads_single_result_file(self, tmp_path: Path) -> None:
        from evals.dashboards.quality_trends import quality_trends
        data = {
            "suite_name": "damage_assessor_component_eval",
            "metrics": {"macro_f1_severity": 0.82},
            "cost_usd": 0.005,
            "n_samples": 10,
            "n_failures": 0,
            "prompt_hashes": {},
            "timestamp": "2026-05-09T10:00:00+00:00",
        }
        (tmp_path / "result.json").write_text(json.dumps(data))
        report = quality_trends(tmp_path)
        assert "damage_assessor_component_eval" in report.trends
        assert len(report.trends["damage_assessor_component_eval"]) == 1
        assert report.latest["damage_assessor_component_eval"]["macro_f1_severity"] == pytest.approx(0.82)

    def test_multiple_results_sorted_chronologically(self, tmp_path: Path) -> None:
        from evals.dashboards.quality_trends import quality_trends
        for ts, score in [("2026-05-01T00:00:00+00:00", 0.80), ("2026-05-09T00:00:00+00:00", 0.85)]:
            data = {
                "suite_name": "damage_assessor_component_eval",
                "metrics": {"macro_f1_severity": score},
                "cost_usd": 0.0,
                "n_samples": 10,
                "n_failures": 0,
                "prompt_hashes": {},
                "timestamp": ts,
            }
            (tmp_path / f"result_{ts[:10]}.json").write_text(json.dumps(data))
        report = quality_trends(tmp_path)
        points = report.trends["damage_assessor_component_eval"]
        assert points[0].metrics["macro_f1_severity"] == pytest.approx(0.80)
        assert points[1].metrics["macro_f1_severity"] == pytest.approx(0.85)
        assert report.latest["damage_assessor_component_eval"]["macro_f1_severity"] == pytest.approx(0.85)

    def test_sub_population_breakdown(self, tmp_path: Path) -> None:
        from evals.dashboards.quality_trends import quality_trends
        data = {
            "suite_name": "damage_assessor_component_eval",
            "metrics": {
                "macro_f1_severity": 0.82,
                "claim_type_auto_macro_f1_severity": 0.85,
                "claim_type_property_macro_f1_severity": 0.78,
            },
            "cost_usd": 0.0,
            "n_samples": 20,
            "n_failures": 0,
            "prompt_hashes": {},
            "timestamp": "2026-05-09T00:00:00+00:00",
        }
        (tmp_path / "result.json").write_text(json.dumps(data))
        report = quality_trends(tmp_path)
        assert "auto" in report.by_claim_type
        assert "property" in report.by_claim_type
        assert report.by_claim_type["auto"]["macro_f1_severity"] == pytest.approx(0.85)
        assert report.by_claim_type["property"]["macro_f1_severity"] == pytest.approx(0.78)

    def test_to_dict_is_json_serializable(self, tmp_path: Path) -> None:
        from evals.dashboards.quality_trends import quality_trends
        data = {
            "suite_name": "s", "metrics": {"m": 0.5}, "cost_usd": 0.0,
            "n_samples": 1, "n_failures": 0, "prompt_hashes": {},
            "timestamp": "2026-05-09T00:00:00+00:00",
        }
        (tmp_path / "r.json").write_text(json.dumps(data))
        report = quality_trends(tmp_path)
        serialized = json.dumps(report.to_dict())
        assert isinstance(serialized, str)
