from unittest.mock import patch

from app.main import ProjectAskRequest, ask_project
from app.ollama_client import _ground_project_qa


def _project_index():
    return {
        "paths": ["main.py", "ollama_client.py"],
        "symbols_by_file": {
            "main.py": {"functions": ["main", "summarize_project"], "classes": []},
            "ollama_client.py": {"functions": ["ask_project_with_ollama"], "classes": []},
        },
        "external_dependencies": ["fastapi", "requests"],
        "local_dependency_edges": [
            {"source": "main.py", "target": "ollama_client.py", "evidence": "import"}
        ],
    }


def _file(path, functions):
    return {
        "file": {"path": path, "name": path.split("/")[-1], "language": "Python", "line_count": 10, "char_count": 100},
        "processing": {"mode": "llm", "reason": "test"},
        "static_analysis": {
            "language": "Python",
            "functions": [{"name": x, "qualified_name": x, "line": 1, "end_line": 2} for x in functions],
            "classes": [],
            "detected_external_dependencies": [],
        },
        "analysis": {"purpose": "test", "overview": "test", "main_flow": [], "change_risks": [], "unknowns": []},
        "verified_facts": {"functions": functions, "classes": [], "external_dependencies": [], "related_files": []},
    }


def test_project_qa_grounding_filters_unknown_path_and_symbol():
    parsed = {
        "answer": "answer",
        "evidence": [
            {"path": "main.py", "symbol": "main", "reason": "ok"},
            {"path": "missing.py", "symbol": "x", "reason": "bad path"},
            {"path": "ollama_client.py", "symbol": "imaginary", "reason": "bad symbol"},
        ],
        "confidence": "high",
        "limitations": [],
    }
    grounded, report = _ground_project_qa(parsed, _project_index())
    assert len(grounded["evidence"]) == 2
    assert grounded["evidence"][0]["symbol"] == "main"
    assert grounded["evidence"][1]["path"] == "ollama_client.py"
    assert grounded["evidence"][1]["symbol"] == ""
    assert report["removed_claim_count"] == 2


def test_project_ask_endpoint_reuses_analysis_without_source_code():
    files = [_file("main.py", ["main", "summarize_project"]), _file("ollama_client.py", ["ask_project_with_ollama"])]
    fake = {
        "model": "qwen3:8b",
        "answer": "main.pyからollama_client.pyへつながります。",
        "evidence": [{"path": "main.py", "symbol": "summarize_project", "reason": "import関係"}],
        "confidence": "high",
        "limitations": [],
        "grounding": {"removed_claim_count": 0, "removed_claims": []},
        "metrics": {},
    }
    req = ProjectAskRequest(
        project_name="demo",
        model="qwen3:8b",
        question="どこが入口？",
        project_index=_project_index(),
        analysis={"purpose": "demo"},
        files=files,
        history=[],
    )
    with patch("app.main.ask_project_with_ollama", return_value=fake) as mocked:
        result = ask_project(req)
    assert result["answer"].startswith("main.py")
    kwargs = mocked.call_args.kwargs
    assert "source" not in kwargs
    assert all("source" not in item for item in kwargs["files"])

from app.ollama_client import (
    _detect_project_qa_intent,
    _select_project_qa_files,
    _select_relevant_history,
    _selected_project_index,
)


def _routing_files():
    names = [
        ("analyzer.py", "Python", "静的解析と言語別解析", ["analyze_source", "_python_analysis"]),
        ("config.py", "Python", "Ollamaとファイル制限の設定", []),
        ("main.py", "Python", "FastAPIの入口とOllama API呼び出し", ["summarize_project", "ask_project"]),
        ("ollama_client.py", "Python", "Ollama API通信とQ&A", ["ask_project_with_ollama", "analyze_project_with_ollama"]),
        ("project_analyzer.py", "Python", "プロジェクト依存関係とgrounding", ["build_project_index"]),
        ("static/app.js", "JavaScript", "画面UIとfetch通信", ["renderProjectResult"]),
        ("templates/index.html", "HTML", "Web UI", []),
    ]
    result = []
    for path, language, purpose, functions in names:
        result.append({
            "file": {"path": path, "name": path.split("/")[-1], "language": language, "line_count": 10, "char_count": 100},
            "static_analysis": {"imports": [], "references": [], "functions": [{"name": x, "qualified_name": x, "line": 1, "end_line": 2} for x in functions], "classes": [], "detected_external_dependencies": ["requests"] if path == "ollama_client.py" else []},
            "analysis": {"purpose": purpose, "overview": purpose, "main_flow": [], "change_risks": [], "unknowns": []},
            "verified_facts": {"functions": functions, "classes": [], "external_dependencies": ["requests"] if path == "ollama_client.py" else [], "related_files": []},
        })
    return result


def _routing_index():
    files = _routing_files()
    return {
        "paths": [f["file"]["path"] for f in files],
        "symbols_by_file": {f["file"]["path"]: {"functions": f["verified_facts"]["functions"], "classes": []} for f in files},
        "external_dependencies": ["fastapi", "requests"],
        "entry_point_candidates": [{"path": "main.py", "evidence": "entry"}, {"path": "templates/index.html", "evidence": "ui"}],
        "local_dependency_edges": [
            {"source": "main.py", "target": "ollama_client.py", "evidence": "import"},
            {"source": "main.py", "target": "analyzer.py", "evidence": "import"},
            {"source": "main.py", "target": "project_analyzer.py", "evidence": "import"},
        ],
    }


def test_intent_and_selection_for_all_python_files_ignores_previous_code_scope():
    index = _routing_index()
    files = _routing_files()
    question = "5つのＰythonファイルをもう少し詳しく解説して"
    routing = _detect_project_qa_intent(question, index)
    assert routing["intent"] == "language_overview"
    assert routing["language_filter"] == "Python"
    # 現在の質問で対象が明示されているため「もう少し」があっても過去会話に依存しない。
    assert routing["is_followup"] is False
    selected, _ = _select_project_qa_files(question, routing, index, files, {})
    paths = [x["file"]["path"] for x in selected]
    assert paths == ["analyzer.py", "config.py", "main.py", "ollama_client.py", "project_analyzer.py"]


def test_unrelated_long_code_history_is_not_reused_for_explicit_language_question():
    index = _routing_index()
    routing = _detect_project_qa_intent("5つのPythonファイルをもう少し詳しく解説して", index)
    history = [
        {"role": "user", "content": "def test_x():\n    assert True\n" * 150 + "analyzer.py"},
        {"role": "assistant", "content": "これはテストコードです。"},
    ]
    selected_history, notes = _select_relevant_history(
        "5つのPythonファイルをもう少し詳しく解説して", history, routing,
        ["analyzer.py", "config.py", "main.py", "ollama_client.py", "project_analyzer.py"],
    )
    assert selected_history == []
    assert any("過去会話" in note for note in notes)


def test_ollama_question_selects_ollama_related_files():
    index = _routing_index()
    files = _routing_files()
    question = "Ollamaとの通信はどのファイルが担当してる？"
    routing = _detect_project_qa_intent(question, index)
    selected, _ = _select_project_qa_files(question, routing, index, files, {})
    paths = [x["file"]["path"] for x in selected]
    assert "ollama_client.py" in paths
    assert "main.py" in paths
    assert len(paths) < len(files)


def test_change_impact_adds_dependency_neighbors():
    index = _routing_index()
    files = _routing_files()
    question = "main.pyを変更したらどこに影響する？"
    routing = _detect_project_qa_intent(question, index)
    assert routing["intent"] == "change_impact"
    selected, _ = _select_project_qa_files(question, routing, index, files, {})
    paths = {x["file"]["path"] for x in selected}
    assert {"main.py", "ollama_client.py", "analyzer.py", "project_analyzer.py"}.issubset(paths)


def test_explicit_followup_uses_only_recent_relevant_history_and_omits_long_code():
    index = _routing_index()
    routing = _detect_project_qa_intent("そこをもう少し詳しく", index)
    assert routing["is_followup"] is True
    history = [
        {"role": "user", "content": "ollama_client.pyの通信部分を教えて"},
        {"role": "assistant", "content": "ask_project_with_ollamaがOllama APIへPOSTします。"},
        {"role": "user", "content": "def test_many():\n    assert True\n" * 120},
    ]
    selected_history, _ = _select_relevant_history("そこをもう少し詳しく", history, routing, ["ollama_client.py"])
    assert selected_history
    assert len(selected_history) <= 4
    assert all(len(x["content"]) < 1200 for x in selected_history)


def test_selected_project_index_contains_only_selected_paths():
    selected = [x for x in _routing_files() if x["file"]["path"] in {"main.py", "ollama_client.py"}]
    narrowed = _selected_project_index(_routing_index(), selected)
    assert narrowed["paths"] == ["main.py", "ollama_client.py"]
    assert set(narrowed["symbols_by_file"]) == {"main.py", "ollama_client.py"}

import json
from app.ollama_client import ask_project_with_ollama


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        return None
    def json(self):
        return self._payload


def test_independent_question_does_not_send_previous_long_code_to_ollama():
    index = _routing_index()
    files = _routing_files()
    llm_payload = {
        "model": "qwen3:14b",
        "message": {"content": json.dumps({
            "answer": "Pythonファイルは5件です。",
            "evidence": [{"path": "analyzer.py", "symbol": "analyze_source", "reason": "静的解析"}],
            "confidence": "high",
            "limitations": [],
        }, ensure_ascii=False)},
        "total_duration": 1,
        "prompt_eval_count": 1,
        "eval_count": 1,
    }
    long_code = "def test_x():\n    assert True\n" * 200
    with patch("app.ollama_client.requests.post", return_value=_FakeResponse(llm_payload)) as mocked:
        result = ask_project_with_ollama(
            project_name="demo",
            project_index=index,
            project_analysis={"purpose": "demo", "overview": "demo"},
            files=files,
            question="5つのＰythonファイルをもう少し詳しく解説して",
            history=[{"role": "user", "content": long_code}, {"role": "assistant", "content": "前の回答"}],
            model="qwen3:14b",
        )
    sent = json.dumps(mocked.call_args.kwargs["json"], ensure_ascii=False)
    assert "def test_x" not in sent
    assert result["context_selection"]["history_turns_used"] == 0
    assert result["context_selection"]["selected_file_count"] == 5
