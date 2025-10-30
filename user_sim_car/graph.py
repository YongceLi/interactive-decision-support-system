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


def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
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


class EmotionScore(TypedDict):
    value: float


class EmotionThreshold(TypedDict):
    lower: float


class StopResult(TypedDict):
    kind: str
    score: EmotionScore
    threshold: EmotionThreshold
    rationale: str
    at_step: int


class SimState(TypedDict):
    seed_persona: str

    persona_family_draft: Optional[str]
    persona_writing_draft: Optional[str]
    persona_interaction_draft: Optional[str]
    persona_intent_draft: Optional[str]

    persona: PersonaDict

    emotion_threshold: Optional[EmotionThreshold]
    emotion_score: Optional[EmotionScore]
    emotion_rationale: Optional[str]
    emotion_delta: Optional[float]
    emotion_delta_rationale: Optional[str]

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
        emotion_score: EmotionScore,
        emotion_threshold: EmotionThreshold,
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
             "Current emotion value vs disengagement threshold: value={emotion} threshold={threshold}\n\n"
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
            "emotion": emotion_score.get("value", 0.0),
            "threshold": emotion_threshold.get("lower", -0.4),
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

    def _normalize_actions(
        self,
        actions: List[Dict[str, Any]],
        user_text: str,
        quick_replies: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Attach reporting labels and enforce quick reply/text alignment."""

        normalized: List[Dict[str, Any]] = []
        quick_reply_choice: Optional[str] = None
        quick_lookup = {
            str(option).strip(): str(option)
            for option in (quick_replies or [])
            if isinstance(option, str)
        }

        for raw in actions:
            if not isinstance(raw, dict):
                continue
            action_type = str(raw.get("type", "")).upper()
            if not action_type:
                continue
            action: Dict[str, Any] = {k: v for k, v in raw.items() if k != "label"}
            action["type"] = action_type

            if action_type == "QUICK_REPLY":
                value = raw.get("value")
                label = str(value).strip() if value is not None else ""
                trimmed_user = user_text.strip()
                # if not label and trimmed_user:
                #     label = trimmed_user
                # if label in quick_lookup:
                #     label = quick_lookup[label]
                # elif trimmed_user in quick_lookup:
                #     label = quick_lookup[trimmed_user]
                action["value"] = label
                action["label"] = label
                quick_reply_choice = label or quick_reply_choice
            elif action_type == "CLICK_CARD":
                try:
                    idx = int(raw.get("index", 0))
                except Exception:
                    idx = 0
                action["index"] = idx
                action["label"] = f"#{idx + 1}"
            else:
                label_raw = raw.get("label")
                if isinstance(label_raw, str) and label_raw.strip():
                    action["label"] = label_raw.strip()

            normalized.append(action)

        if quick_reply_choice:
            user_text = quick_reply_choice

        return normalized, user_text

    def derive_emotion_model(self, persona: PersonaDict) -> Tuple[EmotionThreshold, EmotionScore, str]:
        sys_prompt = (
            "Calibrate the scalar emotion model for a simulated car shopper using their persona facets. "
            "Emotion value ranges from -1 (furious) to 1 (delighted); 0 is neutral. "
            "Set a single lower-bound disengagement threshold: higher (e.g., -0.4) means they disengage quickly, lower (e.g., -1) means they are patient."
            "Most personas begin at 0 unless the seed implies prior satisfaction or frustration."
            "Return JSON only: {{\"threshold\": <float>, \"initial_value\": <float>, \"notes\": <string>}}"
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
        threshold: EmotionThreshold = {"lower": -0.4}
        score: EmotionScore = {"value": 0.0}
        notes = ""
        try:
            data = json.loads(raw)
            if "threshold" in data:
                threshold["lower"] = _clamp(float(data.get("threshold", threshold["lower"])), -0.9, 0.4)
            if "initial_value" in data:
                score["value"] = _clamp(float(data.get("initial_value", score["value"])))
            notes = str(data.get("notes", "")).strip()
        except Exception:
            notes = "Emotion calibration fallback used due to parsing error."
        return threshold, score, notes

    def update_emotion_score(
        self,
        persona: PersonaDict,
        summary: str,
        history: List[HistoryMessage],
        prev_score: EmotionScore,
        last_turn: Optional[Turn],
        last_rationale: Optional[str],
        threshold: EmotionThreshold,
        ui_after: str,
    ) -> Tuple[EmotionScore, float, str]:
        sys_prompt = (
            "Update the shopper's scalar emotion value before they respond to the assistant. "
            "Emotion value is in [-1, 1]; -1 is furious, 1 is thrilled. "
            "Focus on whether the assistant satisfied the shopper's most recent request and what the UI now shows. "
            "Never adjust the score purely because the shopper's words sound positive or negative; treat tone only as a clue to their goals. "
            "Use persona facets, the running summary, truncated conversation history, and the last user/assistant exchange plus resulting UI actions. "
            "Account for the current emotion value and disengagement threshold ({threshold_lower}). "
            "Return a delta between -0.2 and 0.2. "
            "Explain both (a) why the delta was chosen and (b) how the resulting emotion value will influence the shopper's upcoming message and UI actions. "
            "Return JSON only: {{\"delta\": <float>, \"rationale\": <string>}}"
        )
        history_text = "\n".join(
            f"{msg['role'].title()}: {msg['content']}" for msg in (history or [])
        ) or "No prior turns."
        turn_obj = last_turn or {}
        last_user = str(turn_obj.get("user_text", "")).strip()
        last_assistant = str(turn_obj.get("assistant_text", "")).strip()
        actions = turn_obj.get("actions", []) or []
        actions_text = json.dumps(actions, ensure_ascii=False)
        prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("human",
             "Persona facets:\n"
             "- Family: {family}\n- Writing style: {writing}\n- Interaction style: {interaction}\n- Intent: {intent}\n\n"
             "Conversation summary:\n{summary}\n\n"
             "Conversation history:\n{history}\n\n"
             "Previous emotion value: {prev}\n"
             "Last user request: {last_user}\n"
             "Assistant reply: {last_assistant}\n"
             "UI after their actions: {ui_after}\n"
             "User actions executed: {actions}\n"
             "User agent rationale for that turn: {notes}\n"
             "Disengagement threshold (lower bound): {threshold}\n\n"
             "Return JSON only."),
        ])
        raw = (prompt | self.model).invoke({
            "family": persona["family"],
            "writing": persona["writing"],
            "interaction": persona["interaction"],
            "intent": persona["intent"],
            "summary": summary or "",
            "history": history_text,
            "prev": prev_score,
            "last_user": last_user or "No prior user message.",
            "last_assistant": last_assistant or "Assistant response unavailable.",
            "ui_after": ui_after or "UI state unchanged.",
            "actions": actions_text,
            "notes": last_rationale or "None provided",
            "threshold": threshold,
            "threshold_lower": threshold.get("lower", -0.4),
        }).content.strip()
        delta = 0.0
        rationale = ""
        try:
            data = json.loads(raw)
            delta = _clamp(float(data.get("delta", 0.0)), -0.4, 0.4)
            rationale = str(data.get("rationale", "")).strip()
        except Exception:
            rationale = f"Emotion critic returned non-JSON; keeping previous score. Raw: {raw[:200]}"
        new_value = _clamp(prev_score.get("value", 0.0) + delta)
        return {"value": new_value}, delta, rationale


    def produce(
        self,
        persona: PersonaDict,
        summary: str,
        ui_description: str,
        goal: Dict[str, Any],
        emotion_threshold: EmotionThreshold,
        emotion_score: EmotionScore,
        emotion_delta: Optional[float],
        emotion_delta_rationale: Optional[str],
        available_actions: List[str],
        last_assistant: str,
        history: List[HistoryMessage],
        quick_replies: Optional[List[str]],
        reminder: Optional[str] = None,
    ) -> Tuple[str, List[Dict[str, Any]], str]:
        sys_prompt = (
            "You simulate a human car shopper. Use natural, varied sentences matching the persona. Incorporate the running summary, "
            "UI state, emotion value, and last assistant message. When there is no actionable UI element, articulate needs explicitly. Always keep text under 120 words."
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
            "- QUICK_REPLY: press one of the assistant's quick reply chips (include a value field).",
            "- STOP_NEGATIVE: end the session because the shopper is frustrated or disengaging.",
            "- STOP_POSITIVE: end the session joyfully after achieving all shopping goals.",
        ])
        instructions = (
            "Actions must use the available list verbatim when relevant (e.g., CLICK_CARD, CLOSE_DETAIL, TOGGLE_FILTER, REFRESH_FILTERS, SET_MILEAGE, SET_PRICE_BAND, OPEN_FILTER_MENU, CLOSE_FILTER_MENU, CAROUSEL_LEFT, CAROUSEL_RIGHT, SHOW_FAVORITES, HIDE_FAVORITES, TOGGLE_FAVORITE, QUICK_REPLY, STOP_NEGATIVE, STOP_POSITIVE)."
            "Use STOP_NEGATIVE only when the shopper is giving up from low emotion or impatience, and STOP_POSITIVE only when the intent feels completely satisfied and the emotion value is at its peak."
            "If you choose a quick reply, set user_text exactly to that text, include a single QUICK_REPLY action with a value field describing the button label, and avoid conflicting actions."
            "Quick reply actions must mirror the chip label verbatim so the UI action reads 'QUICK_REPLY <value>'."
            "When using CLICK_CARD, include an index field (0 for the first visible card) so the UI log can surface which card was opened."
            "Always include a decision_rationale string explaining how the current emotion value, the latest delta, and persona facets shaped the message and UI plan."
            "Return JSON only: {{\"user_text\": <string>, \"actions\": <list>, \"decision_rationale\": <string>}}"
        )
        reminder_msg = reminder or ""
        history_text = "\n".join(
            f"{msg['role'].title()}: {msg['content']}" for msg in (history or [])
        ) or "No prior turns."
        quick_reply_text = ", ".join(quick_replies or []) if quick_replies else "None"
        delta_str = "{:+.2f}".format(emotion_delta) if emotion_delta is not None else "+0.00"
        prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("system", "Persona facets:\n- Family: {family}\n- Writing style: {writing}\n- Interaction style: {interaction}\n- Intent: {intent}"),
            ("system", "Conversation summary so far:\n{summary}"),
            ("system", "Conversation history (chronological):\n{history}"),
            ("system", "UI context:\n{ui_description}"),
            ("system", "Emotion tracker: value={emotion_value} | delta={emotion_delta} | threshold(lower)={emotion_threshold} | delta_rationale={emotion_delta_rationale}"),
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
            "emotion_value": emotion_score.get("value", 0.0),
            "emotion_delta": delta_str,
            "emotion_threshold": emotion_threshold.get("lower", -0.4),
            "emotion_delta_rationale": emotion_delta_rationale or "None recorded",
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
            notes = str(data.get("decision_rationale", data.get("notes", ""))).strip()
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
            actions, user_text = self._normalize_actions(actions, user_text, quick_replies)
        except Exception:
            user_text = raw
            notes = "Fallback: non-JSON user action payload; no structured UI actions captured."
            actions = []
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
    actions: List[str] = []
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
    actions.extend(["STOP_NEGATIVE", "STOP_POSITIVE"])
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
            threshold = state.get("emotion_threshold")
            score = state.get("emotion_score")
            updates: Dict[str, Any] = {}
            if threshold is None or score is None:
                threshold, score, init_notes = self.user_agent.derive_emotion_model(persona)
                updates.update({
                    "emotion_threshold": threshold,
                    "emotion_score": score,
                    "emotion_rationale": init_notes,
                })
                if self.verbose:
                    print("\n=== Emotion model initialized ===")
                    print(f"Threshold (lower bound): {threshold}")
                    print(f"Initial emotion value: {score}")
                    if init_notes:
                        print(f"Notes: {init_notes}")
                if self.event_callback:
                    payload: Dict[str, Any] = {
                        "threshold": dict(threshold or {}),
                        "score": dict(score or {}),
                        "notes": init_notes,
                    }
                    self.event_callback("emotion_init", payload)
            summary = state.get("conversation_summary", "")
            ui_desc = describe_ui_state(state["ui"], state.get("vehicles", []))
            available_actions = list_available_actions(state["ui"])
            quick_replies = state.get("quick_replies") or []
            if quick_replies:
                available_actions = sorted(set(available_actions + ["QUICK_REPLY"]))
            last_assistant = state.get("last_assistant", "")
            history_messages = build_truncated_history(state.get("history", []))
            reminder = None
            judge_result: Optional[Dict[str, Any]] = None
            user_text, actions, notes = "", [], ""
            for _attempt in range(2):
                user_text, actions, notes = self.user_agent.produce(
                    persona=persona,
                    summary=summary,
                    ui_description=ui_desc,
                    goal=state["goal"],
                    emotion_threshold=threshold or state.get("emotion_threshold", {"lower": -0.4}),
                    emotion_score=score or state.get("emotion_score", {"value": 0.0}),
                    emotion_delta=state.get("emotion_delta"),
                    emotion_delta_rationale=state.get("emotion_delta_rationale"),
                    available_actions=available_actions,
                    last_assistant=last_assistant,
                    history=history_messages,
                    quick_replies=quick_replies or None,
                    reminder=reminder,
                )
                if any((str(a.get("type", "")).upper() if isinstance(a, dict) else str(a).upper()) == "QUICK_REPLY" for a in (actions or [])):
                    judge_result = {"score": 1.0, "passes": True, "feedback": "Quick reply selected; auto-approved.", "reminder": ""}
                    break
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
            vehicles_payload = resp.get("vehicles")
            if vehicles_payload:
                vehicles = vehicles_payload
            else:
                vehicles = state.get("vehicles", [])
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
                print(f"Emotion: {state.get('emotion_score')} | Threshold: {state.get('emotion_threshold')}")
                print(f"Judge: {state.get('last_judge')}")
            hist = state["history"] + [turn]
            self.api.log_event("assistant_response", {
                "snippet": assistant_text[:200],
                "total_vehicles": total,
                "step": state["step"],
            })
            resp_copy = dict(resp)
            resp_copy["vehicles"] = vehicles
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
            updates: Dict[str, Any] = {
                "conversation_summary": summary,
                "summary_version": state.get("summary_version", 0) + 1,
                "summary_notes": summary_notes,
            }
            if self.verbose and summary_notes:
                print(f"Summary notes: {summary_notes}")
            self.api.log_event("summary_update", {
                "summary_excerpt": summary[:200],
                "notes": summary_notes,
                "step": state["step"],
            })
            return updates


        def n_emotion_update(state: SimState):
            completed_steps = int(state.get("step") or 0)
            last_processed = int(state.get("emotion_last_step") or -1)
            history = state.get("history") or []
            if completed_steps <= last_processed:
                return {}
            if not history:
                return {"emotion_last_step": completed_steps}
            threshold = state.get("emotion_threshold") or {"lower": -0.4}
            score = state.get("emotion_score") or {"value": 0.0}
            last_turn = history[-1]
            summary = state.get("conversation_summary", "")
            history_messages = build_truncated_history(history)
            ui_snapshot = describe_ui_state(state["ui"], state.get("vehicles", []))
            new_score, delta, rationale = self.user_agent.update_emotion_score(
                persona=state["persona"],
                summary=summary,
                history=history_messages,
                prev_score=score,
                last_turn=last_turn,
                last_rationale=last_turn.get("notes"),
                threshold=threshold,
                ui_after=ui_snapshot,
            )
            completion_review: Optional[Dict[str, Any]] = None
            stop_result: Optional[StopResult] = None
            completion_gate = 0.999
            if new_score.get("value", 0.0) >= completion_gate:
                completion_review = self.completion_judge.evaluate(
                    persona=state["persona"],
                    goal=state["goal"],
                    summary=summary,
                    history=history_messages,
                    emotion_score=new_score,
                    emotion_threshold=threshold,
                )
                if completion_review.get("should_end"):
                    stop_result = {
                        "kind": "STOP_POSITIVE",
                        "score": new_score,
                        "threshold": threshold,
                        "rationale": completion_review.get("reason") or rationale or "Goals satisfied; completion judge approved.",
                        "at_step": state["step"],
                    }
            if stop_result is None and new_score.get("value", 0.0) <= threshold.get("lower", -0.4):
                stop_result = {
                    "kind": "STOP_NEGATIVE",
                    "score": new_score,
                    "threshold": threshold,
                    "rationale": rationale or "Emotion value dropped below disengagement threshold.",
                    "at_step": state["step"],
                }
            updates: Dict[str, Any] = {
                "emotion_score": new_score,
                "emotion_delta": delta,
                "emotion_delta_rationale": rationale,
                "emotion_rationale": rationale,
                "stop_result": stop_result,
                "completion_review": completion_review,
                "emotion_last_step": completed_steps,
            }
            if self.verbose and rationale:
                print(f"Emotion update: value={new_score.get('value')} delta={delta:+.2f} -> {rationale}")
            self.api.log_event("emotion_update", {
                "score": new_score,
                "delta": delta,
                "threshold": threshold,
                "rationale": rationale,
                "completion_review": completion_review,
                "step": state["step"],
            })
            if state.get("demo_mode"):
                snapshot = {
                    "step": state["step"],
                    "user_text": last_turn.get("user_text"),
                    "assistant_text": last_turn.get("assistant_text"),
                    "actions": last_turn.get("actions"),
                    "summary": summary,
                    "emotion": new_score,
                    "delta": delta,
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
                stop = f"Stop ({sr['kind']}) — emotion={sr['score']} threshold={sr['threshold']}"
            if stop is None:
                if state["step"] >= step_limit:
                    stop = f"Reached step limit {step_limit}"
                else:
                    manual_stop = None
                    for a in last_actions:
                        t = (a.get("type") if isinstance(a, dict) else None) or ""
                        upper = str(t).upper()
                        if upper == "STOP_NEGATIVE":
                            manual_stop = "User decided to stop (negative)"
                            break
                        if upper == "STOP_POSITIVE":
                            manual_stop = "User decided to stop (positive)"
                            break
                    if manual_stop:
                        stop = manual_stop
                if stop is None and selection is not None and goal.get("stop_on_selection", True):
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
        g.add_node("emotion", n_emotion_update)
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
        g.add_edge("ui", "emotion")
        g.add_edge("emotion", "backend")
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
            "emotion_threshold": None,
            "emotion_score": None,
            "emotion_rationale": None,
            "emotion_delta": None,
            "emotion_delta_rationale": None,
            "emotion_last_step": -1,
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
