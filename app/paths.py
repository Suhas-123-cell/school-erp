"""Filesystem locations, resolved from this file so the app works from any CWD."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MOCK_DATA_DIR = BASE_DIR / "mock_data"
FRONTEND_DIR = BASE_DIR / "frontend"
LOGS_DIR = BASE_DIR / "logs"
DB_PATH = Path(os.getenv("ERP_DB_PATH", str(LOGS_DIR / "conversations.db")))
