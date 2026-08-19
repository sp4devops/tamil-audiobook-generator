from __future__ import annotations

import inspect

from tamil_audiobook import app as app_module


def test_web_generation_uses_controlled_omnivoice_path():
    source = inspect.getsource(app_module._generate)
    assert "synthesize_audiobook_with_controls" in source
    assert "controls=OmniVoiceGenerationControls()" in source
