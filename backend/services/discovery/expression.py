"""
Safe parsing and evaluation of model expressions.

Expressions come from three places: the classic family catalog, formulas the
discovery agent proposes, and PySR hall-of-fame equations. All of them are
parsed with ``ast`` and walked by a small numpy evaluator — nothing is ever
passed to ``eval``. Only arithmetic, a fixed set of math functions, numeric
literals, data variables and parameters are accepted.
"""

import ast
import keyword
import math
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np

_FUNCTIONS: dict[str, tuple[int, Callable[..., np.ndarray]]] = {
    "exp": (1, np.exp),
    "log": (1, np.log),
    "log10": (1, np.log10),
    "log2": (1, np.log2),
    "log1p": (1, np.log1p),
    "sqrt": (1, np.sqrt),
    "abs": (1, np.abs),
    "sin": (1, np.sin),
    "cos": (1, np.cos),
    "tan": (1, np.tan),
    "tanh": (1, np.tanh),
    "square": (1, np.square),
    "cube": (1, lambda x: x**3),
    "inv": (1, lambda x: 1.0 / x),
    "neg": (1, np.negative),
    "min": (2, np.minimum),
    "max": (2, np.maximum),
    # level(x, k): 1 where an integer-coded categorical equals k, else 0
    "level": (2, lambda x, k: (np.asarray(x) == k).astype(float)),
}

_CONSTANTS = {"pi": math.pi, "e": math.e}

_BIN_OPS = {
    ast.Add: np.add,
    ast.Sub: np.subtract,
    ast.Mult: np.multiply,
    ast.Div: np.divide,
    ast.Pow: np.power,
}

MAX_EXPRESSION_LENGTH = 2000
MAX_NODES = 300

ALLOWED_FUNCTIONS = tuple(sorted(_FUNCTIONS))


class ExpressionError(ValueError):
    """Raised when an expression is malformed or uses forbidden constructs."""


@dataclass(frozen=True)
class ParsedExpression:
    """A validated expression tree with its free symbols split by role."""

    source: str
    tree: ast.Expression
    variables: tuple[str, ...]
    parameters: tuple[str, ...]
    complexity: int

    def evaluate(self, data: dict[str, np.ndarray], params: dict[str, float]) -> np.ndarray:
        """Evaluate on column arrays; returns an array broadcast to the data length."""
        with np.errstate(all="ignore"):
            out = _eval(self.tree.body, data, params)
        n = len(next(iter(data.values()))) if data else 1
        return np.broadcast_to(np.asarray(out, dtype=float), (n,)).copy()


def _normalize(source: str) -> str:
    # PySR/Julia and humans write powers as ^ ; Python uses **.
    return source.replace("^", "**").strip()


def parse_expression(
    source: str,
    variables: Iterable[str],
    parameters: Iterable[str] | None = None,
) -> ParsedExpression:
    """
    Parse and validate an expression.

    Args:
        source: Expression text, e.g. ``a * (1 - exp(-c * (P + b)))``
        variables: Names that refer to data columns
        parameters: Names that are free parameters. If None, every unknown
            identifier is treated as a parameter.

    Raises:
        ExpressionError: On syntax errors or forbidden constructs.
    """
    if not isinstance(source, str) or not source.strip():
        raise ExpressionError("Expression is empty")
    if len(source) > MAX_EXPRESSION_LENGTH:
        raise ExpressionError(f"Expression longer than {MAX_EXPRESSION_LENGTH} characters")

    text = _normalize(source)
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as e:
        raise ExpressionError(f"Syntax error: {e.msg}") from e

    variable_set = set(variables)
    param_set = set(parameters) if parameters is not None else None
    used_vars: list[str] = []
    used_params: list[str] = []
    nodes = 0
    call_names = {
        id(n.func)
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }

    for node in ast.walk(tree):
        nodes += 1
        if isinstance(node, ast.Expression):
            continue
        if isinstance(node, ast.BinOp):
            if type(node.op) not in _BIN_OPS:
                raise ExpressionError(f"Operator {type(node.op).__name__} is not allowed")
        elif isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, ast.USub | ast.UAdd):
                raise ExpressionError(f"Operator {type(node.op).__name__} is not allowed")
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
                name = getattr(node.func, "id", "?")
                raise ExpressionError(
                    f"Function '{name}' is not allowed. Allowed: {', '.join(ALLOWED_FUNCTIONS)}"
                )
            if node.keywords:
                raise ExpressionError("Keyword arguments are not allowed")
            arity = _FUNCTIONS[node.func.id][0]
            if len(node.args) != arity:
                raise ExpressionError(f"{node.func.id}() takes {arity} argument(s)")
            if node.func.id == "level" and not isinstance(node.args[1], ast.Constant):
                raise ExpressionError("level(x, k) needs a literal category code k")
        elif isinstance(node, ast.Name):
            if not isinstance(node.ctx, ast.Load):
                raise ExpressionError("Assignment is not allowed")
            name = node.id
            if name in _FUNCTIONS:
                if id(node) not in call_names:
                    raise ExpressionError(f"'{name}' is a function; call it as {name}(...)")
                continue
            if name in variable_set:
                if name not in used_vars:
                    used_vars.append(name)
            elif name in _CONSTANTS:
                continue
            elif param_set is None or name in param_set:
                if name.startswith("_"):
                    raise ExpressionError(f"Identifier '{name}' is not allowed")
                if name not in used_params:
                    used_params.append(name)
            else:
                raise ExpressionError(f"Unknown name '{name}'")
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, int | float):
                raise ExpressionError("Only numeric literals are allowed")
            try:
                if not np.isfinite(float(node.value)):
                    raise OverflowError
            except OverflowError:
                raise ExpressionError("Numeric literal is out of range") from None
        elif isinstance(node, ast.operator | ast.unaryop | ast.expr_context):
            continue
        else:
            raise ExpressionError(f"Construct {type(node).__name__} is not allowed")

    if nodes > MAX_NODES:
        raise ExpressionError(f"Expression too large ({nodes} nodes, max {MAX_NODES})")

    return ParsedExpression(
        source=text,
        tree=tree,
        variables=tuple(used_vars),
        parameters=tuple(used_params),
        complexity=_complexity(tree.body),
    )


def names_outside_call(expr: ParsedExpression, names: Iterable[str], func: str) -> set[str]:
    """Which of ``names`` occur other than as the first argument of ``func(...)``."""
    wanted = set(names)
    allowed: set[int] = set()
    for node in ast.walk(expr.tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == func
            and node.args
            and isinstance(node.args[0], ast.Name)
        ):
            allowed.add(id(node.args[0]))
    return {
        node.id
        for node in ast.walk(expr.tree)
        if isinstance(node, ast.Name) and node.id in wanted and id(node) not in allowed
    }


def operators_used(expr: ParsedExpression) -> tuple[set[str], set[str]]:
    """(function names, binary operator symbols) used by an expression."""
    symbols = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "^"}
    funcs, binops = set(), set()
    for node in ast.walk(expr.tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            funcs.add(node.func.id)
        elif isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Pow) and isinstance(node.right, ast.Constant):
                if node.right.value == 2:
                    funcs.add("square")
                    continue
                if node.right.value == 3:
                    funcs.add("cube")
                    continue
            binops.add(symbols[type(node.op)])
    return funcs, binops


def _complexity(node: ast.AST) -> int:
    """Node count in the PySR sense: every operator, function, symbol and literal is 1."""
    if isinstance(node, ast.BinOp):
        return 1 + _complexity(node.left) + _complexity(node.right)
    if isinstance(node, ast.UnaryOp):
        # A negative literal counts as a single constant.
        if isinstance(node.operand, ast.Constant):
            return 1
        return 1 + _complexity(node.operand)
    if isinstance(node, ast.Call):
        return 1 + sum(_complexity(a) for a in node.args)
    return 1


def _eval(node: ast.AST, data: dict[str, np.ndarray], params: dict[str, float]):
    if isinstance(node, ast.BinOp):
        return _BIN_OPS[type(node.op)](
            _eval(node.left, data, params), _eval(node.right, data, params)
        )
    if isinstance(node, ast.UnaryOp):
        val = _eval(node.operand, data, params)
        return -val if isinstance(node.op, ast.USub) else val
    if isinstance(node, ast.Call):
        func = _FUNCTIONS[node.func.id][1]
        return func(*(_eval(a, data, params) for a in node.args))
    if isinstance(node, ast.Name):
        if node.id in data:
            return data[node.id]
        if node.id in params:
            return params[node.id]
        return _CONSTANTS[node.id]
    if isinstance(node, ast.Constant):
        return float(node.value)
    raise ExpressionError(f"Cannot evaluate {type(node).__name__}")


_NUMBER_RE = re.compile(r"(?<![A-Za-z_0-9.])(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?")


def parameterize_constants(
    source: str,
    taken: Iterable[str] = (),
    keep_small_integers: bool = True,
) -> tuple[str, dict[str, float]]:
    """
    Replace numeric literals in an expression with named parameters.

    Used to refit a PySR equation's constants on cross-validation folds so it is
    scored the same way as classic models. Small integers (|n| <= 3), typically
    exponents like ``x^2``, stay fixed when ``keep_small_integers`` is set.

    Args:
        source: Expression text
        taken: Names already in use (data variables) that parameters must avoid

    Returns:
        (expression with ``k0, k1, ...``, initial values)
    """
    taken_set = set(taken)
    prefix = "k"
    while any(name.startswith(prefix) for name in taken_set):
        prefix += "k"
    values: dict[str, float] = {}

    def repl(match: re.Match) -> str:
        literal = match.group(0)
        value = float(literal)
        if keep_small_integers and value.is_integer() and abs(value) <= 3:
            return literal
        name = f"{prefix}{len(values)}"
        values[name] = value
        return name

    return _NUMBER_RE.sub(repl, _normalize(source)), values


def substitute_parameters(source: str, params: dict[str, float], sig: int = 4) -> str:
    """Render an expression with fitted parameter values substituted in."""
    text = _normalize(source)
    for name in sorted(params, key=len, reverse=True):
        value = params[name]
        rendered = f"{value:.{sig}g}"
        if value < 0:
            rendered = f"({rendered})"
        text = re.sub(rf"(?<![A-Za-z_0-9]){re.escape(name)}(?![A-Za-z_0-9])", rendered, text)
    return text.replace("**", "^")


# Identifiers an alias must never take: functions, constants, Python keywords, and the
# parameter-like names used by family templates and PySR re-parameterisation
# (a, b, c, d, k with optional digits). Session adds the exact family parameters.
_PARAM_LIKE = re.compile(r"[abcdk]\d*")
BASE_RESERVED = (
    set(_FUNCTIONS)
    | set(_CONSTANTS)
    | set(keyword.kwlist)
    | set(getattr(keyword, "softkwlist", []))
    | {"None", "True", "False"}
)


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")


def alias_base(name: str, keep_qualifiers: bool = False) -> str:
    """
    Identifier stem for a column name. Units in [...] are dropped; text in (...) is
    dropped unless ``keep_qualifiers`` (used when two columns would otherwise clash,
    e.g. 'pH (KCl)' vs 'pH (H2O)' -> pH_KCl / pH_H2O).
    """
    text = re.sub(r"\[[^\]]*\]", "", _ascii(name))
    if not keep_qualifiers:
        text = re.sub(r"\([^)]*\)", "", text)
    alias = re.sub(r"[^0-9A-Za-z_]+", "_", text).strip("_")
    return re.sub(r"_+", "_", alias)


def make_alias(
    name: str,
    taken: set[str],
    reserved: Iterable[str] = (),
    keep_qualifiers: bool = False,
) -> str:
    """Turn an arbitrary column name into a short identifier usable in expressions."""
    alias = alias_base(name, keep_qualifiers)
    if not alias or alias[0].isdigit():
        alias = f"x_{alias}" if alias else "x"
    reserved_set = BASE_RESERVED | set(reserved)
    if alias in reserved_set or alias.startswith("_") or _PARAM_LIKE.fullmatch(alias):
        alias = f"{alias}_"
    base, i = alias, 2
    while alias in taken:
        alias = f"{base}_{i}"
        i += 1
    return alias
