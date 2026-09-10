from app.main import ProjectDocsRequest, generate_project_docs
from app.project_docs import generate_project_documents


def _files():
    return [
        {
            "file": {"path": "main.py", "name": "main.py", "language": "Python", "line_count": 20, "char_count": 300},
            "processing": {"mode": "llm", "reason": "test"},
            "static_analysis": {
                "language": "Python",
                "imports": ["from .config import OLLAMA_BASE_URL", "from fastapi import FastAPI"],
                "functions": [
                    {
                        "name": "status",
                        "qualified_name": "status",
                        "line": 10,
                        "end_line": 12,
                        "decorators": ["app.get('/api/status')"],
                    }
                ],
                "classes": [],
                "top_level_assignments": ["app"],
                "environment_variables": [],
                "detected_external_dependencies": ["fastapi"],
            },
            "analysis": {
                "purpose": "API entry",
                "overview": "API entry",
                "main_flow": [],
                "key_functions": [{"name": "status", "role": "status"}],
                "key_classes": [],
                "inputs": [],
                "outputs": [],
                "external_dependencies": ["fastapi"],
                "related_files": ["config.py"],
                "change_risks": [],
                "unknowns": [],
            },
            "verified_facts": {"functions": ["status"], "classes": [], "external_dependencies": ["fastapi"], "related_files": ["config.py"]},
        },
        {
            "file": {"path": "config.py", "name": "config.py", "language": "Python", "line_count": 5, "char_count": 100},
            "processing": {"mode": "llm", "reason": "test"},
            "static_analysis": {
                "language": "Python",
                "imports": ["import os"],
                "functions": [],
                "classes": [],
                "top_level_assignments": ["OLLAMA_BASE_URL"],
                "environment_variables": ["OLLAMA_BASE_URL"],
                "detected_external_dependencies": [],
            },
            "analysis": {
                "purpose": "settings",
                "overview": "settings",
                "main_flow": [],
                "key_functions": [],
                "key_classes": [],
                "inputs": [],
                "outputs": [],
                "external_dependencies": [],
                "related_files": [],
                "change_risks": [],
                "unknowns": [],
            },
            "verified_facts": {"functions": [], "classes": [], "external_dependencies": [], "related_files": []},
        },
    ]


def _index():
    return {
        "file_count": 2,
        "total_lines": 25,
        "languages": [{"language": "Python", "files": 2}],
        "paths": ["main.py", "config.py"],
        "symbols_by_file": {
            "main.py": {"functions": ["status"], "classes": []},
            "config.py": {"functions": [], "classes": []},
        },
        "external_dependencies": ["fastapi"],
        "entry_point_candidates": [{"path": "main.py", "evidence": "entry"}],
        "local_dependency_edges": [{"source": "main.py", "target": "config.py", "evidence": "from .config import OLLAMA_BASE_URL"}],
    }


def _analysis():
    return {
        "purpose": "demo project",
        "overview": "demo overview",
        "architecture_flow": ["main.py がリクエストを処理"],
        "entry_points": [{"path": "main.py", "reason": "entry"}],
        "components": [{"path": "main.py", "role": "api"}],
        "external_dependencies": ["fastapi"],
        "config_and_data_files": ["config.py"],
        "read_first": [{"path": "main.py", "reason": "first"}],
        "change_risks": ["API変更時は利用側を確認"],
        "unknowns": ["動的依存は未確認"],
    }


def test_generate_three_grounded_markdown_documents():
    result = generate_project_documents("demo", _index(), _analysis(), _files())
    assert [x["filename"] for x in result["documents"]] == ["README.md", "ARCHITECTURE.md", "HANDOVER.md"]
    docs = {x["filename"]: x["content"] for x in result["documents"]}
    assert "`main.py` → `config.py`" in docs["ARCHITECTURE.md"]
    assert "`GET /api/status`" in docs["ARCHITECTURE.md"]
    assert "`OLLAMA_BASE_URL`" in docs["ARCHITECTURE.md"]
    assert "1. `main.py`" in docs["HANDOVER.md"]
    assert result["generation"]["source_code_embedded"] is False
    assert result["generation"]["extra_ollama_call"] is False


def test_docs_endpoint_rebuilds_grounding_and_does_not_embed_source():
    files = _files()
    files[0]["source"] = "TOP_SECRET_SOURCE_SHOULD_NOT_APPEAR"
    analysis = _analysis()
    analysis["components"].append({"path": "missing.py", "role": "hallucinated"})
    analysis["config_and_data_files"].append("missing.env")
    req = ProjectDocsRequest(
        project_name="demo",
        project_index={"paths": ["missing.py"]},
        analysis=analysis,
        files=files,
    )
    result = generate_project_docs(req)
    joined = "\n".join(x["content"] for x in result["documents"])
    assert "TOP_SECRET_SOURCE_SHOULD_NOT_APPEAR" not in joined
    assert "missing.py" not in joined
    assert "missing.env" not in joined
    assert "main.py" in joined
    assert result["grounding"]["removed_claim_count"] >= 1
