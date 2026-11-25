from scripts.summarize_optimizer_benchmark import summarize


def test_summary_mentions_all_methods_and_overloaded_case_without_claiming_optimality():
    def run(method, minutes):
        return {
            "scenario": "overloaded",
            "method": method,
            "scheduled_minutes": str(minutes),
            "due_coverage_pct": "50",
            "runtime_ms": "5.2",
            "constraint_violations": "0",
        }

    output = summarize([run("greedy_rebuild", 60), run("throughput", 80)])
    assert "throughput | 1 | 80" in output
    assert "overloaded: throughput: +20 min" in output
    assert "not completed assignments" in output
