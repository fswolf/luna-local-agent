"""Arithmetic and unit conversions she can trust.

A language model doesn't calculate, it predicts digits that look right:
close on long numbers, confidently wrong in the last places, and worse
over several steps. This works it out instead, the same rule as
time_until: never calculate, always ask.

    (187.40 * 1.15) / 4     18% of 340     340 + 15%     sqrt(2) * pi
    160 F to C              5 miles in km  3.5 GB to MiB

The math is parsed, never eval'd: numbers, + - * / // % **, brackets
and the functions in _FUNCS, nothing else. Units go through pint when
it's installed (installer/requirements.txt); without it the math still
works and a conversion says so instead of guessing.
"""
import ast
import math
import operator
import re

from . import tool

MAX_CHARS = 200
MAX_DIGITS = 400        # a result bigger than this is refused, not computed


def _pow(base, exp):
    # 9**9**9 would take the process with it: estimate the size first.
    if abs(base) > 1 and abs(exp) * math.log10(abs(base)) > MAX_DIGITS:
        raise ValueError("that number is too big to work out")
    return operator.pow(base, exp)


def _factorial(n):
    if n != int(n) or not 0 <= n <= 200:
        raise ValueError("factorial takes a whole number from 0 to 200")
    return math.factorial(int(n))


_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
        ast.Pow: _pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"sqrt": math.sqrt, "abs": abs, "round": round, "min": min, "max": max,
          "sum": lambda *a: sum(a), "avg": lambda *a: sum(a) / len(a),
          "log": math.log, "log10": math.log10, "log2": math.log2, "exp": math.exp,
          "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin,
          "acos": math.acos, "atan": math.atan, "radians": math.radians, "degrees": math.degrees,
          "ceil": math.ceil, "floor": math.floor, "hypot": math.hypot, "factorial": _factorial}
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        result = _BIN[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(result, int) and len(str(abs(result))) > MAX_DIGITS:
            raise ValueError("that number is too big to work out")
        return result
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS
            and not node.keywords):
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError("only numbers, + - * / % **, brackets and the usual math functions work here")


_NUM = r"\d+(?:\.\d+)?"


def _tidy(text):
    """Spoken math into Python math: x and ÷, ^, thousands commas, and
    percentages the way people say them."""
    t = re.sub(r"^(?:what(?:'s| is)|calculate|work out)\s+", "", text.strip(), flags=re.IGNORECASE)
    t = t.rstrip("=?").strip()
    t = t.replace("×", "*").replace("÷", "/").replace("−", "-").replace("^", "**")
    t = re.sub(r"(?<=\d)\s*[xX]\s*(?=[\d(.])", "*", t)               # 3 x 4
    if not re.search(r"[a-z_]\w*\s*\(", t):                            # no f(a, b): commas are thousands
        t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)
    t = re.sub(rf"({_NUM})\s*%\s*of\s+", r"(\1/100)*", t)              # 18% of 340
    m = re.fullmatch(rf"(.+?)\s*([+-])\s*({_NUM})\s*%", t)            # 340 + 15%
    if m:
        t = f"({m[1]})*(1{m[2]}{m[3]}/100)"
    return re.sub(rf"({_NUM})\s*%", r"(\1/100)", t)                   # what's left: 15% = 0.15


def _fmt(x):
    if isinstance(x, float):
        x = float(f"{x:.10g}")          # ten significant figures: no float noise in the last places
    if isinstance(x, float) and x.is_integer() and abs(x) < 1e15:
        x = int(x)
    if isinstance(x, int):
        return f"{x:,}" if abs(x) >= 10000 else str(x)
    if x != 0 and not 1e-6 <= abs(x) < 1e15:
        return f"{x:.6g}"
    out = f"{x:,.6f}" if abs(x) >= 10000 else f"{x:.6f}"
    return out.rstrip("0").rstrip(".")


def math_answer(expression):
    tidy = _tidy(expression)
    value = _eval(ast.parse(tidy, mode="eval"))
    return f"{expression.strip()} = {_fmt(value)}"


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------
# An amount (it starts with a number) to a unit: "5 miles in km".
_CONVERT = re.compile(r"^([-+]?[\d.].*\S)\s+(?:to|in|into|as)\s+([A-Za-z°µ].*)$", re.IGNORECASE)
# A bare F or C means a temperature here, not farads or coulombs.
_TEMP = re.compile(r"(?<![\w°])°?\s?([FC])\b")
_ureg = []


def _units():
    if not _ureg:
        import pint
        _ureg.append(pint.UnitRegistry(autoconvert_offset_to_baseunit=True))
    return _ureg[0]


def _temps(text):
    return _TEMP.sub(lambda m: f" deg{m[1]}", text).strip()


def convert_answer(amount, target):
    try:
        ureg = _units()
    except ImportError:
        return ("Unit conversions need the pint package (pip install pint) and it isn't installed. "
                "Tell the user that rather than converting it yourself.")

    import pint

    try:
        quantity = ureg.Quantity(_temps(amount))
        result = quantity.to(_temps(target))
    except pint.DimensionalityError:
        return (f"Can't turn {amount} into {target}: they measure different things (a weight and a "
                "volume, say - that needs the ingredient's density). Say so; don't guess a number.")
    except Exception as e:      # pint's parser raises all sorts on text that isn't units
        return f"Couldn't read {amount!r} to {target!r} as units ({e}). Ask the user to say it another way."

    if not isinstance(quantity.magnitude, (int, float)):
        return f"Couldn't read {amount!r} as one amount. Ask the user to say it another way."

    return f"{amount.strip()} = {_fmt(float(result.magnitude))} {result.units:~P}"


@tool(
    "calculate",
    "Exact arithmetic and unit conversions. Use it for any sum past the trivial - money, tips, "
    "percentages, splitting a bill, long numbers, averages, unit conversions - instead of "
    "working it out yourself, and give the user the result it returns.",
    {
        "expression": {
            "type": "string",
            "description": "Plain math, like '(187.40 * 1.15) / 4', '18% of 340', '340 + 15%', "
                           "'sqrt(2) * pi', or a conversion: '160 F to C', '5 miles in km', "
                           "'3.5 GB to MiB', '60 mph to km/h'.",
        },
    },
    required=("expression",),
)
def _calculate(expression):
    text = str(expression or "").strip()

    if not text:
        return "Nothing to work out: pass the sum or conversion as expression."
    if len(text) > MAX_CHARS:
        return f"That's too long to work out in one go ({len(text)} characters). Break it into steps."

    convert = _CONVERT.match(text)

    if convert and re.search(r"[A-Za-z°µ]", convert[1]):
        return convert_answer(convert[1], convert[2])

    try:
        return math_answer(text)
    except ZeroDivisionError:
        return f"{text}: that divides by zero, so there's no answer."
    except (ValueError, TypeError, OverflowError, SyntaxError) as e:
        why = "it isn't a sum I can read" if isinstance(e, SyntaxError) else str(e)
        return f"Couldn't work out {text!r}: {why}. Ask the user, or rewrite it as plain math - don't guess."
