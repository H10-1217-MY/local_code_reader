from __future__ import annotations

import base64
import binascii
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .analyzer import analyze_source
from .config import (
    ALLOWED_EXTENSIONS,
    ALLOWED_FILENAMES,
    PROJECT_EXCLUDED_FILENAMES,
    PROJECT_STRUCTURE_ONLY_FILENAMES,
    MAX_CHAT_HISTORY_MESSAGES,
    MAX_FILE_BYTES,
    MAX_PROJECT_FILES,
    MAX_QUESTION_CHARS,
    OLLAMA_MODEL,
)
from .ollama_client import (
    analyze_project_with_ollama,
    analyze_with_ollama,
    ask_project_with_ollama,
    ask_with_ollama,
    get_ollama_models,
)
from .project_docs import generate_project_documents
from .project_analyzer import (
    build_project_index,
    build_structure_only_analysis,
    classify_project_content,
    sanitize_project_analysis,
    sanitize_project_files,
)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Local Code Reader", version="0.3.4")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class AskRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    model: str = Field(default="", max_length=200)
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    source_base64: str = Field(min_length=1, max_length=(MAX_FILE_BYTES * 4 // 3) + 256)
    history: list[ChatTurn] = Field(default_factory=list, max_length=MAX_CHAT_HISTORY_MESSAGES)


class ProjectSummaryRequest(BaseModel):
    project_name: str = Field(min_length=1, max_length=255)
    model: str = Field(default="", max_length=200)
    files: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_PROJECT_FILES)


class ProjectDocsRequest(BaseModel):
    project_name: str = Field(min_length=1, max_length=255)
    project_index: dict[str, Any]
    analysis: dict[str, Any]
    files: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_PROJECT_FILES)


class ProjectAskRequest(BaseModel):
    project_name: str = Field(min_length=1, max_length=255)
    model: str = Field(default="", max_length=200)
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    project_index: dict[str, Any]
    analysis: dict[str, Any]
    files: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_PROJECT_FILES)
    history: list[ChatTurn] = Field(default_factory=list, max_length=MAX_CHAT_HISTORY_MESSAGES)


def _decode_source(content: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp932", "shift_jis"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=400, detail="文字コードを判定できませんでした。UTF-8 / CP932 / Shift-JISを試しました。")


def _is_allowed_file(filename: str) -> bool:
    name = Path(filename).name
    return name in ALLOWED_FILENAMES or Path(name).suffix.lower() in ALLOWED_EXTENSIONS


def _validate_filename(filename: str) -> str:
    safe_filename = Path(filename).name
    if not _is_allowed_file(safe_filename):
        suffix = Path(safe_filename).suffix.lower()
        raise HTTPException(status_code=400, detail=f"未対応のファイルです: {safe_filename} ({suffix or '拡張子なし'})")
    return safe_filename


def _validate_project_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip("/")
    p = PurePosixPath(normalized)
    if not normalized or p.is_absolute() or ".." in p.parts:
        raise HTTPException(status_code=400, detail="不正なプロジェクト内パスです。")
    if len(normalized) > 600:
        raise HTTPException(status_code=400, detail="プロジェクト内パスが長すぎます。")
    _validate_filename(p.name)
    return normalized


def _validate_content(content: bytes) -> None:
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"ファイルが大きすぎます。1ファイル上限は {MAX_FILE_BYTES // 1024} KiB です。")
    if not content:
        raise HTTPException(status_code=400, detail="ファイルが空です。")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"default_model": OLLAMA_MODEL})


@app.get("/api/status")
def status():
    models = get_ollama_models()
    return {
        "ollama_connected": bool(models),
        "models": models,
        "default_model": OLLAMA_MODEL,
        "limits": {"max_file_bytes": MAX_FILE_BYTES, "max_project_files": MAX_PROJECT_FILES},
        "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
        "allowed_filenames": sorted(ALLOWED_FILENAMES),
        "project_filter": {
            "structure_only_filenames": sorted(PROJECT_STRUCTURE_ONLY_FILENAMES),
            "excluded_filenames": sorted(PROJECT_EXCLUDED_FILENAMES),
        },
    }


async def _analyze_bytes(filename: str, content: bytes, model: str | None, *, project_path: str | None = None):
    _validate_content(content)
    source = _decode_source(content)
    analysis_name = project_path or filename
    static_analysis = analyze_source(analysis_name, source)
    try:
        llm_result = analyze_with_ollama(
            filename=analysis_name,
            static_analysis=static_analysis,
            source=source,
            model=model,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    file_info = {
        "name": filename,
        "language": static_analysis["language"],
        "line_count": static_analysis["line_count"],
        "char_count": static_analysis["char_count"],
    }
    if project_path:
        file_info["path"] = project_path
    return {"file": file_info, "static_analysis": static_analysis, **llm_result}


@app.post("/api/analyze")
async def analyze(request: Request, filename: str = Query(..., min_length=1, max_length=255), model: str = Query(default="", max_length=200)):
    safe_filename = _validate_filename(filename)
    content = await request.body()
    return await _analyze_bytes(safe_filename, content, model.strip() or None)


@app.post("/api/project/analyze-file")
async def analyze_project_file(request: Request, path: str = Query(..., min_length=1, max_length=600), model: str = Query(default="", max_length=200)):
    safe_path = _validate_project_path(path)
    content = await request.body()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"ファイルが大きすぎます。1ファイル上限は {MAX_FILE_BYTES // 1024} KiB です。")

    filename = PurePosixPath(safe_path).name
    # プロジェクト解析では空ファイルをエラーにせず、明示的なskip結果として返す。
    if not content:
        return {
            "file": {"name": filename, "path": safe_path, "language": "Unknown", "line_count": 0, "char_count": 0},
            "processing": {"mode": "skip", "reason": "空ファイル"},
        }

    source = _decode_source(content)
    decision = classify_project_content(safe_path, source)
    if decision["mode"] == "skip":
        return {
            "file": {
                "name": filename,
                "path": safe_path,
                "language": analyze_source(safe_path, source)["language"],
                "line_count": source.count("\n") + (1 if source else 0),
                "char_count": len(source),
            },
            "processing": decision,
        }

    static_analysis = analyze_source(safe_path, source)
    file_info = {
        "name": filename,
        "path": safe_path,
        "language": static_analysis["language"],
        "line_count": static_analysis["line_count"],
        "char_count": static_analysis["char_count"],
    }

    if decision["mode"] == "structure":
        return {
            "file": file_info,
            "processing": decision,
            "static_analysis": static_analysis,
            "analysis": build_structure_only_analysis(safe_path, source, static_analysis),
            "model": None,
            "metrics": {"total_duration_ns": 0, "prompt_eval_count": 0, "eval_count": 0},
        }

    result = await _analyze_bytes(filename, content, model.strip() or None, project_path=safe_path)
    result["processing"] = decision
    return result


@app.post("/api/project/summarize")
def summarize_project(payload: ProjectSummaryRequest):
    if len(payload.files) > MAX_PROJECT_FILES:
        raise HTTPException(status_code=400, detail=f"v3.4では最大 {MAX_PROJECT_FILES} ファイルまでです。")

    compact_files: list[dict[str, Any]] = []
    for item in payload.files:
        file_info = item.get("file") or {}
        if "path" not in file_info:
            raise HTTPException(status_code=400, detail="プロジェクト解析結果にpathがありません。")
        _validate_project_path(str(file_info["path"]))
        # クライアントからソースコードが混入してもプロジェクト要約には渡さない。
        compact_files.append({
            "file": file_info,
            "processing": item.get("processing") or {"mode": "llm", "reason": ""},
            "static_analysis": item.get("static_analysis") or {},
            "analysis": item.get("analysis") or {},
            "model": item.get("model"),
            "metrics": item.get("metrics") or {},
            "grounding": item.get("grounding") or {},
        })

    project_index = build_project_index(compact_files)
    grounded_files, file_grounding = sanitize_project_files(compact_files, project_index)
    try:
        llm_result = analyze_project_with_ollama(
            project_name=payload.project_name.strip(),
            files=grounded_files,
            project_index=project_index,
            model=payload.model.strip() or None,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    grounded_project_analysis, project_grounding = sanitize_project_analysis(
        llm_result.get("analysis") or {}, project_index
    )
    return {
        "project": {"name": payload.project_name.strip(), "file_count": len(compact_files)},
        "project_index": project_index,
        "model": llm_result.get("model"),
        "analysis": grounded_project_analysis,
        # v3.4でも、最終出力/UI/JSONはgrounding済み個別解析を正とする。
        "files": grounded_files,
        "metrics": llm_result.get("metrics") or {},
        "grounding": {
            "file_analysis": file_grounding,
            "project_analysis": project_grounding,
            "removed_claim_count": int(file_grounding.get("removed_claim_count") or 0) + int(project_grounding.get("removed_claim_count") or 0),
        },
    }


@app.post("/api/project/generate-docs")
def generate_project_docs(payload: ProjectDocsRequest):
    if len(payload.files) > MAX_PROJECT_FILES:
        raise HTTPException(status_code=400, detail=f"v3.4では最大 {MAX_PROJECT_FILES} ファイルまでです。")

    compact_files: list[dict[str, Any]] = []
    for item in payload.files:
        file_info = item.get("file") or {}
        path = str(file_info.get("path") or "")
        if not path:
            raise HTTPException(status_code=400, detail="資料生成用データにpathがありません。")
        _validate_project_path(path)
        # 資料生成にも元ソース本文は渡さない。解析済み・検証済み情報だけを使う。
        compact_files.append({
            "file": file_info,
            "processing": item.get("processing") or {"mode": "llm", "reason": ""},
            "static_analysis": item.get("static_analysis") or {},
            "analysis": item.get("analysis") or {},
            "verified_facts": item.get("verified_facts") or {},
            "grounding": item.get("grounding") or {},
        })

    verified_index = build_project_index(compact_files)
    grounded_files, file_grounding = sanitize_project_files(compact_files, verified_index)
    grounded_analysis, project_grounding = sanitize_project_analysis(payload.analysis, verified_index)
    result = generate_project_documents(
        project_name=payload.project_name.strip(),
        project_index=verified_index,
        project_analysis=grounded_analysis,
        files=grounded_files,
    )
    result["grounding"] = {
        "file_analysis": file_grounding,
        "project_analysis": project_grounding,
        "removed_claim_count": int(file_grounding.get("removed_claim_count") or 0) + int(project_grounding.get("removed_claim_count") or 0),
    }
    return result


@app.post("/api/project/ask")
def ask_project(payload: ProjectAskRequest):
    if len(payload.files) > MAX_PROJECT_FILES:
        raise HTTPException(status_code=400, detail=f"v3.4では最大 {MAX_PROJECT_FILES} ファイルまでです。")

    compact_files: list[dict[str, Any]] = []
    for item in payload.files:
        file_info = item.get("file") or {}
        path = str(file_info.get("path") or "")
        if not path:
            raise HTTPException(status_code=400, detail="プロジェクトQ&A用データにpathがありません。")
        _validate_project_path(path)
        # Q&Aにも元ソースコードは渡さない。検証済み解析結果だけを再利用する。
        compact_files.append({
            "file": file_info,
            "processing": item.get("processing") or {"mode": "llm", "reason": ""},
            "static_analysis": item.get("static_analysis") or {},
            "analysis": item.get("analysis") or {},
            "verified_facts": item.get("verified_facts") or {},
            "grounding": item.get("grounding") or {},
        })

    # Q&A時もクライアントから渡されたproject_indexを盲信せず、filesから再構築・再groundingする。
    verified_index = build_project_index(compact_files)
    grounded_files, _ = sanitize_project_files(compact_files, verified_index)
    grounded_analysis, _ = sanitize_project_analysis(payload.analysis, verified_index)

    history = [turn.model_dump() for turn in payload.history[-MAX_CHAT_HISTORY_MESSAGES:]]
    try:
        return ask_project_with_ollama(
            project_name=payload.project_name.strip(),
            project_index=verified_index,
            project_analysis=grounded_analysis,
            files=grounded_files,
            question=payload.question.strip(),
            history=history,
            model=payload.model.strip() or None,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/ask")
def ask(payload: AskRequest):
    safe_filename = _validate_filename(payload.filename)
    try:
        content = base64.b64decode(payload.source_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="ソースコードの転送データを復元できませんでした。") from exc

    _validate_content(content)
    source = _decode_source(content)
    static_analysis = analyze_source(safe_filename, source)
    history = [turn.model_dump() for turn in payload.history[-MAX_CHAT_HISTORY_MESSAGES:]]
    try:
        return ask_with_ollama(
            filename=safe_filename,
            static_analysis=static_analysis,
            source=source,
            question=payload.question.strip(),
            history=history,
            model=payload.model.strip() or None,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
