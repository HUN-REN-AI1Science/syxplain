import os, io, base64, json, tempfile
from typing import Any, TypedDict, List
import numpy as np
import pandas as pd
import sympy
import pysr
from pysr import PySRRegressor
from langgraph.graph import StateGraph, START, END
import matplotlib.pyplot as plt
import seaborn as sns

from shap_calc import get_top_feature_interactions
from backend.services.progress_service import ProgressTracker
from backend.services.llm_service import generate_pysr_config, generate_equation_explanation, deep_research_equations


class State(TypedDict, total=False):
    logger: ProgressTracker
    data: Any
    problem_description_src: str
    target_column: str
    predictor_columns: List[str]
    col_interaction_list: List[str]
    pysr_config_json: str
    pysr_explanations: str
    data_visualization: List[str]
    data_summary: str
    pysr_model: pysr.sr.PySRRegressor
    analysis_type: str  # "quick" or "deep"
    deep_research_model: str  # Model to use for deep research (e.g., "o4-mini-deep-research")
    deep_research_result: dict  # Result from deep research LLM call (dict with 'equations' list)

def data_summary(state: State) -> State:
    # Setting up logger object
    if "logger" not in state:
        state["logger"] = logger.StepLogger()

    state["logger"].log_step("phase_data_analysis", {"status": "Starting data analysis phase"})

    # Summary
    data = state["data"]
    buffer = io.StringIO()
    description = data.describe()
    description.to_csv(buffer)
    state["data_summary"] = buffer.getvalue()
    state["logger"].log_step("data_summary_computed", description.to_dict())

    # Charts (predictors vs target + top predictor interactions regarding target prediction)
    state["data_visualization"] = []

    def create_and_save_visualization(data: pd.DataFrame, col1: str, col2: str, logger=None):
        data.plot(
            x=col1,
            y=col2,
            kind="scatter",
            alpha=0.1,
            figsize=(5, 4),
            title=f"{col1} vs {col2}"
        )
        plt.tight_layout()

        # Save to memory (for base64 and DB)
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=300)
        img_bytes = buf.getvalue()

        # Log artifact to DB
        if logger is not None:
            logger.log_artifact(f"{col1}_vs_{col2}.png", img_bytes, media_type="image/png")

        # For base64 (frontend preview if needed in state)
        base64_image = base64.b64encode(img_bytes).decode("utf-8")
        state["data_visualization"].append(base64_image)

        plt.close()

    # Create visualizations for each predictor
    state["logger"].log_step("visualization_start", {"status": "Creating feature visualizations", "count": len(state["predictor_columns"])})
    for idx, col in enumerate(state["predictor_columns"]):
        create_and_save_visualization(data, col, state["target_column"], state["logger"])
        # Log progress periodically (every 3 features)
        if (idx + 1) % 3 == 0 or idx == len(state["predictor_columns"]) - 1:
            state["logger"].log_step("visualization_progress", {"completed": idx + 1, "total": len(state["predictor_columns"])})

    # SHAP feature interaction analysis
    state["logger"].log_step("shap_analysis_start", {"status": "Starting SHAP interaction analysis"})
    state["col_interaction_list"] = get_top_feature_interactions(state["data"], state["predictor_columns"], state["target_column"])
    state["logger"].log_step("shap_analysis_complete", {"top_interactions": len(state["col_interaction_list"])})

    # Create interaction visualizations
    state["logger"].log_step("interaction_viz_start", {"status": "Creating interaction visualizations"})
    for (col1, col2) in state["col_interaction_list"]:
        create_and_save_visualization(data, col1, col2, state["logger"])
    state["logger"].log_step("interaction_viz_complete", state["col_interaction_list"])

    return state

def llm_pysr_config_generator(state: State) -> State:
    state["logger"].log_step("phase_config_generation", {"status": "Starting LLM config generation"})

    project_description_src = state["problem_description_src"]
    summary_csv_text = state["data_summary"]
    visualizations = state["data_visualization"]

    state["logger"].log_step("llm_config_request", {
        "project_description": project_description_src[:200] + "..." if len(project_description_src) > 200 else project_description_src,
        "visual_count": len(visualizations)
    })

    config_json = generate_pysr_config(
        project_description=project_description_src,
        dataset_statistics=summary_csv_text,
        visualizations_b64=visualizations
    )

    # Save results
    state["pysr_config_json"] = config_json
    state["logger"].log_step("llm_config_received", {"config_length": len(config_json)})

    return state

def pysr_with_generated_config(state: State) -> State:
    state["logger"].log_step("phase_symbolic_regression", {"status": "Starting symbolic regression phase"})

    def estimate_niterations(state):
        # Input features
        sample_nbr, feature_dim_nbr = state["data"][state["predictor_columns"]].shape
        x_complexity_factor = feature_dim_nbr * np.log10(sample_nbr)

        # Target
        y = state["data"][state["target_column"]]
        if np.mean(y) == 0 or len(y) == 0:
            y_complexity_factor = 1
        else:
            noise_level = np.std(y - np.mean(y)) / np.mean(np.abs(y))
            y_complexity_factor = np.clip(1 + noise_level, 1, 3)

        # Final value
        iters = max(200, int(10 * x_complexity_factor * y_complexity_factor))
        return iters, sample_nbr, feature_dim_nbr

    pysr_config = json.loads(state["pysr_config_json"])
    niterations, sample_nbr, feature_dim_nbr = estimate_niterations(state)
    pysr_config["niterations"] = niterations

    state["logger"].log_step("pysr_config_computed", {
        "niterations": niterations,
        "samples": sample_nbr,
        "features": feature_dim_nbr
    })

    pysr_config["extra_sympy_mappings"] = {}
    pysr_config["constraints"] = {}
    if "^" in pysr_config["binary_operators"]:
        pysr_config["constraints"]["^"] = (-1, 1)
    pysr_config["nested_constraints"] = {}
    if "exp" in pysr_config["unary_operators"]:
        pysr_config["nested_constraints"]["exp"] = {"exp": 2}
    if "sin" in pysr_config["unary_operators"]:
        pysr_config["nested_constraints"]["sin"] = {"sin": 0}

    # Force resource limits and logging
    cpu_count = os.cpu_count() or 4  # Fallback to 4 if detection fails
    pysr_config["parallelism"] = "multiprocessing"  # Use multithreading or multiprocessing
    pysr_config["procs"] = cpu_count  # Use all available CPUs
    pysr_config["verbosity"] = 1 # Log to stdout
    pysr_config["progress"] = True  # Show progress bar

    # Isolate temp files for parallel execution
    if "logger" in state and hasattr(state["logger"], "run_id") and state["logger"].run_id:
        run_id = state["logger"].run_id
        temp_dir = os.path.join(tempfile.gettempdir(), f"pysr_{run_id}")
        os.makedirs(temp_dir, exist_ok=True)
        pysr_config["tempdir"] = temp_dir

    state["logger"].log_step("pysr_training_start", {"cpu_count": cpu_count, "niterations": niterations})

    # Train symbolic regressor
    pysr = PySRRegressor(**pysr_config)
    pysr.fit(
        X=state["data"][state["predictor_columns"]],
        y=state["data"][state["target_column"]]
    )

    state["pysr_model"] = pysr
    state["logger"].log_step("pysr_training_complete", {"equations_found": len(pysr.equations_) if hasattr(pysr, 'equations_') else 0})

    return state

def explain_pysr_equations(state: State) -> State:
    state["logger"].log_step("phase_explanation", {"status": "Starting equation explanation phase"})

    model = state["pysr_model"]
    to_explain = dict(equation=list(), loss=list(), complexity=list())
    selected_equations = (model.equations_[model.equations_["loss"] < float(model.equations_["loss"].tail(1).iloc[0])*1.5]).copy()

    # Store indices for scatter plot generation
    equation_indices = []
    for idx, row in selected_equations.iterrows():
        to_explain["equation"].append(row["equation"])
        to_explain["loss"].append(row["loss"])
        to_explain["complexity"].append(row["complexity"])
        equation_indices.append(idx)

    state["logger"].log_step("equations_selected", {"count": len(to_explain["equation"])})

    # Generate scatter plot data for each selected equation (raw data for frontend Chart.js)
    state["logger"].log_step("scatter_data_start", {"status": "Generating scatter plot data"})
    scatter_data_list = []
    X = state["data"][state["predictor_columns"]]
    y_actual = state["data"][state["target_column"]].values

    # Subsample if too many points (for frontend performance)
    max_points = 500
    if len(y_actual) > max_points:
        indices = np.random.choice(len(y_actual), max_points, replace=False)
        indices = np.sort(indices)
        X_sample = X.iloc[indices]
        y_actual_sample = y_actual[indices]
    else:
        X_sample = X
        y_actual_sample = y_actual

    for i, eq_idx in enumerate(equation_indices):
        try:
            # Predict using this specific equation
            y_pred = model.predict(X_sample, index=eq_idx)

            # Store raw data as lists for JSON serialization
            scatter_data = {
                "measured": y_actual_sample.tolist(),
                "predicted": y_pred.tolist()
            }
            scatter_data_list.append(scatter_data)
        except Exception as e:
            state["logger"].log_step("scatter_data_error", {"equation_index": i, "error": str(e)})
            scatter_data_list.append(None)

    state["logger"].log_step("scatter_data_complete", {"count": len(scatter_data_list)})

    project_spec_json = state["problem_description_src"]
    data_spec_json = json.dumps(to_explain, indent=2)

    # Get deep research context if available (for deep analysis mode)
    deep_research_context = state.get("deep_research_result")

    state["logger"].log_step("llm_explanation_request", {
        "equations_count": len(to_explain["equation"]),
        "has_deep_research": deep_research_context is not None
    })

    explanation = generate_equation_explanation(
        project_spec_json=project_spec_json,
        data_spec_json=data_spec_json,
        deep_research_context=deep_research_context
    )

    # Merge scatter data into the explanation JSON
    try:
        explanation_data = json.loads(explanation)
        if "equations" in explanation_data:
            for i, eq in enumerate(explanation_data["equations"]):
                if i < len(scatter_data_list) and scatter_data_list[i]:
                    eq["scatter_data"] = scatter_data_list[i]
        explanation = json.dumps(explanation_data, indent=2)
    except json.JSONDecodeError as e:
        state["logger"].log_step("scatter_data_merge_error", {"error": str(e)})

    # Save results
    state["pysr_explanations"] = explanation
    state["logger"].log_step("llm_explanation_complete", {"explanation_length": len(explanation)})

    return state


def deep_research_node(state: State) -> State:
    """Node for deep research step - searches scientific literature for equations.

    This node is only added to the graph for deep analysis mode.
    It calls the o4-mini-deep-research model to find physically-based equations.
    """
    state["logger"].log_step("deep_research_start", {"status": "starting deep research"})

    # Get the features dictionary from the problem description
    problem_desc = json.loads(state["problem_description_src"])
    features_dict = problem_desc.get("features", {})

    if not features_dict:
        state["logger"].log_step("deep_research_skip", {"reason": "no features defined"})
        state["deep_research_result"] = {"equations": []}
        return state

    try:
        # Get user-selected model from state, if available
        model_name = state.get("deep_research_model")
        result = deep_research_equations(features_dict, model_name=model_name)
        state["deep_research_result"] = result
        # Log summary for debugging
        equations_count = len(result.get("equations", []))
        state["logger"].log_step("deep_research_result", {"equations_count": equations_count, "result": json.dumps(result)[:500]})
    except Exception as e:
        state["logger"].log_step("deep_research_error", {"error": str(e)})
        state["deep_research_result"] = {"equations": []}

    return state

def run_syxplain(entry_point):
    g = StateGraph(State)
    g.add_node("entry_point", entry_point)
    g.add_node("data_summary", data_summary)
    g.add_node("pysr_config_generator", llm_pysr_config_generator)
    g.add_node("pysr_executor", pysr_with_generated_config)
    g.add_node("pysr_explainer", explain_pysr_equations)

    g.add_edge(START, "entry_point")
    g.add_edge("entry_point", "data_summary")
    g.add_edge("data_summary", "pysr_config_generator")
    g.add_edge("pysr_config_generator", "pysr_executor")
    g.add_edge("pysr_executor", "pysr_explainer")
    g.add_edge("pysr_explainer", END)

    app = g.compile()
    final = app.invoke(State())
    with open("pysr_explanations.json", "w") as f:
        f.write(final["pysr_explanations"])

    # Save JSON as artifact for download
    if "logger" in final and final["logger"]:
        final["logger"].log_artifact(
            "pysr_explanations.json",
            final["pysr_explanations"].encode('utf-8'),
            media_type="application/json"
        )
