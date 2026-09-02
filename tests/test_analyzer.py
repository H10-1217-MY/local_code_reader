from app.analyzer import analyze_source


def test_python_static_analysis():
    source = '''import os\nfrom pathlib import Path\n\nclass Reader:\n    def read(self, path):\n        return Path(path).read_text()\n\ndef load(path):\n    return Reader().read(path)\n'''
    result = analyze_source("sample.py", source)
    assert result["language"] == "Python"
    assert "os" in result["imports"]

    reader = next(c for c in result["classes"] if c["name"] == "Reader")
    assert reader["line"] == 4
    assert reader["end_line"] == 6

    method = next(f for f in result["functions"] if f["qualified_name"] == "Reader.read")
    assert method["kind"] == "method"
    assert method["line"] == 5
    assert method["end_line"] == 6
    assert "Path.read_text" in method["calls"]

    load = next(f for f in result["functions"] if f["name"] == "load")
    assert load["line"] == 8
    assert load["end_line"] == 9
    assert "Reader" in load["calls"]
