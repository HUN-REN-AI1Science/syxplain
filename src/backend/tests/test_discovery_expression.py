import numpy as np
import pytest

from backend.services.discovery.expression import (
    ExpressionError,
    make_alias,
    parameterize_constants,
    parse_expression,
    substitute_parameters,
)


def test_parses_variables_and_parameters():
    expr = parse_expression("a * (1 - exp(-c * (P + b)))", variables=["P", "pH"])
    assert expr.variables == ("P",)
    assert set(expr.parameters) == {"a", "b", "c"}
    out = expr.evaluate({"P": np.array([0.0, 10.0])}, {"a": 2.0, "b": 0.0, "c": 0.1})
    np.testing.assert_allclose(out, [0.0, 2 * (1 - np.exp(-1.0))])


def test_caret_is_power_and_min_is_elementwise():
    expr = parse_expression("x^2 + min(x, 1)", variables=["x"])
    np.testing.assert_allclose(expr.evaluate({"x": np.array([0.5, 3.0])}, {}), [0.75, 10.0])


@pytest.mark.parametrize(
    "source",
    [
        "__import__('os').system('ls')",
        "x.__class__",
        "open('f')",
        "[x for x in y]",
        "lambda: 1",
        "x if x else 1",
        "'text'",
        "exp(x, y)",
        "exp(x=1)",
    ],
)
def test_rejects_unsafe_or_unknown_constructs(source):
    with pytest.raises(ExpressionError):
        parse_expression(source, variables=["x", "y"])


def test_unknown_names_rejected_when_parameters_are_fixed():
    with pytest.raises(ExpressionError):
        parse_expression("a * x", variables=["x"], parameters=())


def test_pysr_constants_become_parameters_but_small_integers_stay():
    template, values = parameterize_constants("2.5*x^2 + exp(-0.31*y) - 1", taken=["x", "y"])
    assert template == "k0*x**2 + exp(-k1*y) - 1"
    assert values == {"k0": 2.5, "k1": 0.31}


def test_parameter_prefix_avoids_feature_names():
    template, values = parameterize_constants("1.5*k0", taken=["k0"])
    assert "kk0" in template and values == {"kk0": 1.5}


def test_substitute_parameters_renders_values():
    assert substitute_parameters("a + b*x", {"a": 1.0, "b": -2.5}) == "1 + (-2.5)*x"


def test_make_alias_cleans_column_names():
    taken: set[str] = set()
    a = make_alias("Spin coater: Absolute Humidity [g/m3]", taken)
    assert a == "Spin_coater_Absolute_Humidity"
    taken.add(a)
    assert (
        make_alias("Spin coater: Absolute Humidity (%)", taken) == "Spin_coater_Absolute_Humidity_2"
    )
    assert make_alias("1st value", set()) == "x_1st_value"
    assert make_alias("exp", set()) == "exp_"
