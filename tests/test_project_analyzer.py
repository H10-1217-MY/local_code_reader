from app.project_analyzer import build_project_index


def test_local_python_relative_import_edges():
    files = [
        {
            "file": {"path": "app/main.py", "language": "Python", "line_count": 10, "char_count": 100},
            "static_analysis": {"imports": ["from .analyzer import analyze_source", "from .config import OLLAMA_MODEL"]},
            "analysis": {},
        },
        {
            "file": {"path": "app/analyzer.py", "language": "Python", "line_count": 20, "char_count": 200},
            "static_analysis": {"imports": []},
            "analysis": {},
        },
        {
            "file": {"path": "app/config.py", "language": "Python", "line_count": 5, "char_count": 50},
            "static_analysis": {"imports": []},
            "analysis": {},
        },
    ]

    index = build_project_index(files)
    edges = {(edge["source"], edge["target"]) for edge in index["local_dependency_edges"]}
    assert ("app/main.py", "app/analyzer.py") in edges
    assert ("app/main.py", "app/config.py") in edges
    assert index["file_count"] == 3
    assert index["total_lines"] == 35

from app.analyzer import analyze_source
from app.project_analyzer import build_structure_only_analysis, classify_project_content


def test_empty_init_is_skipped():
    decision = classify_project_content("app/__init__.py", "")
    assert decision["mode"] == "skip"


def test_simple_init_is_structure_only():
    source = 'from .analyzer import analyze_source\n__all__ = ["analyze_source"]\n'
    decision = classify_project_content("app/__init__.py", source)
    assert decision["mode"] == "structure"


def test_init_with_runtime_logic_uses_llm():
    source = 'from .analyzer import analyze_source\nprint("boot")\n'
    decision = classify_project_content("app/__init__.py", source)
    assert decision["mode"] == "llm"


def test_requirements_are_structure_only_and_extract_packages():
    source = "fastapi>=0.116\nuvicorn[standard]>=0.35\n# comment\n"
    decision = classify_project_content("requirements.txt", source)
    assert decision["mode"] == "structure"
    static = analyze_source("requirements.txt", source)
    analysis = build_structure_only_analysis("requirements.txt", source, static)
    assert "fastapi" in analysis["external_dependencies"]
    assert "uvicorn" in analysis["external_dependencies"]


def test_processing_counts_are_in_project_index():
    files = [
        {"file": {"path": "app/main.py", "language": "Python", "line_count": 2, "char_count": 10}, "processing": {"mode": "llm"}, "static_analysis": {"imports": []}, "analysis": {}},
        {"file": {"path": "requirements.txt", "language": "Text", "line_count": 1, "char_count": 5}, "processing": {"mode": "structure"}, "static_analysis": {"imports": []}, "analysis": {}},
    ]
    index = build_project_index(files)
    assert index["processing_counts"] == {"llm": 1, "structure": 1}

from app.project_analyzer import sanitize_project_analysis, sanitize_project_files


def test_project_index_collects_static_external_dependencies():
    files = [
        {
            "file": {"path": "main.py", "language": "Python", "line_count": 3, "char_count": 40},
            "processing": {"mode": "llm"},
            "static_analysis": {"language": "Python", "imports": ["from fastapi import FastAPI", "import os", "from .config import X"], "functions": [], "classes": []},
            "analysis": {},
        },
        {
            "file": {"path": "config.py", "language": "Python", "line_count": 1, "char_count": 5},
            "processing": {"mode": "llm"},
            "static_analysis": {"language": "Python", "imports": [], "functions": [], "classes": []},
            "analysis": {},
        },
    ]
    index = build_project_index(files)
    assert index["external_dependencies"] == ["fastapi"]
    assert "main.py" in index["paths"]


def test_sanitize_project_files_removes_fake_symbols_and_related_files():
    files = [
        {
            "file": {"path": "main.py", "language": "Python", "line_count": 5, "char_count": 50},
            "processing": {"mode": "llm"},
            "static_analysis": {
                "language": "Python",
                "imports": ["from fastapi import FastAPI", "from .config import X"],
                "functions": [{"name": "main", "qualified_name": "main"}],
                "classes": [{"name": "App", "qualified_name": "App"}],
            },
            "analysis": {
                "key_functions": [{"name": "main", "role": "ok"}, {"name": "imaginary", "role": "bad"}],
                "key_classes": [{"name": "Ghost", "role": "bad"}],
                "related_files": ["config.py", "missing.py"],
                "external_dependencies": ["FastAPI", "made-up-sdk"],
            },
        },
        {
            "file": {"path": "config.py", "language": "Python", "line_count": 2, "char_count": 10},
            "processing": {"mode": "llm"},
            "static_analysis": {"language": "Python", "imports": [], "functions": [], "classes": []},
            "analysis": {},
        },
    ]
    index = build_project_index(files)
    grounded, report = sanitize_project_files(files, index)
    analysis = grounded[0]["analysis"]
    assert [x["name"] for x in analysis["key_functions"]] == ["main"]
    assert analysis["key_classes"] == []
    assert analysis["related_files"] == ["config.py"]
    assert analysis["external_dependencies"] == ["fastapi"]
    assert report["removed_claim_count"] >= 3


def test_sanitize_project_analysis_rejects_nonexistent_paths():
    index = {
        "paths": ["main.py", "static/app.js"],
        "external_dependencies": ["fastapi", "requests"],
    }
    raw = {
        "purpose": "コード読解ツール",
        "overview": "main.py と frontend.js が連携する",
        "architecture_flow": ["main.py がAPIを提供", "frontend.js が表示"],
        "entry_points": [{"path": "main.py", "reason": "API"}, {"path": "frontend.js", "reason": "UI"}],
        "components": [{"path": "app.js", "role": "UI"}],
        "external_dependencies": ["fake-sdk"],
        "config_and_data_files": ["README.md"],
        "read_first": [{"path": "README.md", "reason": "docs"}],
        "change_risks": ["frontend.js の変更に注意", "main.py の変更に注意"],
        "unknowns": [],
    }
    clean, report = sanitize_project_analysis(raw, index)
    assert clean["entry_points"] == [{"path": "main.py", "reason": "API"}]
    assert clean["components"] == [{"path": "static/app.js", "role": "UI"}]
    assert clean["read_first"] == []
    assert clean["external_dependencies"] == ["fastapi", "requests"]
    assert clean["architecture_flow"] == ["main.py がAPIを提供"]
    assert clean["change_risks"] == ["main.py の変更に注意"]
    assert report["removed_claim_count"] >= 4


def test_html_reference_creates_local_dependency_edge():
    files = [
        {
            "file": {"path": "templates/index.html", "language": "HTML", "line_count": 1, "char_count": 20},
            "processing": {"mode": "llm"},
            "static_analysis": {"language": "HTML", "imports": [], "references": ["/static/app.js"], "functions": [], "classes": []},
            "analysis": {},
        },
        {
            "file": {"path": "static/app.js", "language": "JavaScript", "line_count": 1, "char_count": 20},
            "processing": {"mode": "llm"},
            "static_analysis": {"language": "JavaScript", "imports": [], "references": [], "functions": [], "classes": []},
            "analysis": {},
        },
    ]
    index = build_project_index(files)
    edges = {(e["source"], e["target"]) for e in index["local_dependency_edges"]}
    assert ("templates/index.html", "static/app.js") in edges


def test_sanitize_project_files_preserves_metadata_and_adds_verified_facts():
    files = [
        {
            "file": {"path": "main.py", "language": "Python", "line_count": 2, "char_count": 20},
            "processing": {"mode": "llm"},
            "static_analysis": {"language": "Python", "imports": ["import requests"], "functions": [{"name": "main", "qualified_name": "main"}], "classes": []},
            "analysis": {"key_functions": [{"name": "main", "role": "entry"}], "key_classes": [], "related_files": ["config.py"], "external_dependencies": ["fake-sdk"]},
            "model": "qwen3:14b",
            "metrics": {"eval_count": 12},
            "grounding": {"removed_claim_count": 1},
        },
        {
            "file": {"path": "config.py", "language": "Python", "line_count": 1, "char_count": 5},
            "processing": {"mode": "llm"},
            "static_analysis": {"language": "Python", "imports": [], "functions": [], "classes": []},
            "analysis": {},
            "model": "qwen3:14b",
        },
    ]
    index = build_project_index(files)
    grounded, _ = sanitize_project_files(files, index)
    first = grounded[0]
    assert first["model"] == "qwen3:14b"
    assert first["metrics"]["eval_count"] == 12
    assert first["verified_facts"]["external_dependencies"] == ["requests"]
    assert first["verified_facts"]["related_files"] == ["config.py"]
    assert first["analysis"]["external_dependencies"] == ["requests"]
