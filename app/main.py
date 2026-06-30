import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

from app.api.chat import router as chat_router
from app.memory import conversation_store as mem
from app.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    mem.init_db()
    logger.info("School ERP Assistant started")
    yield
    logger.info("School ERP Assistant shut down")


app = FastAPI(
    title="AI School ERP Assistant",
    description="Natural language interface for School ERP — attendance, marks, fees, homework, timetable, and more.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc), "status_code": 500},
    )


@app.get("/", tags=["Frontend"], include_in_schema=False)
async def serve_frontend():
    return FileResponse(Path("frontend/index.html"))


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy", "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")}


app.include_router(chat_router)

app.mount("/", StaticFiles(directory="frontend"), name="static")
