from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except Exception:
    pass


def env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y"}


APP_NAME = os.getenv("APP_NAME", "TrueStack University Assistant")
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(ROOT / "storage" / "university.db")))
CHROMA_PATH = Path(os.getenv("CHROMA_PATH", str(ROOT / "storage" / "chroma")))
DOCUMENTS_PATH = Path(os.getenv("DOCUMENTS_PATH", str(ROOT / "data" / "documents")))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
MOCK_LLM = env_bool("MOCK_LLM", True)
TOP_K = max(1, int(os.getenv("TOP_K", "5")))
MAX_UPLOAD_MB = max(1, int(os.getenv("MAX_UPLOAD_MB", "100")))

OCR_MAX_PAGES = max(1, int(os.getenv("OCR_MAX_PAGES", "12")))
OCR_DPI = max(80, int(os.getenv("OCR_DPI", "140")))
