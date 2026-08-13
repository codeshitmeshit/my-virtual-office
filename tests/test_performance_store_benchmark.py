import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tests" / "performance_store_benchmark.py"


def load_module():
    spec = importlib.util.spec_from_file_location("performance_store_benchmark", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_comparison_reports_speedup_and_regression_without_hiding_sign():
    module = load_module()
    faster = module.comparison({"medianMs": 4.0}, {"medianMs": 1.0})
    slower = module.comparison({"medianMs": 1.0}, {"medianMs": 2.0})
    assert faster["medianSpeedup"] == 4.0
    assert faster["medianLatencyReductionPct"] == 75.0
    assert slower["medianSpeedup"] == 0.5
    assert slower["medianLatencyReductionPct"] == -100.0


def test_smoke_benchmark_covers_all_declared_hot_paths():
    module = load_module()
    agent = module.benchmark_agent(20, runs=2, warmups=0)
    meeting = module.benchmark_meeting(1, runs=2, warmups=0)
    assert set(agent) >= {"append", "scopedQuery", "bytes"}
    assert set(meeting) >= {"eventAppend", "targetDetailRead", "bytes"}
    for operation in (agent["append"], agent["scopedQuery"], meeting["eventAppend"], meeting["targetDetailRead"]):
        assert operation["legacyJson"]["runs"] == 2
        assert operation["sqlite"]["runs"] == 2
