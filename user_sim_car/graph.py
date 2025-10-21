"""
graph.py — LangGraph-based user simulator for your car recommendation UI.

This version:
- Keeps TOP-3 vehicle UI (picture, model/make, price, mileage). To see details, user must CLICK_CARD (0..2).
- User can take ZERO or MANY actions per turn (actions: list).
- /chat request sends "message" first (built in adapter).
- Response fields consumed: response (assistant text), session_id, vehicles (list).
- Prints each turn.
- Adds a 3-channel stop score model (positive / neutral / negative):
    * On the FIRST loop, UserAgent derives thresholds in [0,1] and initial scores in [0,1].
    * On EVERY turn, UserAgent updates the scores given persona, last assistant text, visible items, and recent history.
    * If any score > its threshold, the agent emits STOP and we record a structured stop_result.
- Raises graph recursion limit to avoid GraphRecursionError.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from user_sim_car.adapter import ApiClient
import json


# ---------- State ----------

class PersonaDict(TypedDict):
    family: str
    writing: str
    interaction: str
    intent: str

class UIState(TypedDict):
    total: int               # total items (we only show top 3)
    visible_count: int       # fixed at 3
    start: int               # 0 in this UI (top 3)
    selection: Optional[int] # absolute index selected (0..2)
    last_actions: List[Dict[str, Any]]

class Turn(TypedDict):
    user_text: str
    assistant_text: str
    actions: List[Dict[str, Any]]
    visible_indices: List[int]
    notes: str

class StopScores(TypedDict):
    positive: float
    neutral: float
    negative: float

class StopThresholds(TypedDict):
    positive: float
    neutral: float
    negative: float

class StopResult(TypedDict):
    kind: str                 # "positive" | "neutral" | "negative"
    scores: StopScores
    thresholds: StopThresholds
    rationale: str
    at_step: int

class SimState(TypedDict):
    seed_persona: str

    # Drafts produced by parallel persona shapers
    persona_family_draft: Optional[str]
    persona_writing_draft: Optional[str]
    persona_interaction_draft: Optional[str]
    persona_intent_draft: Optional[str]

    # Final merged persona
    persona: PersonaDict

    # NEW: stop model
    stop_thresholds: Optional[StopThresholds]
    stop_scores: Optional[StopScores]
    stop_result: Optional[StopResult]
    stop_rationale: Optional[str]

    goal: Dict[str, Any]
    ui: UIState
    history: List[Turn]
    step: int
    stop_reason: Optional[str]
    session_id: Optional[str]
    backend_response: Dict[str, Any]  # raw last response (holds response, vehicles, session_id)


# ---------- Persona Agents ----------

@dataclass
class PersonaAgent:
    name: str
    model: BaseChatModel

    def run(self, seed: str) -> str:
        sys_prompt = (
            "You are a concise persona shaper. Read the seed persona text and draft a short, concrete spec for the "
            f"{self.name} of the user. DO NOT invent out-of-distribution facts; constrain to realistic human signals "
            "given the seed. Avoid bullets; 2-4 natural sentences. Do not restate the other persona facets. "
            "Keep it human, varied, and non-repetitive."
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("human", "Seed persona:\n{seed}\n\nWrite the {facet} facet:"),
        ]).partial(facet=self.name)
        return (prompt | self.model).invoke({"seed": seed}).content.strip()


# ---------- User Agent (multi-action + stop scores) ----------

@dataclass
class UserAgent:
    model: BaseChatModel

    # --- A) Derive thresholds & initial scores once, from persona ---

    def derive_stop_model(
        self, persona: PersonaDict
    ) -> Tuple[StopThresholds, StopScores, str]:
        """
        Ask the LLM to propose thresholds and initial scores (all in [0,1]) given the persona.
        Returns (thresholds, initial_scores, notes).
        """
        sys_prompt = (
            "You calibrate three stop channels (positive_stop, neutral_stop, negative_stop) in [0,1]. "
            "Given the user persona, output JSON with keys {{\"thresholds\"}} and {{\"initial_scores\"}} "
            "where each has fields {{\"positive\"}}, {{\"neutral\"}}, {{\"negative\"}} ∈ [0,1]. "
            "Interpretation:\n"
            "- positive: the user is satisfied (e.g., found a great fit, next step is calling dealer).\n"
            "- neutral: external/time friction (session long, needs to leave, fatigue).\n"
            "- negative: dissatisfaction (irrelevant recs, unhelpful responses, frustration).\n"
            "Choose thresholds that reflect how quickly this persona tends to stop for each channel."
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("human",
             "Persona facets:\n"
             "- Family: {family}\n- Writing style: {writing}\n- Interaction style: {interaction}\n- Intent: {intent}\n\n"
             "Return JSON only: {{\"thresholds\": {{\"positive\": <float>, \"neutral\": <float>, \"negative\": <float>}}, "
             "\"initial_scores\": {{\"positive\": <float>, \"neutral\": <float>, \"negative\": <float>}}, \"notes\": <string>}}")
        ])
        raw = (prompt | self.model).invoke({
            "family": persona["family"],
            "writing": persona["writing"],
            "interaction": persona["interaction"],
            "intent": persona["intent"],
        }).content.strip()

        # Safe defaults if parsing fails
        thresholds: StopThresholds = {"positive": 1, "neutral": 0.5, "negative": 0.5}
        initial: StopScores = {"positive": 0.25, "neutral": 0.25, "negative": 0.25}
        notes = ""
        try:
            data = json.loads(raw)
            if isinstance(data.get("thresholds"), dict):
                for k in ("positive", "neutral", "negative"):
                    v = float(data["thresholds"].get(k, thresholds[k]))
                    thresholds[k] = max(0.0, min(1.0, v))
            if isinstance(data.get("initial_scores"), dict):
                for k in ("positive", "neutral", "negative"):
                    v = float(data["initial_scores"].get(k, initial[k]))
                    initial[k] = max(0.0, min(1.0, v))
            notes = str(data.get("notes", "")).strip()
        except Exception:
            notes = "LLM returned non-JSON; using conservative defaults."
        return thresholds, initial, notes

    # --- B) Update scores each turn ---

    def update_stop_scores(
        self,
        persona: PersonaDict,
        last_assistant: str,
        prev_scores: StopScores,
        visible_vehicles: List[Dict[str, Any]],
        history_tail: List[Turn],
    ) -> Tuple[StopScores, str]:
        """
        Ask LLM to produce new scores based on last assistant text, what is visible now (top-3),
        and a short recent history (last ~2 turns). Returns (scores, rationale).
        """
        sys_prompt = (
            "Update three stop scores in [0,1]: {{\"positive\"}}, {{\"neutral\"}}, {{\"negative\"}}. "
            "Base it on the most recent assistant message, the top-3 visible vehicles (make/model/price/mileage), "
            "and brief recent history. Return JSON: {{\"scores\": {{...}}, \"rationale\": <string>}}. "
            "Guidance:\n"
            "- Increase positive if the assistant aligns well to needs (budget, body style, safety, etc.).\n"
            "- Increase neutral with time/friction/fatigue, long explanations, or if user already did many turns.\n"
            "- Increase negative if recommendations are mismatched, repetitive, or confusing."
        )
        # keep history short for prompt
        recent = history_tail[-2:] if history_tail else []
        vehicles_brief = []
        for v in (visible_vehicles or [])[:3]:
            vehicles_brief.append({
                "make": v.get("vehicle").get("make") or "",
                "model": v.get("vehicle").get("model") or "",
                "price": v.get("retailListing").get("price") or "",
                "mileage": v.get("retailListing").get("miles") or "",
            })

        prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("human",
             "Persona facets:\n"
             "- Family: {family}\n- Writing style: {writing}\n- Interaction style: {interaction}\n- Intent: {intent}\n\n"
             "Previous scores: {prev_scores}\n"
             "Recent history (<=2 turns): {recent}\n"
             "Top-3 vehicles now: {vehicles}\n"
             "Last assistant message:\n{assistant_text}\n\n"
             "Return JSON only: {{\"scores\": {{\"positive\": <float>, \"neutral\": <float>, \"negative\": <float>}}, "
             "\"rationale\": <string>}}")
        ])
        raw = (prompt | self.model).invoke({
            "family": persona["family"],
            "writing": persona["writing"],
            "interaction": persona["interaction"],
            "intent": persona["intent"],
            "prev_scores": prev_scores,
            "recent": recent,
            "vehicles": vehicles_brief,
            "assistant_text": last_assistant or "",
        }).content.strip()

        new_scores: StopScores = dict(prev_scores)  # start from previous
        rationale = ""
        try:
            data = json.loads(raw)
            if isinstance(data.get("scores"), dict):
                for k in ("positive", "neutral", "negative"):
                    v = float(data["scores"].get(k, new_scores[k]))
                    new_scores[k] = max(0.0, min(1.0, v))
            rationale = str(data.get("rationale", "")).strip()
        except Exception:
            # conservative fallback: small neutral drift upward across time
            new_scores["neutral"] = max(new_scores["neutral"], min(1.0, new_scores["neutral"] + 0.05))
            rationale = "LLM returned non-JSON; applied small neutral drift."
        return new_scores, rationale

    # --- C) Produce the next message & action list ---

    def produce(
        self,
        persona: PersonaDict,
        last_assistant: str,
        ui: UIState,
        goal: Dict[str, Any],
        thresholds: StopThresholds,
        scores: StopScores,
    ) -> Tuple[str, List[Dict[str, Any]], str]:
        """
        Returns: (user_text, actions, notes)
        actions is a LIST (zero or more). Each action is an object:
          - {"type": "CLICK_CARD", "index": 0|1|2}
          - {"type": "APPLY_FILTER", "filters": {...}}
          - {"type": "SCROLL"} | {"type": "STARE"} | {"type": "STOP"}
        The prompt includes current stop thresholds & scores so the agent can decide organically.
        """
        sys_prompt = (
            "You simulate a human car shopper. Speak naturally with brief, varied sentences; never repeat yourself. "
            "Base decisions on the persona facets below. The UI only shows 3 vehicles at a time; each shows a picture, "
            "model/make, price, and mileage. To see more details about a vehicle, the user must CLICK its card. \n\n"
            "Communicate naturally, based on the persona facets and UI state, and the history of the conversation. When there is nothing on the UI (nothing in selection section and 0 total vehicles reported) to act on, "
            "communicate with the assistant clearly with what you are looking for, considering the persona facets and assistant message.\n\n"
            "Produce two things:\n"
            "1) Next user message to the car-recommendation assistant.\n"
            "2) ZERO or MORE UI actions as JSON array, using:\n"
            '   {{"type": "CLICK_CARD", "index": 0|1|2}}\n'
            '   {{"type": "APPLY_FILTER", "filters": {{...}}}}\n'
            '   {{"type": "SCROLL"}} | {{"type": "STARE"}} | {{"type": "STOP"}}\n'
            "If any stop score is likely above its threshold, include a STOP action."
        )
        ui_desc = (
            f"Visible (top 3) indices: [0,1,2], selection: {ui.get('selection')}, total vehicles reported: {ui['total']}"
        )
        goal_desc = f"Goal thresholds: {goal}"
        stop_desc = (
            f"Stop thresholds: {thresholds}; current stop scores: {scores}"
        )
        last_assistant = last_assistant or ""

        prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("system", "Persona facets:\n- Family: {family}\n- Writing style: {writing}\n- Interaction style: {interaction}\n- Intent: {intent}"),
            ("system", "UI: {ui_desc}\n{goal_desc}\n{stop_desc}"),
            ("human",
             "Assistant just said:\n{assistant_text}\n\nNow:\n"
             "- Write the next user message.\n"
             "- Return JSON with keys: {{\"user_text\": <string>, \"actions\": <list of objects>, \"notes\": <string>}}.\n"
             "No code blocks.")
        ]).partial(ui_desc=ui_desc, goal_desc=goal_desc, stop_desc=stop_desc)

        raw = (prompt | self.model).invoke({
            "family": persona["family"],
            "writing": persona["writing"],
            "interaction": persona["interaction"],
            "intent": persona["intent"],
            "assistant_text": last_assistant
        }).content.strip()

        user_text, notes = "", ""
        actions: List[Dict[str, Any]] = []
        try:
            data = json.loads(raw)
            user_text = str(data.get("user_text", "")).strip()
            notes = str(data.get("notes", "")).strip()
            # Normalize actions to list[dict]
            raw_actions = data.get("actions", [])
            if isinstance(raw_actions, dict):
                raw_actions = [raw_actions]
            for a in raw_actions or []:
                if isinstance(a, str):
                    if a.upper() in {"SCROLL", "STARE", "STOP"}:
                        actions.append({"type": a.upper()})
                elif isinstance(a, dict) and "type" in a:
                    t = a["type"].upper()
                    item = {"type": t}
                    if t == "CLICK_CARD":
                        idx = a.get("index", 1)
                        try:
                            idx = int(idx)
                        except Exception:
                            idx = 1
                        idx = max(0, min(2, idx))
                        item["index"] = idx
                    elif t == "APPLY_FILTER":
                        item["filters"] = a.get("filters", {})
                    actions.append(item)
        except Exception:
            user_text = raw
            actions = [{"type": "STARE"}]
            notes = "LLM returned non-JSON; using text and STARE."
        return user_text, actions, notes


# ---------- UI Environment (apply a LIST of actions) ----------

def apply_ui_actions(ui: UIState, actions: List[Dict[str, Any]]) -> UIState:
    total = ui["total"]
    selection = ui.get("selection")

    # Only CLICK_CARD and STOP affect UI state in this top-3 model
    for a in actions:
        t = (a.get("type") or "").upper()
        if t == "CLICK_CARD":
            idx = int(a.get("index", 1))
            idx = max(0, min(2, idx))
            selection = idx
        elif t == "STOP":
            pass

    return {
        "total": total,
        "visible_count": 3,
        "start": 0,
        "selection": selection,
        "last_actions": actions,
    }


# ---------- Graph ----------

class GraphRunner:
    def __init__(self, chat_model: BaseChatModel, base_url: Optional[str] = None, verbose: bool = True):
        self.model = chat_model
        self.api = ApiClient(base_url=base_url or os.getenv("CARREC_BASE_URL", "http://localhost:8000"))
        self.memory = MemorySaver()
        self.verbose = verbose

        self.family_agent = PersonaAgent("Family background (size, location, preferences)", chat_model)
        self.writing_agent = PersonaAgent("Writing style (grammar, spelling, consistency)", chat_model)
        self.interaction_agent = PersonaAgent("Interaction style (clarification, coherence)", chat_model)
        self.intent_agent = PersonaAgent("Intent (market research, checking, comparing)", chat_model)

        self.user_agent = UserAgent(chat_model)
        self.graph = self._build_graph()

    def _build_graph(self):
        g = StateGraph(SimState)

        # --- Persona nodes (each writes its own draft key; no collisions)
        def n_family(state: SimState):
            return {"persona_family_draft": self.family_agent.run(state["seed_persona"])}

        def n_writing(state: SimState):
            return {"persona_writing_draft": self.writing_agent.run(state["seed_persona"])}

        def n_interaction(state: SimState):
            return {"persona_interaction_draft": self.interaction_agent.run(state["seed_persona"])}

        def n_intent(state: SimState):
            return {"persona_intent_draft": self.intent_agent.run(state["seed_persona"])}

        # Merge: only set final persona once all drafts exist
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

        # --- USER NODE: derive/refresh stop model; generate message & actions ---
        def n_user(state: SimState):
            last_assistant = state.get("backend_response", {}).get("response", "")
            persona = state["persona"]

            # Initialize thresholds & initial scores on first entry
            thresholds = state.get("stop_thresholds")
            scores = state.get("stop_scores")
            init_notes = ""
            if thresholds is None or scores is None:
                thresholds, scores, init_notes = self.user_agent.derive_stop_model(persona)
                if self.verbose:
                    print("\n=== Stop model initialized ===")
                    print(f"Thresholds: {thresholds}")
                    print(f"Initial scores: {scores}")
                    if init_notes:
                        print(f"Notes: {init_notes}")

            # Update scores based on last assistant, visible items, short history
            last_resp = state.get("backend_response") or {}
            vehicles = last_resp.get("vehicles") or []
            visible_now = vehicles[:3] if isinstance(vehicles, list) else []
            new_scores, rationale = self.user_agent.update_stop_scores(
                persona=persona,
                last_assistant=last_assistant,
                prev_scores=scores,  # type: ignore
                visible_vehicles=visible_now,
                history_tail=state.get("history", []),
            )
            # If any score exceeds threshold, force STOP and record a result
            stop_kind: Optional[str] = None
            for k in ("positive", "neutral", "negative"):
                if new_scores[k] > (thresholds[k] if thresholds else 1.0):
                    stop_kind = k
                    break

            # Produce next user message & proposed actions
            user_text, actions, notes = self.user_agent.produce(
                persona=persona,
                last_assistant=last_assistant,
                ui=state["ui"],
                goal=state["goal"],
                thresholds=thresholds,  # type: ignore
                scores=new_scores,
            )

            if stop_kind:
                # Ensure STOP is included exactly once
                if not any((a.get("type") or "").upper() == "STOP" for a in actions):
                    actions = actions + [{"type": "STOP"}]
                stop_result: StopResult = {
                    "kind": stop_kind,
                    "scores": new_scores,
                    "thresholds": thresholds,  # type: ignore
                    "rationale": rationale or "Threshold exceeded.",
                    "at_step": state["step"],
                }
                # store for check_stop & auditing
                return {
                    "backend_response": {"pending_user_text": user_text, "pending_actions": actions, "notes": notes},
                    "stop_scores": new_scores,
                    "stop_thresholds": thresholds,
                    "stop_result": stop_result,
                    "stop_rationale": rationale,
                }

            # No threshold breach yet
            return {
                "backend_response": {"pending_user_text": user_text, "pending_actions": actions, "notes": notes},
                "stop_scores": new_scores,
                "stop_thresholds": thresholds,
                "stop_rationale": rationale,
            }

        def n_ui(state: SimState):
            pending = state["backend_response"]
            actions = pending.get("pending_actions", [])
            ui_next = apply_ui_actions(state["ui"], actions)

            self.api.log_event("user_actions_applied", {
                "actions": actions,
                "ui_state_before": state["ui"],
                "ui_state_after": ui_next,
                "step": state["step"]
            })
            return {"ui": ui_next}

        def n_call_backend(state: SimState):
            pending = state["backend_response"]
            user_text = pending.get("pending_user_text", "")

            # Compose minimal UI context for backend
            ui_ctx = {
                "start": 0,  # top-3 UI only
                "visible_count": 3,
                "selection": state["ui"].get("selection"),
            }
            # Include actions in meta (extra fields allowed)
            meta = {"step": state["step"], "actions": pending.get("pending_actions", [])}

            resp = self.api.chat(message=user_text, ui_context=ui_ctx, meta=meta)
            # resp: { "session_id": ..., "response": ..., "vehicles": [...] }

            # Update UI totals using vehicles count (top 3 visible only)
            vehicles = resp.get("vehicles") or []
            total = len(vehicles)

            ui_updated: UIState = {
                "total": int(total),
                "visible_count": 3,
                "start": 0,
                "selection": state["ui"].get("selection"),
                "last_actions": state["ui"].get("last_actions", []),
            }

            # Build the turn object for printing & history
            visible_indices = list(range(0, min(3, total)))
            assistant_text = resp.get("response", "")

            turn: Turn = {
                "user_text": user_text,
                "assistant_text": assistant_text,
                "actions": pending.get("pending_actions", []),
                "visible_indices": visible_indices,
                "notes": pending.get("notes", ""),
            }

            # ---- PRINT PER TURN ----
            if self.verbose:
                turn_no = state["step"] + 1
                print(f"\n--- Turn {turn_no} ---")
                if turn["notes"]:
                    print(f"Notes: {turn['notes']}")
                print(f"User: {turn['user_text']}")
                print(f"Actions: {turn['actions']}")
                print(f"Assistant: {assistant_text if len(assistant_text) < 2000 else assistant_text[:2000] + '…'}")
                print("-----")
                print(f"Scores: {state.get('stop_scores')} | Thresholds: {state.get('stop_thresholds')}")
                print(f"Re-scoring reasoning: {state.get('stop_rationale')}")
                print("-----")
                if vehicles:
                    def vfmt(v):
                        make = v.get("vehicle").get("make") or ""
                        model = v.get("vehicle").get("model") or ""
                        price = v.get("retailListing").get("price") or ""
                        mileage = v.get("retailListing").get("miles") or ""
                        return f"{make} {model} — {price}, {mileage} mi"
                    print("Visible vehicles:")
                    for i, idx in enumerate(visible_indices):
                        if idx < len(vehicles):
                            print(f"  [{i}] {vfmt(vehicles[idx])}")
                    print(f"Total vehicles reported: {total}")
            else:
                turn_no = state["step"] + 1
                print(f"\n\n--- Turn {turn_no} ---")
                print(f"User: {turn['user_text']}")
                print("----")
                print(f"Actions: {turn['actions']}")
                print("----")
                print(f"Assistant: {assistant_text if len(assistant_text) < 2000 else assistant_text[:2000] + '…'}")
                print("-----")
                print(f"Scores: {state.get('stop_scores')} | Thresholds: {state.get('stop_thresholds')}")
                print("-----")
                if vehicles:
                    def vfmt(v):
                        make = v.get("vehicle").get("make") or ""
                        model = v.get("vehicle").get("model") or ""
                        price = v.get("retailListing").get("price") or ""
                        mileage = v.get("retailListing").get("miles") or ""
                        return f"{make} {model} — {price}, {mileage} mi"
                    print("Visible vehicles:")
                    for i, idx in enumerate(visible_indices):
                        if idx < len(vehicles):
                            print(f"  [{i}] {vfmt(vehicles[idx])}")
                    print(f"Total vehicles reported: {total}")

            hist = state["history"] + [turn]

            # Log assistant response
            self.api.log_event("assistant_response", {
                "snippet": assistant_text[:200],
                "total_vehicles": total,
                "step": state["step"]
            })

            # Capture raw backend response for downstream nodes
            resp_copy = dict(resp)

            return {
                "backend_response": resp_copy,
                "ui": ui_updated,
                "history": hist,
                "step": state["step"] + 1,
                "session_id": self.api.session_id,
            }

        def n_check_stop(state: SimState):
            goal = state["goal"]
            step_limit = int(goal.get("max_steps", 8))
            selection = state["ui"].get("selection")
            last_actions = state["ui"].get("last_actions") or []
            stop = None

            # Prefer model-based stop if present
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
                    "stop_result": state.get("stop_result")
                })
                if self.verbose:
                    print(f"\n=== Stop: {stop} ===")
                return {"stop_reason": stop}
            return {}

        # Nodes
        g.add_node("family", n_family)
        g.add_node("writing", n_writing)
        g.add_node("interaction", n_interaction)
        g.add_node("intent", n_intent)
        g.add_node("merge", n_merge)
        g.add_node("await_more", lambda state: {})  # parked until all drafts exist
        g.add_node("user", n_user)
        g.add_node("ui", n_ui)
        g.add_node("backend", n_call_backend)
        g.add_node("check_stop", n_check_stop)

        # Parallel persona edges
        g.add_edge(START, "family")
        g.add_edge(START, "writing")
        g.add_edge(START, "interaction")
        g.add_edge(START, "intent")
        g.add_edge("family", "merge")
        g.add_edge("writing", "merge")
        g.add_edge("interaction", "merge")
        g.add_edge("intent", "merge")

        # Merge gate
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

        # Main loop
        g.add_edge("user", "ui")
        g.add_edge("ui", "backend")
        g.add_edge("backend", "check_stop")

        def route_check(state: SimState) -> str:
            return END if state.get("stop_reason") else "user"
        g.add_conditional_edges("check_stop", route_check, {"user": "user", END: END})

        return g.compile(checkpointer=self.memory)

    # ---------- Public API ----------

    def run_session(
        self,
        seed_persona: str,
        chat_model: BaseChatModel,
        max_steps: int = 8,
        thread_id: Optional[str] = None,
        recursion_limit: int = 100,  # NEW: raise beyond default 25
    ) -> SimState:
        init: SimState = {
            "seed_persona": seed_persona,
            "persona_family_draft": None,
            "persona_writing_draft": None,
            "persona_interaction_draft": None,
            "persona_intent_draft": None,
            "persona": {"family": "", "writing": "", "interaction": "", "intent": ""},

            # stop model
            "stop_thresholds": None,
            "stop_scores": None,
            "stop_result": None,
            "stop_rationale": None,

            "goal": {"max_steps": max_steps, "stop_on_selection": False},
            "ui": {"total": 0, "visible_count": 3, "start": 0, "selection": None, "last_actions": []},
            "history": [],
            "step": 0,
            "stop_reason": None,
            "session_id": None,
            "backend_response": {},
        }

        # Required when a checkpointer is present; plus set recursion_limit here
        tid = thread_id or "sim-thread"
        state = self.graph.invoke(
            init,
            config={
                "configurable": {"thread_id": tid},
                "recursion_limit": recursion_limit,  # <-- prevents GraphRecursionError
            },
        )
        return state