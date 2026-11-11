#!/usr/bin/env python3
"""Run a Syxplain analysis through the public API and save the results.

Create an API key in the web app (Profile -> API Keys), then:

    export SYXPLAIN_API_KEY=syxp_...
    python examples/api_client.py data/example_1 --base-url http://localhost:8000

The example folder must contain a data file (.csv/.xlsx) and a
``problem_description.json`` with ``project_description``, ``target_variable``
and ``features`` (column name -> description). When the folder holds several data
files, name one with ``--data-file``. The full API reference is served by the
backend at ``/docs``; docs/api.md describes the results.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

TERMINAL = {"completed", "failed", "timeout", "cancelled"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "example_dir", type=Path, help="folder with the data file and problem_description.json"
    )
    parser.add_argument(
        "--data-file", help="data file in the folder (needed when it holds more than one)"
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--out", type=Path, default=Path("api_results"), help="where to save results and plots"
    )
    parser.add_argument("--poll", type=int, default=15, help="seconds between status checks")
    args = parser.parse_args()

    api_key = os.environ.get("SYXPLAIN_API_KEY")
    if not api_key:
        sys.exit("Set SYXPLAIN_API_KEY to an API key created in the web app (Profile -> API Keys).")
    session = requests.Session()
    session.headers["X-API-Key"] = api_key

    params = json.loads((args.example_dir / "problem_description.json").read_text())
    if args.data_file:
        data_file = args.example_dir / args.data_file
        if not data_file.is_file():
            sys.exit(f"{data_file} does not exist.")
    else:
        data_files = sorted(
            p for p in args.example_dir.iterdir() if p.suffix.lower() in {".csv", ".xlsx", ".xls"}
        )
        if len(data_files) != 1:
            names = ", ".join(p.name for p in data_files) or "none"
            sys.exit(
                f"Expected one .csv/.xlsx file in {args.example_dir}, found: {names}. "
                "Choose one with --data-file."
            )
        data_file = data_files[0]

    with data_file.open("rb") as fh:
        resp = session.post(
            f"{args.base_url}/api/v1/analyze",
            files={"file": (data_file.name, fh)},
            data={"params": json.dumps(params)},
            timeout=120,
        )
    if not resp.ok:
        sys.exit(f"The analysis was not accepted ({resp.status_code}): {resp.text}")
    accepted = resp.json()
    run_id = accepted["run_id"]
    print(f"Started run {run_id}")
    for original, stored in accepted.get("renamed_columns", {}).items():
        print(f"  column '{original}' is called '{stored}' in the results")

    while True:
        status = session.get(f"{args.base_url}/api/v1/runs/{run_id}", timeout=60).json()
        phase = (status.get("phase") or {}).get("label", "")
        print(f"  {status['status']:<10} {status['progress']:>3}%  {phase}")
        if status["status"] in TERMINAL:
            break
        time.sleep(args.poll)

    if status["status"] != "completed":
        print(f"Run ended with status {status['status']}: {status.get('error')}")
        return 1

    headline = status["results"].get("best_equation") or {}
    if headline:
        score = headline.get("holdout_r2")
        basis = "holdout R2" if score is not None else "cross-validated R2"
        score = score if score is not None else headline.get("cv_r2")
        print(f"Headline equation: {headline.get('equation')}  ({basis}: {score})")
    for warning in status.get("warnings", []):
        print(f"Warning ({warning.get('stage')}): {warning.get('message')}")

    out = args.out / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(status["results"], indent=2))
    for art in status.get("artifacts", []):
        content = session.get(f"{args.base_url}{art['download_url']}", timeout=120).content
        (out / art["filename"]).write_bytes(content)
    print(f"Saved results and {len(status.get('artifacts', []))} artifacts to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
