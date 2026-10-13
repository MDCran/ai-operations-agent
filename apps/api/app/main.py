from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.routes import router
from app.auth.security import redis
from app.core.config import settings
from app.core.errors import DomainError
from app.db.session import engine

app = FastAPI(
    title="AI Operations Agent",
    version="0.1.0",
    description="Authorized tools, durable approvals, tenant-scoped operations.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
)


@app.middleware("http")
async def browser_security(request: Request, call_next):
    content_length = request.headers.get("content-length", "0")
    if content_length.isdigit() and int(content_length) > settings().max_upload_bytes + 1024 * 1024:
        return JSONResponse(
            status_code=413,
            content={"error": {"code": "upload_size", "message": "Request exceeds upload limit."}},
        )
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin not in settings().origins:
        return JSONResponse(
            status_code=403,
            content={"error": {"code": "origin_rejected", "message": "Origin is not allowed."}},
        )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(DomainError)
async def domain_error(request, exc):
    return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Avoid echoing passwords, uploads or other input values in error responses/logs.
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Check the submitted fields.",
                "fields": [
                    {"path": ".".join(str(v) for v in e["loc"]), "type": e["type"]} for e in exc.errors()
                ],
            }
        },
    )


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(
        status_code=409,
        content={"error": {"code": "conflict", "message": "A record with these details already exists."}},
    )


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "The request could not be completed."}},
    )


@app.get("/health")
def health():
    try:
        with engine.connect() as db:
            db.execute(text("SELECT 1"))
        redis.ping()
    except Exception:
        raise DomainError("unhealthy", "A dependency is unavailable.", 503) from None
    return {"status": "ok"}


app.include_router(router)
