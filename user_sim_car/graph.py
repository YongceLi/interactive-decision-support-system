"""
graph.py — LangGraph-based user simulator for the car recommendation UI.

This revision introduces:
- A rolling RL-style scorer with positive/negative channels updated after each assistant response.
- A conversation summary agent that maintains an aggregated memory of the dialogue and UI actions.
- A judge agent that enforces persona/goal alignment before committing user turns.
- Richer UI state modeling (filters, detail modal, favorites, etc.) and dynamic action availability.
- Optional demo-mode snapshots for downstream visualization layers.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from user_sim_car.adapter import ApiClient


_HISTORY_TOKEN_LIMIT = 20_000
_APPROX_CHARS_PER_TOKEN = 4


class HistoryMessage(TypedDict):
    role: str
    content: str


def build_truncated_history(turns: List["Turn"]) -> List[HistoryMessage]:
    """Return a token-bounded message history using only user/assistant text."""
    messages: List[HistoryMessage] = []
    for turn in turns or []:
        user_text = turn.get("user_text")
        if user_text:
            messages.append({"role": "user", "content": str(user_text)})
        assistant_text = turn.get("assistant_text")
        if assistant_text:
            messages.append({"role": "assistant", "content": str(assistant_text)})

    if not messages:
        return []

    max_chars = _HISTORY_TOKEN_LIMIT * _APPROX_CHARS_PER_TOKEN
    total_chars = 0
    trimmed: List[HistoryMessage] = []
    for message in reversed(messages):
        total_chars += len(message["content"])
        trimmed.append(message)
        if total_chars >= max_chars:
            break
    trimmed.reverse()
    return trimmed


# ---------- Helpers & TypedDicts ----------


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


class PersonaDict(TypedDict):
    family: str
    writing: str
    interaction: str
    intent: str


class UIState(TypedDict, total=False):
    total: int
    visible_count: int
    start: int
    selection: Optional[int]
    detail_open: bool
    detail_index: Optional[int]
    favorites: List[int]
    filter_tokens: List[str]
    applied_filters: Dict[str, Any]
    pending_filters: Dict[str, Any]
    has_unapplied_filters: bool
    filter_menu_open: bool
    showing_favorites: bool
    last_actions: List[Dict[str, Any]]
    mileage_limit: Optional[int]
    price_band: Optional[str]


class Turn(TypedDict):
    user_text: str
    assistant_text: str
    actions: List[Dict[str, Any]]
    visible_indices: List[int]
    notes: str


class RLScores(TypedDict):
    positive: float
    negative: float


class RLThresholds(TypedDict):
    positive: float
    negative: float


class StopResult(TypedDict):
    kind: str
    scores: RLScores
    thresholds: RLThresholds
    rationale: str
    at_step: int


class SimState(TypedDict):
    seed_persona: str

    persona_family_draft: Optional[str]
    persona_writing_draft: Optional[str]
    persona_interaction_draft: Optional[str]
    persona_intent_draft: Optional[str]

    persona: PersonaDict

    rl_thresholds: Optional[RLThresholds]
    rl_scores: Optional[RLScores]
    rl_rationale: Optional[str]

    goal: Dict[str, Any]
    ui: UIState
    history: List[Turn]
    step: int
    stop_reason: Optional[str]
    session_id: Optional[str]
    backend_response: Dict[str, Any]
    vehicles: List[Dict[str, Any]]
    last_assistant: str
    quick_replies: Optional[List[str]]

    conversation_summary: str
    summary_version: int
    summary_notes: Optional[str]

    stop_result: Optional[StopResult]
    last_judge: Optional[Dict[str, Any]]
    completion_review: Optional[Dict[str, Any]]

    demo_mode: bool
    demo_snapshots: List[Dict[str, Any]]


# ---------- Persona Agents ----------


@dataclass
class PersonaAgent:
    name: str
    model: BaseChatModel

    def run(self, seed: str) -> str:
        sys_prompt = (
            "You are a concise persona shaper. Read the seed persona text and draft a short, concrete spec for the "
            f"{self.name} of the user. DO NOT invent out-of-distribution facts; constrain to realistic human signals given the seed. "
            "Avoid bullets; 2-4 natural sentences. Do not restate the other persona facets. Keep it human, varied, and non-repetitive."
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("human", "Seed persona:\n{seed}\n\nWrite the {facet} facet:"),
        ]).partial(facet=self.name)
        return (prompt | self.model).invoke({"seed": seed}).content.strip()


# ---------- Summary Agent ----------


@dataclass
class SummaryAgent:
    model: BaseChatModel

    def update(self, previous_summary: str, turn: Turn, ui: UIState, vehicles: List[Dict[str, Any]]) -> Tuple[str, str]:
        """Return (updated_summary, notes)."""
        sys_prompt = (
            "You maintain a rolling summary for a simulated car shopper interacting with an AI assistant. "
            "Blend new information from the latest turn with the prior summary. Capture evolving goals, constraints, emotional tone, "
            "and notable UI actions (filters, favorites, detail views). Keep the summary under 180 words. Notes should mention any significant changes or observations. "
            "Return JSON only: {{\"summary\": <string>, \"notes\": <string>}}"
        )
        vehicles_brief = []
        for v in (vehicles or [])[:3]:
            vehicle = v.get("vehicle", {}) if isinstance(v, dict) else {}
            listing = v.get("retailListing", {}) if isinstance(v, dict) else {}
            vehicles_brief.append({
                "make": vehicle.get("make", ""),
                "model": vehicle.get("model", ""),
                "price": listing.get("price"),
                "miles": listing.get("miles"),
            })
        prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("human",
             "Previous summary (can be empty):\n{previous}\n\n"
             "Latest turn:\n{turn}\n\n"
             "UI snapshot:\n{ui_state}\n\n"
             "Visible vehicles (top 3): {vehicles}\n\n"
             "Return JSON only."),
        ])
        raw = (prompt | self.model).invoke({
            "previous": previous_summary or "",
            "turn": turn,
            "ui_state": ui,
            "vehicles": vehicles_brief,
        }).content.strip()
        summary, notes = previous_summary, ""
        try:
            data = json.loads(raw)
            summary = str(data.get("summary", previous_summary or "")).strip() or previous_summary
            notes = str(data.get("notes", "")).strip()
        except Exception:
            notes = "Summary agent returned non-JSON; carrying previous summary forward."
        return summary, notes


# ---------- Judge Agent ----------


@dataclass
class JudgeAgent:
    model: BaseChatModel
    threshold: float = 0.75

    def evaluate(
        self,
        persona: PersonaDict,
        goal: Dict[str, Any],
        summary: str,
        candidate_text: str,
        actions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        sys_prompt = (
            "You are an alignment judge ensuring the simulated user's response stays true to their persona facets and shopping goal. "
            "Score alignment values range from 0 to 1. Provide constructive feedback and, when misaligned, a short reminder of the persona/goal. "
            "Return JSON only: {{\"score\": <float>, \"passes\": <bool>, \"feedback\": <string>, \"reminder\": <string>}}"
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("human",
             "Persona facets:\n"
             "- Family: {family}\n- Writing style: {writing}\n- Interaction style: {interaction}\n- Intent: {intent}\n\n"
             "Goal context: {goal}\n\n"
             "Conversation summary:\n{summary}\n\n"
             "Candidate user response: {text}\n"
             "Planned UI actions: {actions}\n\n"
             "Return JSON only."),
        ])
        raw = (prompt | self.model).invoke({
            "family": persona["family"],
            "writing": persona["writing"],
            "interaction": persona["interaction"],
            "intent": persona["intent"],
            "goal": goal,
            "summary": summary or "",
            "text": candidate_text,
            "actions": actions,
        }).content.strip()
        result = {"score": 0.0, "passes": False, "feedback": raw, "reminder": ""}
        try:
            data = json.loads(raw)
            result["score"] = float(data.get("score", 0.0))
            result["passes"] = bool(data.get("passes", False))
            result["feedback"] = str(data.get("feedback", "")).strip()
            result["reminder"] = str(data.get("reminder", "")).strip()
        except Exception:
            result["feedback"] = f"Judge returned non-JSON; treating as failure. Raw: {raw[:200]}"
        return result


@dataclass
class CompletionJudgeAgent:
    model: BaseChatModel

    def evaluate(
        self,
        persona: PersonaDict,
        goal: Dict[str, Any],
        summary: str,
        history: List[HistoryMessage],
        scores: RLScores,
        thresholds: RLThresholds,
    ) -> Dict[str, Any]:
        sys_prompt = (
            "You determine if the simulated shopper has achieved their intents and can wrap up the conversation. "
            "Use the persona facets, running summary, and full conversation history. "
            "If core needs remain unmet, recommend continuing."
            "Return JSON only: {{\"should_end\": <bool>, \"confidence\": <float>, \"reason\": <string>}}"
        )
        history_text = "\n".join(
            f"{msg['role'].title()}: {msg['content']}" for msg in (history or [])
        ) or "No conversation yet."
        prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("human",
             "Persona facets:\n"
             "- Family: {family}\n- Writing style: {writing}\n- Interaction style: {interaction}\n- Intent: {intent}\n\n"
             "Goal context: {goal}\n\n"
             "Current satisfaction scores vs thresholds: scores={scores} thresholds={thresholds}\n\n"
             "Conversation summary:\n{summary}\n\n"
             "Conversation history:\n{history}\n\n"
             "Return JSON only."),
        ])
        raw = (prompt | self.model).invoke({
            "family": persona["family"],
            "writing": persona["writing"],
            "interaction": persona["interaction"],
            "intent": persona["intent"],
            "goal": goal,
            "scores": scores,
            "thresholds": thresholds,
            "summary": summary or "",
            "history": history_text,
        }).content.strip()
        result = {"should_end": False, "confidence": 0.0, "reason": raw}
        try:
            data = json.loads(raw)
            result["should_end"] = bool(data.get("should_end", False))
            result["confidence"] = float(data.get("confidence", 0.0))
            result["reason"] = str(data.get("reason", "")).strip()
        except Exception:
            result["reason"] = f"Completion judge returned non-JSON; defaulting to continue. Raw: {raw[:200]}"
        return result


# ---------- User Agent (RL scorer + action planner) ----------


@dataclass
class UserAgent:
    model: BaseChatModel

    def derive_rl_model(self, persona: PersonaDict) -> Tuple[RLThresholds, RLScores, float, str]:
        sys_prompt = (
            "Calibrate a two-channel stop model for a simulated car shopper based on their persona facets. "
            "Positive channel represents satisfaction momentum; negative represents frustration."
            "The higher the positive channel is, the harder to please the persona, and vice versa. "
            "The lower the negative channel is, the easier the persona to be disappointed, impatient, likely to disengage. "
            "Thresholds set stopping points for each channel, where higher means harder to stop."
            "Set these thresholds conservatively. Thresholds usually have positive values around from 0.8 to 1.0 and negative values around from 0.6 to 0.8. "
            "Initial returns reflect starting satisfaction/frustration levels. The initial values usually have positive and negative values equal to 0, "
            "unless the persona comes into the conversation with prior satisfaction/frustration."
            "Positive, negative values range from 0 to 1."
            "Return JSON only: {{\"thresholds\": {{\"positive\": <float>, \"negative\": <float>}}, \"initial_returns\": {{\"positive\": <float>, \"negative\": <float>}}, \"notes\": <string>}}"
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("human",
             "Persona facets:\n"
             "- Family: {family}\n- Writing style: {writing}\n- Interaction style: {interaction}\n- Intent: {intent}\n\n"
             "Return JSON only."),
        ])
        raw = (prompt | self.model).invoke({
            "family": persona["family"],
            "writing": persona["writing"],
            "interaction": persona["interaction"],
            "intent": persona["intent"],
        }).content.strip()
        thresholds: RLThresholds = {"positive": 0.85, "negative": 0.65}
        scores: RLScores = {"positive": 0.15, "negative": 0.15}
        notes = ""
        try:
            data = json.loads(raw)
            if isinstance(data.get("thresholds"), dict):
                for k in ("positive", "negative"):
                    thresholds[k] = _clamp(float(data["thresholds"].get(k, thresholds[k])), 0.2, 0.99)
            if isinstance(data.get("initial_returns"), dict):
                for k in ("positive", "negative"):
                    scores[k] = _clamp(float(data["initial_returns"].get(k, scores[k])), 0.0, 0.9)
            notes = str(data.get("notes", "")).strip()
        except Exception:
            notes = "RL calibration fallback used due to parsing error."
        return thresholds, scores, notes

    def update_rl_scores(
        self,
        persona: PersonaDict,
        summary: str,
        turn: Turn,
        prev_scores: RLScores,
        visible_vehicles: List[Dict[str, Any]],
        history: List[HistoryMessage],
    ) -> Tuple[RLScores, str]:
        sys_prompt = (
            "Act as a critic for a simulated shopper. Based on the latest assistant reply, user response, UI action, and running summary, "
            "Positive delta boosts satisfaction, negative delta boosts frustration. The higher the delta, the stronger the effect. "
            "Positive delta increases when the latest assistant replies fit with what the user asks, the UI shows relevant results, "
            "or the information/question shows in the assistant replies are not repetitive with what inside the summary, etc. Vice versa when positive delta decreases."
            "Negative delta increases when the latest assistant replies are not relevant, gives the user frustration, or repetitive, etc."
            "Consider utility of visible vehicles too."
            "Positive, negative deltas range from -0.1 to 0.1"
            "Return JSON only: {{\"deltas\": {{\"positive\": <float>, \"negative\": <float>}}, \"rationale\": <string>}}"
        )
        vehicles_brief = []
        for v in (visible_vehicles or [])[:3]:
            vehicle = v.get("vehicle", {}) if isinstance(v, dict) else {}
            listing = v.get("retailListing", {}) if isinstance(v, dict) else {}
            vehicles_brief.append({
                "make": vehicle.get("make", ""),
                "model": vehicle.get("model", ""),
                "price": listing.get("price"),
                "miles": listing.get("miles"),
            })
        history_text = "\n".join(
            f"{msg['role'].title()}: {msg['content']}" for msg in (history or [])
        ) or "No prior turns."
        prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("human",
             "Persona facets:\n"
             "- Family: {family}\n- Writing style: {writing}\n- Interaction style: {interaction}\n- Intent: {intent}\n\n"
             "Conversation summary:\n{summary}\n\n"
             "Conversation history:\n{history}\n\n"
             "Previous returns: {prev}\n"
             "Latest turn: {turn}\n"
             "Visible vehicles now: {vehicles}\n\n"
             "Return JSON only."),
        ])
        raw = (prompt | self.model).invoke({
            "family": persona["family"],
            "writing": persona["writing"],
            "interaction": persona["interaction"],
            "intent": persona["intent"],
            "summary": summary or "",
            "history": history_text,
            "prev": prev_scores,
            "turn": turn,
            "vehicles": vehicles_brief,
        }).content.strip()
        deltas = {"positive": 0.0, "negative": 0.0}
        rationale = ""
        try:
            data = json.loads(raw)
            if isinstance(data.get("deltas"), dict):
                for k in ("positive", "negative"):
                    deltas[k] = float(data["deltas"].get(k, 0.0))
            rationale = str(data.get("rationale", "")).strip()
        except Exception:
            rationale = "RL critic returned non-JSON; applying mild decay."
        new_scores: RLScores = {
            "positive": _clamp(prev_scores["positive"] + deltas.get("positive", 0.0), 0.0, 1.0),
            "negative": _clamp(prev_scores["negative"] + deltas.get("negative", 0.0), 0.0, 1.0),
        }
        return new_scores, rationale

    def produce(
        self,
        persona: PersonaDict,
        summary: str,
        ui_description: str,
        goal: Dict[str, Any],
        thresholds: RLThresholds,
        scores: RLScores,
        available_actions: List[str],
        last_assistant: str,
        history: List[HistoryMessage],
        quick_replies: Optional[List[str]],
        reminder: Optional[str] = None,
    ) -> Tuple[str, List[Dict[str, Any]], str]:
        sys_prompt = (
            "You simulate a human car shopper. Use natural, varied sentences matching the persona. Incorporate the running summary, "
            "UI state, and last assistant message. When there is no actionable UI element, articulate needs explicitly. Always keep text under 120 words."
        )
        action_guide = "\n".join([
            "- CLICK_CARD: open the vehicle detail modal for the given carousel index (0-2).",
            "- CLOSE_DETAIL: close the currently open vehicle detail modal.",
            "- TOGGLE_FAVORITE: add/remove the highlighted vehicle from favorites (requires index).",
            "- CAROUSEL_LEFT / CAROUSEL_RIGHT: move the vehicle carousel backward or forward to see different cars.",
            "- TOGGLE_FILTER: toggle a shorthand filter token (use the provided id field).",
            "- REFRESH_FILTERS: apply pending filter adjustments to refresh the listings.",
            "- SET_MILEAGE / SET_PRICE_BAND: adjust numeric search constraints.",
            "- OPEN_FILTER_MENU / CLOSE_FILTER_MENU: open or close the filter drawer.",
            "- SHOW_FAVORITES / HIDE_FAVORITES: switch between favorites-only and all results.",
            "- SCROLL or STARE: continue browsing without changes (SCROLL implies casually looking through listings).",
            "- STOP: end the session intentionally once goals are satisfied.",
        ])
        instructions = (
            "Actions must use the available list verbatim when relevant (e.g., CLICK_CARD, CLOSE_DETAIL, TOGGLE_FILTER, REFRESH_FILTERS, SET_MILEAGE, SET_PRICE_BAND, OPEN_FILTER_MENU, CLOSE_FILTER_MENU, CAROUSEL_LEFT, CAROUSEL_RIGHT, SHOW_FAVORITES, HIDE_FAVORITES, TOGGLE_FAVORITE, SCROLL, STARE, STOP)."
            "If you choose a quick reply button, set user_text exactly to that text and mention it in the notes."
            "Return JSON only: {{\"user_text\": <string>, \"actions\": <list>, \"notes\": <string>}}"
        )
        reminder_msg = reminder or ""
        history_text = "\n".join(
            f"{msg['role'].title()}: {msg['content']}" for msg in (history or [])
        ) or "No prior turns."
        quick_reply_text = ", ".join(quick_replies or []) if quick_replies else "None"
        prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("system", "Persona facets:\n- Family: {family}\n- Writing style: {writing}\n- Interaction style: {interaction}\n- Intent: {intent}"),
            ("system", "Conversation summary so far:\n{summary}"),
            ("system", "Conversation history (chronological):\n{history}"),
            ("system", "UI context:\n{ui_description}"),
            ("system", "Goal/stop model: thresholds={thresholds} | scores={scores}"),
            ("system", "Available UI actions right now: {available}"),
            ("system", "UI action guide:\n{action_guide}"),
            ("system", "Quick reply buttons visible: {quick_replies}. If one fits perfectly, you can click it by echoing the same text."),
            ("system", "Judge reminder: {reminder}"),
            ("human",
             "Assistant just said:\n{assistant}\n\n"
             "Craft the next user message and UI action plan. {instructions}"),
        ]).partial(instructions=instructions)
        raw = (prompt | self.model).invoke({
            "family": persona["family"],
            "writing": persona["writing"],
            "interaction": persona["interaction"],
            "intent": persona["intent"],
            "summary": summary or "",
            "history": history_text,
            "ui_description": ui_description,
            "thresholds": thresholds,
            "scores": scores,
            "available": available_actions,
            "action_guide": action_guide,
            "quick_replies": quick_reply_text,
            "assistant": last_assistant or "",
            "reminder": reminder_msg or "None",
        }).content.strip()
        user_text, notes = "", ""
        actions: List[Dict[str, Any]] = []
        try:
            data = json.loads(raw)
            user_text = str(data.get("user_text", "")).strip()
            notes = str(data.get("notes", "")).strip()
            raw_actions = data.get("actions", [])
            if isinstance(raw_actions, dict):
                raw_actions = [raw_actions]
            for a in raw_actions or []:
                if isinstance(a, dict) and "type" in a:
                    action = {"type": str(a["type"]).upper()}
                    for key, value in a.items():
                        if key == "type":
                            continue
                        action[key] = value
                    actions.append(action)
                elif isinstance(a, str):
                    actions.append({"type": a.upper()})
        except Exception:
            user_text = raw
            notes = "Fallback: non-JSON user action payload; defaulting to STARE."
            actions = [{"type": "STARE"}]
        return user_text, actions, notes


# ---------- UI utilities ----------

_FILTER_TOKEN_EFFECTS = {
    "new": {"year": "2023-2024"},
    "used": {"year": "2015-2023"},
    "suv": {"body_style": "suv"},
    "sedan": {"body_style": "sedan"},
    "truck": {"body_style": "truck"},
    "electric": {"fuel_type": "electric"},
    "luxury": {"price_min": 40000},
    "family": {"seating_capacity": 5},
    "toyota": {"make": "Toyota"},
    "honda": {"make": "Honda"},
    "ford": {"make": "Ford"},
    "bmw": {"make": "BMW"},
    "tesla": {"make": "Tesla"},
    "subaru": {"make": "Subaru"},
    "camry": {"model": "Camry"},
    "cr-v": {"model": "CR-V"},
    "f-150": {"model": "F-150"},
    "model-3": {"model": "Model 3"},
    "x3": {"model": "X3"},
    "outback": {"model": "Outback"},
    "under30k": {"price_max": 30000},
    "30k-50k": {"price_min": 30000, "price_max": 50000},
    "50k-80k": {"price_min": 50000, "price_max": 80000},
    "over80k": {"price_min": 80000},
}

_PRICE_BANDS = {
    "under30k": {"price_max": 30000},
    "30k-50k": {"price_min": 30000, "price_max": 50000},
    "50k-80k": {"price_min": 50000, "price_max": 80000},
    "over80k": {"price_min": 80000},
}


def _compile_filters(tokens: List[str], mileage_limit: Optional[int], price_band: Optional[str]) -> Dict[str, Any]:
    compiled: Dict[str, Any] = {}
    for token in tokens:
        effect = _FILTER_TOKEN_EFFECTS.get(token.lower())
        if not effect:
            continue
        for key, value in effect.items():
            compiled[key] = value
    if mileage_limit is not None and mileage_limit < 200000:
        compiled["mileage_max"] = mileage_limit
    if price_band and price_band in _PRICE_BANDS:
        compiled.update(_PRICE_BANDS[price_band])
    return compiled


def apply_ui_actions(ui: UIState, actions: List[Dict[str, Any]]) -> UIState:
    new_ui: UIState = dict(ui)
    tokens = list(new_ui.get("filter_tokens", []))
    favorites = list(new_ui.get("favorites", []))
    mileage_limit = new_ui.get("mileage_limit")
    price_band = new_ui.get("price_band")
    start_index = int(new_ui.get("start") or 0)
    total = int(new_ui.get("total") or 0)
    visible_count = int(new_ui.get("visible_count") or 3) or 3
    for action in actions:
        t = str(action.get("type", "")).upper()
        if t == "CLICK_CARD":
            idx = int(action.get("index", 0))
            idx = max(0, min(2, idx))
            new_ui["selection"] = idx
            new_ui["detail_open"] = True
            new_ui["detail_index"] = idx
        elif t == "CLOSE_DETAIL":
            new_ui["detail_open"] = False
            new_ui["detail_index"] = None
        elif t == "TOGGLE_FAVORITE":
            idx = int(action.get("index", 0))
            idx = max(0, min(2, idx))
            if idx in favorites:
                favorites.remove(idx)
            else:
                favorites.append(idx)
        elif t == "SHOW_FAVORITES":
            new_ui["showing_favorites"] = True
        elif t == "HIDE_FAVORITES":
            new_ui["showing_favorites"] = False
        elif t == "TOGGLE_FILTER":
            token = str(action.get("id", "")).lower()
            if token in tokens:
                tokens.remove(token)
            else:
                tokens.append(token)
            new_ui["has_unapplied_filters"] = True
        elif t == "SET_MILEAGE":
            mileage_limit = int(action.get("value", 200000))
            new_ui["has_unapplied_filters"] = True
        elif t == "SET_PRICE_BAND":
            price_band = str(action.get("band", "")).lower() or None
            new_ui["has_unapplied_filters"] = True
        elif t == "REFRESH_FILTERS":
            compiled = _compile_filters(tokens, mileage_limit, price_band)
            new_ui["applied_filters"] = compiled
            new_ui["pending_filters"] = compiled
            new_ui["has_unapplied_filters"] = False
        elif t == "OPEN_FILTER_MENU":
            new_ui["filter_menu_open"] = True
        elif t == "CLOSE_FILTER_MENU":
            new_ui["filter_menu_open"] = False
        elif t == "APPLY_FILTER":
            filters = action.get("filters", {})
            if isinstance(filters, dict):
                new_ui["applied_filters"] = filters
                new_ui["pending_filters"] = filters
                new_ui["has_unapplied_filters"] = False
        elif t == "CAROUSEL_LEFT":
            if total and visible_count:
                start_index = max(0, start_index - visible_count)
        elif t == "CAROUSEL_RIGHT":
            if total and visible_count:
                max_start = max(0, total - visible_count)
                start_index = min(max_start, start_index + visible_count)
    new_ui["filter_tokens"] = tokens
    new_ui["favorites"] = favorites
    new_ui["mileage_limit"] = mileage_limit
    new_ui["price_band"] = price_band
    new_ui["pending_filters"] = _compile_filters(tokens, mileage_limit, price_band)
    max_start = max(0, total - visible_count) if total and visible_count else 0
    new_ui["visible_count"] = visible_count
    new_ui["start"] = max(0, min(start_index, max_start))
    new_ui["last_actions"] = actions
    return new_ui


def describe_ui_state(ui: UIState, vehicles: List[Dict[str, Any]]) -> str:
    selection = ui.get("selection")
    detail = ui.get("detail_open", False)
    favorites = ui.get("favorites", [])
    tokens = ui.get("filter_tokens", [])
    applied = ui.get("applied_filters", {})
    showing_favorites = ui.get("showing_favorites", False)
    has_unapplied = ui.get("has_unapplied_filters", False)
    filter_menu_open = ui.get("filter_menu_open", False)
    start = int(ui.get("start") or 0)
    visible = int(ui.get("visible_count") or 3) or 3
    total = int(ui.get("total") or len(vehicles or []))
    top_cards = []
    window = (vehicles or [])[start:start + visible]
    for offset, v in enumerate(window):
        idx = start + offset
        vehicle = v.get("vehicle", {}) if isinstance(v, dict) else {}
        listing = v.get("retailListing", {}) if isinstance(v, dict) else {}
        label = f"[{idx}] {vehicle.get('make', '')} {vehicle.get('model', '')}"
        price = listing.get("price")
        miles = listing.get("miles")
        if price:
            label += f", ${price:,}"
        if miles:
            label += f", {miles:,} mi"
        top_cards.append(label)
    window_end = min(total, start + visible)
    if window_end <= start:
        window_range = "none"
    else:
        window_range = f"{start}-{window_end - 1}"
    parts = [
        f"Top carousel cards: {top_cards if top_cards else 'None available yet'}.",
        f"Detail modal {'open' if detail else 'closed'} (selection={selection}).",
        f"Favorites badges on indices: {favorites if favorites else 'none'}.",
        f"Active filter tokens: {tokens if tokens else 'none'}; applied filters: {applied if applied else 'none'}.",
        f"Filter drawer {'open' if filter_menu_open else 'closed'}, pending changes require Refresh button: {has_unapplied}.",
        f"Favorites view {'active' if showing_favorites else 'hidden'}.",
        f"Carousel window showing indices {window_range} of {total} total.",
    ]
    return " ".join(parts)


def list_available_actions(ui: UIState) -> List[str]:
    actions = ["SCROLL", "STARE"]
    if ui.get("detail_open"):
        actions.append("CLOSE_DETAIL")
        actions.append("TOGGLE_FAVORITE")
    else:
        actions.append("CLICK_CARD")
    actions.extend(["TOGGLE_FILTER", "REFRESH_FILTERS", "SET_MILEAGE", "SET_PRICE_BAND", "OPEN_FILTER_MENU", "CLOSE_FILTER_MENU"])
    total = int(ui.get("total") or 0)
    visible = int(ui.get("visible_count") or 3) or 3
    start = int(ui.get("start") or 0)
    if total and visible:
        if start > 0:
            actions.append("CAROUSEL_LEFT")
        if start + visible < total:
            actions.append("CAROUSEL_RIGHT")
    actions.extend(["SHOW_FAVORITES", "HIDE_FAVORITES"])
    actions.append("STOP")
    return sorted(set(actions))


# ---------- Graph Runner ----------


class GraphRunner:
    def __init__(
        self,
        chat_model: BaseChatModel,
        base_url: Optional[str] = None,
        verbose: bool = True,
        event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        self.model = chat_model
        self.api = ApiClient(base_url=base_url or os.getenv("CARREC_BASE_URL", "http://localhost:8000"))
        self.memory = MemorySaver()
        self.verbose = verbose
        self.event_callback = event_callback

        self.family_agent = PersonaAgent("Family background (size, location, preferences)", chat_model)
        self.writing_agent = PersonaAgent("Writing style (grammar, spelling, consistency)", chat_model)
        self.interaction_agent = PersonaAgent("Interaction style (clarification, coherence)", chat_model)
        self.intent_agent = PersonaAgent("Intent (market research, checking, comparing)", chat_model)

        self.user_agent = UserAgent(chat_model)
        self.summary_agent = SummaryAgent(chat_model)
        self.judge_agent = JudgeAgent(chat_model)
        self.completion_judge = CompletionJudgeAgent(chat_model)

        self.graph = self._build_graph()

    def _build_graph(self):
        g = StateGraph(SimState)

        def n_family(state: SimState):
            return {"persona_family_draft": self.family_agent.run(state["seed_persona"])}

        def n_writing(state: SimState):
            return {"persona_writing_draft": self.writing_agent.run(state["seed_persona"])}

        def n_interaction(state: SimState):
            return {"persona_interaction_draft": self.interaction_agent.run(state["seed_persona"])}

        def n_intent(state: SimState):
            return {"persona_intent_draft": self.intent_agent.run(state["seed_persona"])}

        def n_merge(state: SimState):
            fam = state.get("persona_family_draft")
            wri = state.get("persona_writing_draft")
            inter = state.get("persona_interaction_draft")
            intent = state.get("persona_intent_draft")
            if not all([fam, wri, inter, intent]):
                return {}
            persona: PersonaDict = {
                "family": fam or "",
                "writing": wri or "",
                "interaction": inter or "",
                "intent": intent or "",
            }
            if self.verbose:
                print("\n=== Persona merged ===")
                print(f"- Family:      {persona['family']}")
                print(f"- Writing:     {persona['writing']}")
                print(f"- Interaction: {persona['interaction']}")
                print(f"- Intent:      {persona['intent']}")
            return {"persona": persona}

        def n_user(state: SimState):
            persona = state["persona"]
            thresholds = state.get("rl_thresholds")
            scores = state.get("rl_scores")
            updates: Dict[str, Any] = {}
            if thresholds is None or scores is None:
                thresholds, scores, init_notes = self.user_agent.derive_rl_model(persona)
                updates.update({
                    "rl_thresholds": thresholds,
                    "rl_scores": scores,
                    "rl_rationale": init_notes,
                })
                if self.verbose:
                    print("\n=== RL model initialized ===")
                    print(f"Thresholds: {thresholds}")
                    print(f"Initial returns: {scores}")
                    if init_notes:
                        print(f"Notes: {init_notes}")
                if self.event_callback:
                    payload: Dict[str, Any] = {
                        "thresholds": dict(thresholds or {}),
                        "scores": dict(scores or {}),
                        "notes": init_notes,
                    }
                    self.event_callback("rl_init", payload)
            summary = state.get("conversation_summary", "")
            ui_desc = describe_ui_state(state["ui"], state.get("vehicles", []))
            available_actions = list_available_actions(state["ui"])
            last_assistant = state.get("last_assistant", "")
            history_messages = build_truncated_history(state.get("history", []))
            quick_replies = state.get("quick_replies")
            reminder = None
            judge_result: Optional[Dict[str, Any]] = None
            user_text, actions, notes = "", [], ""
            for _attempt in range(2):
                user_text, actions, notes = self.user_agent.produce(
                    persona=persona,
                    summary=summary,
                    ui_description=ui_desc,
                    goal=state["goal"],
                    thresholds=thresholds or state.get("rl_thresholds", {"positive": 0.85, "negative": 0.65}),
                    scores=scores or state.get("rl_scores", {"positive": 0.15, "negative": 0.15}),
                    available_actions=available_actions,
                    last_assistant=last_assistant,
                    history=history_messages,
                    quick_replies=quick_replies,
                    reminder=reminder,
                )
                judge_result = self.judge_agent.evaluate(persona, state["goal"], summary, user_text, actions)
                if judge_result.get("score", 0.0) >= self.judge_agent.threshold:
                    break
                reminder = judge_result.get("reminder") or "Stay in character and honor the intent before responding again."
            updates["backend_response"] = {
                "pending_user_text": user_text,
                "pending_actions": actions,
                "notes": notes,
            }
            updates["last_judge"] = judge_result
            return updates

        def n_ui(state: SimState):
            pending = state["backend_response"]
            actions = pending.get("pending_actions", [])
            ui_next = apply_ui_actions(state["ui"], actions)
            self.api.log_event("user_actions_applied", {
                "actions": actions,
                "ui_state_before": state["ui"],
                "ui_state_after": ui_next,
                "step": state["step"],
            })
            return {"ui": ui_next}

        def n_call_backend(state: SimState):
            pending = state["backend_response"]
            user_text = pending.get("pending_user_text", "")
            ui_ctx = {
                "start": state["ui"].get("start", 0),
                "visible_count": state["ui"].get("visible_count", 3),
                "selection": state["ui"].get("selection"),
                "filters": state["ui"].get("applied_filters", {}),
                "favorites": state["ui"].get("favorites", []),
                "detail_open": state["ui"].get("detail_open", False),
            }
            meta = {
                "step": state["step"],
                "actions": pending.get("pending_actions", []),
                "summary": state.get("conversation_summary", ""),
                "judge": state.get("last_judge"),
            }
            resp = self.api.chat(message=user_text, ui_context=ui_ctx, meta=meta)
            vehicles = resp.get("vehicles") or []
            total = len(vehicles)
            ui_updated: UIState = dict(state["ui"])
            start_index = int(ui_updated.get("start") or 0)
            visible_count = int(ui_updated.get("visible_count") or 3) or 3
            max_start = max(0, total - visible_count)
            start_index = max(0, min(start_index, max_start))
            ui_updated.update({
                "total": int(total),
                "visible_count": visible_count,
                "start": start_index,
            })
            visible_indices = list(range(start_index, min(total, start_index + visible_count)))
            assistant_text = resp.get("response", "")
            quick_replies = resp.get("quick_replies")
            turn: Turn = {
                "user_text": user_text,
                "assistant_text": assistant_text,
                "actions": pending.get("pending_actions", []),
                "visible_indices": visible_indices,
                "notes": pending.get("notes", ""),
            }
            if self.verbose:
                turn_no = state["step"] + 1
                print(f"\n--- Turn {turn_no} ---")
                if turn["notes"]:
                    print(f"Notes: {turn['notes']}")
                print(f"User: {turn['user_text']}")
                print(f"Actions: {turn['actions']}")
                print(f"Assistant: {assistant_text if len(assistant_text) < 2000 else assistant_text[:2000] + '…'}")
                print("-----")
                print(f"Scores: {state.get('rl_scores')} | Thresholds: {state.get('rl_thresholds')}")
                print(f"Judge: {state.get('last_judge')}")
            hist = state["history"] + [turn]
            self.api.log_event("assistant_response", {
                "snippet": assistant_text[:200],
                "total_vehicles": total,
                "step": state["step"],
            })
            resp_copy = dict(resp)
            return {
                "backend_response": resp_copy,
                "ui": ui_updated,
                "history": hist,
                "vehicles": vehicles,
                "step": state["step"] + 1,
                "session_id": self.api.session_id,
                "last_assistant": assistant_text,
                "quick_replies": quick_replies,
            }

        def n_post_backend(state: SimState):
            if not state.get("history"):
                return {}
            turn = state["history"][-1]
            summary_prev = state.get("conversation_summary", "")
            summary, summary_notes = self.summary_agent.update(summary_prev, turn, state["ui"], state.get("vehicles", []))
            scores = state.get("rl_scores") or {"positive": 0.15, "negative": 0.15}
            thresholds = state.get("rl_thresholds") or {"positive": 0.85, "negative": 0.65}
            history_messages = build_truncated_history(state.get("history", []))
            new_scores, rationale = self.user_agent.update_rl_scores(
                persona=state["persona"],
                summary=summary,
                turn=turn,
                prev_scores=scores,
                visible_vehicles=state.get("vehicles", []),
                history=history_messages,
            )
            stop_result: Optional[StopResult] = None
            completion_review: Optional[Dict[str, Any]] = None
            if new_scores["positive"] >= thresholds["positive"]:
                completion_review = self.completion_judge.evaluate(
                    persona=state["persona"],
                    goal=state["goal"],
                    summary=summary,
                    history=history_messages,
                    scores=new_scores,
                    thresholds=thresholds,
                )
                if completion_review.get("should_end"):
                    stop_result = {
                        "kind": "positive",
                        "scores": new_scores,
                        "thresholds": thresholds,
                        "rationale": (completion_review.get("reason") or rationale or "Intents satisfied; judge approved completion."),
                        "at_step": state["step"],
                    }
            elif new_scores["negative"] >= thresholds["negative"]:
                stop_result = {
                    "kind": "negative",
                    "scores": new_scores,
                    "thresholds": thresholds,
                    "rationale": rationale or "Negative frustration exceeded threshold.",
                    "at_step": state["step"],
                }
            updates: Dict[str, Any] = {
                "conversation_summary": summary,
                "summary_version": state.get("summary_version", 0) + 1,
                "summary_notes": summary_notes,
                "rl_scores": new_scores,
                "rl_rationale": rationale,
                "stop_result": stop_result,
                "completion_review": completion_review,
            }
            if self.verbose and rationale:
                print(f"RL rationale: {rationale}")
            self.api.log_event("post_turn_metrics", {
                "summary_excerpt": summary[:200],
                "scores": new_scores,
                "thresholds": thresholds,
                "rationale": rationale,
                "judge": state.get("last_judge"),
                "completion_review": completion_review,
                "step": state["step"],
            })
            if state.get("demo_mode"):
                snapshot = {
                    "step": state["step"],
                    "user_text": turn["user_text"],
                    "assistant_text": turn["assistant_text"],
                    "actions": turn["actions"],
                    "summary": summary,
                    "scores": new_scores,
                    "judge": state.get("last_judge"),
                    "rationale": rationale,
                    "quick_replies": state.get("quick_replies"),
                    "completion_review": completion_review,
                    "vehicles": (state.get("vehicles", []) or [])[:3],
                }
                updates["demo_snapshots"] = state.get("demo_snapshots", []) + [snapshot]
                if self.event_callback:
                    self.event_callback("turn", snapshot)
            return updates

        def n_check_stop(state: SimState):
            goal = state["goal"]
            step_limit = int(goal.get("max_steps", 8))
            selection = state["ui"].get("selection")
            last_actions = state["ui"].get("last_actions") or []
            stop = None
            if state.get("stop_result"):
                sr = state["stop_result"]
                stop = f"Stop ({sr['kind']}) — scores={sr['scores']} thresholds={sr['thresholds']}"
            if stop is None:
                if state["step"] >= step_limit:
                    stop = f"Reached step limit {step_limit}"
                elif any((a.get("type") or "").upper() == "STOP" for a in last_actions):
                    stop = "User decided to stop"
                elif selection is not None and goal.get("stop_on_selection", True):
                    stop = f"Selected item index {selection}"
            if stop:
                self.api.log_event("session_stop", {
                    "reason": stop,
                    "steps": state["step"],
                    "stop_result": state.get("stop_result"),
                })
                if self.verbose:
                    print(f"\n=== Stop: {stop} ===")
                return {"stop_reason": stop}
            return {}

        g.add_node("family", n_family)
        g.add_node("writing", n_writing)
        g.add_node("interaction", n_interaction)
        g.add_node("intent", n_intent)
        g.add_node("merge", n_merge)
        g.add_node("await_more", lambda state: {})
        g.add_node("user", n_user)
        g.add_node("ui", n_ui)
        g.add_node("backend", n_call_backend)
        g.add_node("post_backend", n_post_backend)
        g.add_node("check_stop", n_check_stop)

        g.add_edge(START, "family")
        g.add_edge(START, "writing")
        g.add_edge(START, "interaction")
        g.add_edge(START, "intent")
        g.add_edge("family", "merge")
        g.add_edge("writing", "merge")
        g.add_edge("interaction", "merge")
        g.add_edge("intent", "merge")

        def route_merge(state: SimState) -> str:
            if all([
                state.get("persona_family_draft"),
                state.get("persona_writing_draft"),
                state.get("persona_interaction_draft"),
                state.get("persona_intent_draft"),
            ]):
                return "user"
            return "await_more"

        g.add_conditional_edges("merge", route_merge, {"user": "user", "await_more": "await_more"})

        g.add_edge("user", "ui")
        g.add_edge("ui", "backend")
        g.add_edge("backend", "post_backend")
        g.add_edge("post_backend", "check_stop")

        def route_check(state: SimState) -> str:
            return END if state.get("stop_reason") else "user"

        g.add_conditional_edges("check_stop", route_check, {"user": "user", END: END})

        return g.compile(checkpointer=self.memory)

    def run_session(
        self,
        seed_persona: str,
        chat_model: BaseChatModel,
        max_steps: int = 8,
        thread_id: Optional[str] = None,
        recursion_limit: int = 100,
        demo_mode: bool = False,
    ) -> SimState:
        init: SimState = {
            "seed_persona": seed_persona,
            "persona_family_draft": None,
            "persona_writing_draft": None,
            "persona_interaction_draft": None,
            "persona_intent_draft": None,
            "persona": {"family": "", "writing": "", "interaction": "", "intent": ""},
            "rl_thresholds": None,
            "rl_scores": None,
            "rl_rationale": None,
            "goal": {"max_steps": max_steps, "stop_on_selection": False},
            "ui": {
                "total": 0,
                "visible_count": 3,
                "start": 0,
                "selection": None,
                "detail_open": False,
                "detail_index": None,
                "favorites": [],
                "filter_tokens": [],
                "applied_filters": {},
                "pending_filters": {},
                "has_unapplied_filters": False,
                "filter_menu_open": False,
                "showing_favorites": False,
                "last_actions": [],
                "mileage_limit": None,
                "price_band": None,
            },
            "history": [],
            "step": 0,
            "stop_reason": None,
            "session_id": None,
            "backend_response": {},
            "vehicles": [],
            "last_assistant": "",
            "quick_replies": None,
            "conversation_summary": "",
            "summary_version": 0,
            "summary_notes": None,
            "stop_result": None,
            "last_judge": None,
            "completion_review": None,
            "demo_mode": demo_mode,
            "demo_snapshots": [],
        }
        tid = thread_id or "sim-thread"
        state = self.graph.invoke(
            init,
            config={
                "configurable": {"thread_id": tid},
                "recursion_limit": recursion_limit,
            },
        )
        return state
