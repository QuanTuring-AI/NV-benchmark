"""Pure-function tools for the tool-calling test (P07).

No side effects, no network, no files. Every result is mechanically checkable,
and the same functions produce the expected answers in questions.json.
"""
import datetime

LENGTH_M = {"mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0,
            "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344}

# Synthetic parts registry. The codes are invented, so a model cannot know them without the tool.
PARTS = {
    "ZK-3107": {"name": "hex bolt M8", "stock": 418},
    "QV-2290": {"name": "ball valve 1/2 in", "stock": 73},
    "LM-8841": {"name": "linear rail 400 mm", "stock": 26},
    "TR-1175": {"name": "timing belt GT2", "stock": 1204},
    "BX-6632": {"name": "bearing 6204", "stock": 391},
    "CN-4058": {"name": "cable gland PG9", "stock": 857},
    "HP-7713": {"name": "hydraulic hose 3 m", "stock": 12},
    "SF-5520": {"name": "shaft coupling 8x10", "stock": 149},
    "RD-9064": {"name": "reed switch NO", "stock": 638},
    "PW-3381": {"name": "power relay 24 V", "stock": 57},
}


def multiply_integers(a, b):
    return {"result": a * b}


def days_between(start_date, end_date):
    s = datetime.date.fromisoformat(start_date)
    e = datetime.date.fromisoformat(end_date)
    return {"days": (e - s).days}


def convert_length(value, from_unit, to_unit):
    if from_unit not in LENGTH_M or to_unit not in LENGTH_M:
        raise ValueError(f"unsupported unit; supported: {sorted(LENGTH_M)}")
    return {"result": round(value * LENGTH_M[from_unit] / LENGTH_M[to_unit], 4), "unit": to_unit}


def lookup_part(part_code):
    if part_code not in PARTS:
        raise KeyError(f"part code not found: {part_code}")
    return {"part_code": part_code, **PARTS[part_code]}


# name -> (function, {arg: (python types, required)}, OpenAI tool schema)
REGISTRY = {
    "multiply_integers": (multiply_integers, {"a": ((int,), True), "b": ((int,), True)}, {
        "type": "function", "function": {"name": "multiply_integers", "description": "Multiply two integers exactly.",
            "parameters": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"]}}}),
    "days_between": (days_between, {"start_date": ((str,), True), "end_date": ((str,), True)}, {
        "type": "function", "function": {"name": "days_between", "description": "Number of days from start_date to end_date (ISO format YYYY-MM-DD).",
            "parameters": {"type": "object", "properties": {"start_date": {"type": "string"}, "end_date": {"type": "string"}}, "required": ["start_date", "end_date"]}}}),
    "convert_length": (convert_length, {"value": ((int, float), True), "from_unit": ((str,), True), "to_unit": ((str,), True)}, {
        "type": "function", "function": {"name": "convert_length", "description": "Convert a length between units: mm, cm, m, km, in, ft, yd, mi.",
            "parameters": {"type": "object", "properties": {"value": {"type": "number"}, "from_unit": {"type": "string"}, "to_unit": {"type": "string"}}, "required": ["value", "from_unit", "to_unit"]}}}),
    "lookup_part": (lookup_part, {"part_code": ((str,), True)}, {
        "type": "function", "function": {"name": "lookup_part", "description": "Look up a part in the parts registry by its code. Returns name and units in stock.",
            "parameters": {"type": "object", "properties": {"part_code": {"type": "string"}}, "required": ["part_code"]}}}),
}

TOOL_SCHEMAS = [v[2] for v in REGISTRY.values()]


def validate(name, args):
    """(valid, reason). No type coercion: invented or mistyped arguments are invalid."""
    if name not in REGISTRY:
        return False, f"unknown tool {name}"
    if not isinstance(args, dict):
        return False, f"arguments not an object ({type(args).__name__})"
    schema = REGISTRY[name][1]
    for k, (types, required) in schema.items():
        if k not in args:
            if required:
                return False, f"missing argument {k}"
            continue
        v = args[k]
        if isinstance(v, bool) or not isinstance(v, types):
            return False, f"{k}: expected {'/'.join(t.__name__ for t in types)}, got {type(v).__name__}"
    extra = set(args) - set(schema)
    if extra:
        return False, f"unexpected arguments {sorted(extra)}"
    return True, ""


def execute(name, args):
    """(ok, result_or_error). Executes only valid calls."""
    valid, reason = validate(name, args)
    if not valid:
        return False, {"error": reason}
    try:
        return True, REGISTRY[name][0](**args)
    except Exception as e:
        return False, {"error": f"{type(e).__name__}: {e}"}
