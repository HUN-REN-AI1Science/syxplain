"""JSON utility functions for handling LLM output."""
import json
import logging
import re

logger = logging.getLogger(__name__)


def clean_and_fix_json_string(text: str) -> str:
    """Clean and fix common JSON issues from LLM output.

    Handles:
    - Markdown code blocks
    - JSON objects and arrays
    - Single quotes instead of double quotes (only if initial parse fails)
    """
    cleaned = text.replace("```json", "").replace("```", "").strip()

    # Check if it looks like a JSON object or array
    is_object = cleaned.startswith("{") and cleaned.endswith("}")
    is_array = cleaned.startswith("[") and cleaned.endswith("]")

    # Extract JSON if wrapped in other content
    if not is_object and not is_array:
        # Try to find object first
        obj_start = cleaned.find("{")
        obj_end = cleaned.rfind("}") + 1
        # Try to find array
        arr_start = cleaned.find("[")
        arr_end = cleaned.rfind("]") + 1

        # Pick whichever comes first and is valid
        if obj_start >= 0 and obj_end > obj_start and (arr_start < 0 or obj_start < arr_start):
            cleaned = cleaned[obj_start:obj_end]
        elif arr_start >= 0 and arr_end > arr_start:
            cleaned = cleaned[arr_start:arr_end]

    # First, try to parse as-is (most LLMs output valid JSON)
    try:
        json.loads(cleaned)
        return cleaned  # Already valid, no fixes needed
    except json.JSONDecodeError as initial_error:
        logger.debug(f"Initial JSON parse failed: {initial_error}. Attempting quote fixes.")

    # Only apply aggressive quote fixes if initial parse failed
    # Fix single quotes to double quotes (common LLM issue)
    fixed = re.sub(r"(?<=[{\[:,])\s*'", ' "', cleaned)  # Opening quotes
    fixed = re.sub(r"'\s*(?=[}\]:,])", '"', fixed)     # Closing quotes
    fixed = re.sub(r"(?<=\[)'", '"', fixed)            # Opening quote after [
    fixed = re.sub(r"'(?=\])", '"', fixed)             # Closing quote before ]

    # Verify the fix worked
    try:
        json.loads(fixed)
        return fixed
    except json.JSONDecodeError as fix_error:
        logger.warning(f"Quote fix didn't help. Original error: {initial_error}, After fix: {fix_error}")
        # Return the cleaned version without quote fixes (let caller handle the error)
        return cleaned
