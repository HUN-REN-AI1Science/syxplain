---
description: Guide for adding new LLM capabilities using DSPy
---

# Backend: Add LLM Feature

This workflow outlines the steps to add new Large Language Model capabilities, ensuring integration with DSPy and run cost accounting.

## 1. Define DSPy Signature
Create a signature that defines the input/output contract for the LLM.
- **Location**: `backend/infrastructure/llm/signatures.py`
- **Guidelines**:
  - Class docstring: Acts as the system prompt. Be specific about role and task.
  - Fields: Use `dspy.InputField` and `dspy.OutputField` with descriptions.
  - JSON Output: If JSON is required, specify `STRICT JSON` in the docstring and use string output field (DSPy JSON support is evolving, manual parsing is often more robust).

```python
class MySignature(dspy.Signature):
    """
    You are an expert...
    Arguments: ...
    Return STRICT JSON...
    """
    input_text: str = dspy.InputField()
    output_json: str = dspy.OutputField()
```

## 2. Implement Service Logic
Orchestrate the LLM call in the service layer.
- **Location**: `backend/services/llm_service.py`
- **Steps**:
  1.  **Create Client**: Use `create_dspy_model` (or `create_literature_model` for web search) from `backend.infrastructure.llm.client`.
  2.  **Predict**: Create `dspy.Predict(MySignature)`.
  3.  **Execute**: Call predictor inside `dspy.settings.context(lm=lm)`. Token usage and cost are counted automatically for calls inside an analysis run (`dspy.track_usage` in the orchestrator, `backend/infrastructure/monitoring/llm_costs.py`).
  4.  **Parse & Validate**: Use `_clean_json_string` and `json.loads` if expecting JSON. Handle errors gracefully.

```python
def my_llm_feature(text: str):
    lm = create_dspy_model()
    predictor = dspy.Predict(MySignature)

    with dspy.settings.context(lm=lm):
        response = predictor(input_text=text)

    return response.output_json
```

## 3. Configuration
- If new API keys or model names are needed, add them to `LLMSettings` in `backend/core/config.py` and document in `README.md`.
