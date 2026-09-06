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


def test_javascript_declared_functions_only():
    source = '''
function showError(message) { return message; }
const loadStatus = async () => { return fetch("/api/status"); };
items.forEach(item => console.log(item));
byId("x").addEventListener("click", () => {});
class Reader {}
'''
    result = analyze_source("static/app.js", source)
    names = {f["name"] for f in result["functions"]}
    assert "showError" in names
    assert "loadStatus" in names
    assert "forEach" not in names
    assert "byId" not in names
    assert {c["name"] for c in result["classes"]} == {"Reader"}


def test_css_media_is_not_function():
    source = '''
:root { --space: 8px; }
.card { padding: var(--space); }
@media (max-width: 800px) {
  .card { padding: 4px; }
}
'''
    result = analyze_source("static/style.css", source)
    assert result["functions"] == []
    assert any(x.startswith("@media") for x in result["css_at_rules"])
    assert "--space" in result["css_custom_properties"]
    assert ".card" in result["css_selectors"]


def test_python_external_dependencies_exclude_stdlib():
    source = '''import os\nfrom pathlib import Path\nfrom fastapi import FastAPI\nimport requests\nfrom .config import OLLAMA_MODEL\n'''
    result = analyze_source("app/main.py", source)
    assert set(result["detected_external_dependencies"]) == {"fastapi", "requests"}


def test_html_local_references_are_collected():
    source = '''<link rel="stylesheet" href="/static/style.css"><script src="/static/app.js"></script>'''
    result = analyze_source("templates/index.html", source)
    assert "/static/style.css" in result["references"]
    assert "/static/app.js" in result["references"]
