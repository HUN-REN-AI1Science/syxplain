import os, io, base64, json
from typing import Any, TypedDict, List
import numpy as np
import pandas as pd
import sympy
import pysr
from pysr import PySRRegressor
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langchain_core.prompts import PromptTemplate
import matplotlib.pyplot as plt
import seaborn as sns

import logger
from shap_calc import get_top_feature_interactions
from logger import StepLogger


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
    
def data_summary(state: State) -> State:
    # Setting up logger object
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

        # Save to hard drive
        if logger is not None:
            file_path = os.path.join(logger.operator_selection_charts_dir, f"{col1}_vs_{col2}.png")
            plt.savefig(file_path, format="png", dpi=300)

        # Save to memory (for base64)
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        base64_image = base64.b64encode(buf.getvalue()).decode("utf-8")
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
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro",response_mime_type="application/json")
    project_description_src = state["problem_description_src"]
    summary_csv_text = state["data_summary"]

    with open("./templates/llm_sym_operator_selection_prompt.txt", "r") as f:
        system_prompt = f.read()

    parts = [
        { "type": "text", "text": system_prompt},
        { "type": "text", "text": f"### Project description json\n{project_description_src}\n\n"},
        { "type": "text", "text": f"### Dataset statistics\n{summary_csv_text}\n\n"},
        { "type": "text", "text": "### Dataset visualization"},
    ]
    for img_b64 in state["data_visualization"]:
        parts.append({"type": "image_url", "image_url": f"data:image/png;base64,{img_b64}"})
    msg = llm.invoke([HumanMessage(content=parts)])
    state["logger"].log_step("pysr_config_prompt", parts)

    # Save results
    state["pysr_config_json"] = msg.content
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
        iters = max(200, int(100 * x_complexity_factor * y_complexity_factor))
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
    
    with open("./templates/pysr_explainer_sys_prompt.txt", "r") as f:
        py_sr_explainer_sys_prompt = f.read()
    with open("./templates/pysr_explainer_usr_prompt.txt", "r") as f:
        pysr_explainer_usr_prompt_template = f.read()
    pysr_explainer_usr_prompt = PromptTemplate(variables=["problem_description", "to_explain"], template=pysr_explainer_usr_prompt_template)
    
    
    parts = [
        { "type": "text", "text": py_sr_explainer_sys_prompt},
        { "type": "text", "text": pysr_explainer_usr_prompt.format(problem_description=state["problem_description_src"], to_explain=json.dumps(to_explain, indent=2))},
    ]
    
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro")
    msg = llm.invoke([HumanMessage(content=parts)],response_mime_type="text/plain")
    state["logger"].log_step("pysr_explainer_prompt", parts)

    # Save results
    state["pysr_explanations"] = msg.content
    state["logger"].log_step("pysr_explainer_answer", state["pysr_explanations"])
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