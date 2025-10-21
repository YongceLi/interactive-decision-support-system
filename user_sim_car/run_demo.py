"""
run_demo.py — small runner to try the user simulator.

Set environment vars as needed:
- CARREC_BASE_URL=http://localhost:8000
- OPENAI_API_KEY=... (if using langchain-openai)
"""
import os
from pprint import pprint

from langchain_openai import ChatOpenAI  # swap to your provider as desired

from user_sim_car.graph import GraphRunner
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()


def main():
    model = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)  # choose your model
    runner = GraphRunner(
        chat_model=model,
        base_url=os.getenv("CARREC_BASE_URL", "http://localhost:8000"),
        verbose=True,  # prints each turn
    )

    seed_persona = (
        "Married couple in Colorado with a toddler and a medium-sized dog. Mixed city/highway commute; "
        "budget-conscious but safety-focused. Considering SUVs and hybrids; casually written messages with occasional typos; "
        "asks clarifying questions and compares trims; intent: actively shopping."
    )
    # seed_persona = (
    #     "A completely depressed person who just wants to check the new recommendation system, and will end the conversation very quickly."
    # )

    final_state = runner.run_session(
        seed_persona=seed_persona,
        chat_model=model,
        max_steps=20,
        thread_id="demo-run-100",
        recursion_limit=300,
    )

    print("\n=== STOPPED ===")
    print("Reason:", final_state.get("stop_reason"))
    print("Steps:", final_state.get("step"))
    # print("\n=== HISTORY (last 3 turns) ===")
    # for turn in final_state.get("history", [])[-3:]:
    #     pprint(turn)


if __name__ == "__main__":
    main()
