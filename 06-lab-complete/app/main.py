"""
Production AI Agent — Part 6 Final Project.

Chạy: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
Kiểm tra: python check_production_ready.py
"""
import json
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, estimate_tokens, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


# ── Structured logging: mỗi dòng là 1 JSON object ────────────
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "lvl": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "extra_fields", {}))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _setup_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("agent")
    log.handlers = [handler]
    log.setLevel(settings.log_level)
    log.propagate = False
    return log


logger = _setup_logging()


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"extra_fields": fields})


# ── Lifespan: startup / graceful shutdown ────────────────────
# uvicorn tự bắt SIGTERM: ngừng nhận kết nối mới, chờ request đang chạy xong,
# rồi chạy phần sau `yield` và thoát với exit code 0.
@asynccontextmanager
async def lifespan(_: FastAPI):
    log_event("startup", environment=settings.environment, port=settings.port,
              redis_ok=redis_healthy())
    yield
    log_event("shutdown", reason="SIGTERM or stop")
    try:
        r.close()
    except Exception:  # noqa: BLE001
        pass


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def request_log(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log_event("unhandled_error", logging.ERROR, path=request.url.path, request_id=request_id)
        response = JSONResponse({"detail": "Internal server error"}, status_code=500)
    ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    log_event("request", method=request.method, path=request.url.path,
              status=response.status_code, ms=ms, request_id=request_id)
    return response


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=128)


@app.get("/")
def root():
    return {"service": "production-ai-agent", "environment": settings.environment,
            "endpoints": ["/health", "/ready", "POST /ask"]}


@app.get("/health")
def health():
    """Liveness: luôn 200 khi process còn chạy (không phụ thuộc Redis)."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready")
def ready():
    """Readiness: 200 khi Redis kết nối được, 503 nếu không."""
    if redis_healthy():
        return {"status": "ready", "redis": "ok"}
    return JSONResponse({"status": "not_ready", "redis": "unavailable"}, status_code=503)


@app.post("/ask")
async def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()
    answer = await run_in_threadpool(llm_ask, body.question)
    cost = record_cost(estimate_tokens(body.question), estimate_tokens(answer))
    log_event("ask", user_id=body.user_id, q_len=len(body.question), cost_usd=round(cost, 8))
    return {"question": body.question, "answer": answer}
