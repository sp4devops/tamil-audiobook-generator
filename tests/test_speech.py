from tamil_audiobook.engine import chunk_text, detect_language
from tamil_audiobook.speech import classify_language, looks_tanglish, plan_speech_units


def test_tanglish_detector_is_conservative_but_handles_colloquial_tamil():
    assert looks_tanglish("enna da idhu")
    assert looks_tanglish("seri machi, poitu varen")
    assert not looks_tanglish("this server is running normally")


def test_tanglish_is_not_forced_through_english_language_mode():
    language, profile = classify_language("enna da idhu, server down aayiducha?")
    assert language == "None"
    assert profile == "tanglish"
    assert detect_language("seri machi") == "None"


def test_mixed_script_stays_in_multilingual_mode():
    language, profile = classify_language("டேய், Kubernetes மறுபடியும் crash ஆயிடுச்சா?")
    assert language == "None"
    assert profile == "mixed-script"


def test_native_planner_preserves_questions_as_prosodic_boundaries():
    units = plan_speech_units(
        "டேய், என்னடா இது? Kubernetes மறுபடியும் crash ஆயிடுச்சா? சரி, logs முதல்ல பார்ப்போம்.",
        target_chars=80,
        max_chars=120,
    )
    assert len(units) >= 3
    assert units[0].boundary == "question"
    assert units[1].boundary == "question"
    assert units[-1].boundary in {"sentence", "paragraph"}


def test_long_sentence_prefers_clause_boundaries_before_hard_splitting():
    text = (
        "இந்த service சரியாக வேலை செய்தது, ஆனால் traffic அதிகமானதும் latency உயர்ந்தது, "
        "அதனால் முதலில் logs பார்க்க வேண்டும், பின்னர் database connection pool சரிபார்க்க வேண்டும்."
    )
    units = plan_speech_units(text, target_chars=60, max_chars=90)
    assert len(units) > 1
    assert all(len(unit.text) <= 90 for unit in units)
    rebuilt = " ".join(unit.text for unit in units)
    assert "latency" in rebuilt
    assert "database connection pool" in rebuilt


def test_existing_chunk_api_exposes_speech_diagnostics_without_breaking_contract():
    chunks = chunk_text("இது தமிழ் உரை. This is English text.", target_chars=20, max_chars=60)
    assert chunks
    assert all(chunk.text for chunk in chunks)
    assert all(chunk.language in {"tamil", "english", "None"} for chunk in chunks)
    assert all(chunk.speech_profile for chunk in chunks)
    assert all(chunk.boundary for chunk in chunks)
