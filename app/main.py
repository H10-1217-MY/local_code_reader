from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .analyzer import analyze_source
from .config import ALLOWED_EXTENSIONS, MAX_FILE_BYTES, OLLAMA_MODEL
from .ollama_client import analyze_with_ollama, get_ollama_models

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Local Code Reader", version="0.1.1")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _decode_source(content: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp932", "shift_jis"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=400, detail="文字コードを判定できませんでした。UTF-8 / CP932 / Shift-JISを試しました。")


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
    safe_filename = Path(filename).name
    suffix = Path(safe_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"未対応の拡張子です: {suffix or '(なし)'}",
        )

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"ファイルが大きすぎます。v1の上限は {MAX_FILE_BYTES // 1024} KiB です。",
        )

    # multipart/UploadFileを使わず、生のリクエスト本文をメモリ上で読む。
    content = await request.body()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"ファイルが大きすぎます。v1の上限は {MAX_FILE_BYTES // 1024} KiB です。",
        )
    if not content:
        raise HTTPException(status_code=400, detail="ファイルが空です。")

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
