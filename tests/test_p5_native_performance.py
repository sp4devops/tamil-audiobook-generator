from __future__ import annotations

from tamil_audiobook.pronunciation import apply_pronunciation_overrides, load_overrides
from tamil_audiobook.prosody import PROSODY_VERSION, prosody_for_chunk


def test_p6_prosody_version_is_bumped():
    assert PROSODY_VERSION >= 3


def test_formal_tamil_keeps_neutral_accepted_baseline():
    profile = prosody_for_chunk(
        "தமிழ்மொழியின் செழுமை அதன் இலக்கிய மரபில் வெளிப்படுகிறது.",
        "sentence",
    )
    assert profile.name == "neutral"
    assert profile.instruct == "None"


def test_colloquial_tamil_english_gets_indian_code_switch_delivery():
    profile = prosody_for_chunk(
        "மச்சி, அந்த server மறுபடியும் down ஆயிடுச்சு டா.",
        "sentence",
    )
    assert profile.name == "mixed-conversational"
    assert "South-Indian English" in profile.instruct
    assert "American or British accent" in profile.instruct
    assert "same speaker identity" in profile.instruct


def test_romanized_tanglish_gets_indian_code_switch_delivery():
    profile = prosody_for_chunk(
        "Machi, intha query romba slow ah irukku; first check pannalaam.",
        "sentence",
    )
    assert profile.name == "tanglish-conversational"
    assert "South-Indian English" in profile.instruct
    assert "Tamil phrase rhythm" in profile.instruct


def test_mixed_dialogue_keeps_indian_code_switch_profile():
    profile = prosody_for_chunk('“டேய், server மீண்டும் down ஆயிடுச்சு.”', "sentence")
    assert profile.name == "mixed-dialogue"
    assert "South-Indian English" in profile.instruct
    assert "same speaker identity" in profile.instruct


def test_mixed_question_keeps_indian_code_switch_profile():
    profile = prosody_for_chunk(
        "இந்த deploy உண்மையிலேயே safe-ஆ இருக்கா?",
        "question",
    )
    assert profile.name == "mixed-question"
    assert "Tamil question contour" in profile.instruct
    assert "American or British accent" in profile.instruct


def test_mixed_exclamation_keeps_indian_code_switch_profile():
    profile = prosody_for_chunk(
        "அட, deployment live ஆயிடுச்சு!",
        "exclamation",
    )
    assert profile.name == "mixed-exclamation"
    assert "Tamil conversational cadence" in profile.instruct
    assert "South-Indian English" in profile.instruct


def test_pure_english_question_is_not_forced_into_indian_code_switch_profile():
    profile = prosody_for_chunk("What happened to the database?", "question")
    assert profile.name == "question"
    assert "South-Indian English" not in profile.instruct


def test_pure_tamil_dialogue_is_not_forced_into_code_switch_profile():
    profile = prosody_for_chunk('“மச்சி, என்னடா நடந்தது?”', "question")
    assert profile.name == "dialogue"
    assert "South-Indian English" not in profile.instruct


def test_tanglish_tokens_are_normalized_only_for_model_facing_text():
    source = "Machi, naan backup eduthuttu varen; nee meanwhile ready pannidu."
    result = apply_pronunciation_overrides(source, load_overrides())
    assert source.startswith("Machi")
    assert "மச்சி" in result.text
    assert "நான்" in result.text
    assert "நீ" in result.text
    assert "meanwhile" in result.text
    assert set(result.applied) >= {"Machi", "naan", "nee"}


def test_technical_override_survives_tamil_suffix_attachment():
    result = apply_pronunciation_overrides(
        "API-ஐ check பண்ணு; MongoDB-க்கு reconnect பண்ணு.",
        load_overrides(),
    )
    assert "A P I-ஐ" in result.text
    assert "Mongo D B-க்கு" in result.text
    assert result.applied[:2] == ("API", "MongoDB")


def test_technical_overrides_are_case_insensitive():
    result = apply_pronunciation_overrides("mongodb api cpu", load_overrides())
    assert result.text == "Mongo D B A P I C P U"
    assert result.applied == ("mongodb", "api", "cpu")
