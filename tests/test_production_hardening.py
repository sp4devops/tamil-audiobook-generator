from __future__ import annotations

import json
import multiprocessing as mp
import sys
import threading
import time
import types
import unicodedata
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tamil_audiobook import controlled_engine, engine
from tamil_audiobook.generation_controls import OmniVoiceGenerationControls
from tamil_audiobook.locking import GenerationLock
from tamil_audiobook.prosody import prosody_for_chunk
from tamil_audiobook.speech import _grapheme_clusters, _hard_split


def _tone(seconds: float = 1.2, rate: int = 24000) -> np.ndarray:
    t = np.arange(int(seconds * rate), dtype=np.float32) / rate
    return (0.12 * np.sin(2 * np.pi * 180 * t)).astype(np.float32)


def _hold_generation_lock(root: str, ready, release) -> None:
    lock = GenerationLock(Path(root))
    ready.send(lock.try_acquire())
    release.recv()
    lock.release()


def test_generation_lock_is_interprocess_and_advisory(tmp_path: Path):
    root = tmp_path / "library"
    root.mkdir()
    ready_parent, ready_child = mp.Pipe()
    release_parent, release_child = mp.Pipe()
    process = mp.Process(target=_hold_generation_lock, args=(str(root), ready_child, release_child))
    process.start()
    try:
        assert ready_parent.recv() is True
        competing = GenerationLock(root)
        assert competing.try_acquire() is False
        release_parent.send(True)
        process.join(timeout=5)
        assert process.exitcode == 0
        assert competing.try_acquire() is True
        competing.release()
    finally:
        if process.is_alive():
            release_parent.send(True)
            process.join(timeout=2)
            if process.is_alive():
                process.terminate()


def _write_flac(path: Path, rate: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, _tone(rate=rate), rate, format="FLAC", subtype="PCM_16")


def test_corrupt_middle_checkpoint_is_deleted_but_surrounding_chunks_survive(tmp_path: Path):
    checkpoint_dir = tmp_path / "chunks"
    checkpoint_dir.mkdir()
    (checkpoint_dir / "manifest.json").write_text(
        json.dumps({"key": "same", "total_chunks": 3}), encoding="utf-8"
    )
    first = checkpoint_dir / "chunk_00000.flac"
    middle = checkpoint_dir / "chunk_00001.flac"
    last = checkpoint_dir / "chunk_00002.flac"
    _write_flac(first)
    middle.write_bytes(b"fLaC" + b"corrupt" * 80)
    _write_flac(last)

    assert engine._prepare_checkpoint_dir(checkpoint_dir, "same", 3) == 1
    assert engine.is_valid_checkpoint(first, 24000)
    assert not middle.exists()
    assert engine.is_valid_checkpoint(last, 24000)


def test_checkpoint_reuse_rejects_wrong_sample_rate(tmp_path: Path):
    path = tmp_path / "chunk.flac"
    _write_flac(path, 16000)
    assert engine.is_valid_checkpoint(path)
    assert not engine.is_valid_checkpoint(path, 24000)


def test_crossfade_changes_only_assembly_identity(tmp_path: Path):
    reference = tmp_path / "reference.wav"
    sf.write(reference, _tone(), 24000)
    common = dict(
        text="வணக்கம் Kubernetes உலகம்",
        reference_audio=reference,
        reference_text="வணக்கம் this is reference",
        num_steps=20,
        guidance_scale=2.5,
        target_chars=140,
        max_chars=220,
        pronunciation_signature="sig",
    )
    key_a = engine._checkpoint_key(**common, crossfade_ms=20)
    key_b = engine._checkpoint_key(**common, crossfade_ms=120)
    assert key_a == key_b
    assert engine._assembly_key(synthesis_key=key_a, crossfade_ms=20) != engine._assembly_key(
        synthesis_key=key_b, crossfade_ms=120
    )


def test_tamil_grapheme_hard_split_preserves_combining_clusters():
    token = ("கா" + "க்" + "கி" + "கூ") * 12
    chunks = _hard_split(token, 9)
    assert "".join(chunks) == token
    assert all(len(chunk) <= 9 for chunk in chunks)
    expected_clusters = _grapheme_clusters(token)
    rebuilt_clusters = [cluster for chunk in chunks for cluster in _grapheme_clusters(chunk)]
    assert rebuilt_clusters == expected_clusters
    assert all(not unicodedata.category(chunk[0]).startswith("M") for chunk in chunks)
    assert all(not chunk.startswith("\u0bcd") for chunk in chunks)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("தமிழ் இலக்கியத்தின் வரலாற்றை விரிவாக ஆராய்கிறோம்.", "neutral"),
        ("தரவுத்தளத்தில் குறியீட்டு அமைப்பு மற்றும் சேமிப்பு செயல்திறன் விளக்கப்படுகிறது.", "neutral"),
        ("என்னடா மச்சி, இவ்வளவு நேரம் எங்கே போன?", "tamil-conversational"),
        ("machi enna da, server ready ah?", "tanglish-conversational"),
        ("மச்சி Kubernetes deploy பண்ணலாமா?", "mixed-question"),
    ],
)
def test_conversational_detection_is_lexical_not_substring(text: str, expected: str):
    boundary = "question" if text.endswith("?") else "continuation"
    assert prosody_for_chunk(text, boundary).name == expected


def test_controlled_syntheses_keep_independent_controls_and_cache_signatures(monkeypatch):
    captured: list[tuple[dict, str]] = []
    capture_lock = threading.Lock()

    fake_utils = types.ModuleType("mlx_audio.tts.utils")
    fake_utils.load_model = lambda *args, **kwargs: object()
    monkeypatch.setitem(sys.modules, "mlx_audio", types.ModuleType("mlx_audio"))
    monkeypatch.setitem(sys.modules, "mlx_audio.tts", types.ModuleType("mlx_audio.tts"))
    monkeypatch.setitem(sys.modules, "mlx_audio.tts.utils", fake_utils)

    def fake_synthesize(**kwargs):
        wrapped = kwargs["model_loader"]("model")
        with capture_lock:
            captured.append((wrapped._controls.as_dict(), kwargs["checkpoint_salt"]))
        time.sleep(0.02)
        return {"chunk_reports": []}

    monkeypatch.setattr(controlled_engine.base_engine, "synthesize_audiobook", fake_synthesize)
    controls_a = OmniVoiceGenerationControls(class_temperature=0.1, t_shift=0.05)
    controls_b = OmniVoiceGenerationControls(class_temperature=0.8, t_shift=0.25)
    threads = [
        threading.Thread(target=controlled_engine.synthesize_audiobook_with_controls, kwargs={"controls": controls_a}),
        threading.Thread(target=controlled_engine.synthesize_audiobook_with_controls, kwargs={"controls": controls_b}),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(captured) == 2
    temperatures = {item[0]["class_temperature"] for item in captured}
    signatures = {item[1] for item in captured}
    assert temperatures == {0.1, 0.8}
    assert len(signatures) == 2


def _install_fake_prompt_modules(monkeypatch) -> None:
    modules = {
        "mlx_audio": types.ModuleType("mlx_audio"),
        "mlx_audio.tts": types.ModuleType("mlx_audio.tts"),
        "mlx_audio.tts.models": types.ModuleType("mlx_audio.tts.models"),
        "mlx_audio.tts.models.omnivoice": types.ModuleType("mlx_audio.tts.models.omnivoice"),
        "mlx_audio.tts.models.omnivoice.utils": types.ModuleType("mlx_audio.tts.models.omnivoice.utils"),
    }
    modules["mlx_audio.tts.models.omnivoice.utils"].create_voice_clone_prompt = (
        lambda *args, **kwargs: np.ones(8, dtype=np.int32)
    )
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


class _FakeResult:
    def __init__(self):
        self.audio = _tone(0.15)
        self.sample_rate = 24000


class _FakeModel:
    sample_rate = 24000
    audio_tokenizer = object()

    def generate(self, **kwargs):
        yield _FakeResult()


def test_cooperative_cancellation_keeps_completed_checkpoint_resumable(tmp_path: Path, monkeypatch):
    _install_fake_prompt_modules(monkeypatch)
    reference = tmp_path / "reference.wav"
    sf.write(reference, _tone(), 24000)
    checkpoints = tmp_path / "chunks"
    calls = {"progress": 0}

    def cancel_check() -> bool:
        return calls["progress"] >= 1

    def progress(payload: dict) -> None:
        if payload.get("stage") == "synthesizing" and payload.get("completed_chunks") == 1:
            calls["progress"] += 1

    with pytest.raises(engine.GenerationCancelled):
        engine.synthesize_audiobook(
            text=("வணக்கம் இது ஒரு நீளமான சோதனை வாக்கியம். " * 20),
            reference_audio=reference,
            reference_text="வணக்கம் exact reference transcript",
            output_wav=tmp_path / "partial.wav",
            checkpoint_dir=checkpoints,
            target_chars=70,
            max_chars=90,
            generation_mode="fast",
            model_loader=lambda *args, **kwargs: _FakeModel(),
            progress_callback=progress,
            cancel_check=cancel_check,
        )
    assert engine.is_valid_checkpoint(checkpoints / "chunk_00000.flac", 24000)
