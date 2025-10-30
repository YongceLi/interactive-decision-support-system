"""
run_demo.py — small runner to try the user simulator.

Set environment vars as needed:
- CARREC_BASE_URL=http://localhost:8000
- OPENAI_API_KEY=... (if using langchain-openai)
"""
import argparse
import os
from langchain_openai import ChatOpenAI  # swap to your provider as desired

from user_sim_car.graph import GraphRunner
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the car-rec user simulator")
    parser.add_argument("--persona", type=str, default="", help="Optional custom seed persona text")
    parser.add_argument("--max-steps", type=int, default=20, help="Maximum simulation turns")
    parser.add_argument("--demo", action="store_true", help="Enable demo-mode snapshots for downstream UIs")
    parser.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature for the LLM")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    persona = args.persona.strip() or (
        "Married couple in Colorado with a toddler and a medium-sized dog. Mixed city/highway commute; "
        "budget-conscious but safety-focused. Considering SUVs and hybrids; casually written messages with occasional typos; "
        "asks clarifying questions and compares trims; intent: actively shopping."
    )

    model = ChatOpenAI(model="gpt-4o-mini", temperature=args.temperature)
    runner = GraphRunner(
        chat_model=model,
        base_url=os.getenv("CARREC_BASE_URL", "http://localhost:8000"),
        verbose=True,
    )

    final_state = runner.run_session(
        seed_persona=persona,
        chat_model=model,
        max_steps=args.max_steps,
        thread_id="demo-run-100",
        recursion_limit=300,
        demo_mode=args.demo,
    )

    print("\n=== STOPPED ===")
    print("Reason:", final_state.get("stop_reason"))
    print("Steps:", final_state.get("step"))
    print("Final scores:", final_state.get("rl_scores"))
    print("Final thresholds:", final_state.get("rl_thresholds"))
    print("Final RL rationale:", final_state.get("rl_rationale"))
    print("Judge summary:", final_state.get("last_judge"))
    print("Conversation summary (truncated):", (final_state.get("conversation_summary") or "")[:400])

    if args.demo:
        print("\n=== Demo snapshots ===")
        for snap in final_state.get("demo_snapshots", []):
            print(f"Step {snap['step']}: alignment={snap.get('judge', {}).get('score')} scores={snap['scores']}")
            if snap.get("rationale"):
                print(f"  Rationale: {snap['rationale']}")
            print("  User:", snap["user_text"])
            print("  Assistant:", snap["assistant_text"][:140])
            print("  Actions:", snap["actions"])
            print("  Summary excerpt:", snap["summary"][:160])
            print("---")


if __name__ == "__main__":
    main()
