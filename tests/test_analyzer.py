from app.analyzer import analyze_source


def test_python_static_analysis():
    source = '''import os\nfrom pathlib import Path\n\nclass Reader:\n    pass\n\ndef load(path):\n    return Path(path).read_text()\n'''
    result = analyze_source("sample.py", source)
    assert result["language"] == "Python"
    assert "os" in result["imports"]
    assert any(c["name"] == "Reader" for c in result["classes"])
    assert any(f["name"] == "load" for f in result["functions"])
