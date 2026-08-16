from pathlib import Path


def test_stage2_contract_is_explicit():
    text = Path('README.md').read_text(encoding='utf-8')
    assert 'RTF <= 2.0' in text
    assert '3 GiB' in text
    assert 'human quality gate' in text.lower()
