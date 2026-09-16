from app.environment_setup import build_environment_plan
from app.main import EnvironmentPlanRequest, environment_plan
from app.project_analyzer import build_project_index


def _files_with_requirements():
    return [
        {
            "file": {"path": "requirements.txt", "name": "requirements.txt", "language": "Text", "line_count": 2, "char_count": 30},
            "processing": {"mode": "structure", "reason": "deps"},
            "static_analysis": {"language": "Text", "imports": [], "functions": [], "classes": [], "detected_external_dependencies": []},
            "analysis": {"external_dependencies": ["fastapi", "pydantic"], "environment_metadata": {}},
        },
        {
            "file": {"path": ".python-version", "name": ".python-version", "language": "Unknown", "line_count": 1, "char_count": 5},
            "processing": {"mode": "structure", "reason": "python version"},
            "static_analysis": {"language": "Unknown", "imports": [], "functions": [], "classes": [], "detected_external_dependencies": []},
            "analysis": {"external_dependencies": [], "environment_metadata": {"python_version": "3.12"}},
        },
        {
            "file": {"path": "main.py", "name": "main.py", "language": "Python", "line_count": 12, "char_count": 200},
            "processing": {"mode": "static", "reason": "setup scan"},
            "static_analysis": {
                "language": "Python",
                "imports": ["from fastapi import FastAPI", "import requests"],
                "functions": [],
                "classes": [],
                "environment_variables": ["API_URL"],
                "detected_external_dependencies": ["fastapi", "requests"],
            },
            "analysis": {"external_dependencies": ["fastapi", "requests"]},
        },
    ]


def test_environment_plan_prefers_manifest_and_separates_import_only_candidates():
    files = _files_with_requirements()
    index = build_project_index(files)
    result = build_environment_plan(
        "demo",
        index,
        files,
        target_os="ubuntu_debian",
        shell="auto",
        python_version="",
        gpu="none",
    )
    assert result["dependency_plan"]["kind"] == "requirements"
    assert "pip install -r requirements.txt" in result["dependency_plan"]["command"]
    assert result["dependency_plan"]["import_only_candidates"] == ["requests"]
    assert result["detected"]["python_version_hint"] == "3.12"
    assert result["generation"]["extra_ollama_call"] is False
    assert result["generation"]["auto_execute"] is False
    names = [x["filename"] for x in result["generated_files"]]
    assert "SETUP.md" in names
    assert ".env.example.generated" in names
    assert "requirements.candidates.txt" not in names


def test_environment_plan_without_manifest_generates_commented_candidates_only():
    files = [
        {
            "file": {"path": "main.py", "name": "main.py", "language": "Python", "line_count": 3, "char_count": 50},
            "processing": {"mode": "static", "reason": "setup scan"},
            "static_analysis": {"language": "Python", "imports": ["import cv2", "import requests"], "functions": [], "classes": [], "environment_variables": [], "detected_external_dependencies": ["cv2", "requests"]},
            "analysis": {"external_dependencies": ["cv2", "requests"]},
        }
    ]
    index = build_project_index(files)
    result = build_environment_plan("demo", index, files, target_os="windows", shell="powershell", python_version="3.12", gpu="nvidia")
    assert result["dependency_plan"]["kind"] == "import_candidates"
    candidates = next(x for x in result["generated_files"] if x["filename"] == "requirements.candidates.txt")
    assert "# cv2" in candidates["content"]
    assert "# requests" in candidates["content"]
    assert "\ncv2\n" not in candidates["content"]
    assert any("GPU" in x["title"] for x in result["reproducibility_findings"])


def test_environment_endpoint_rebuilds_index_and_does_not_embed_source():
    files = _files_with_requirements()
    files[2]["source"] = "TOP_SECRET_SHOULD_NOT_APPEAR"
    req = EnvironmentPlanRequest(
        project_name="demo",
        target_os="ubuntu_debian",
        shell="bash",
        python_version="3.12",
        gpu="none",
        files=files,
    )
    result = environment_plan(req)
    joined = "\n".join(x["content"] for x in result["generated_files"])
    assert "TOP_SECRET_SHOULD_NOT_APPEAR" not in joined
    assert result["project"]["file_count"] == 3
