"""JSON utility functions for handling LLM output."""
import re


def clean_and_fix_json_string(text: str) -> str:
    """Clean and fix common JSON issues from LLM output.

    Handles:
    - Markdown code blocks
    - JSON objects and arrays
    - Single quotes instead of double quotes
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

    # Fix single quotes to double quotes (common LLM issue)
    # Use regex to replace single quotes used as JSON string delimiters
    # This handles: {'key': 'value'} -> {"key": "value"}
    cleaned = re.sub(r"(?<=[{\[:,])\s*'", ' "', cleaned)  # Opening quotes
    cleaned = re.sub(r"'\s*(?=[}\]:,])", '"', cleaned)     # Closing quotes
    cleaned = re.sub(r"(?<=\[)'", '"', cleaned)            # Opening quote after [
    cleaned = re.sub(r"'(?=\])", '"', cleaned)             # Closing quote before ]
    return cleaned
