from unittest.mock import patch

from app.main import ProjectSummaryRequest, summarize_project


def test_project_summary_returns_grounded_files_not_raw_files():
    raw_files = [
        {
            "file": {"path": "main.py", "name": "main.py", "language": "Python", "line_count": 3, "char_count": 30},
            "processing": {"mode": "llm", "reason": "test"},
            "static_analysis": {
                "language": "Python",
                "imports": ["import requests"],
                "functions": [{"name": "main", "qualified_name": "main"}],
                "classes": [],
            },
            "analysis": {
                "purpose": "test",
                "overview": "test",
                "main_flow": [],
                "key_functions": [{"name": "imaginary", "role": "bad"}],
                "key_classes": [],
                "inputs": [],
                "outputs": [],
                "external_dependencies": ["fake-sdk"],
                "related_files": ["missing.py"],
                "change_risks": [],
                "unknowns": [],
            },
            "model": "qwen3:14b",
            "metrics": {"eval_count": 1},
        }
    ]
    fake_llm = {
        "model": "qwen3:14b",
        "analysis": {
            "purpose": "test project",
            "overview": "test",
            "architecture_flow": [],
            "entry_points": [{"path": "main.py", "reason": "entry"}],
            "components": [{"path": "main.py", "role": "app"}],
            "external_dependencies": ["fake"],
            "config_and_data_files": [],
            "read_first": [{"path": "main.py", "reason": "first"}],
            "change_risks": [],
            "unknowns": [],
        },
        "metrics": {},
    }
    with patch("app.main.analyze_project_with_ollama", return_value=fake_llm):
        result = summarize_project(ProjectSummaryRequest(project_name="demo", model="qwen3:14b", files=raw_files))

    assert "files" in result
    item = result["files"][0]
    assert item["analysis"]["key_functions"] == []
    assert item["analysis"]["external_dependencies"] == ["requests"]
    assert item["analysis"]["related_files"] == []
    assert item["verified_facts"]["external_dependencies"] == ["requests"]
    assert item["model"] == "qwen3:14b"
