"""Utility to run the car-rec user simulator for the web_simulation UI.

This script mirrors ``run_demo.py`` but produces a compact JSON payload on stdout
so non-Python front ends (like the ``web_simulation`` Next.js app) can execute a
full simulation run. The script always enables demo mode in the underlying graph
runner so turn-by-turn snapshots are available for visualization.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from user_sim_car.graph import GraphRunner

load_dotenv()


DEFAULT_PERSONA = (
    "Married couple in Colorado with a toddler and a medium-sized dog. Mixed city/highway commute; "
    "budget-conscious but safety-focused. Considering SUVs and hybrids; casually written messages with occasional typos; "
    "asks clarifying questions and compares trims; intent: actively shopping. Specifically looking for options in zip code 94305"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Emit JSON for a simulator session")
    parser.add_argument("--persona", type=str, default="", help="Persona seed text (falls back to stdin if empty)")
    parser.add_argument("--max-steps", type=int, default=8, help="Maximum simulation turns")
    parser.add_argument("--temperature", type=float, default=0.7, help="LLM sampling temperature")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="Chat model name")
    return parser


def collect_persona(args: argparse.Namespace) -> str:
    """Determine the persona text from CLI args or stdin."""
    persona = args.persona.strip()
    if persona:
        return persona
    if not sys.stdin.isatty():
        piped = sys.stdin.read().strip()
        if piped:
            return piped
    return DEFAULT_PERSONA


def emit_event(event_type: str, payload: Dict[str, Any]) -> None:
    """Write a JSONL event to stdout so the UI can stream updates."""
    event = {"type": event_type, "data": payload}
    sys.stdout.write(json.dumps(event))
    sys.stdout.write("\n")
    sys.stdout.flush()


def sanitize_for_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Filter the final state into JSON-serializable primitives."""
    snapshots = payload.get("demo_snapshots") or []
    serializable_snaps = []
    for snap in snapshots:
                serializable_snaps.append(
                    {
                        "step": snap.get("step"),
                        "user_text": snap.get("user_text", ""),
                        "assistant_text": snap.get("assistant_text", ""),
                        "actions": snap.get("actions", []),
                        "decision_rationale": snap.get("decision_rationale"),
                        "summary": snap.get("summary", ""),
                        "emotion": snap.get("emotion", {}),
                "judge": snap.get("judge"),
                "rationale": snap.get("rationale"),
                "quick_replies": snap.get("quick_replies"),
                "completion_review": snap.get("completion_review"),
                "vehicles": snap.get("vehicles"),
            }
        )

    judge = payload.get("last_judge")
    if judge is not None:
        judge = {
            "score": judge.get("score"),
            "passes": judge.get("passes"),
            "feedback": judge.get("feedback"),
            "reminder": judge.get("reminder"),
        }

    persona = payload.get("persona") or {}

    return {
        "step": payload.get("step"),
        "stop_reason": payload.get("stop_reason"),
        "conversation_summary": payload.get("conversation_summary"),
        "summary_version": payload.get("summary_version"),
        "summary_notes": payload.get("summary_notes"),
        "emotion_value": payload.get("emotion_value"),
        "emotion_threshold": payload.get("emotion_threshold"),
        "emotion_delta": payload.get("emotion_delta"),
        "emotion_rationale": payload.get("emotion_rationale"),
        "last_emotion_event": payload.get("last_emotion_event"),
        "last_judge": judge,
        "persona": {
            "family": persona.get("family"),
            "writing": persona.get("writing"),
            "interaction": persona.get("interaction"),
            "intent": persona.get("intent"),
        },
        "goal": payload.get("goal"),
        "ui": payload.get("ui"),
        "history": payload.get("history"),
        "quick_replies": payload.get("quick_replies"),
        "completion_review": payload.get("completion_review"),
        "demo_snapshots": serializable_snaps,
    }


def main() -> None:
    args = build_parser().parse_args()
    persona = collect_persona(args)

    model = ChatOpenAI(model=args.model, temperature=args.temperature)

    def handle_event(event_type: str, payload: Dict[str, Any]) -> None:
        data: Dict[str, Any] = {}
        if event_type == "turn":
            data = {
                "step": payload.get("step"),
                "user_text": payload.get("user_text", ""),
                "assistant_text": payload.get("assistant_text", ""),
                "actions": payload.get("actions", []),
                "decision_rationale": payload.get("decision_rationale"),
                "summary": payload.get("summary", ""),
                "emotion": payload.get("emotion"),
                "judge": payload.get("judge"),
                "rationale": payload.get("rationale"),
                "quick_replies": payload.get("quick_replies"),
                "completion_review": payload.get("completion_review"),
                "vehicles": payload.get("vehicles"),
            }
        elif event_type in {"emotion_init", "emotion_update"}:
            data = {
                "value": payload.get("value"),
                "delta": payload.get("delta"),
                "threshold": payload.get("threshold"),
                "rationale": payload.get("rationale"),
            }
        else:
            data = payload
        emit_event(event_type, data)

    runner = GraphRunner(
        chat_model=model,
        base_url=os.getenv("CARREC_BASE_URL", "http://localhost:8000"),
        verbose=False,
        event_callback=handle_event,
    )

    final_state = runner.run_session(
        seed_persona=persona,
        chat_model=model,
        max_steps=args.max_steps,
        thread_id="web-demo",  # deterministic thread name for logging dedupe
        recursion_limit=300,
        demo_mode=True,
    )

    payload = {
        "seed_persona": persona,
        "max_steps": args.max_steps,
        "temperature": args.temperature,
        "model": args.model,
    }
    payload.update(sanitize_for_json(final_state))
    emit_event("complete", payload)


if __name__ == "__main__":
    main()
