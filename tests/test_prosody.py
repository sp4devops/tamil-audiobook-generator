from tamil_audiobook.prosody import PROSODY_VERSION, prosody_for_chunk


def test_ordinary_narration_keeps_accepted_baseline_instruction():
    profile = prosody_for_chunk("The server recovered normally.", "sentence")
    assert profile.name == "neutral"
    assert profile.instruct == "None"


def test_dialogue_gets_restrained_conversational_instruction():
    profile = prosody_for_chunk('“டேய், server மீண்டும் down ஆயிடுச்சு.”', "sentence")
    assert profile.name == "dialogue"
    assert "same speaker identity" in profile.instruct


def test_question_gets_questioning_instruction_when_not_dialogue():
    profile = prosody_for_chunk("What happened to the database?", "question")
    assert profile.name == "question"
    assert "questioning intonation" in profile.instruct


def test_exclamation_gets_only_slight_emphasis():
    profile = prosody_for_chunk("The deployment is live!", "exclamation")
    assert profile.name == "exclamation"
    assert "Slightly emphatic" in profile.instruct


def test_heading_and_list_roles_are_detected_before_boundary_style():
    heading = prosody_for_chunk("Chapter 4: Recovery", "sentence")
    item = prosody_for_chunk("- Check MongoDB health", "sentence")
    assert heading.name == "heading"
    assert item.name == "list"


def test_prosody_version_is_explicit_for_checkpoint_invalidation():
    assert PROSODY_VERSION >= 1
