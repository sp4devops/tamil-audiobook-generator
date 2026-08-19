from __future__ import annotations

import json
from pathlib import Path

BENCHMARK = Path(__file__).resolve().parents[1] / "benchmarks" / "tamil_voice_quality.json"


def _load() -> dict:
    return json.loads(BENCHMARK.read_text(encoding="utf-8"))


def test_benchmark_is_permanent_versioned_human_gate():
    data = _load()
    assert data["benchmark"] == "tamil-voice-quality"
    assert int(data["version"]) >= 1
    assert data["human_gate"] is True
    assert len(data["cases"]) >= 20


def test_benchmark_has_required_quality_categories():
    data = _load()
    required = set(data["required_categories"])
    present = {case["category"] for case in data["cases"]}
    assert required <= present
    assert {
        "formal_tamil",
        "colloquial_tamil",
        "chennai_conversational",
        "kongu_conversational",
        "english",
        "tanglish",
        "code_switching",
        "technical",
        "numbers",
        "names",
        "dialogue",
        "questions",
        "emotion",
    } <= present


def test_benchmark_cases_are_unique_and_actionable():
    data = _load()
    ids = [case["id"] for case in data["cases"]]
    assert len(ids) == len(set(ids))
    for case in data["cases"]:
        assert case["text"].strip()
        assert case["tags"]
        assert case["listen_for"]


def test_benchmark_contains_real_script_and_code_switch_stress():
    texts = "\n".join(case["text"] for case in _load()["cases"])
    assert any("\u0b80" <= char <= "\u0bff" for char in texts)
    assert "MongoDB" in texts
    assert "PostgreSQL" in texts
    assert "Kubernetes" in texts
    assert "₹" in texts
    assert "?" in texts
    assert "!" in texts
