from __future__ import annotations

import inspect
import json
from pathlib import Path

from tamil_audiobook import engine


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
    assert "load_model(MODEL_ID, revision=MODEL_REVISION)" in source


def test_report_semantics_do_not_claim_listening_quality_pass():
    source = inspect.getsource(engine.synthesize_audiobook)
    assert '"status": "GENERATED"' in source
    assert '"quality_status": "UNREVIEWED"' in source
    assert '"status": "PASS"' not in source


def test_progressive_frontend_avoids_global_monkey_patches_and_duplicate_chunker():
    static_root = Path(__file__).parents[1] / "tamil_audiobook" / "static"
    progressive = (static_root / "progressive.js").read_text(encoding="utf-8")
    index = (static_root / "index.html").read_text(encoding="utf-8")

    assert "provisionalChunkText" not in progressive
    assert "splitSentences" not in progressive
    assert "estimateChunkSeconds" not in progressive
    assert "openBook =" not in progressive
    assert "loadBook =" not in progressive
    assert "audio.ontimeupdate =" not in progressive
    assert "audio.onended =" not in progressive
    assert "MutationObserver" in progressive
    assert "audio.addEventListener('timeupdate'" in progressive
    assert index.index('/static/app.js') < index.index('/static/progressive.js')
