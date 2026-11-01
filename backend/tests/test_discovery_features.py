"""Time-dependent features: lags and period aggregates, edge padding, checks, evidence."""

import numpy as np
import pandas as pd

from backend.services.discovery.feature_stage import parse_selection, parse_specs
from backend.services.discovery.features import (
    FeatureSpec,
    SeriesContext,
    TrainView,
    build_candidates,
    compute_spec,
    feature_evidence,
    pad_edge,
    validate_spec,
)
from backend.services.discovery.series import SeriesGrid
from backend.services.discovery.temporal import TimeStructure


def _ctx(df, time="t", group=None, held=None):
    """Context over a frame that is already sorted by trajectory, then time."""
    grid = SeriesGrid.build(df, TimeStructure(time, group, confidence="strong"))
    n = len(df)
    return SeriesContext(
        grid=grid,
        pos=np.arange(n),
        keys=grid.key.copy(),
        held=np.zeros(n, dtype=bool) if held is None else held,
        time_column=time,
        group_column=group,
    )


def _monthly(n=36, start="2000-01-01"):
    t = pd.date_range(start, periods=n, freq="MS")
    return pd.DataFrame({"t": t.strftime("%Y-%m-%d"), "v": np.arange(1.0, n + 1)})


def test_edge_padding_stays_within_each_trajectory():
    values = np.array([np.nan, np.nan, 3.0, np.nan, 5.0, np.nan, 7.0, 8.0])
    keys = np.array([0, 0, 0, 0, 0, 1, 1, 1])
    filled, padded, backfilled = pad_edge(values, keys)
    # start: the first available value; interior gap: the nearest earlier value
    assert filled.tolist() == [3.0, 3.0, 3.0, 3.0, 5.0, 7.0, 7.0, 8.0]
    assert padded.tolist() == [True, True, False, True, False, True, False, False]
    assert backfilled.tolist() == [True, True, False, False, False, True, False, False]


def test_lag_keeps_the_row_count_and_pads_a_gap_from_earlier():
    df = pd.DataFrame({"t": [2000, 2001, 2002, 2004, 2005], "v": [1.0, 2.0, 3.0, 5.0, 6.0]})
    ctx = _ctx(df)
    raw = compute_spec(FeatureSpec(source="v", kind="lag", steps=1), ctx, df["v"].to_numpy())
    filled, padded, _ = pad_edge(raw, ctx.keys)
    assert len(filled) == len(df)
    # 2000 has no history (first value), 2004's previous year is missing (2002's lag value)
    assert filled.tolist() == [1.0, 1.0, 2.0, 2.0, 5.0]
    assert padded.tolist() == [True, False, False, True, False]


def test_calendar_year_aggregate_is_repeated_and_previous_year_follows():
    df = _monthly(36)  # 2000-2002, values 1..36
    ctx = _ctx(df)
    raw = df["v"].to_numpy()
    same = compute_spec(FeatureSpec(source="v", kind="period", period="year", stat="sum"), ctx, raw)
    assert np.allclose(same[:12], sum(range(1, 13))) and np.allclose(
        same[12:24], sum(range(13, 25))
    )
    prev = compute_spec(
        FeatureSpec(source="v", kind="period", period="year", stat="mean", offset=1), ctx, raw
    )
    assert np.all(np.isnan(prev[:12])) and np.allclose(prev[12:24], 6.5)
    assert np.allclose(prev[24:], 18.5)


def test_incomplete_period_has_no_sum_but_has_a_mean():
    df = _monthly(30, start="2000-07-01")  # 2000 holds only 6 months
    ctx = _ctx(df)
    raw = df["v"].to_numpy()
    total = compute_spec(
        FeatureSpec(source="v", kind="period", period="year", stat="sum"), ctx, raw
    )
    assert np.all(np.isnan(total[:6])) and np.allclose(total[6:18], sum(range(7, 19)))
    mean = compute_spec(
        FeatureSpec(source="v", kind="period", period="year", stat="mean"), ctx, raw
    )
    assert np.allclose(mean[:6], 3.5)  # half of the year's months are enough for a mean


def test_block_and_trajectory_aggregates():
    df = pd.DataFrame({"t": list(range(6)) * 2, "g": [0] * 6 + [1] * 6, "v": np.arange(12.0)})
    ctx = _ctx(df, group="g")
    raw = df["v"].to_numpy()
    block = compute_spec(
        FeatureSpec(source="v", kind="period", period="block", block_steps=3, stat="max"),
        ctx,
        raw,
    )
    assert block.tolist() == [2, 2, 2, 5, 5, 5, 8, 8, 8, 11, 11, 11]
    whole = compute_spec(
        FeatureSpec(source="v", kind="period", period="trajectory", stat="mean"), ctx, raw
    )
    assert whole.tolist() == [2.5] * 6 + [8.5] * 6


def test_validation_rules():
    ctx = _ctx(_monthly(120))
    sources = {"v"}

    def why(**kw):
        return validate_spec(FeatureSpec(**kw), ctx, sources, "y")

    assert why(source="v", kind="lag", steps=1) is None
    assert why(source="y", kind="lag", steps=1) is None
    assert "unknown source" in why(source="t", kind="lag", steps=1)
    assert "padded rows" in why(source="v", kind="lag", steps=13)  # 10% of 120 rows
    assert "current target value" in why(source="y", kind="period", period="year")
    assert why(source="y", kind="period", period="year", offset=1) is None
    assert "block_steps" in why(source="v", kind="period", period="block")
    assert "not available" in why(source="v", kind="period", period="trajectory")
    numeric = _ctx(pd.DataFrame({"t": np.arange(50), "v": np.arange(50.0)}))
    assert numeric.allowed_periods == ["block"]
    months = pd.date_range("2000", periods=40, freq="MS").strftime("%Y-%m-%d")
    assert "month" not in _ctx(pd.DataFrame({"t": months, "v": 1.0})).allowed_periods


def test_candidates_are_checked_after_computation_and_evidence_skips_padding():
    rng = np.random.default_rng(0)
    n = 120
    z = rng.normal(size=n)
    y = np.r_[0.0, 0.0, 3 * z[:-2]] + rng.normal(0, 0.1, n)
    df = pd.DataFrame({"t": np.arange(n), "z": z, "y": y})
    held = np.zeros(n, dtype=bool)
    held[-20:] = True
    ctx = _ctx(df, held=held)
    specs = [
        FeatureSpec(source="z", kind="lag", steps=2),
        FeatureSpec(source="z", kind="lag", steps=2),  # duplicate
        FeatureSpec(source="z", kind="period", period="block", block_steps=20, stat="mean",
                    offset=1),  # pads the first 20 rows: beyond 10% of 100 training rows
    ]  # fmt: skip
    cands, rejected = build_candidates(
        specs,
        ctx,
        lambda a: df[a].to_numpy(dtype=float),
        {"z": "z", "y": "y"},
        {"z"},
        "y",
        {"z", "y"},
        set(),
    )
    assert [c.alias for c in cands] == ["z_l2"]
    assert [r["reason"][:9] for r in rejected] == ["duplicate", "needs 20 "]
    z, y = df["z"].to_numpy(dtype=float), df["y"].to_numpy(dtype=float)
    view = TrainView.build([z], y, ctx.keys, ~held)
    ev = feature_evidence(cands, view, {"z": z, "y": y})
    row = ev["candidates"][0]
    assert row["gain"] > 0.9 and row["padded_share"] == round(2 / 100, 3)
    assert abs(row["step_change_r"]) < 0.5  # white noise: the lag is no shifted copy


def test_parsers_reject_malformed_entries_and_cap_the_selection():
    specs, bad = parse_specs(
        '{"specs": [{"source": "z", "kind": "lag", "steps": 1}, {"source": "z", "kind": "x"}]}'
    )
    assert len(specs) == 1 and bad[0]["reason"].startswith("kind")
    picked = [{"feature": f"f{i}", "reason": "r"} for i in range(12)] + [{"feature": "zz"}]
    reasons, _, ignored = parse_selection(
        '{"selected": ' + str(picked).replace("'", '"') + ', "rationale": "ok"}',
        {f"f{i}" for i in range(12)},
    )
    assert len(reasons) == 8 and "zz" in ignored and any("beyond" in i for i in ignored)
