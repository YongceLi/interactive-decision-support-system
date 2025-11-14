"""
Utilities for persisting conversation transcripts for debugging.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

from langchain_core.messages import BaseMessage

from idss_agent.utils.logger import get_logger


logger = get_logger("utils.conversation_logger")

DEFAULT_LOG_ROOT = Path(
    os.getenv(
        "IDSS_CONVERSATION_LOG_DIR",
        Path(__file__).resolve().parent.parent.parent / "logs" / "conversations",
    )
)


def _ensure_directory(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)


def _serialize_message(message: BaseMessage) -> Dict[str, Any]:
    return {
        "role": getattr(message, "type", message.__class__.__name__.lower()),
        "content": message.content,
    }


def save_conversation_log(
    session_id: str,
    state: Dict[str, Any],
    log_root: Path | None = None,
) -> Path | None:
    """
    Persist the current conversation state to a JSON file for troubleshooting.
    """
    try:
        log_dir = Path(log_root) if log_root else DEFAULT_LOG_ROOT
        _ensure_directory(log_dir)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        # Include timestamp in filename to avoid overwriting previous logs
        filename = f"{timestamp}_{session_id or 'unknown'}.json"
        log_path = log_dir / filename

        conversation: Iterable[BaseMessage] = state.get("conversation_history", [])
        serialized_history = [_serialize_message(msg) for msg in conversation]

        # Get products/vehicles - check both fields for compatibility
        recommended_products = state.get('recommended_products') or state.get('recommended_vehicles', [])
        
        payload = {
            "session_id": session_id,
            "timestamp": timestamp,
            "ai_response": state.get("ai_response"),
            "explicit_filters": state.get("explicit_filters"),
            "implicit_preferences": state.get("implicit_preferences"),
            "recommended_products": recommended_products[:20] if recommended_products else [],
            "conversation_history": serialized_history,
            "diagnostics": state.get("diagnostics"),
            "latency": state.get("_latency"),
            "latency_stats": state.get("_latency_stats"),
            "last_updated": timestamp,
        }

        log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        logger.info("Conversation log saved to %s", log_path)
        return log_path
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to persist conversation log: %s", exc, exc_info=True)
        return None



