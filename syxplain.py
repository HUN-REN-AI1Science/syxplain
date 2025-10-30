import os
import subprocess
import json
import pandas as pd
from syxplain_lib import run_syxplain


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
    problem_description_src = json.dumps(problem_description, indent=2)
    problem_description = json.loads(problem_description_src)
    state["data"] = sample_data
    state["problem_description_src"] = problem_description_src
    state["target_column"] = problem_description["target_variable"]
    state["predictor_columns"] = list(problem_description["features"].keys())
    return state

if __name__ == "__main__":
    run_syxplain(entry_point)