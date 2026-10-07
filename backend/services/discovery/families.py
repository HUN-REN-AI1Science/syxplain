"""
Catalog of classic, named function families.

Each family is an expression template over one or more features plus a
deterministic, data-driven initial guess. Fitting itself is generic (see
``fitting.py``); the guesses matter because most of these models are
nonlinear in their parameters and fail to converge from zeros.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

Guess = Callable[[list[np.ndarray], np.ndarray], dict[str, float]]


@dataclass(frozen=True)
class Family:
    """A named model form."""

    name: str
    label: str
    formula: str  # human-readable, x / x1..xn for features
    description: str
    domain: str
    n_inputs: int  # 1 = univariate, 0 = any number (multivariate)
    build: Callable[[list[str]], str]
    guess: Guess
    requires_positive_x: bool = False
    requires_positive_y: bool = False
    max_inputs: int = 6
    lower_bounds: dict[str, float] = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "formula": self.formula,
            "inputs": "1 feature" if self.n_inputs == 1 else f"2-{self.max_inputs} features",
            "typical_use": self.domain,
            "requires": [
                r
                for r, flag in (
                    ("x > 0", self.requires_positive_x),
                    ("y > 0", self.requires_positive_y),
                )
                if flag
            ],
        }


# ---------------------------------------------------------------------------
# Initial-guess helpers
# ---------------------------------------------------------------------------


def _span(v: np.ndarray) -> float:
    s = float(np.nanmax(v) - np.nanmin(v))
    return s if s > 0 else 1.0


def _linfit(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Intercept, slope of an OLS line (robust to constant x)."""
    if np.ptp(x) == 0:
        return float(np.mean(y)), 0.0
    slope, intercept = np.polyfit(x, y, 1)
    return float(intercept), float(slope)


def _safe_log(v: np.ndarray) -> np.ndarray:
    return np.log(np.clip(v, 1e-12, None))


def _top(y: np.ndarray) -> float:
    return float(np.quantile(y, 0.95))


def _bottom(y: np.ndarray) -> float:
    return float(np.quantile(y, 0.05))


def _linear_in_params_guess(names: list[str]) -> Guess:
    return lambda xs, y: dict.fromkeys(names, 0.0) | {names[0]: float(np.mean(y))}


# ---------------------------------------------------------------------------
# Univariate families
# ---------------------------------------------------------------------------


def _g_power(xs, y):
    x = xs[0]
    ok = (x > 0) & (y > 0)
    if ok.sum() >= 3:
        la, b = _linfit(_safe_log(x[ok]), _safe_log(y[ok]))
        return {"a": float(np.exp(la)), "b": b}
    return {"a": float(np.mean(y)), "b": 0.5}


def _g_power_offset(xs, y):
    p = _g_power(xs, y)
    return {"a": 0.0, "b": p["a"], "c": p["b"]}


def _g_exponential(xs, y):
    x = xs[0]
    if (y > 0).sum() >= 3:
        ok = y > 0
        la, b = _linfit(x[ok], _safe_log(y[ok]))
        return {"a": float(np.exp(la)), "b": b}
    return {"a": float(np.mean(y)), "b": 0.0}


def _g_exponential_offset(xs, y):
    x = xs[0]
    _, slope = _linfit(x, y)
    rising = slope >= 0
    # Saturating-like default: y = a + b*exp(c*x) with c < 0
    return {
        "a": _top(y) if rising else _bottom(y),
        "b": -_span(y) if rising else _span(y),
        "c": -3.0 / _span(x),
    }


def _g_log(xs, y):
    x = xs[0]
    ok = x > 0
    a, b = _linfit(_safe_log(x[ok]), y[ok]) if ok.sum() >= 3 else (float(np.mean(y)), 0.0)
    return {"a": a, "b": b}


def _g_reciprocal(xs, y):
    x = xs[0]
    ok = x != 0
    if ok.sum() >= 3:
        a, b = _linfit(1.0 / x[ok], y[ok])
        return {"a": a, "b": b}
    return {"a": float(np.mean(y)), "b": 0.0}


def _g_michaelis(xs, y):
    x = xs[0]
    return {"a": _top(y) * 1.2, "b": float(np.median(x[x > 0])) if (x > 0).any() else 1.0}


def _g_mitscherlich(xs, y):
    x = xs[0]
    return {"a": _top(y) * 1.1, "b": 0.0, "c": 3.0 / _span(x)}


def _g_logistic(xs, y):
    x = xs[0]
    _, slope = _linfit(x, y)
    sign = 1.0 if slope >= 0 else -1.0
    return {
        "a": _span(y),
        "b": sign * 8.0 / _span(x),
        "c": float(np.median(x)),
        "d": _bottom(y),
    }


def _g_gompertz(xs, y):
    x = xs[0]
    return {"a": _top(y) * 1.1, "b": 2.0, "c": 3.0 / _span(x)}


def _g_linear_plateau(xs, y):
    x = xs[0]
    c = float(np.quantile(x, 0.6))
    lower = x <= c
    a, b = _linfit(x[lower], y[lower]) if lower.sum() >= 3 else _linfit(x, y)
    return {"a": a, "b": b, "c": c}


def _g_quadratic_plateau(xs, y):
    return _g_linear_plateau(xs, y)


def _g_gaussian(xs, y):
    x = xs[0]
    order = np.argsort(x)
    k = max(3, len(x) // 10)
    smooth = np.convolve(y[order], np.ones(k) / k, mode="same")
    peak = x[order][int(np.argmax(smooth))]
    return {"a": _bottom(y), "b": _span(y), "c": float(peak), "d": _span(x) / 4}


def _g_arrhenius(xs, y):
    x = xs[0]
    ok = (x > 0) & (y > 0)
    if ok.sum() >= 3:
        la, slope = _linfit(1.0 / x[ok], _safe_log(y[ok]))
        return {"a": float(np.exp(la)), "b": -slope}
    return {"a": float(np.mean(y)), "b": 1.0}


# ---------------------------------------------------------------------------
# Multivariate families
# ---------------------------------------------------------------------------


def _b_multiple_linear(fs: list[str]) -> str:
    return "a0 + " + " + ".join(f"b{i}*{f}" for i, f in enumerate(fs))


def _g_multiple_linear(xs, y):
    A = np.column_stack([np.ones_like(y), *xs])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    return {"a0": float(coef[0])} | {f"b{i}": float(c) for i, c in enumerate(coef[1:])}


def _b_linear_interactions(fs: list[str]) -> str:
    terms = [f"b{i}*{f}" for i, f in enumerate(fs)]
    k = 0
    for i in range(len(fs)):
        for j in range(i + 1, len(fs)):
            terms.append(f"c{k}*{fs[i]}*{fs[j]}")
            k += 1
    return "a0 + " + " + ".join(terms)


def _g_linear_interactions(xs, y):
    cols, names = [np.ones_like(y)], ["a0"]
    for i, x in enumerate(xs):
        cols.append(x)
        names.append(f"b{i}")
    k = 0
    for i in range(len(xs)):
        for j in range(i + 1, len(xs)):
            cols.append(xs[i] * xs[j])
            names.append(f"c{k}")
            k += 1
    coef, *_ = np.linalg.lstsq(np.column_stack(cols), y, rcond=None)
    return {n: float(c) for n, c in zip(names, coef, strict=True)}


def _b_cobb_douglas(fs: list[str]) -> str:
    return "a * " + " * ".join(f"{f}^b{i}" for i, f in enumerate(fs))


def _g_cobb_douglas(xs, y):
    ok = (y > 0) & np.all([x > 0 for x in xs], axis=0)
    if ok.sum() >= len(xs) + 2:
        A = np.column_stack([np.ones(ok.sum()), *(_safe_log(x[ok]) for x in xs)])
        coef, *_ = np.linalg.lstsq(A, _safe_log(y[ok]), rcond=None)
        return {"a": float(np.exp(coef[0]))} | {f"b{i}": float(c) for i, c in enumerate(coef[1:])}
    return {"a": float(np.mean(y))} | {f"b{i}": 0.3 for i in range(len(xs))}


def _b_mitscherlich_baule(fs: list[str]) -> str:
    return "a * " + " * ".join(f"(1 - exp(-c{i}*({f} + b{i})))" for i, f in enumerate(fs))


def _g_mitscherlich_baule(xs, y):
    g = {"a": _top(y) * 1.1}
    for i, x in enumerate(xs):
        g[f"b{i}"] = 0.0
        g[f"c{i}"] = 3.0 / _span(x)
    return g


def _b_additive_saturating(fs: list[str]) -> str:
    return "a0 + " + " + ".join(f"a{i + 1}*(1 - exp(-c{i}*{f}))" for i, f in enumerate(fs))


def _g_additive_saturating(xs, y):
    g = {"a0": _bottom(y)}
    for i, x in enumerate(xs):
        g[f"a{i + 1}"] = _span(y) / len(xs)
        g[f"c{i}"] = 3.0 / _span(x)
    return g


# Rate constants c0..c9 of multivariate saturating forms must be >= 0, otherwise the
# "saturating" terms turn into unbounded exponentials.
_RATES_NONNEGATIVE = {f"c{i}": 0.0 for i in range(10)}


def _uni(template: str) -> Callable[[list[str]], str]:
    return lambda fs: template.format(x=fs[0])


FAMILIES: dict[str, Family] = {
    f.name: f
    for f in [
        Family(
            "linear",
            "Linear",
            "a + b*x",
            "Straight-line response.",
            "baseline for any data",
            1,
            _uni("a + b*{x}"),
            _linear_in_params_guess(["a", "b"]),
        ),
        Family(
            "quadratic",
            "Quadratic polynomial",
            "a + b*x + c*x^2",
            "Single bend; optimum or diminishing returns.",
            "agronomic yield response",
            1,
            _uni("a + b*{x} + c*{x}^2"),
            _linear_in_params_guess(["a", "b", "c"]),
        ),
        Family(
            "cubic",
            "Cubic polynomial",
            "a + b*x + c*x^2 + d*x^3",
            "Flexible curve with an inflection; weak extrapolation.",
            "empirical smoothing",
            1,
            _uni("a + b*{x} + c*{x}^2 + d*{x}^3"),
            _linear_in_params_guess(["a", "b", "c", "d"]),
        ),
        Family(
            "power",
            "Power law / Freundlich",
            "a*x^b",
            "Scale-free relationship; Freundlich sorption isotherm.",
            "sorption isotherms, allometry, scaling laws",
            1,
            _uni("a*{x}^b"),
            _g_power,
            requires_positive_x=True,
        ),
        Family(
            "power_offset",
            "Power law with offset",
            "a + b*x^c",
            "Power law with a baseline level.",
            "allometry with background level",
            1,
            _uni("a + b*{x}^c"),
            _g_power_offset,
            requires_positive_x=True,
        ),
        Family(
            "exponential",
            "Exponential",
            "a*exp(b*x)",
            "Constant relative growth or decay rate.",
            "growth, decay, first-order kinetics",
            1,
            _uni("a*exp(b*{x})"),
            _g_exponential,
        ),
        Family(
            "exponential_offset",
            "Exponential with asymptote",
            "a + b*exp(c*x)",
            "Exponential approach to an asymptote a.",
            "relaxation, cooling, depletion",
            1,
            _uni("a + b*exp(c*{x})"),
            _g_exponential_offset,
        ),
        Family(
            "logarithmic",
            "Logarithmic",
            "a + b*log(x)",
            "Each doubling of x adds a constant amount.",
            "Weber-Fechner, diminishing returns",
            1,
            _uni("a + b*log({x})"),
            _g_log,
            requires_positive_x=True,
        ),
        Family(
            "reciprocal",
            "Reciprocal",
            "a + b/x",
            "Inverse relationship with asymptote a.",
            "dilution, inverse scaling",
            1,
            _uni("a + b/{x}"),
            _g_reciprocal,
        ),
        Family(
            "michaelis_menten",
            "Michaelis-Menten / Langmuir",
            "a*x/(b + x)",
            "Hyperbolic saturation; a = maximum, b = half-saturation.",
            "enzyme kinetics, Langmuir sorption isotherm (P sorption), nutrient uptake",
            1,
            _uni("a*{x}/(b + {x})"),
            _g_michaelis,
            lower_bounds={"b": 0.0},
        ),
        Family(
            "mitscherlich",
            "Mitscherlich",
            "a*(1 - exp(-c*(x + b)))",
            "Law of diminishing returns; a = maximum response, b = native supply, c = efficiency.",
            "crop yield vs fertilizer (P, N, K), soil test calibration",
            1,
            _uni("a*(1 - exp(-c*({x} + b)))"),
            _g_mitscherlich,
            lower_bounds={"c": 0.0},
        ),
        Family(
            "logistic",
            "Logistic (sigmoid)",
            "d + a/(1 + exp(-b*(x - c)))",
            "S-shaped transition between two levels centred at c.",
            "population growth, dose-response, phase transitions",
            1,
            _uni("d + a/(1 + exp(-b*({x} - c)))"),
            _g_logistic,
        ),
        Family(
            "gompertz",
            "Gompertz",
            "a*exp(-b*exp(-c*x))",
            "Asymmetric sigmoid growth.",
            "growth curves, tumour/biomass growth",
            1,
            _uni("a*exp(-b*exp(-c*{x}))"),
            _g_gompertz,
            lower_bounds={"c": 0.0},
        ),
        Family(
            "linear_plateau",
            "Linear-plateau",
            "a + b*min(x, c)",
            "Linear increase until a critical value c, then flat.",
            "critical soil-test level, Liebig limiting factor",
            1,
            _uni("a + b*min({x}, c)"),
            _g_linear_plateau,
        ),
        Family(
            "quadratic_plateau",
            "Quadratic-plateau",
            "a + b*m - b*m^2/(2*c), m = min(x, c)",
            "Smooth quadratic rise joining a plateau at x = c.",
            "fertilizer response, economic optimum rate",
            1,
            _uni("a + b*min({x}, c) - b*min({x}, c)^2/(2*c)"),
            _g_quadratic_plateau,
            lower_bounds={"c": 1e-9},
        ),
        Family(
            "gaussian_peak",
            "Gaussian peak",
            "a + b*exp(-(x - c)^2/(2*d^2))",
            "Single optimum at c with width d.",
            "pH or temperature optima, spectral peaks",
            1,
            _uni("a + b*exp(-({x} - c)^2/(2*d^2))"),
            _g_gaussian,
            lower_bounds={"d": 1e-9},
        ),
        Family(
            "arrhenius",
            "Arrhenius-type",
            "a*exp(-b/x)",
            "Rate controlled by an activation barrier; x is absolute temperature.",
            "reaction rates vs temperature (Kelvin)",
            1,
            _uni("a*exp(-b/{x})"),
            _g_arrhenius,
            requires_positive_x=True,
        ),
        Family(
            "multiple_linear",
            "Multiple linear",
            "a0 + b1*x1 + ... + bn*xn",
            "Additive linear effects.",
            "baseline for multivariate data",
            0,
            _b_multiple_linear,
            _g_multiple_linear,
            max_inputs=10,
        ),
        Family(
            "linear_interactions",
            "Linear with pairwise interactions",
            "a0 + sum(bi*xi) + sum(cij*xi*xj)",
            "Linear effects plus all pairwise products.",
            "factorial experiments",
            0,
            _b_linear_interactions,
            _g_linear_interactions,
            max_inputs=4,
        ),
        Family(
            "cobb_douglas",
            "Log-linear / Cobb-Douglas",
            "a * x1^b1 * ... * xn^bn",
            "Multiplicative power-law effects (linear in log space).",
            "production functions, allometry, multiplicative scaling",
            0,
            _b_cobb_douglas,
            _g_cobb_douglas,
            requires_positive_x=True,
        ),
        Family(
            "mitscherlich_baule",
            "Mitscherlich-Baule",
            "a * prod(1 - exp(-ci*(xi + bi)))",
            "Multiplicative diminishing returns over several limiting inputs.",
            "multi-nutrient yield response (N, P, K)",
            0,
            _b_mitscherlich_baule,
            _g_mitscherlich_baule,
            max_inputs=4,
            lower_bounds=_RATES_NONNEGATIVE,
        ),
        Family(
            "additive_saturating",
            "Additive saturating",
            "a0 + sum(ai*(1 - exp(-ci*xi)))",
            "Independent saturating contributions that add up.",
            "independent diminishing-return effects",
            0,
            _b_additive_saturating,
            _g_additive_saturating,
            max_inputs=5,
            lower_bounds=_RATES_NONNEGATIVE,
        ),
    ]
}
