import asyncio
import logging
import sqlite3

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .auth import router as auth_router
from .auth import COOKIE_NAME, COOKIE_SECURE
from .cleanup import cleanup_loop
from .database import database_ready, initialize_database
from .transfers import router as transfer_router
from .uploads import router as uploads_router
from .downloads import router as downloads_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()

    stop = asyncio.Event()
    cleanup_task = asyncio.create_task(cleanup_loop(stop))

    try:
        yield
    finally:
        stop.set()
        await cleanup_task


app = FastAPI(
    title="File Transfer API",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.include_router(auth_router)
app.include_router(transfer_router)
app.include_router(uploads_router)
app.include_router(downloads_router)

@app.middleware("http")
async def clear_invalid_session(request: Request, call_next):
    response = await call_next(request)

    if getattr(request.state, "clear_account_cookie", False):
        response.delete_cookie(
            COOKIE_NAME,
            path="/",
            secure=COOKIE_SECURE,
            httponly=True,
            samesite="lax",
        )

    return response


@app.exception_handler(RequestValidationError)
async def validation_error(
    request: Request,
    error: RequestValidationError,
):
    return JSONResponse(
        status_code=422,
        headers={"Cache-Control": "no-store"},
        content={
            "detail": [
                {
                    "loc": item["loc"],
                    "msg": item["msg"],
                    "type": item["type"],
                }
                for item in error.errors()
            ],
        },
    )


@app.exception_handler(sqlite3.Error)
async def database_error(
    request: Request,
    error: sqlite3.Error,
):
    logging.error(
        "Database request failed.",
        exc_info=error,
    )

    return JSONResponse(
        status_code=503,
        headers={"Cache-Control": "no-store"},
        content={"detail": "Database unavailable."},
    )


@app.get("/health")
def health():
    try:
        database_ready()
    except (sqlite3.Error, OSError):
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "Database unavailable",
            },
        )

    return {
        "ok": True,
        "database": "sqlite3",
    }