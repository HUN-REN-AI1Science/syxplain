from langgraph.graph import StateGraph, START, END
from syxplain_lib import State, pysr_with_generated_config, data_summary, llm_pysr_config_generator, explain_pysr_equations


def run_syxplain(entry_point):
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