"""FastAPI-сервис: чат и запуск benchmark. Контракт — spec/tech/api.md.

    uvicorn backend.app.main:app --port 8000
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.app import config, llm, rag
from backend.app.llm import LLMUnavailable
from benchmark.run import run_benchmark
from search import config as search_config

log = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        index = rag.get_index()
        log.info("Индекс загружен: %d документов, %d фрагментов", len(index.documents), len(index.chunks))
    except FileNotFoundError:
        log.warning("Индекс не найден — соберите его: python -m search.build")
    yield


app = FastAPI(title="RAG-ассистент ИУ-5", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def error(status: int, code: str, detail: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"error": code}
    if detail:
        body["detail"] = detail
    return JSONResponse(status_code=status, content=body)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    code = "message_invalid" if request.url.path == "/api/chat" else "request_invalid"
    return error(400, code)


@app.exception_handler(Exception)
async def internal_error(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Внутренняя ошибка")
    return error(500, "internal")


# --- чат ------------------------------------------------------------------
class HistoryMessage(BaseModel):
    role: str
    text: str = ""


class ChatRequest(BaseModel):
    message: str
    history: list[HistoryMessage] = []


@app.post("/api/chat")
def chat(request: ChatRequest):
    message = request.message.strip()
    if not message or len(message) > config.MAX_MESSAGE_CHARS:
        return error(400, "message_invalid")
    try:
        index = rag.get_index()
    except FileNotFoundError:
        return error(503, "service_unavailable", "Индекс не собран: python -m search.build")
    history = [m.model_dump() for m in request.history]
    try:
        result = rag.answer(message, history=history, index=index)
    except LLMUnavailable as exc:
        log.warning("LLM недоступна: %s", exc)
        return error(503, "service_unavailable", str(exc))
    return {"text": result.text, "sources": result.sources, "finish_reason": result.finish_reason}


@app.get("/api/health")
def health():
    try:
        index = rag.get_index()
        documents, chunks = len(index.documents), len(index.chunks)
    except FileNotFoundError:
        index, documents, chunks = None, 0, 0
    llm_status = llm.status()
    return {
        "status": "ok" if index is not None and llm_status == "available" else "degraded",
        "index_loaded": index is not None,
        "documents": documents,
        "chunks": chunks,
        "llm": llm_status,
        "model": config.OLLAMA_MODEL,
    }


# --- benchmark в рантайме -----------------------------------------------------
class BenchmarkRequest(BaseModel):
    k: int = Field(default=search_config.TOP_K, ge=1, le=20)
    mode: Literal["retrieval", "full"] = "full"


_runs: dict[str, dict] = {}
_runs_lock = threading.Lock()
_active_run: str | None = None


def _benchmark_worker(run_id: str, k: int, mode: str) -> None:
    global _active_run

    def on_progress(done: int, total: int, row: dict) -> None:
        with _runs_lock:
            _runs[run_id]["progress"] = {"done": done, "total": total}

    def answer_fn(question: str, k: int) -> rag.Answer:
        return rag.answer(question, history=[], k=k)

    try:
        result = run_benchmark(
            k=k,
            mode=mode,
            answer_fn=answer_fn if mode == "full" else None,
            on_progress=on_progress,
            index=rag.get_index(),
            model=config.OLLAMA_MODEL if mode == "full" else None,
        )
        result["run_id"] = run_id
        with _runs_lock:
            _runs[run_id] = result
    except Exception as exc:  # прогон в фоне: ошибку отдаём через статус
        log.exception("Ошибка benchmark %s", run_id)
        with _runs_lock:
            _runs[run_id].update(status="error", error=str(exc))
    finally:
        with _runs_lock:
            _active_run = None


@app.post("/api/benchmark/run", status_code=202)
def start_benchmark(request: BenchmarkRequest):
    global _active_run
    try:
        rag.get_index()
    except FileNotFoundError:
        return error(503, "service_unavailable", "Индекс не собран: python -m search.build")
    if request.mode == "full" and llm.status() != "available":
        return error(503, "service_unavailable", f"Ollama или модель {config.OLLAMA_MODEL} недоступны")
    with _runs_lock:
        if _active_run is not None:
            return error(409, "benchmark_running", f"Уже идёт прогон {_active_run}")
        run_id = base = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        suffix = 1
        while run_id in _runs:  # два прогона в одну секунду
            suffix += 1
            run_id = f"{base}-{suffix}"
        _runs[run_id] = {
            "run_id": run_id,
            "status": "running",
            "progress": {"done": 0, "total": None},
            "params": {"k": request.k, "mode": request.mode},
        }
        _active_run = run_id
    threading.Thread(target=_benchmark_worker, args=(run_id, request.k, request.mode), daemon=True).start()
    return {"run_id": run_id, "status": "running"}


@app.get("/api/benchmark/runs/{run_id}")
def benchmark_status(run_id: str):
    with _runs_lock:
        run = _runs.get(run_id)
        if run is None:
            return error(404, "run_not_found")
        return dict(run)
