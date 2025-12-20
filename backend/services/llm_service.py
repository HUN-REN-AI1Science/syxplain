"""
LLM Service.

Orchestrates LLM interactions for the application, including:
- PySR configuration generation
- Equation explanation
- Deep research
"""
import json
import logging
from typing import List, Dict, Any, Optional, Union

import dspy

from backend.infrastructure.llm.signatures import (
    PySrConfigGenerator,
    ExplainPySrEquations,
    ExplainPySrEquationsDeep,
    DeepResearchEquations
)
from backend.infrastructure.llm.client import create_dspy_model, create_deep_research_model
from backend.infrastructure.monitoring.langfuse_service import observe, report_usage, flush_traces

logger = logging.getLogger(__name__)


def _clean_json_string(text: str) -> str:
    """Clean markdown code blocks from JSON string."""
    cleaned = text.replace("```json", "").replace("```", "").strip()

    # Extract JSON if wrapped in other content
    if not (cleaned.startswith("{") and cleaned.endswith("}")):
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            cleaned = cleaned[start:end]

    return cleaned


@observe(name="generate_pysr_config", as_type="generation")
def generate_pysr_config(
    project_description: str,
    dataset_statistics: str,
    visualizations_b64: List[str]
) -> str:
    """
    Generates PySR configuration JSON using LLM.

    Args:
        project_description: Description of the project
        dataset_statistics: Statistics of the dataset
        visualizations_b64: List of base64 encoded images

    Returns:
        JSON string containing PySR configuration
    """
    lm = create_dspy_model()
    visual_inputs = [dspy.Image(f"data:image/png;base64,{img_b64}") for img_b64 in visualizations_b64]

    predictor = dspy.Predict(PySrConfigGenerator)

    try:
        with dspy.settings.context(lm=lm):
            response = predictor(
                project_description=project_description,
                dataset_statistics=dataset_statistics,
                visualizations=visual_inputs
            )

        config_json = response.config_json
        cleaned_json = _clean_json_string(config_json)

        try:
            json.loads(cleaned_json)
        except json.JSONDecodeError as e:
            flush_traces()
            logger.error(f"Failed to parse LLM response: {e}")
            raise ValueError(f"Failed to parse LLM response as valid JSON: {e}")

        report_usage(lm)
        return cleaned_json

    except Exception as e:
        logger.error(f"Error in generate_pysr_config: {e}")
        flush_traces()
        raise


@observe(name="generate_equation_explanation", as_type="generation")
def generate_equation_explanation(
    project_spec_json: str,
    data_spec_json: str,
    deep_research_context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generates explanation for PySR equations as structured JSON.

    Args:
        project_spec_json: JSON string of project specification
        data_spec_json: JSON string of equations data
        deep_research_context: Optional dict from deep research step

    Returns:
        JSON string with structured equation explanations
    """
    is_deep_analysis = deep_research_context and deep_research_context.get("equations")

    # Select appropriate model and signature
    if is_deep_analysis:
        # Use deep research model configuration (search enabled)
        # Actually, deep_research_equations uses the search model.
        # This function explains EXISTING equations. It might use search to verify?
        # The original code checked `is_deep_analysis` and set `web_search_options` if so.
        # We should replicate that.

        # Original: if is_deep_analysis: lm_kwargs["web_search_options"] = ...
        # But it used the STANDARD model `OPENAI_MODEL_NAME`, not the DEEP_RESEARCH_MODEL.
        # It just ENABLED search on the standard model?
        # `model=f"openai/{model_name}"` where model_name is from OPENAI_MODEL_NAME env.
        # So it uses the main model but asks it to search?
        # Wait, if main model (gpt-4o) doesn't support search via `tools` parameter directly unless it's configured...
        # The code assumes `openai` provider in dspy supports `extra_body`.

        # I'll use `create_dspy_model` with extra kwargs.

        lm = create_dspy_model(
            extra_body={
                "tools": [
                    {
                        "type": "web_search_preview",
                        "search_context_size": "high"
                    }
                ]
            }
        )

        # Enhance project spec with deep research results
        try:
            enhanced_project_spec = json.loads(project_spec_json)
            enhanced_project_spec["deep_research_equations"] = deep_research_context.get("equations", [])
            project_spec_json = json.dumps(enhanced_project_spec, indent=2)
        except json.JSONDecodeError:
            logger.warning("Failed to parse project_spec_json for enhancement, proceeding with original")

        predictor = dspy.Predict(ExplainPySrEquationsDeep)

    else:
        lm = create_dspy_model()
        predictor = dspy.Predict(ExplainPySrEquations)

    logger.info(f"Generating explanations. Deep Analysis: {is_deep_analysis}")

    try:
        with dspy.settings.context(lm=lm):
            response = predictor(
                project_spec_json=project_spec_json,
                data_spec_json=data_spec_json
            )
        report_usage(lm)

        explanation_json = response.explanation_json
        cleaned_json = _clean_json_string(explanation_json)

        # Validation Logic (adapted from original)
        try:
            parsed = json.loads(cleaned_json)

            # Ensure defaults
            parsed.setdefault("equations", [])
            parsed.setdefault("summary", {"key_drivers": [], "secondary_drivers": [], "findings": ""})
            parsed.setdefault("recommendation", {"equation_id": 1, "simplified_equation": "", "rationale": []})

            # Post-process: Renumber equation IDs
            if parsed["equations"]:
                old_to_new_id = {}
                for new_id, eq in enumerate(parsed["equations"], start=1):
                    old_id = eq.get("id")
                    if old_id is not None:
                        old_to_new_id[old_id] = new_id
                    eq["id"] = new_id

                # Update recommendation ID
                rec = parsed.get("recommendation", {})
                old_rec_id = rec.get("equation_id")
                if old_rec_id in old_to_new_id:
                    rec["equation_id"] = old_to_new_id[old_rec_id]

            return json.dumps(parsed, indent=2)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse explanation JSON: {e}")
            # Fallback
            fallback = {
                "equations": [],
                "summary": {"key_drivers": [], "secondary_drivers": [], "findings": explanation_json},
                "recommendation": {"equation_id": 0, "simplified_equation": "", "rationale": []},
                "_parse_error": str(e)
            }
            return json.dumps(fallback, indent=2)

    except Exception as e:
        logger.error(f"Error in generate_equation_explanation: {e}")
        flush_traces()
        raise


@observe(name="deep_research_equations", as_type="generation")
def deep_research_equations(features_dict: Dict[str, str], model_name: str = None) -> Dict[str, Any]:
    """
    Performs deep scientific research to find equations relating features.

    Args:
        features_dict: Dictionary mapping variable names to descriptions
        model_name: Optional override for model name

    Returns:
        Dictionary with 'equations' list
    """
    try:
        lm = create_deep_research_model(model_name)

        features_json = json.dumps(features_dict, indent=2)
        predictor = dspy.Predict(DeepResearchEquations)

        with dspy.settings.context(lm=lm):
            response = predictor(features_json=features_json)

        report_usage(lm, model_name=model_name)

        equations_str = response.equations
        cleaned_json = _clean_json_string(equations_str)

        try:
            parsed = json.loads(cleaned_json)
            parsed.setdefault("equations", [])
            return parsed
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse deep research JSON: {e}")
            return {"equations": [], "_parse_error": str(e)}

    except Exception as e:
        logger.error(f"Error in deep_research_equations: {e}")
        flush_traces()
        raise
