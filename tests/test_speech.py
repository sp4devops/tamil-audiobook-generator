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


def test_p2_does_not_merge_across_language_profile_changes():
    units = plan_speech_units(
        "இது முழுக்க தமிழ் வாக்கியம். This sentence is entirely English.",
        target_chars=140,
        max_chars=220,
    )
    assert len(units) == 2
    assert units[0].profile == "tamil"
    assert units[1].profile == "english"


def test_p2_semantic_contrast_gets_a_real_boundary_in_long_sentence():
    text = (
        "இந்த service காலை முழுவதும் சரியாக வேலை செய்தது ஆனால் traffic திடீரென அதிகரித்ததும் "
        "latency மிகவும் உயர்ந்தது அதனால் முதலில் logs மற்றும் database pool இரண்டையும் பார்க்க வேண்டும்."
    )
    units = plan_speech_units(text, target_chars=70, max_chars=110)
    assert len(units) >= 2
    assert any(unit.boundary in {"clause", "clause-strong"} for unit in units[:-1])
    assert " ".join(unit.text for unit in units).replace("  ", " ") == text


def test_p2_dialogue_lines_are_not_folded_into_one_model_request():
    text = '“என்ன நடந்தது?”\n“Server மீண்டும் down ஆயிடுச்சு.”'
    units = plan_speech_units(text, target_chars=140, max_chars=220)
    assert len(units) == 2
    assert units[0].boundary == "question"
    assert units[1].boundary == "paragraph"


def test_p2_list_items_remain_separate_turns():
    text = "- முதலில் logs பார்க்கவும்\n- பின்னர் database pool பார்க்கவும்\n- கடைசியாக memory usage பார்க்கவும்"
    units = plan_speech_units(text, target_chars=140, max_chars=220)
    assert len(units) == 3
    assert all(unit.text.startswith("-") for unit in units)


def test_p2_balances_unpunctuated_long_sentence_near_target_not_only_maximum():
    text = " ".join(f"word{i}" for i in range(45))
    units = plan_speech_units(text, target_chars=70, max_chars=120)
    lengths = [len(unit.text) for unit in units]
    assert len(units) >= 3
    assert max(lengths) <= 120
    assert sum(length <= 95 for length in lengths) >= len(lengths) - 1
    assert " ".join(unit.text for unit in units) == text
