"""
DEPRECATED: Use generate_architecture_diagram.py instead

This script only generates the interview workflow.
For complete architecture visualization, use:
    python scripts/generate_architecture_diagram.py

That script generates:
    - High-level architecture diagram (Mermaid)
    - Interview workflow diagram (LangGraph)
"""
import os
import sys

if __name__ == "__main__":
    print("=" * 70)
    print("⚠️  DEPRECATED SCRIPT")
    print("=" * 70)
    print("\nThis script only generates the interview workflow.")
    print("For complete architecture visualization, please use:\n")
    print("    python scripts/generate_architecture_diagram.py")
    print("\nThat script generates:")
    print("  - architecture_diagram.md: High-level intent-based routing")
    print("  - interview_workflow.png: Detailed interview workflow")
    print("\n" + "=" * 70)
    print("\nRunning new script instead...\n")

    # Run the new script
    import subprocess
    subprocess.run([sys.executable, "scripts/generate_architecture_diagram.py"])
