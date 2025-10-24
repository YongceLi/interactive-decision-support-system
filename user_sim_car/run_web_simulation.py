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
    "asks clarifying questions and compares trims; intent: actively shopping."
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
                "summary": snap.get("summary", ""),
                "scores": snap.get("scores", {}),
                "judge": snap.get("judge"),
                "rationale": snap.get("rationale"),
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
        "rl_scores": payload.get("rl_scores"),
        "rl_thresholds": payload.get("rl_thresholds"),
        "rl_rationale": payload.get("rl_rationale"),
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
        "demo_snapshots": serializable_snaps,
    }


def main() -> None:
    args = build_parser().parse_args()
    persona = collect_persona(args)

    model = ChatOpenAI(model=args.model, temperature=args.temperature)
    runner = GraphRunner(
        chat_model=model,
        base_url=os.getenv("CARREC_BASE_URL", "http://localhost:8000"),
        verbose=False,
    )

    def emit(event: Dict[str, Any]) -> None:
        json.dump(event, sys.stdout)
        sys.stdout.write("\n")
        sys.stdout.flush()

    emit(
        {
            "type": "start",
            "persona": persona,
            "max_steps": args.max_steps,
            "temperature": args.temperature,
            "model": args.model,
        }
    )

    def handle_progress(event: Dict[str, Any]) -> None:
        emit(event)

    final_state = runner.run_session(
        seed_persona=persona,
        chat_model=model,
        max_steps=args.max_steps,
        thread_id="web-demo",  # deterministic thread name for logging dedupe
        recursion_limit=300,
        demo_mode=True,
        progress_callback=handle_progress,
    )

    payload = {
        "seed_persona": persona,
        "max_steps": args.max_steps,
        "temperature": args.temperature,
        "model": args.model,
    }
    payload.update(sanitize_for_json(final_state))
    emit({"type": "complete", "payload": payload})


if __name__ == "__main__":
    main()
