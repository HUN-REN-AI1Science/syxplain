---
description: Guide for adding new LLM capabilities using DSPy and Langfuse
---

# Backend: Add LLM Feature

This workflow outlines the steps to add new Large Language Model capabilities, ensuring integration with DSPy and Langfuse tracing.

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
  1.  **Decorate**: Use `@observe` from `backend.infrastructure.monitoring`.
  2.  **Create Client**: Use `create_dspy_model` or `create_deep_research_model` from `backend.infrastructure.llm.client`.
  3.  **Predict**: Create `dspy.Predict(MySignature)`.
  4.  **Execute**: Call predictor inside `dspy.settings.context(lm=lm)`.
  5.  **Report Usage**: Call `report_usage(lm)` to track tokens in Langfuse.
  6.  **Parse & Validate**: Use `_clean_json_string` and `json.loads` if expecting JSON. Handle errors gracefully.

```python
@observe(name="my_feature")
def my_llm_feature(text: str):
    lm = create_dspy_model()
    predictor = dspy.Predict(MySignature)

    with dspy.settings.context(lm=lm):
        response = predictor(input_text=text)

    report_usage(lm)
    return response.output_json
```

## 3. Configuration
- If new API keys or model names are needed, add them to `LLMSettings` in `backend/core/config.py` and document in `README.md`.
