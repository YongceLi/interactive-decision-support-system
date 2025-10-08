"""
Visualize the LangGraph workflow structure using LangGraph's built-in methods.

This script uses LangGraph's get_graph() method to visualize the vehicle
search agent workflow.
"""
import os
import sys
# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from idss_agent import create_vehicle_agent


if __name__ == "__main__":
    print("Generating LangGraph workflow visualization...")
    print("=" * 70)

    try:
        # Create the agent workflow
        agent = create_vehicle_agent()

        # Use LangGraph's built-in get_graph() method
        graph = agent.get_graph()

        # Draw as Mermaid diagram
        mermaid_png = graph.draw_mermaid_png()

        # Save to file
        output_file = "graph_visualization.png"
        with open(output_file, "wb") as f:
            f.write(mermaid_png)

        print(f"✓ Graph visualization saved to: {output_file}")

    except Exception as e:
        print(f"Error generating diagram: {e}")
        print("\nTrying alternative method (ASCII representation)...")

        try:
            # Alternative: print ASCII representation
            agent = create_vehicle_agent()
            graph = agent.get_graph()
            print(graph)
        except Exception as e2:
            print(f"Error: {e2}")
            import traceback
            traceback.print_exc()
