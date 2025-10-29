import os
import subprocess
import json

import pandas as pd
import pysr
from pysr import PySRRegressor

from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langchain_core.prompts import PromptTemplate
from syxplain_lib import State, pysr_with_generated_config, data_summary, llm_pysr_config_generator, explain_pysr_equations



def get_api_key(model: str = "gemini") -> str | None:
    """Decrypt and return the API key from a GPG-encrypted file."""
    try:
        api_key = subprocess.check_output(
            ["gpg", "--quiet", "--decrypt", f"./credentials/api_key_{model}.gpg"],
            stderr=subprocess.DEVNULL,  # Suppress error output
        ).decode("utf-8").strip()
    except subprocess.CalledProcessError as e:
        print(f"Failed to decrypt API key: {e}")
        api_key = None
    return api_key


def entry_point(state: State) -> State:
    api_key = get_api_key()
    os.environ["GOOGLE_API_KEY"] = api_key
    sample_data = pd.read_csv("./data/sample_data.csv")
    with open("./data/problem_description.json", "r") as f:
        problem_description = json.load(f)
    problem_description_src = json.dumps(problem_description, indent=4)
    problem_description = json.loads(problem_description_src)
    state["data"] = sample_data
    state["problem_description_src"] = problem_description_src
    state["target_column"] = problem_description["target_variable"]
    state["predictor_columns"] = list(problem_description["features"].keys())
    return state

if __name__ == "__main__":
    g = StateGraph(State)
    g.add_node("entry_point", entry_point)
    g.add_node("data_summary", data_summary)
    g.add_node("pysr_config_generator", llm_pysr_config_generator)
    g.add_node("pysr_executer", pysr_with_generated_config)
    g.add_node("pysr_explainer", explain_pysr_equations)

    g.add_edge(START, "entry_point")
    g.add_edge("entry_point", "data_summary")
    g.add_edge("data_summary", "pysr_config_generator")
    g.add_edge("pysr_config_generator", "pysr_executer")
    g.add_edge("pysr_executer", "pysr_explainer")
    g.add_edge("pysr_explainer", END)

    app = g.compile()
    final = app.invoke(State())
    with open("pysr_explanations.md", "w") as f:
        f.write(final["pysr_explanations"])