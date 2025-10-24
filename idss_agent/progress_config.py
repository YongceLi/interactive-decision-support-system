"""
Progress tracking configuration for each execution mode.

Defines the standard execution steps for each mode (buying, discovery, analytical, general).
"""
from typing import List, Dict
from idss_agent.state import ProgressStep
import time


# Step definitions for each mode
# Format: {"step_id": "unique_id", "description": "User-friendly description"}

BUYING_MODE_NOT_INTERVIEWED_STEPS = [
    {"step_id": "intent_classification", "description": "Understanding your request"},
    {"step_id": "semantic_parsing", "description": "Extracting initial preferences"},
    {"step_id": "interview_questions", "description": "Asking questions to understand your needs"},
    {"step_id": "extracting_preferences", "description": "Analyzing your responses"},
    {"step_id": "searching_vehicles", "description": "Finding available vehicles"},
    {"step_id": "generating_recommendations", "description": "Preparing personalized recommendations"},
    {"step_id": "complete", "description": "Complete"}
]

BUYING_MODE_INTERVIEWED_STEPS = [
    {"step_id": "intent_classification", "description": "Understanding your request"},
    {"step_id": "semantic_parsing", "description": "Parsing your search criteria"},
    {"step_id": "updating_recommendations", "description": "Searching for vehicles"},
    {"step_id": "generating_response", "description": "Preparing recommendations"},
    {"step_id": "complete", "description": "Complete"}
]

DISCOVERY_MODE_STEPS = [
    {"step_id": "intent_classification", "description": "Understanding your request"},
    {"step_id": "semantic_parsing", "description": "Checking for new search criteria"},
    {"step_id": "updating_recommendations", "description": "Searching for vehicles"},
    {"step_id": "generating_response", "description": "Presenting vehicles"},
    {"step_id": "complete", "description": "Complete"}
]

ANALYTICAL_MODE_STEPS = [
    {"step_id": "intent_classification", "description": "Understanding your question"},
    {"step_id": "semantic_parsing", "description": "Extracting relevant information"},
    {"step_id": "updating_recommendations", "description": "Searching for vehicles (if needed)"},
    {"step_id": "executing_tools", "description": "Analyzing data"},
    {"step_id": "generating_response", "description": "Synthesizing answer"},
    {"step_id": "complete", "description": "Complete"}
]

GENERAL_MODE_STEPS = [
    {"step_id": "intent_classification", "description": "Understanding your message"},
    {"step_id": "generating_response", "description": "Preparing response"},
    {"step_id": "complete", "description": "Complete"}
]


def get_steps_for_mode(mode: str, interviewed: bool = False) -> List[Dict[str, str]]:
    """
    Get the list of steps for a given mode.

    Args:
        mode: One of "buying", "discovery", "analytical", "general"
        interviewed: For buying mode, whether user has been interviewed

    Returns:
        List of step configurations
    """
    if mode == "buying":
        return BUYING_MODE_INTERVIEWED_STEPS if interviewed else BUYING_MODE_NOT_INTERVIEWED_STEPS
    elif mode == "discovery":
        return DISCOVERY_MODE_STEPS
    elif mode == "analytical":
        return ANALYTICAL_MODE_STEPS
    elif mode == "general":
        return GENERAL_MODE_STEPS
    else:
        # Fallback for unknown mode
        return [
            {"step_id": "processing", "description": "Processing"},
            {"step_id": "complete", "description": "Complete"}
        ]


def initialize_progress(mode: str, interviewed: bool = False) -> Dict:
    """
    Initialize execution progress for a given mode.

    Returns:
        ExecutionProgress dict ready to be set in state
    """
    steps_config = get_steps_for_mode(mode, interviewed)

    # Create progress steps (all pending initially)
    steps = [
        ProgressStep(
            step_id=step["step_id"],
            description=step["description"],
            status="pending",
            timestamp=0.0
        )
        for step in steps_config
    ]

    return {
        "current_step_index": 0,
        "total_steps": len(steps),
        "steps": steps,
        "mode": mode
    }


def start_step(progress: Dict, step_id: str) -> Dict:
    """
    Mark a step as in_progress.

    Args:
        progress: Current ExecutionProgress
        step_id: ID of step to start

    Returns:
        Updated progress
    """
    for i, step in enumerate(progress["steps"]):
        if step["step_id"] == step_id:
            progress["steps"][i]["status"] = "in_progress"
            progress["steps"][i]["timestamp"] = time.time()
            progress["current_step_index"] = i
            break

    return progress


def complete_step(progress: Dict, step_id: str) -> Dict:
    """
    Mark a step as completed.

    Args:
        progress: Current ExecutionProgress
        step_id: ID of step to complete

    Returns:
        Updated progress
    """
    for i, step in enumerate(progress["steps"]):
        if step["step_id"] == step_id:
            progress["steps"][i]["status"] = "completed"
            progress["steps"][i]["timestamp"] = time.time()
            break

    return progress


def fail_step(progress: Dict, step_id: str) -> Dict:
    """
    Mark a step as failed.

    Args:
        progress: Current ExecutionProgress
        step_id: ID of step that failed

    Returns:
        Updated progress
    """
    for i, step in enumerate(progress["steps"]):
        if step["step_id"] == step_id:
            progress["steps"][i]["status"] = "failed"
            progress["steps"][i]["timestamp"] = time.time()
            break

    return progress


def get_progress_percentage(progress: Dict) -> float:
    """
    Calculate progress percentage based on completed steps.

    Returns:
        Float between 0.0 and 100.0
    """
    if progress["total_steps"] == 0:
        return 0.0

    completed_count = sum(
        1 for step in progress["steps"]
        if step["status"] == "completed"
    )

    return (completed_count / progress["total_steps"]) * 100.0
