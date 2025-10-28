import pysr
from pysr import PySRRegressor
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI

class State(TypedDict, total=False):
    data: Any
    problem_description_src: str
    target_column: str
    predictor_columns: List[str]
    pysr_config_json: str
    pysr_explanations: str
    data_visualization: str
    data_summary: str
    pysr_model: pysr.sr.PySRRegressor
def data_summary(state: State) -> State:
    data = state["data"]
    buffer = io.StringIO()
    data.describe().to_csv(buffer)
    summary_csv = buffer.getvalue()
    state["data_summary"] = summary_csv
    buf = io.BytesIO()
    plt.figure(figsize=(10, 8))
    sns.pairplot(data)
    plt.savefig(buf, format='png')
    base64_image = base64.b64encode(buf.getvalue()).decode('utf-8')
    state["data_visualization"] = base64_image
    return state

def llm_pysr_config_generator(state: State) -> State:
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro",response_mime_type="application/json")
    project_description_src = state["problem_description_src"]
    img_b64 = state["data_visualization"]
    summary_csv_text = state["data_summary"]
    img_data_uri = f"data:image/png;base64,{img_b64}"
    with open("./templates/llm_pysr_config_generator_system_prompt.txt", "r") as f:
        system_prompt = f.read()

    parts = [
        { "type": "text", "text": system_prompt},
        { "type": "text", "text": f"### Project description json\n{project_description_src}"},
        { "type": "text", "text": "### Data Summary CSV\n" + summary_csv_text},
        { "type": "text", "text": "### Visualization Image"},
        { "type": "image_url", "image_url": img_data_uri},
    ]
    msg = llm.invoke([HumanMessage(content=parts)])
    state["pysr_config_json"] = msg.content  
    return state

def pysr_with_generated_config(state: State) -> State:
    pysr_config = json.loads(state["pysr_config_json"])
    pysr_config["extra_sympy_mappings"] = {
        "gaussian": lambda x: sympy.exp(-x*x),
        "sigmoid": lambda x: 1 / (1 + sympy.exp(-x)),
    }
    pysr_config["nested_constraints"] = {
        "exp": {"exp": 2},
        "sin": {"sin": 0},
        "gaussian": {"gaussian": 0},
        "sigmoid": {"sigmoid": 0},
    }
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
        { "type": "text", "text": pysr_explainer_usr_prompt.format(problem_description=problem_description_src, to_explain=json.dumps(to_explain, indent=2))},
    ]
    
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro")
    msg = llm.invoke([HumanMessage(content=parts)],response_mime_type="text/plain")
    state["pysr_explanations"] = msg.content
    return state
