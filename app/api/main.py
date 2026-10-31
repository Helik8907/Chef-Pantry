"""FastAPI backend application for Memory Chef."""

from contextlib import asynccontextmanager
import time
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import get_container
from app.api.routes import auth, chat, users


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context for startup and shutdown initialization."""
    # Eagerly initialize container on startup
    _ = get_container()
    yield


app = FastAPI(
    title="Memory Chef API",
    description="REST API backend for Memory Chef culinary memory and chat services.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_route_access(request: Request, call_next):
    """Log incoming HTTP request method, path, response status, and duration to the console."""
    start_time = time.time()
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"

    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    print(f"[ROUTE VISIT] {request.method} {path} -> {response.status_code} ({duration_ms:.1f}ms)", flush=True)
    return response

# Include Routers
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(chat.router, prefix="/api")


@app.get("/api/health", tags=["system"])
def health_check() -> dict[str, str]:
    """System health check endpoint."""
    return {"status": "healthy", "service": "Memory Chef API"}
