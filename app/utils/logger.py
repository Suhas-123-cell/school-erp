import json
import time
from pathlib import Path
from loguru import logger

Path("logs").mkdir(exist_ok=True)

logger.add(
    "logs/erp_assistant.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    rotation="10 MB",
    retention="30 days",
    level="INFO",
)

logger.add(
    "logs/erp_errors.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    rotation="5 MB",
    retention="30 days",
    level="ERROR",
)


def log_interaction(
    query: str,
    intent: str,
    tools: list,
    execution_time: float,
    response: str,
    student_id: str,
) -> dict:
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "student_id": student_id,
        "user_query": query,
        "identified_intent": intent,
        "selected_tools": tools,
        "execution_time_ms": round(execution_time * 1000, 2),
        "response_preview": response[:200] if response else "",
    }
    logger.info(f"INTERACTION | {json.dumps(entry)}")
    return entry
