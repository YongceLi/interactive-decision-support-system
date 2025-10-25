"""
adapter.py — API client adapter for the car recommendation backend.

This version matches your API exactly:
- POST /chat expects a JSON with "message" as the FIRST key.
- The response JSON includes:
    session_id = data['session_id']   # revealed on first chat
    response   = data['response']     # assistant text
    vehicles   = data['vehicles']     # full ranked list
- Event logging: POST /session/{session_id}/event
    payload = {"event_type": <str>, "data": {"details": <dict>}}

Set BASE_URL via env var CARREC_BASE_URL or edit default below.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from collections import OrderedDict

import requests


def _get_base_url() -> str:
    return os.getenv("CARREC_BASE_URL", "http://localhost:8000")


@dataclass
class ApiClient:
    base_url: str = field(default_factory=_get_base_url)
    session_id: Optional[str] = None
    timeout: int = 300

    # ---------- Chat ----------

    def chat(self, message: str, ui_context: Dict[str, Any], meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a chat turn. The 'message' key MUST be first in the JSON object.
        We also send optional ui_context and meta after it.
        Response keys (per your API):
          - session_id (str)  -- adopt and cache on first turn
          - response (str)    -- assistant's text
          - vehicles (list)   -- ranked vehicles (we show top 3 in UI)
        """
        payload = OrderedDict()
        payload["message"] = message                 # MUST be first
        if ui_context:
            payload["ui_context"] = ui_context
        if meta:
            payload["meta"] = meta

        r = requests.post(f"{self.base_url}/chat", json=payload, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()

        # Adopt canonical session id from server
        sid = data.get("session_id")
        if sid:
            self.session_id = sid

        return data

    # ---------- Events ----------

    def log_event(self, event_type: str, details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Log an event to POST /session/{session_id}/event with payload:
          {"event_type": event_type, "data": {"details": details}}
        If no session has been established yet (no /chat done), we no-op gracefully.
        """
        if not self.session_id:
            # No session yet; can't log
            return {"ok": False, "note": "No session_id yet; skipping event", "details": details}

        path = f"/session/{self.session_id}/event"
        payload = {
            "event_type": event_type,
            "data": {"details": details}
        }
        try:
            r = requests.post(f"{self.base_url}{path}", json=payload, timeout=self.timeout)
            if r.status_code < 400:
                return r.json()
        except Exception:
            pass
        return {"ok": False, "note": "Event post failed", "payload": payload}
