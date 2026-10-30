"""Discovery session: data contract, searches, selection, report, reconciler, literature."""

import asyncio
import json

import numpy as np
import pandas as pd
import pytest

from backend.services.discovery.expression import ExpressionError
from backend.services.discovery.literature import fit_law, fit_literature_laws, run_literature
from backend.services.discovery.reconcile import check_claims, reconcile
from backend.services.discovery.report import build_results, explanation_data_spec, json_safe
from backend.services.discovery.selection import select
from backend.services.discovery.session import DiscoveryBudget, DiscoverySession
from backend.services.discovery.tools import build_tools


class FakeLauncher:
    """Stands in for Slurm: returns canned PySR output after a delay."""

    def __init__(self, equations=None, fail=False, delay=0.01, submit_delay=0.0, error="boom"):
        self.equations = equations or []
        self.fail = fail
        self.delay = delay
        self.submit_delay = submit_delay
        self.error = error
        self.submitted: list[tuple[str, dict]] = []
        self.cancelled: list[str] = []

    async def submit(self, search_id, input_data, on_job_id=None):
        self.submitted.append((search_id, input_data))
        job_id = f"job-{search_id}"
        if on_job_id:
            on_job_id(job_id)
        await asyncio.sleep(self.submit_delay)
        return job_id

    async def wait(self, job_id):
        await asyncio.sleep(self.delay)
        if self.fail:
            return False, None, self.error
        return True, {"status": "success", "equations": self.equations}, None

    async def cancel(self, job_id):
        self.cancelled.append(job_id)


def _data(n=400, seed=0):
    rng = np.random.default_rng(seed)
    P = rng.uniform(0, 150, n)
    pH = rng.uniform(4, 8, n)
    noise = rng.normal(size=n)
    y = 60 * (1 - np.exp(-0.03 * (P + 10))) * (pH / 6) + rng.normal(0, 1.5, n)
    return pd.DataFrame({"P added": P, "pH": pH, "noise": noise, "yield": y})


def _session(launcher=None, budget=None, events=None, df=None):
    df = _data() if df is None else df
    return DiscoverySession(
        df,
        "yield",
        [c for c in df.columns if c != "yield"],
        budget=budget,
        launcher=launcher,
        on_event=(events.append if events is not None else None),
    )


GOOD_FRONT = [
    {"equation": "(0.31 * P_added) + 20.5", "complexity": 5, "loss": 50.0},
    {"equation": "10.1 * pH * (1 - exp(-0.03 * P_added))", "complexity": 11, "loss": 3.0},
    {"equation": "not ( valid", "complexity": 3, "loss": 1.0},
]


# ---------------------------------------------------------------- data contract


def test_aliases_avoid_reserved_names_and_keep_qualifiers():
    rng = np.random.default_rng(1)
    n = 120
    df = pd.DataFrame(
        {
            "a": rng.uniform(1, 5, n),
            "d": rng.uniform(1, 5, n),
            "in": rng.uniform(1, 5, n),
            "pH (KCl)": rng.uniform(4, 8, n),
            "pH (H2O)": rng.uniform(4, 8, n),
            "y": rng.normal(size=n),
        }
    )
    df["y"] = 2 * df["a"] + rng.normal(0, 0.1, n)
    s = DiscoverySession(df, "y", ["a", "d", "in", "pH (KCl)", "pH (H2O)"])
    assert s.alias_of["a"] == "a_" and s.alias_of["d"] == "d_" and s.alias_of["in"] == "in_"
    assert s.alias_of["pH (KCl)"] == "pH_KCl" and s.alias_of["pH (H2O)"] == "pH_H2O"
    assert s.fit_family("mitscherlich", ["a_"]).n_params == 3
    lin = s.fit_family("linear", ["a_"])
    assert lin.params["b"] == pytest.approx(2.0, rel=0.05)
    s.fit_custom("k*in_ + c")  # an alias that was a keyword parses


def test_typo_alias_is_rejected_not_fitted_as_a_constant():
    rng = np.random.default_rng(2)
    df = pd.DataFrame({"Olsen_P": rng.uniform(1, 50, 80), "y": rng.normal(size=80)})
    s = DiscoverySession(df, "y", ["Olsen_P"])
    with pytest.raises(ExpressionError, match="Olsen_P"):
        s.fit_custom("Vmax*Olsen_p/(Km + Olsen_p)")
    s.fit_custom("Vmax*Olsen_P/(Km + Olsen_p)", initial_params={"Olsen_p": 1, "Vmax": 1, "Km": 1})


def test_categoricals_missingness_and_exclusion():
    rng = np.random.default_rng(3)
    n = 200
    soil = rng.integers(1, 6, n).astype(float)
    dose = rng.choice([0, 40, 80, 120, 160], n).astype(float)
    sparse = rng.uniform(0, 1, n)
    sparse[rng.random(n) < 0.6] = np.nan
    y = 0.3 * dose + 5 * (soil == 3) + rng.normal(0, 1, n)
    df = pd.DataFrame({"usda_soil_type": soil, "N rate": dose, "sparse": sparse, "y": y})
    s = DiscoverySession(df, "y", ["usda_soil_type", "N rate", "sparse"])
    assert s.kinds["usda_soil_type"] == "categorical"
    assert s.kinds["N_rate"] == "continuous"  # designed dose levels are magnitudes
    assert [c["column"] for c in s.excluded_columns] == ["sparse"]
    assert any(n["kind"] == "data_issue" and "sparse" in n["text"] for n in s.notebook)
    split = s.split_info()
    assert split["uploaded"] == n and split["dropped_incomplete"] == 0
    with pytest.raises(ValueError, match="categor"):
        s.fit_family("power", ["usda_soil_type"])
    with pytest.raises(ExpressionError, match="level"):
        s.fit_custom("a + b*usda_soil_type")
    m = s.fit_custom("a + b*N_rate + c*level(usda_soil_type, 3)")
    assert m.cv_r2 > 0.9


def test_small_dataset_uses_cv_never_in_sample_holdout():
    rng = np.random.default_rng(4)
    x = rng.uniform(0.5, 20, 33)
    df = pd.DataFrame({"x": x, "y": 5 * x / (2 + x) + rng.normal(0, 0.1, 33)})
    s = DiscoverySession(df, "y", ["x"])
    s.profile()
    mm = s.fit_family("michaelis_menten", ["x"])
    s.fit_custom("a + b*x + c*x^2 + d*x^3 + e*x^4 + f*x^5", label="poly5")
    results = build_results(s, None, None)
    assert all(m.holdout is None for m in s.models.values())
    assert results["discovery"]["split"]["has_holdout"] is False
    assert {e["metric_basis"] for e in results["equations"]} == {"cv"}
    assert results["best_equation"]["model_id"] == mm.model_id
    assert results["best_equation"]["scatter_data"]["basis"] == "cv_oof"
    assert explanation_data_spec(results)["split"]["metric_basis"] == "cv"


def test_larger_dataset_reports_holdout():
    s = _session()
    s.profile()
    s.fit_family("mitscherlich", ["P_added"])
    results = build_results(s, None, None)
    e = results["equations"][0]
    assert e["metric_basis"] == "holdout" and e["holdout_n"] == 80 and e["holdout_r2"] is not None


# ----------------------------------------------------------------- selection


def test_selection_prefers_simpler_model_within_one_se():
    s = _session()
    s.profile()
    simple = s.fit_custom("a*(1 - exp(-c*(P_added + b)))*pH", {"a": 10, "b": 0, "c": 0.03})
    complex_ = s.fit_custom(
        "a*(1 - exp(-c*(P_added + b)))*pH + e*noise + f*noise^2", {"a": 10, "b": 0, "c": 0.03}
    )
    sel = select(s.ranked_models(), [])
    assert sel.headline is simple
    assert complex_ in sel.shortlist or len(sel.shortlist) >= 1


def test_agent_pick_is_vetoed_when_it_fails_guards():
    s = _session()
    s.profile()
    poor = s.fit_family("linear", ["noise"])
    good = s.fit_custom("a*(1 - exp(-c*(P_added + b)))*pH", {"a": 10, "b": 0, "c": 0.03})
    sel = select(s.ranked_models(), [poor.model_id])
    assert sel.headline is good
    assert sel.agent_pick_rejected[0]["model_id"] == poor.model_id


def test_one_se_rule_avoids_noise_features():
    picks = 0
    for seed in range(30):
        rng = np.random.default_rng(100 + seed)
        df = pd.DataFrame(
            {"x1": rng.uniform(0, 10, 80)} | {f"z{k}": rng.normal(size=80) for k in range(5)}
        )
        df["y"] = 2 * df["x1"] + rng.normal(0, 2, 80)
        s = DiscoverySession(df, "y", [c for c in df.columns if c != "y"])
        s.fit_data.ceiling_r2, s.fit_data.ceiling_sd = 0.85, 0.02
        s.fit_family("linear", ["x1"])
        for k in range(5):
            s.fit_family("multiple_linear", ["x1", f"z{k}"])
        picks += select(s.ranked_models(), []).headline.features == ["x1"]
    assert picks >= 27  # >= 90%


# ------------------------------------------------------------------ searches


def test_search_lifecycle_full_front_and_report():
    front = [
        {
            "equation": f"{1 + 0.01 * i} * pH * (1 - exp(-0.03 * P_added)) * 10",
            "complexity": i,
            "loss": 40 - i,
        }
        for i in range(1, 36)
    ]
    launcher = FakeLauncher(equations=front + GOOD_FRONT)
    events: list = []

    async def scenario():
        s = _session(launcher, events=events)
        await s.ensure_profile()
        rec = await s.start_search(
            features=["P_added", "pH"],
            unary_operators=["exp"],
            binary_operators=["+", "*", "-"],
            guesses=["0.3*P_added + 20", "min(P_added, 3)", "log(P_added)"],
            rationale="test",
        )
        await s.wait_any([rec.search_id], 5)
        return s, rec

    s, rec = asyncio.run(scenario())
    assert rec.status == "completed" and rec.n_front == 38
    assert len(rec.model_ids) >= 36  # 40 kept, the unparsable one dropped
    assert rec.guesses == ["0.3*P_added + 20"]
    assert {g["guess"] for g in rec.rejected_guesses} == {"min(P_added, 3)", "log(P_added)"}
    _sid, payload = launcher.submitted[0]
    assert payload["predictor_columns"] == ["P_added", "pH"]
    assert len(payload["data"]["data"]) == len(s.train)  # holdout never sent to PySR
    started = next(e for e in events if e["kind"] == "search_started")
    assert started["features"] == ["P_added", "pH"] and started["rationale"] == "test"
    done = next(e for e in events if e["kind"] == "search_completed")
    best = s.models[done["model_id"]]  # the event carries the best model for the live UI
    assert done["n_equations"] >= 36 and done["cv_r2"] == round(best.cv_r2, 4)
    assert done["expression"] == best.fitted_expression and done["problem"] == "static"
    first = s.state_line(1, 10)
    assert rec.unread and "UNREAD" in first and "[event] pysr_1 completed" in first
    assert "[event]" not in s.state_line(2, 10)  # the inbox is consumed once
    s.mark_read(rec.search_id)
    assert not rec.unread

    results = build_results(
        s, {"recommended_models": [{"model_id": rec.model_ids[-1], "why": "x"}]}, None
    )
    json.dumps(results, allow_nan=False)
    assert results["best_equation"]["is_headline"]
    spec = explanation_data_spec(results)
    assert [e["model_id"] for e in spec["equations"]] == [
        e["model_id"] for e in results["equations"]
    ]
    assert spec["selection"]["headline_position"] is not None


def test_guess_model_ids_resolved_in_transformed_space():
    async def scenario():
        s = _session(FakeLauncher())
        await s.ensure_profile()
        m = s.fit_family("mitscherlich", ["P_added"], target_transform="log")
        rec = await s.start_search(
            ["P_added"],
            ["exp"],
            ["+", "-", "*"],
            target_transform="log",
            guess_model_ids=[m.model_id],
        )
        rec2 = await s.start_search(
            ["P_added"],
            ["exp"],
            ["+", "-", "*"],
            guess_model_ids=[m.model_id],
            enforce_budget=False,
        )
        await s.cancel_all()
        return m, rec, rec2

    m, rec, rec2 = asyncio.run(scenario())
    assert rec.guesses == [m.fitted_core] and not m.fitted_core.startswith("exp(")
    assert rec2.guesses == [] and "target_transform" in rec2.rejected_guesses[0]["reason"]


def test_cancel_during_submit_cancels_the_slurm_job():
    launcher = FakeLauncher(submit_delay=1.0)

    async def scenario():
        s = _session(launcher)
        rec = await s.start_search(["pH"], [], ["+"], enforce_budget=False)
        await asyncio.sleep(0.05)
        rec.task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await rec.task
        return rec

    rec = asyncio.run(scenario())
    assert launcher.cancelled == ["job-pysr_1"] and rec.status == "cancelled"


def test_budget_limits_and_note_validation():
    async def scenario():
        s = _session(
            FakeLauncher(delay=10), budget=DiscoveryBudget(max_pysr_runs=2, max_concurrent_pysr=1)
        )
        await s.ensure_profile()
        await s.start_search(["pH"], [], ["+"], enforce_budget=False)
        tools = {t.__name__: t for t in build_tools(s)}
        busy = await tools["start_pysr_search"](["pH"], [], ["+"])
        await s.cancel_search("pysr_1")
        ok = await tools["start_pysr_search"](["pH"], [], ["*"])
        over = await tools["start_pysr_search"](["pH"], [], ["-"])
        bad_formula = await tools["fit_formula"]("__import__('os')")
        bad_note = await tools["note"]([{"kind": "insight", "text": "x", "model_ids": ["C999"]}])
        good_note = await tools["note"](
            [{"kind": "insight", "text": "a"}, {"kind": "data_issue", "text": "b"}]
        )
        await s.ensure_result(grace_s=0, max_wait_s=0)
        return busy, ok, over, bad_formula, bad_note, good_note, s

    busy, ok, over, bad_formula, bad_note, good_note, _s = asyncio.run(scenario())
    assert busy.startswith("Error:") and "already running" in busy
    assert '"search_id":"pysr_2"' in ok
    assert over.startswith("BUDGET EXHAUSTED")
    assert bad_formula.startswith("Error:")
    assert bad_note.startswith("Error:") and "C999" in bad_note
    assert '"recorded":2' in good_note


def test_failed_searches_still_leave_classic_models_and_flag_old_worker():
    async def scenario():
        s = _session(
            FakeLauncher(fail=True, error="error: unrecognized arguments: --task-key pysr_1")
        )
        await s.ensure_profile()
        await s.start_search(["pH"], [], ["+"], enforce_budget=False)
        await s.ensure_result(grace_s=1, max_wait_s=1)
        n = await asyncio.to_thread(s.auto_screen)
        return s, n

    s, n = asyncio.run(scenario())
    assert s.searches["pysr_1"].status == "failed"
    assert any("worker image" in n_["text"] for n_ in s.notebook)
    assert n > 10
    results = build_results(s, None, "agent crashed")
    assert results["equations"] and all(e["origin"] != "symbolic" for e in results["equations"])


def test_json_safe_replaces_nan():
    assert json_safe({"a": float("nan"), "b": [np.float64(1.5), np.inf]}) == {
        "a": None,
        "b": [1.5, None],
    }


# ----------------------------------------------------------------- reconciler


def test_reconciler_flags_late_searches_and_bad_claims():
    async def scenario():
        s = _session(FakeLauncher(equations=GOOD_FRONT))
        await s.ensure_profile()
        m = s.fit_family("mitscherlich", ["P_added"])
        await s.start_search(["P_added", "pH"], ["exp"], ["+", "*"], enforce_budget=False)
        await s.ensure_result(grace_s=2, max_wait_s=2)
        report = {
            "summary": f"{m.model_id} reaches R2 0.99 and C999 is great.",
            "recommended_models": [{"model_id": m.model_id, "why": "simple"}],
            "rejected_forms": [],
            "insights": [],
        }
        return s, m, await reconcile(s, report, review=None)

    s, m, out = asyncio.run(scenario())
    assert out["stale"] is True and out["late_searches"] == ["pysr_1"]
    assert any(n["kind"] == "candidate" and "pysr_1" in n["text"] for n in s.notebook)
    issues = " ".join(c["issue"] for c in out["claims_failed"])
    assert "C999" in issues and m.model_id in issues


def test_reconciler_review_pass_clears_stale():
    async def review(report, late):
        for sid in late:
            s.mark_read(sid)
        return report | {"summary": "reviewed", "review_steps": 2}

    async def scenario():
        nonlocal s
        s = _session(FakeLauncher(equations=GOOD_FRONT))
        await s.ensure_profile()
        await s.start_search(["P_added", "pH"], ["exp"], ["+", "*"], enforce_budget=False)
        await s.ensure_result(grace_s=2, max_wait_s=2)
        return await reconcile(s, {"summary": "x", "recommended_models": []}, review)

    s = None
    out = asyncio.run(scenario())
    assert (
        out["stale"] is False
        and out["review_steps"] == 2
        and out["reviewed_searches"] == ["pysr_1"]
    )


def test_check_claims_accepts_correct_numbers():
    s = _session()
    s.profile()
    m = s.fit_family("mitscherlich", ["P_added"])
    report = {"summary": f"{m.model_id} has CV R2 {m.cv_r2:.3f}", "recommended_models": []}
    assert check_claims(s, report) == []


# ----------------------------------------------------------------- literature


def test_literature_laws_are_mapped_and_fitted_once():
    calls = []

    async def lookup():
        calls.append(1)
        return {
            "equations": [
                {"equation": "yield = a*P_added/(b + P_added)", "citations": ["https://doi.org/x"]},
                {"equation": "yield = k*Zn", "citations": []},
                {"equation": "pH = 0.5*P_added", "citations": []},
            ]
        }

    async def scenario():
        s = _session(FakeLauncher())
        await s.ensure_profile()
        s.literature_task = asyncio.create_task(run_literature(s, lookup))
        await s.literature_task
        return s

    s = asyncio.run(scenario())
    # Collected only: the agent's exploration is blind to them (no models, no inbox event)
    assert s.known_laws["status"] == "pending" and len(s.literature_raw) == 3 and len(calls) == 1
    assert not any(m.kind == "literature" for m in s.models.values())
    assert any(e["kind"] == "literature" for e in s.events) and s.take_inbox() == []

    fitted = fit_literature_laws(s)
    laws = s.known_laws["laws"]
    assert s.known_laws["status"] == "ok" and len(fitted) == 1
    assert laws[0]["model_id"].startswith("L") and laws[0]["cv_r2"] is not None
    assert laws[1]["unmapped"] == ["Zn"] and laws[1]["model_id"] is None
    assert "not the target" in laws[2]["fit_error"]


def test_fit_law_takes_coefficients_named_after_variables_as_parameters():
    s = _session()
    s.profile()
    for i, eq in enumerate(
        [
            "yield = a_P_added + b_P_added * P_added",  # fuzzily close to P_added
            "yield = Y_ref * (P_added / P_ref)^beta_P",
            "yield = a_pH + b_pH * pH + b_trend * P_added",
        ],
        1,
    ):
        law = fit_law(s, {"equation": eq}, i)
        assert law["model_id"] and law["fit_error"] is None and law["unmapped"] == [], eq
    law = fit_law(s, {"equation": "yield = a_Zn + b_Zn * Zn"}, 4)
    assert law["unmapped"] == ["Zn"]


def test_fit_law_uses_published_constants():
    s = _session()
    s.profile()
    law = fit_law(s, {"equation": "yield = 70*(1 - exp(-0.03*P_added))*pH/6"}, 1)
    assert law["model_id"] and law["cv_r2"] > 0.9
