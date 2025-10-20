"""
Visualize the LangGraph workflow structures using LangGraph's built-in methods.

This script generates PNG visualizations for both the interview and supervisor workflows.
"""
import os
import sys
# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from idss_agent.workflows.interview_workflow import get_interview_graph
from idss_agent.workflows.supervisor_workflow import get_supervisor_graph


if __name__ == "__main__":
    print("Generating LangGraph workflow visualizations...")
    print("=" * 70)

    try:
        # Create interview workflow graph
        print("Creating interview workflow graph...")
        interview_graph = get_interview_graph()
        interview_vis = interview_graph.get_graph()
        interview_png = interview_vis.draw_mermaid_png()

        # Save interview graph
        interview_file = "interview_workflow.png"
        with open(interview_file, "wb") as f:
            f.write(interview_png)
        print(f"✓ Interview workflow saved to: {interview_file}")

    except Exception as e:
        print(f"Error generating interview workflow diagram: {e}")
        import traceback
        traceback.print_exc()

    try:
        # Create supervisor workflow graph
        print("\nCreating supervisor workflow graph...")
        supervisor_graph = get_supervisor_graph()
        supervisor_vis = supervisor_graph.get_graph()
        supervisor_png = supervisor_vis.draw_mermaid_png()

        # Save supervisor graph
        supervisor_file = "supervisor_workflow.png"
        with open(supervisor_file, "wb") as f:
            f.write(supervisor_png)
        print(f"✓ Supervisor workflow saved to: {supervisor_file}")

    except Exception as e:
        print(f"Error generating supervisor workflow diagram: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("✅ Visualization complete!")
    print("\nGenerated files:")
    print("  - interview_workflow.png: Interview phase workflow")
    print("  - supervisor_workflow.png: Supervisor phase workflow")
    print("\nNote: The main router (agent.py) switches between these two workflows")
    print("      based on the 'interviewed' flag in the state.")
