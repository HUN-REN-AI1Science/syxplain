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

import logger
from shap_calc import get_top_feature_interactions
from logger import StepLogger
from llm_modules import generate_pysr_config, generate_equation_explanation, deep_research_equations


class State(TypedDict, total=False):
    logger: StepLogger
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
    deep_research_result: str  # Result from deep research LLM call

def data_summary(state: State) -> State:
    # Setting up logger object
    if "logger" not in state:
        state["logger"] = logger.StepLogger()

    # Summary
    data = state["data"]
    buffer = io.StringIO()
    description = data.describe()
    description.to_csv(buffer)
    state["data_summary"] = buffer.getvalue()
    state["logger"].log_step("data_summary", description.to_dict())

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

    for col in state["predictor_columns"]:
        create_and_save_visualization(data, col, state["target_column"], state["logger"])

    state["col_interaction_list"] = get_top_feature_interactions(state["data"], state["predictor_columns"], state["target_column"])
    for (col1, col2) in state["col_interaction_list"]:
        create_and_save_visualization(data, col1, col2, state["logger"])
    state["logger"].log_step("top_column_interactions", state["col_interaction_list"])

    return state

def llm_pysr_config_generator(state: State) -> State:
    project_description_src = state["problem_description_src"]
    summary_csv_text = state["data_summary"]
    visualizations = state["data_visualization"]

    config_json = generate_pysr_config(
        project_description=project_description_src,
        dataset_statistics=summary_csv_text,
        visualizations_b64=visualizations
    )

    state["logger"].log_step("pysr_config_prompt", {
        "project_description": project_description_src,
        "dataset_statistics": summary_csv_text,
        "visual_count": len(visualizations)
    })

    # Save results
    state["pysr_config_json"] = config_json
    state["logger"].log_step("pysr_config_answer", state["pysr_config_json"])

    return state

def pysr_with_generated_config(state: State) -> State:
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
        state["logger"].log_step(
            "niters_calculation",
            {
                "sample_nbr": sample_nbr,
                "feature_dim_nbr": feature_dim_nbr,
                "x_complexity_factor": x_complexity_factor,
                "y_complexity_factor": y_complexity_factor,
                "iters": iters
            }
        )
        return iters

    pysr_config = json.loads(state["pysr_config_json"])
    pysr_config["niterations"] = estimate_niterations(state)
    pysr_config["extra_sympy_mappings"] = {
        # "gaussian": lambda x: sympy.exp(-x*x),
        # "sigmoid": lambda x: 1 / (1 + sympy.exp(-x)),
    }
    pysr_config["constraints"] = {}
    if "^" in pysr_config["binary_operators"]:
        pysr_config["constraints"]["^"] = (-1, 1)
    pysr_config["nested_constraints"] = {}
    if "exp" in pysr_config["unary_operators"]:
        pysr_config["nested_constraints"]["exp"] = {"exp": 2}
    if "sin" in pysr_config["unary_operators"]:
        pysr_config["nested_constraints"]["sin"] = {"sin": 0}
    state["logger"].log_step("pysr_config_final", pysr_config)

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
        state["logger"].log_step("pysr_tempdir", temp_dir)

    julia_threads = os.environ.get("JULIA_NUM_THREADS", "1")
    state["logger"].log_step("pysr_cpu_config", {"cpu_count": cpu_count, "parallelism": pysr_config["parallelism"], "julia_threads": julia_threads})

    # Train symbolic regressor
    pysr = PySRRegressor(**pysr_config)
    pysr.fit(
        X=state["data"][state["predictor_columns"]],
        y=state["data"][state["target_column"]]
    )
    state["pysr_model"] = pysr
    return state

def explain_pysr_equations(state: State) -> State:
    model = state["pysr_model"]
    to_explain =dict(equation=list(), loss=list(), complexity=list())
    selected_equations = (model.equations_[model.equations_["loss"] < float(model.equations_["loss"].tail(1).iloc[0])*1.5]).copy()
    for _, row in selected_equations.iterrows():
        to_explain["equation"].append(row["equation"])
        to_explain["loss"].append(row["loss"])
        to_explain["complexity"].append(row["complexity"])

    project_spec_json = state["problem_description_src"]
    data_spec_json = json.dumps(to_explain, indent=2)

    # Get deep research context if available (for deep analysis mode)
    deep_research_context = state.get("deep_research_result")

    explanation = generate_equation_explanation(
        project_spec_json=project_spec_json,
        data_spec_json=data_spec_json,
        deep_research_context=deep_research_context
    )

    state["logger"].log_step("pysr_explainer_prompt", {
        "project_spec": project_spec_json,
        "data_spec": data_spec_json,
        "has_deep_research": deep_research_context is not None
    })

    # Save results
    state["pysr_explanations"] = explanation
    state["logger"].log_step("pysr_explainer_answer", state["pysr_explanations"])
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
        state["deep_research_result"] = ""
        return state

    try:
        result = deep_research_equations(features_dict)
        state["deep_research_result"] = result
        state["logger"].log_step("deep_research_result", {"result": result[:500] if result else ""})
    except Exception as e:
        state["logger"].log_step("deep_research_error", {"error": str(e)})
        state["deep_research_result"] = ""

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
    with open("pysr_explanations.md", "w") as f:
        f.write(final["pysr_explanations"])

    # Save markdown as artifact for download
    if "logger" in final and final["logger"]:
        final["logger"].log_artifact(
            "pysr_explanations.md",
            final["pysr_explanations"].encode('utf-8'),
            media_type="text/markdown"
        )
