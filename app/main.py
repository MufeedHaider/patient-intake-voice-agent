"""FastAPI entry point: wires together the REST API, the Vapi webhook and the dashboard."""
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import dashboard, patients, vapi
from app.config import LOG_LEVEL, SEED_DATA
from app.db import SessionLocal, init_db
from app.schemas import envelope
from app.services.patients import seed

logging.basicConfig(
    stream=sys.stdout,
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if SEED_DATA:
        with SessionLocal() as db:
            seed(db)
    log.info("startup complete")
    yield


app = FastAPI(
    title="Patient Intake Voice Agent API",
    description="Voice AI patient registration: REST API, Vapi webhook and dashboard.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    details = []
    for err in exc.errors():
        loc = [str(x) for x in err.get("loc", []) if x not in ("body", "query", "path")]
        details.append({"field": ".".join(loc) or None, "message": str(err.get("msg", "")).removeprefix("Value error, ")})
    status = 400 if any(e.get("type") == "json_invalid" for e in exc.errors()) else 422
    return JSONResponse(
        status_code=status,
        content=envelope(error={"code": "validation_error", "message": "Invalid input", "details": details}),
    )


@app.exception_handler(StarletteHTTPException)
async def http_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=envelope(error={"code": "http_error", "message": str(exc.detail), "details": None}),
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=envelope(error={"code": "internal_error", "message": "Something went wrong", "details": None}),
    )


@app.get("/health", tags=["health"])
def health():
    return envelope({"status": "ok"})


app.include_router(patients.router)
app.include_router(vapi.router)
app.include_router(dashboard.router)
