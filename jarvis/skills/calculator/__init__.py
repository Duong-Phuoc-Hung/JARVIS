"""
JARVIS Built-in Skill: Calculator & Currency Converter
Safely evaluates arithmetic expressions, percentages, and handles currency conversions.
"""
from __future__ import annotations

import ast
import math
import operator
import re
from typing import Any, Callable, Dict, Optional

EXCHANGE_RATES_TO_USD = {
    "USD": 1.0,
    "VND": 0.000039,  # ~25,600 VND per USD
    "EUR": 1.08,
    "GBP": 1.28,
    "JPY": 0.0065,   # ~154 JPY per USD
    "CAD": 0.73,
    "AUD": 0.65,
    "SGD": 0.75,
}

_SAFE_OPERATORS: Dict[type, Callable[..., Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_SAFE_FUNCTIONS: Dict[str, Callable[..., Any]] = {
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "ceil": math.ceil,
    "floor": math.floor,
}

_SAFE_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
}


def _safe_eval(node: ast.AST) -> float:
    """Recursively evaluate an AST node safely without using raw eval()."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError(f"Unsupported constant type: {type(node.value)}")
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Operator {op_type.__name__} is not supported.")
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        return _SAFE_OPERATORS[op_type](left, right)
    elif isinstance(node, ast.UnaryOp):
        unary_op_type = type(node.op)
        if unary_op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Unary operator {unary_op_type.__name__} is not supported.")
        operand = _safe_eval(node.operand)
        return _SAFE_OPERATORS[unary_op_type](operand)
    elif isinstance(node, ast.Name):
        name_lower = node.id.lower()
        if name_lower in _SAFE_CONSTANTS:
            return _SAFE_CONSTANTS[name_lower]
        raise ValueError(f"Variable '{node.id}' is not defined.")
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            func_name = node.func.id.lower()
            if func_name in _SAFE_FUNCTIONS:
                args = [_safe_eval(arg) for arg in node.args]
                return float(_SAFE_FUNCTIONS[func_name](*args))
        raise ValueError("Function call is not supported.")
    else:
        raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def evaluate_expression(expr: str) -> float:
    """Clean and evaluate a mathematical expression."""
    cleaned = expr.replace("^", "**").replace("x", "*").replace("X", "*")
    cleaned = cleaned.replace("×", "*").replace("÷", "/")
    cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*%', r'(\1/100)', cleaned)

    tree = ast.parse(cleaned, mode="eval")
    return _safe_eval(tree)


def execute(
    expression: str = "",
    action: str = "eval",
    amount: float = 1.0,
    currency_from: str = "USD",
    currency_to: str = "VND",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Execute mathematical calculation or currency conversion.
    """
    act = action.lower().strip()

    if act == "convert_currency" or (currency_from and currency_to and currency_from.upper() != currency_to.upper() and not expression):
        c_from = currency_from.upper().strip()
        c_to = currency_to.upper().strip()

        rate_from = EXCHANGE_RATES_TO_USD.get(c_from)
        rate_to = EXCHANGE_RATES_TO_USD.get(c_to)

        if not rate_from or not rate_to:
            msg = f"Không hỗ trợ mã tiền tệ '{c_from}' hoặc '{c_to}'. Hỗ trợ: {', '.join(EXCHANGE_RATES_TO_USD.keys())}"
            return {"data": {"text": msg, "success": False}, "output": msg}

        val_usd = amount * rate_from
        converted = val_usd / rate_to

        if c_to == "VND":
            formatted_converted = f"{converted:,.0f} VND"
        else:
            formatted_converted = f"{converted:,.2f} {c_to}"

        if c_from == "VND":
            formatted_amount = f"{amount:,.0f} VND"
        else:
            formatted_amount = f"{amount:,.2f} {c_from}"

        msg = f"💱 {formatted_amount} = {formatted_converted} (tỷ giá ước tính)."
        return {
            "data": {
                "text": msg,
                "from_currency": c_from,
                "to_currency": c_to,
                "original_amount": amount,
                "converted_amount": converted,
                "success": True,
            },
            "output": msg,
        }

    else:
        if not expression.strip():
            msg = "Vui lòng cung cấp biểu thức toán học cần tính."
            return {"data": {"text": msg, "success": False}, "output": msg}

        try:
            result = evaluate_expression(expression)
            if result.is_integer():
                formatted_res = f"{int(result):,}"
            else:
                formatted_res = f"{result:,.4f}".rstrip("0").rstrip(".")

            msg = f"🔢 Kết quả của `{expression}` là: **{formatted_res}**"
            return {
                "data": {
                    "text": msg,
                    "expression": expression,
                    "result": result,
                    "formatted_result": formatted_res,
                    "success": True,
                },
                "output": msg,
            }
        except Exception as exc:
            msg = f"Không thể tính toán biểu thức '{expression}': {exc}"
            return {"data": {"text": msg, "error": str(exc), "success": False}, "output": msg}
