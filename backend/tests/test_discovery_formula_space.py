"""The formula space: the literature's relationships and statements, measured against the data."""

import asyncio

import numpy as np
import pandas as pd
import pytest

from backend.schemas.programmatic import AnalyzeParams
from backend.services.discovery import literature_coherence
from backend.services.discovery.formula_space import (
    challenger_reading,
    measure_relation,
    measure_relations,
    statement_checks,
)
from backend.services.discovery.literature import (
    fit_literature_laws,
    merged_lookup,
    run_literature,
)
from backend.services.discovery.report import build_results
from backend.services.discovery.session import DiscoverySession
from backend.services.run_digest import build_run_digest


def _session() -> DiscoverySession:
    """rate = 0.06*temp*p/(2.5+p) - 0.4*flow; the gauge reads 15 + p + 4*flow; humidity is idle."""
    rng = np.random.default_rng(1)
    n = 400
    p, temp, flow = rng.uniform(1, 12, n), rng.uniform(150, 250, n), rng.uniform(0.5, 4, n)
    df = pd.DataFrame(
        {
            "precursor": p,
            "temp": temp,
            "flow": flow,
            "humidity": rng.uniform(20, 60, n),
            "gauge": 15 + p + 4 * flow + rng.normal(0, 0.3, n),
            "rate": 0.06 * temp * p / (2.5 + p) - 0.4 * flow + rng.normal(0, 0.3, n),
        }
    )
    s = DiscoverySession(df, "rate", ["precursor", "temp", "flow", "humidity", "gauge"])
    s.profile()
    return s


def test_a_relationship_is_measured_as_published_and_refitted():
    s = _session()
    holds = measure_relation(s, {"equation": "gauge = 15 + precursor + 4 * flow", "source": "N2"})
    assert holds["status"] == "holds" and holds["r2_published"] > 0.99
    assert holds["variable"] == "gauge" and set(holds["variables"]) == {"precursor", "flow"}

    form = measure_relation(s, {"equation": "gauge = 40 + 7.5 * precursor + 9.5 * flow"})
    assert form["status"] == "holds_in_form"
    assert form["r2_published"] < 0.9 < form["r2_refitted"]
    assert form["fitted_equation"].startswith("gauge = ")

    free = measure_relation(s, {"equation": "gauge = p1 + p2 * precursor + p3 * flow"})
    assert free["status"] == "holds_in_form" and free["r2_published"] is None

    wrong = measure_relation(
        s, {"equation": "gauge = 2 * humidity", "conditions": "in an open chamber"}
    )
    assert wrong["status"] == "does_not_hold" and wrong["conditions"] == "in an open chamber"

    # stated for the other variables fixed: the data cannot test it alone
    alone = measure_relation(s, {"equation": "rate = p1 * precursor / (p2 + precursor)"})
    assert alone["status"] == "not_testable_alone" and "temp" in alone["left_out"]

    # the target may stand on the right side of a relationship
    assert measure_relation(s, {"equation": "temp = p1 * rate"})["status"] != "na"


def test_unusable_relationships_say_why_and_never_raise():
    s = _session()
    for equation, why in [
        ("gauge = 15 + pressure_of_argon", "not in the data"),
        ("something = precursor", "left side"),
        ("gauge = gauge + 1", "both sides"),
        ("gauge = 3 +* flow", "parse"),
        ("no equals sign", "left side"),
    ]:
        r = measure_relation(s, {"equation": equation})
        assert r["status"] == "na" and why in r["error"], (equation, r["error"])
    measured = measure_relations(
        s, ["not an object", {"equation": "gauge = flow"}, {"equation": "gauge=flow"}, {}]
    )
    assert len(measured) == 1  # duplicates and non-objects are left out


def _run(s, result):
    async def lookup():
        return result | {"source": "supplied"}

    asyncio.run(run_literature(s, lookup))
    fit_literature_laws(s)
    return build_results(s, None, None)


def test_the_data_speaks_against_a_statement_a_paradigm_shift():
    s = _session()
    s.fit_custom("a*precursor/(b+precursor) + c*flow", label="without temp")
    s.fit_custom("a*temp*precursor/(b+precursor) + c*flow", label="with temp")
    results = _run(
        s,
        {
            "equations": [
                {"equation": "rate = p1 * precursor / (p2 + precursor)", "citations": ["N3"]},
                {"equation": "gauge = 15 + precursor + 4 * flow", "citations": ["N2"]},
            ],
            "constraints": [
                {
                    "type": "not_a_cause",
                    "variable": "temp",
                    "source": "N3",
                    "conditions": "limited by mass transport",
                }
            ],
        },
    )
    coherence = results["discovery"]["coherence"]
    assert coherence["challenger_reading"] == "paradigm_shift"
    (statement,) = coherence["literature_statements"]
    assert statement["variable"] == "temp" and statement["data"] == "contradicts"
    checks = {c["key"]: c for c in coherence["checks"]}
    assert "paradigm shift" in checks["supplied_literature"]["detail"]
    assert "limited by mass transport" in checks["supplied_literature"]["detail"]
    # the relationship written among the equations is measured too, not thrown away
    assert checks["literature_relations"]["status"] == "pass"
    assert "temp" not in results["best_equation"]["equation"]  # the recommendation is unchanged

    digest = build_run_digest(results)
    assert digest["literature"]["relations"][0]["status"] == "holds"


def test_the_data_does_not_speak_against_a_statement_a_wrong_relationship():
    s = _session()
    s.fit_custom("a*temp*precursor/(b+precursor) + c*flow", label="right")
    s.fit_custom("a*temp*precursor/(b+precursor) + c*flow + d*humidity", label="uses humidity")
    results = _run(
        s,
        {
            "equations": [],
            "constraints": [{"type": "not_a_cause", "variable": "humidity", "source": "N1"}],
            "relations": [{"equation": "gauge = 2 * humidity", "conditions": "open chamber"}],
        },
    )
    coherence = results["discovery"]["coherence"]
    (statement,) = coherence["literature_statements"]
    assert statement["data"] == "does_not_contradict"
    checks = {c["key"]: c for c in coherence["checks"]}
    assert checks["literature_relations"]["status"] == "warn"
    assert "open chamber" in checks["literature_relations"]["detail"]


def test_the_reading_is_only_given_for_statements_the_data_can_be_asked_about():
    s = _session()
    plain = s.fit_custom("a*precursor + c*flow")
    assert statement_checks(s, plain, None) == []
    assert challenger_reading([]) is None
    used = {"used_by_challenger": True, "data": "does_not_contradict"}
    assert challenger_reading([used]) == "wrong_relationship"
    assert challenger_reading([used | {"data": "contradicts"}]) == "paradigm_shift"
    assert challenger_reading([used | {"used_by_challenger": False, "data": "contradicts"}]) is None


def test_both_kinds_of_research_are_merged_and_one_may_fail():
    async def supplied():
        return {"equations": [{"equation": "rate = p1*precursor"}], "constraints": [{"type": "x"}]}

    async def web():
        return {"equations": [{"equation": "rate = p1*temp"}], "relations": [{"equation": "a=b"}]}

    async def broken():
        raise RuntimeError("no key")

    both = asyncio.run(merged_lookup({"web": web, "supplied": supplied})())
    assert both["source"] == "both"
    assert [e["origin"] for e in both["equations"]] == ["supplied", "web"]
    assert both["constraints"][0]["origin"] == "supplied"
    assert both["relations"][0]["origin"] == "web"

    one = asyncio.run(merged_lookup({"web": broken, "supplied": supplied})())
    assert one["source"] == "supplied" and "web: no key" in one["_parse_error"]
    with pytest.raises(RuntimeError):
        asyncio.run(merged_lookup({"web": broken})())


def test_one_kind_of_research_must_be_used():
    base = {"project_description": "a project", "target_variable": "y", "features": {"x": "x"}}
    assert AnalyzeParams(**base).web_literature is True
    assert AnalyzeParams(**base, web_literature=False, literature_text="Note 1").literature_text
    with pytest.raises(ValueError, match="One kind of literature research"):
        AnalyzeParams(**base, web_literature=False)


def test_a_web_statement_decides_only_when_it_is_valid_in_the_context():
    def results_for(applies):
        s = _session()
        s.fit_custom("a*temp*precursor/(b+precursor) + c*flow", label="right")
        s.fit_custom("a*precursor/(b+precursor) + c*flow", label="without temp")

        async def lookup():
            return {
                "equations": [],
                "constraints": [
                    {
                        "type": "not_a_cause",
                        "variable": "temp",
                        "origin": "web",
                        "applies": applies,
                        "source": "doi",
                    }
                ],
                "source": "web",
            }

        asyncio.run(run_literature(s, lookup))
        fit_literature_laws(s)
        return build_results(s, None, None)

    open_ = results_for("unknown")
    assert "temp" in open_["best_equation"]["equation"]  # the statement only warns
    assert open_["discovery"]["selection"]["coherence_first"]["status"] == "coherent"
    checks = {c["key"]: c for c in open_["discovery"]["coherence"]["checks"]}
    assert checks["web_statements"]["status"] == "warn"

    valid = results_for("yes")
    # now it decides: the selection is coherence first and sees the conflict
    info = valid["discovery"]["selection"]["coherence_first"]
    assert info is not None and info["n_coherent"] < info["n_candidates"]


def test_a_law_is_composed_from_a_law_and_a_holding_relationship():
    s = _session()
    s.fit_custom("a*temp*precursor/(b+precursor) + c*flow", label="right")
    results = _run(
        s,
        {
            "equations": [{"equation": "rate = p1 * temp - p2 * gauge", "citations": ["N9"]}],
            "relations": [
                {"equation": "gauge = 15 + precursor + 4 * flow"},
                {"equation": "gauge = 2 * humidity"},  # does not hold: not composed
            ],
        },
    )
    laws = results["discovery"]["literature"]["laws"]
    (composed,) = [law for law in laws if law.get("composed_from")]
    assert composed["equation"] == "rate = p1 * temp - p2 * (15 + precursor + 4 * flow)"
    assert composed["model_id"] and composed["cv_r2"] is not None
    assert s.models[composed["model_id"]].label.startswith("Composed law")
    # the plain law uses gauge together with nothing it is connected to; the headline does not
    checks = {c["key"]: c for c in results["discovery"]["coherence"]["checks"]}
    assert "count the same effect twice" not in checks["literature_relations"]["detail"]


def test_the_headline_using_connected_variables_is_pointed_out():
    s = _session()
    s.fit_custom("a*temp*precursor/(b+precursor) + c*gauge + d*flow", label="gauge and flow")
    results = _run(
        s, {"equations": [], "relations": [{"equation": "gauge = 15 + precursor + 4 * flow"}]}
    )
    checks = {c["key"]: c for c in results["discovery"]["coherence"]["checks"]}
    assert "gauge together with" in checks["literature_relations"]["detail"]


def _soil_session() -> DiscoverySession:
    """A concentration that rises with p; four of the highest values sit just above lime 0.9."""
    rng = np.random.default_rng(3)
    n = 300
    p = rng.uniform(5, 300, n)
    lime = np.where(rng.random(n) < 0.5, rng.uniform(0, 0.6, n), rng.uniform(1.2, 20, n))
    y = 3 * p * rng.lognormal(0, 0.1, n) + 80 / (lime - 0.888)
    df = pd.DataFrame({"p": p, "lime": lime, "conc": y})
    s = DiscoverySession(df, "conc", ["p", "lime"])
    s.profile()
    return s


def test_an_equation_must_stay_in_the_realistic_range_inside_the_data():
    s = _soil_session()
    lit = literature_coherence.build(s)
    plain = s.fit_custom("a*p", label="plain")
    assert lit.conflicts(plain) == []

    # divides by zero at a lime content inside the range of the data
    divides = s.fit_custom("a*p + b/(lime - 0.888)", initial_params={"b": 50.0}, label="divides")
    (conflict,) = lit.conflicts(divides)
    assert "for lime near 0." in conflict and "inside the range of the data" in conflict

    # the context gives a lower limit for the target
    negative = s.fit_custom("a*p - 400", label="negative")
    assert lit.conflicts(negative) == []  # without a limit from the context: no conflict
    s.context_ranges = {"low": -150, "high": None, "reason": "the sensor's lower limit"}
    (conflict,) = literature_coherence.build(s).conflicts(negative)
    assert "below -150" in conflict and "the sensor's lower limit" in conflict

    # a limit that the measured target itself breaks is not used
    s.context_ranges = {"low": 1e9, "high": "nonsense"}
    c = literature_coherence.realistic_range_constraint(s)
    assert c["low"] is None and c["high"] is None


def test_the_context_decides_the_recommendation_without_any_literature():
    s = _soil_session()
    s.fit_custom("a*p", label="plain")
    divides = s.fit_custom("a*p + b/(lime - 0.888)", initial_params={"b": 50.0}, label="divides")
    results = build_results(s, None, None)
    info = results["discovery"]["selection"]["coherence_first"]
    assert info is not None and results["best_equation"]["model_id"] != divides.model_id
    assert results["discovery"]["context"]["realistic_range"]["origin"] == "context"
    row = next(m for m in results["discovery"]["leaderboard"] if m["model_id"] == divides.model_id)
    assert row["literature_conflicts"]
