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
