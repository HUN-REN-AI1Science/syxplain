"""
Try the discovery agent on an example dataset without the full stack.

The agent and its classic-model tools run for real against the LLM configured in
.env (OPENAI_API_KEY / OPENAI_API_BASE / OPENAI_MODEL_NAME, or
DISCOVERY_AGENT_MODEL). PySR searches are replaced by the mock-Slurm least-squares
stand-in, so no cluster, Julia, database or Keycloak is needed.

Usage (from the repo root):
    python dev/try_discovery_agent.py --example 1
    python dev/try_discovery_agent.py --example 3 --max-iters 20 --minutes 15
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev"))

EXAMPLES = {
    1: ("data/example_1/sample_data.csv", "data/example_1/problem_description.json"),
    3: ("data/example_3/Celegans_AggregatedData.csv", "data/example_3/problem_description.json"),
}


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            value = value.split(" #")[0].strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)


class MockLauncher:
    """PySR stand-in: least-squares equations over the requested features after a delay."""

    def __init__(self, delay_s: float):
        self.delay_s = delay_s
        self.inputs: dict[str, dict] = {}

    async def submit(self, search_id, input_data, on_job_id=None):
        self.inputs[search_id] = input_data
        if on_job_id:
            on_job_id(search_id)
        return search_id

    async def wait(self, job_id):
        from mock_slurmrestd import _mock_pysr_results

        await asyncio.sleep(self.delay_s)
        return True, _mock_pysr_results(self.inputs[job_id]), None

    async def cancel(self, job_id):
        pass


async def main(args: argparse.Namespace) -> None:
    import pandas as pd

    from backend.core.config import get_discovery_settings
    from backend.infrastructure.llm.client import create_dspy_model
    from backend.services.discovery.agent import run_discovery_agent
    from backend.services.discovery.relate import screen_named_laws
    from backend.services.discovery.report import build_results
    from backend.services.discovery.session import DiscoveryBudget, DiscoverySession
    from backend.services.discovery.tools import build_tools

    data_path, desc_path = EXAMPLES[args.example]
    desc = json.loads((ROOT / desc_path).read_text())
    df = pd.read_csv(ROOT / data_path)
    columns = [c for c in desc["features"] if c in df.columns]

    def show(event):
        print(f"[{event['t']:6.1f}s] {event['kind']:17s} {event['text'][:160]}", flush=True)

    session = DiscoverySession(
        df,
        desc["target_variable"],
        columns,
        budget=DiscoveryBudget(
            max_iters=args.max_iters, max_pysr_runs=3, wall_clock_s=args.minutes * 60
        ),
        launcher=MockLauncher(args.pysr_delay),
        on_event=show,
    )
    project = {
        "project_description": desc.get("project_description", ""),
        "target": {"alias": session.target_alias, "column": desc["target_variable"]},
        "features": {
            session.alias_of[c]: {"column": c, "description": desc["features"][c]} for c in columns
        },
    }
    lm = create_dspy_model(model_name=get_discovery_settings().model_name or None)
    if session.series is not None:
        from backend.services.discovery.feature_stage import run_series_feature_stage

        await run_series_feature_stage(session, lambda: lm, project)
        print(f"Feature stage: {json.dumps(session.series.get('feature_stage'), default=str)}")
    if session.continuous_features:
        await session.start_search(
            session.continuous_features,
            ["exp", "log", "sqrt"],
            ["+", "-", "*", "/"],
            rationale="Baseline: all continuous features",
            enforce_budget=False,
        )

    t0 = time.time()
    await session.ensure_profile()
    session.reset_clock()
    report = await run_discovery_agent(
        session, build_tools(session), lm, project, max_iters=args.max_iters
    )
    await session.ensure_result(grace_s=args.pysr_delay * 3, max_wait_s=args.pysr_delay * 6)
    print(f"Named laws fitted after exploration: {screen_named_laws(session)}")
    results = build_results(session, report, None)

    print("\n=== Agent report ===")
    print(json.dumps(report, indent=2))
    print("\n=== Leaderboard (held-out R2) ===")
    for e in results["discovery"]["leaderboard"][:8]:
        print(
            f"{e['label'][:38]:38s} cv={e['cv_r2'] or 0:.3f} holdout={e['holdout_r2'] or 0:.3f} "
            f"{e['verdict']:9s} {e['equation'][:80]}"
        )
    print(f"\nNotebook entries: {len(session.notebook)}; elapsed {time.time() - t0:.0f}s")
    print("\n=== Relation to known laws (headline) ===")
    for r in (results["discovery"].get("relations") or {}).get("headline", []):
        print(f"{r['law_id']:5s} {r['relation']:10s} {r['comparison']:6s} {r['label']}")
    print("\n=== Coherence ===")
    print(json.dumps(results["discovery"].get("coherence"), indent=2))
    if args.explain:
        from backend.infrastructure.llm.images import png_images
        from backend.services.discovery.literature import literature_context
        from backend.services.discovery.report import explanation_data_spec, merge_explanations
        from backend.services.llm_service import generate_equation_explanation

        explanation = await asyncio.to_thread(
            generate_equation_explanation,
            project_spec_json=json.dumps(desc),
            data_spec_json=json.dumps(explanation_data_spec(results)),
            literature_context=literature_context(results["discovery"].get("literature")),
            shap_plots=png_images([p["b64"] for p in session.shap_plots]),
        )
        results["explanations"], _ = merge_explanations(explanation, results["equations"])
        print("\n=== Explanation coherence ===")
        print(json.dumps(explanation.get("coherence"), indent=2))
    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2))
        print(f"Results written to {args.output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--example", type=int, choices=sorted(EXAMPLES), default=1)
    parser.add_argument("--max-iters", type=int, default=16)
    parser.add_argument("--minutes", type=float, default=10)
    parser.add_argument("--pysr-delay", type=float, default=20, help="Seconds a mock search takes")
    parser.add_argument("--output", help="Write the full results JSON here")
    parser.add_argument("--explain", action="store_true", help="Also run the explanation LLM")
    parser.add_argument(
        "--no-shap-images", action="store_true", help="Text SHAP only (no plots for the agent)"
    )
    cli_args = parser.parse_args()
    if cli_args.no_shap_images:
        os.environ["DISCOVERY_SHAP_IMAGES"] = "false"
    load_env(ROOT / ".env")
    import dspy

    from backend.infrastructure.monitoring.llm_costs import summarize

    with dspy.track_usage() as usage:
        asyncio.run(main(cli_args))
    print("\n=== LLM usage and cost ===")
    print(json.dumps(summarize(usage), indent=2))
