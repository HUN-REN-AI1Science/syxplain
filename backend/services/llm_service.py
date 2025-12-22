"""
LLM Service.

Orchestrates LLM interactions for the application, including:
- PySR configuration generation
- Equation explanation
- Deep research
"""
import json
import logging
from typing import List, Dict, Any, Optional

import dspy

from backend.infrastructure.llm.signatures import (
    PySrConfigGenerator,
    ExplainPySrEquations,
    ExplainPySrEquationsDeep,
    DeepResearchEquations
)
from backend.infrastructure.llm.client import create_dspy_model, create_deep_research_model
from backend.infrastructure.monitoring.langfuse_service import observe, report_usage, flush_traces
from backend.utils.json_utils import clean_and_fix_json_string

logger = logging.getLogger(__name__)


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
        cleaned_json = clean_and_fix_json_string(config_json)

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
        logger.debug(f"Deep Research Output: {equations_str}")
        cleaned_json = clean_and_fix_json_string(equations_str)

        try:
            parsed = json.loads(cleaned_json)
            # If model returned a bare array, wrap it in an object
            if isinstance(parsed, list):
                parsed = {"equations": parsed}
            else:
                parsed.setdefault("equations", [])
            return parsed
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse deep research JSON: {e}. Raw: {cleaned_json[:200]}")
            return {"equations": [], "_parse_error": str(e)}

    except Exception as e:
        logger.error(f"Error in deep_research_equations: {e}")
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
            logger.debug(f"Explain Equations Input - Project Spec: {project_spec_json}")
            logger.debug(f"Explain Equations Input - Data Spec: {data_spec_json}")

            response = predictor(
                project_spec_json=project_spec_json,
                data_spec_json=data_spec_json
            )
        report_usage(lm)

        explanation_json = response.explanation_json
        logger.debug(f"Explain Equations Output: {explanation_json}")

        cleaned_json = clean_and_fix_json_string(explanation_json)
        logger.debug(f"Explain Equations Cleaned Output: {cleaned_json}")

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
            # Log detailed error information for debugging
            error_pos = e.pos if hasattr(e, 'pos') else 'unknown'
            context_start = max(0, error_pos - 50) if isinstance(error_pos, int) else 0
            context_end = min(len(cleaned_json), error_pos + 50) if isinstance(error_pos, int) else 100
            context = cleaned_json[context_start:context_end] if isinstance(error_pos, int) else cleaned_json[:100]
            logger.error(
                f"Failed to parse explanation JSON: {e}. "
                f"Error at position {error_pos}. Context around error: ...{context}..."
            )
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
