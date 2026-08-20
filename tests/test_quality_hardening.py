from __future__ import annotations

import inspect
import json
from pathlib import Path

from tamil_audiobook import controlled_engine, engine


def test_model_is_immutably_pinned_and_cache_records_revision(tmp_path: Path):
    assert engine.MODEL_ID == "mlx-community/OmniVoice-bfloat16"
    assert len(engine.MODEL_REVISION) == 40
    assert all(ch in "0123456789abcdef" for ch in engine.MODEL_REVISION)

    checkpoint_dir = tmp_path / "chunks"
    engine._prepare_checkpoint_dir(checkpoint_dir, "key", 1)
    manifest = json.loads((checkpoint_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["model_id"] == engine.MODEL_ID
    assert manifest["model_revision"] == engine.MODEL_REVISION

    source = inspect.getsource(engine.synthesize_audiobook)
    assert "model_loader(MODEL_ID, revision=MODEL_REVISION)" in source


def test_controlled_engine_uses_explicit_injection_not_global_monkey_patch():
    source = inspect.getsource(controlled_engine.synthesize_audiobook_with_controls)
    assert "model_loader=controlled_load_model" in source
    assert "checkpoint_salt=" in source
    assert "tts_utils.load_model =" not in source
    assert "base_engine._checkpoint_key =" not in source


def test_report_semantics_do_not_claim_listening_quality_pass():
    source = inspect.getsource(engine.synthesize_audiobook)
    assert '"status": "GENERATED"' in source
    assert '"quality_status": "UNREVIEWED"' in source
    assert '"status": "PASS"' not in source


def test_progressive_frontend_has_one_absolute_playback_position_contract():
    static_root = Path(__file__).parents[1] / "tamil_audiobook" / "static"
    progressive = (static_root / "progressive.js").read_text(encoding="utf-8")
    index = (static_root / "index.html").read_text(encoding="utf-8")

    assert "provisionalChunkText" not in progressive
    assert "splitSentences" not in progressive
    assert "estimateChunkSeconds" not in progressive
    assert "openBook =" not in progressive
    assert "loadBook =" not in progressive
    assert "canonicalPlaybackPosition" in progressive
    assert "state.playbackPosition = canonicalPlaybackPosition" in progressive
    assert "chunkOffset(partial.index) + Number(audio.currentTime" in progressive
    assert "duration: bookDuration()" in progressive
    assert "persistCanonicalProgress" in progressive
    assert "seconds: position.seconds" in progressive
    assert "duration: position.duration" in progressive
    assert "audio.onended =" not in progressive
    assert "MutationObserver" in progressive
    assert index.index('/static/app.js') < index.index('/static/progressive.js')
