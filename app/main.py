from __future__ import annotations

import base64
import binascii
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .analyzer import analyze_source
from .config import (
    ALLOWED_EXTENSIONS,
    MAX_CHAT_HISTORY_MESSAGES,
    MAX_FILE_BYTES,
    MAX_QUESTION_CHARS,
    OLLAMA_MODEL,
)
from .ollama_client import analyze_with_ollama, ask_with_ollama, get_ollama_models

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Local Code Reader", version="0.1.2")
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


def _decode_source(content: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp932", "shift_jis"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=400, detail="文字コードを判定できませんでした。UTF-8 / CP932 / Shift-JISを試しました。")


def _validate_filename(filename: str) -> str:
    safe_filename = Path(filename).name
    suffix = Path(safe_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"未対応の拡張子です: {suffix or '(なし)'}",
        )
    return safe_filename


def _validate_content(content: bytes) -> None:
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"ファイルが大きすぎます。v1の上限は {MAX_FILE_BYTES // 1024} KiB です。",
        )
    if not content:
        raise HTTPException(status_code=400, detail="ファイルが空です。")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"default_model": OLLAMA_MODEL},
    )


@app.get("/api/status")
def status():
    models = get_ollama_models()
    return {"ollama_connected": bool(models), "models": models, "default_model": OLLAMA_MODEL}


@app.post("/api/analyze")
async def analyze(
    request: Request,
    filename: str = Query(..., min_length=1, max_length=255),
    model: str = Query(default="", max_length=200),
):
    safe_filename = _validate_filename(filename)

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_FILE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"ファイルが大きすぎます。v1の上限は {MAX_FILE_BYTES // 1024} KiB です。",
                )
        except ValueError:
            pass

    # multipart/UploadFileを使わず、生のリクエスト本文をメモリ上で読む。
    content = await request.body()
    _validate_content(content)

    source = _decode_source(content)
    static_analysis = analyze_source(safe_filename, source)

    try:
        llm_result = analyze_with_ollama(
            filename=safe_filename,
            static_analysis=static_analysis,
            source=source,
            model=model.strip() or None,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # ソースコード本体はレスポンスにもディスクにも保存しない。
    return {
        "file": {
            "name": safe_filename,
            "language": static_analysis["language"],
            "line_count": static_analysis["line_count"],
            "char_count": static_analysis["char_count"],
        },
        "static_analysis": static_analysis,
        **llm_result,
    }


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
