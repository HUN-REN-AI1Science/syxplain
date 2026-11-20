"""Supplied literature: its statements are tested on every equation, and the selection is coherence first."""

import asyncio

import numpy as np
import pandas as pd
import pytest

from backend.schemas.programmatic import AnalyzeParams
from backend.services.discovery.coherence import _known_laws
from backend.services.discovery.fitting import ModelResult
from backend.services.discovery.literature import fit_literature_laws, run_literature
from backend.services.discovery.literature_coherence import (
    LiteratureCoherence,
    normalize_constraints,
)
from backend.services.discovery.relate import is_known
from backend.services.discovery.report import build_results
from backend.services.discovery.selection import select
from backend.services.discovery.session import DiscoverySession
from backend.services.run_digest import build_run_digest
from backend.tests.test_discovery_shap import _interaction_session

# y = 3*x1*x2 + exp(x3) + noise; the column "noise" has no effect
RAW = [
    {"type": "not_a_cause", "variable": "noise", "source": "Note 1", "reason": "sealed"},
    {"type": "monotone", "variable": "x1", "direction": "increasing", "source": "Note 2"},
    {"type": "defined_over", "ranges": {"x1": [0.2, 6], "nope": [0, 1]}, "source": "Note 1"},
    {
        "type": "limit",
        "variable": "x1",
        "toward": "large",
        "quantity": "target/x1",
        "expect": "finite_positive",
        "source": "Note 3",
    },
]


def _status(lit: LiteratureCoherence, model) -> dict[str, str]:
    by_id = {c["id"]: c["type"] for c in lit.constraints}
    return {by_id[r["id"]]: r["status"] for r in lit.evaluate(model)}


def test_constraints_are_validated_and_mapped():
    s = _interaction_session()
    kept, dropped = normalize_constraints(
        s,
        [
            *RAW,
            {"type": "not_a_cause", "variable": "unknown_column"},
            {"type": "monotone", "variable": "x1", "direction": "sideways"},
            {"type": "limit", "variable": "x1", "toward": "large", "quantity": "target*zzz"},
            {"type": "made_up", "variable": "x1"},
            "not an object",
        ],
    )
    assert [c["type"] for c in kept] == ["not_a_cause", "monotone", "defined_over", "limit"]
    assert kept[2]["ranges"] == {"x1": [0.2, 6.0]}  # the unknown column's range is left out
    assert kept[3]["quantity"] == f"{s.target_alias}/x1"
    assert len(dropped) == 5
    assert normalize_constraints(s, None) == ([], [])


def test_each_constraint_is_computed_on_the_equation():
    s = _interaction_session()
    kept, _ = normalize_constraints(s, RAW)
    lit = LiteratureCoherence(s, kept)

    good = s.fit_custom("k*x1*x2 + c*exp(x3)", label="right form")
    assert set(_status(lit, good).values()) == {"agrees"}
    assert lit.conflicts(good) == []

    with_noise = s.fit_custom("k*x1*x2 + c*exp(x3) + d*noise", label="uses noise")
    assert _status(lit, with_noise)["not_a_cause"] == "conflict"
    assert "Note 1" in lit.conflicts(with_noise)[0]

    undefined = s.fit_custom("k*x2*log(x1 - 0.5) + c*exp(x3) + m", label="log")
    assert _status(lit, undefined)["defined_over"] == "conflict"

    no_x1 = s.fit_custom("a*x2 + c*exp(x3)", label="misses x1")
    status = _status(lit, no_x1)
    assert status["monotone"] == "silent" and status["defined_over"] == "silent"

    quadratic = s.fit_custom("k*x1*x1*x2 + c*exp(x3)", label="grows too fast")
    assert _status(lit, quadratic)["limit"] == "conflict"


def test_selection_is_coherence_first_and_keeps_the_challenger():
    s = _interaction_session()
    good = s.fit_custom("k*x1*x2 + c*exp(x3)", label="right form")
    with_noise = s.fit_custom("k*x1*x2 + c*exp(x3) + d*noise", label="uses noise")
    s.final_scoring()
    kept, _ = normalize_constraints(s, RAW)
    lit = LiteratureCoherence(s, kept)
    models = [m for m in s.ranked_models() if m in (good, with_noise)]

    # Without supplied literature nothing changes, and nothing new is stored
    plain = select(models, [with_noise.model_id])
    assert plain.headline is with_noise and "coherence_first" not in plain.to_dict()

    sel = select(models, [with_noise.model_id], conflicts=lit.conflicts)
    info = sel.to_dict()["coherence_first"]
    assert sel.headline is good and sel.headline_reason.startswith("coherent_")
    assert info["status"] == "coherent" and info["n_coherent"] == 1 and info["n_candidates"] == 2
    assert "supplied literature" in sel.agent_pick_rejected[0]["reason"]
    if info["challenger_model_id"]:  # the incoherent model scored better: it is kept beside
        assert info["challenger_model_id"] == with_noise.model_id
        assert with_noise in sel.shortlist and info["gap_se"] >= 0


def test_no_coherent_discovery_falls_back_to_a_coherent_law_or_the_metric():
    s = _interaction_session()
    good = s.fit_custom("k*x1*x2 + c*exp(x3)", label="right form")
    law = s.fit_custom("a*x2 + b", label="Published law 1", kind="literature")
    s.final_scoring()
    kept, _ = normalize_constraints(s, [{"type": "not_a_cause", "variable": "x1"}])
    lit = LiteratureCoherence(s, kept)

    sel = select([good, law], [], reference=is_known, conflicts=lit.conflicts)
    assert sel.headline is law and sel.headline_is_reference
    assert sel.headline_reason == "coherent_literature_law"
    info = sel.coherence_first
    assert info["challenger_model_id"] == good.model_id and info["gap_se"] > 1
    assert info["headline_conflicts"] == [] and info["challenger_conflicts"]
    # The discovered equations were usable: the check must not say they were not
    details = [c["detail"] for c in _known_laws(law, [], None, sel.headline_reason)]
    assert any("coherent with the supplied literature" in d for d in details)
    assert not any("was usable" in d for d in details)

    # An agent's pick that the law overrules is recorded as rejected, with the reason
    sel = select([good, law], [good.model_id], reference=is_known, conflicts=lit.conflicts)
    assert sel.headline is law
    assert sel.agent_pick_rejected[-1]["model_id"] == good.model_id
    assert "supplied literature" in sel.agent_pick_rejected[-1]["reason"]

    # No coherent law either: the metric decides, and the reason says so
    sel = select([good], [], reference=is_known, conflicts=lit.conflicts)
    assert sel.headline is good and sel.headline_reason.endswith("_no_coherent_model")
    assert sel.coherence_first["status"] == "no_coherent_model"
    assert sel.coherence_first["headline_conflicts"]


def test_gap_is_measured_from_the_headline():
    def model(model_id: str, cv_rmse: float, complexity: int) -> ModelResult:
        return ModelResult(
            model_id=model_id,
            kind="custom",
            name=model_id,
            label=model_id,
            expression="x",
            features=["x"],
            complexity=complexity,
            cv_r2=0.9,
            cv_rmse=cv_rmse,
            cv_se=0.1,
            verdict="good",
        )

    challenger, best, simple = model("M1", 1.0, 9), model("M2", 1.2, 7), model("M3", 1.25, 3)
    sel = select(
        [challenger, best, simple], [], conflicts=lambda m: ["uses z"] if m is challenger else []
    )
    # The headline is the simplest tied model, not the best coherent one
    assert sel.headline is simple and sel.headline_reason == "coherent_simplest_within_1se"
    assert sel.coherence_first["best_coherent_cv_rmse"] == 1.2
    assert sel.coherence_first["gap_se"] == pytest.approx(2.5)


def test_limit_on_a_single_variable_equation_and_the_target_by_its_alias():
    rng = np.random.default_rng(0)
    x = rng.uniform(0.5, 10, 300)
    df = pd.DataFrame({"dose (mg)": x, "Yield (t/ha)": 5 * x / (2 + x) + rng.normal(0, 0.1, 300)})
    s = DiscoverySession(df, "Yield (t/ha)", ["dose (mg)"])
    dose = s.features[0]
    assert s.target_alias != s.target_column
    kept, dropped = normalize_constraints(
        s,
        [
            {
                "type": "limit",
                "variable": dose,
                "toward": "large",
                "quantity": "target",
                "expect": "finite_positive",
            },
            {  # the target under its alias, the name the scout is given for it
                "type": "limit",
                "variable": dose,
                "toward": "large",
                "quantity": f"{s.target_alias}/{dose}",
                "expect": "zero",
            },
            # Malformed ranges are dropped alone; they do not take the others with them
            {"type": "defined_over", "ranges": [[0, 1]]},
            {"type": "defined_over", "ranges": {dose: {"min": 0, "max": 1}}},
        ],
    )
    assert [c["type"] for c in kept] == ["limit", "limit"] and len(dropped) == 2
    assert kept[1]["quantity"] == f"{s.target_alias}/{dose}"

    lit = LiteratureCoherence(s, kept)
    saturating = s.fit_custom(f"p*{dose}/(q + {dose})", label="saturating")
    linear = s.fit_custom(f"p*{dose} + q", label="linear")
    assert [r["status"] for r in lit.evaluate(saturating)] == ["agrees", "agrees"]
    assert [r["status"] for r in lit.evaluate(linear)] == ["conflict", "conflict"]


def test_the_grid_stays_within_its_budget():
    rng = np.random.default_rng(0)
    names = [f"v{i}" for i in range(12)]
    df = pd.DataFrame({n: rng.uniform(1, 2, 80) for n in names})
    df["y"] = df.sum(axis=1)
    s = DiscoverySession(df, "y", names)
    lit = LiteratureCoherence(s, [])
    grid = lit._grid(s.features, {}, lead=s.features[0])
    assert len(grid[s.features[0]]) <= 200_000


def test_supplied_literature_reaches_the_results():
    s = _interaction_session()
    s.fit_custom("k*x1*x2 + c*exp(x3)", label="right form")
    s.fit_custom("k*x1*x2 + c*exp(x3) + d*noise", label="uses noise")

    async def lookup():
        return {
            "equations": [{"equation": "y = p1*x1*x2 + p2", "citations": ["Note 2"]}],
            "constraints": RAW,
            "source": "supplied",
        }

    asyncio.run(run_literature(s, lookup))
    assert len(fit_literature_laws(s)) == 1
    assert s.known_laws["source"] == "supplied" and len(s.known_laws["constraints"]) == 4

    results = build_results(s, None, None)
    selection = results["discovery"]["selection"]
    assert selection["coherence_first"]["status"] == "coherent"
    headline = results["best_equation"]
    assert "noise" not in headline["equation"] and headline["literature_conflicts"] == []
    checks = {c["key"]: c["status"] for c in results["discovery"]["coherence"]["checks"]}
    assert checks["supplied_literature"] in ("pass", "warn")
    assert all("literature_conflicts" in e for e in results["discovery"]["leaderboard"])

    digest = build_run_digest(results)
    assert digest["selection"]["coherence_first"]["n_coherent"] >= 1
    assert digest["literature"]["source"] == "supplied"
    assert digest["literature"]["constraints"][0]["type"] == "not_a_cause"


def test_statements_without_an_equation_still_constrain():
    s = _interaction_session()
    s.fit_custom("k*x1*x2 + c*exp(x3) + d*noise", label="uses noise")

    async def lookup():
        return {"equations": [], "constraints": RAW[:1], "source": "supplied"}

    asyncio.run(run_literature(s, lookup))
    assert fit_literature_laws(s) == []
    assert s.known_laws["status"] == "ok" and s.literature_constraints


def test_literature_text_is_an_optional_bounded_parameter():
    base = {"project_description": "p", "target_variable": "y", "features": {"x": "d"}}
    assert AnalyzeParams(**base).literature_text is None
    assert AnalyzeParams(**base, literature_text="Note 1 ...").literature_text == "Note 1 ..."
    with pytest.raises(ValueError):
        AnalyzeParams(**base, literature_text="x" * 60_001)


def test_a_recommended_literature_law_has_its_own_counts():
    s = _interaction_session()
    good = s.fit_custom("k*x1*x2 + c*exp(x3)", label="right form")
    law = s.fit_custom("a*x2 + b", label="Published law 1", kind="literature")
    bad_law = s.fit_custom("a*x1 + b", label="Published law 2", kind="literature")
    s.final_scoring()
    kept, _ = normalize_constraints(s, [{"type": "not_a_cause", "variable": "x1"}])
    lit = LiteratureCoherence(s, kept)

    sel = select([good, law, bad_law], [], reference=is_known, conflicts=lit.conflicts)
    info = sel.coherence_first
    assert sel.headline is law and info["status"] == "coherent_reference"
    # One discovered equation and two laws were candidates; only one law is coherent
    assert info["n_candidates"] == 3 and info["n_coherent"] == 1
    assert info["best_coherent_cv_rmse"] == law.cv_rmse and info["headline_conflicts"] == []
    assert info["challenger_model_id"] == good.model_id and info["challenger_conflicts"]
    assert sel.shortlist[0] is law and good in sel.shortlist
