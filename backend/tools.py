"""Built-in tools: web search, Python sandbox, RAG, image generation."""
import ast
import operator
import os

import search
import store

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the live web. Use for current events, facts, and citations.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Evaluate a safe Python subset using bounded arithmetic, assignments, loops, and print. Imports, files, network, and attributes are not available.",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": "Search documents previously uploaded to Axiom.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Describe an image to generate. Returns a URL if a generator is configured.",
            "parameters": {
                "type": "object",
                "properties": {"prompt": {"type": "string"}},
                "required": ["prompt"],
            },
        },
    },
]


async def run_python(code: str) -> str:
    code = (code or "").strip()
    if not code or len(code) > 8000:
        return "Python tool: empty or too long."
    try:
        tree = ast.parse(code, mode="exec")
        if sum(1 for _ in ast.walk(tree)) > 500:
            raise ValueError("snippet has too many operations")

        environment = {}
        output = []
        budget = [10_000]
        builtins = {
            "abs": abs, "bool": bool, "float": float, "int": int, "len": len,
            "max": max, "min": min, "round": round, "sorted": sorted, "str": str,
            "sum": sum, "tuple": tuple, "list": list,
        }

        def checked(value):
            if isinstance(value, (str, list, tuple, dict, set, range)) and len(value) > 10_000:
                raise ValueError("result exceeds the 10,000-item limit")
            if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 10**18:
                raise ValueError("integer result is too large")
            return value

        def evaluate(node):
            if isinstance(node, ast.Constant):
                if not isinstance(node.value, (str, int, float, bool, type(None))):
                    raise ValueError("unsupported literal")
                return checked(node.value)
            if isinstance(node, ast.Name):
                if node.id in environment:
                    return environment[node.id]
                if node.id in builtins:
                    return builtins[node.id]
                raise ValueError(f"unknown name: {node.id}")
            if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
                values = [evaluate(item) for item in node.elts]
                return checked(values if isinstance(node, ast.List) else tuple(values) if isinstance(node, ast.Tuple) else set(values))
            if isinstance(node, ast.Dict):
                return checked({evaluate(k): evaluate(v) for k, v in zip(node.keys, node.values)})
            if isinstance(node, ast.BinOp):
                left, right = evaluate(node.left), evaluate(node.right)
                ops = {
                    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
                    ast.Mod: operator.mod, ast.Pow: operator.pow,
                }
                fn = ops.get(type(node.op))
                if fn is None:
                    raise ValueError("unsupported operator")
                if isinstance(node.op, ast.Pow) and (not isinstance(right, (int, float)) or abs(right) > 12):
                    raise ValueError("exponent is outside the allowed range")
                if isinstance(node.op, ast.Mult) and isinstance(left, (str, list, tuple)) and isinstance(right, int):
                    if len(left) * max(right, 0) > 10_000:
                        raise ValueError("result exceeds the 10,000-item limit")
                return checked(fn(left, right))
            if isinstance(node, ast.UnaryOp):
                ops = {ast.UAdd: operator.pos, ast.USub: operator.neg, ast.Not: operator.not_}
                fn = ops.get(type(node.op))
                if fn is None:
                    raise ValueError("unsupported unary operator")
                return checked(fn(evaluate(node.operand)))
            if isinstance(node, ast.BoolOp):
                values = [evaluate(item) for item in node.values]
                return all(values) if isinstance(node.op, ast.And) else any(values)
            if isinstance(node, ast.Compare):
                left = evaluate(node.left)
                ops = {
                    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
                    ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
                    ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
                }
                for op, comparator in zip(node.ops, node.comparators):
                    fn = ops.get(type(op))
                    right = evaluate(comparator)
                    if fn is None or not fn(left, right):
                        return False
                    left = right
                return True
            if isinstance(node, ast.IfExp):
                return evaluate(node.body if evaluate(node.test) else node.orelse)
            if isinstance(node, ast.Subscript):
                return checked(evaluate(node.value)[evaluate(node.slice)])
            if isinstance(node, ast.Slice):
                return slice(
                    evaluate(node.lower) if node.lower else None,
                    evaluate(node.upper) if node.upper else None,
                    evaluate(node.step) if node.step else None,
                )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                name = node.func.id
                args = [evaluate(arg) for arg in node.args]
                if node.keywords:
                    raise ValueError("keyword arguments are not supported")
                if name == "range":
                    values = range(*args)
                    return checked(values)
                if name == "print":
                    output.append(" ".join(str(arg) for arg in args))
                    return None
                fn = builtins.get(name)
                if fn is None:
                    raise ValueError(f"function is not allowed: {name}")
                return checked(fn(*args))
            raise ValueError(f"unsupported syntax: {type(node).__name__}")

        def execute(statements):
            last = None
            for statement in statements:
                budget[0] -= 1
                if budget[0] < 0:
                    raise ValueError("execution exceeded the operation limit")
                if isinstance(statement, ast.Expr):
                    last = evaluate(statement.value)
                elif isinstance(statement, ast.Assign):
                    if len(statement.targets) != 1:
                        raise ValueError("only simple variable assignments are supported")
                    target = statement.targets[0]
                    if not isinstance(target, ast.Name):
                        raise ValueError("only simple variable assignments are supported")
                    environment[target.id] = evaluate(statement.value)
                    last = None
                elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name) and statement.value:
                    environment[statement.target.id] = evaluate(statement.value)
                    last = None
                elif isinstance(statement, ast.AugAssign) and isinstance(statement.target, ast.Name):
                    environment[statement.target.id] = evaluate(
                        ast.BinOp(
                            left=ast.Constant(environment[statement.target.id]),
                            op=statement.op,
                            right=statement.value,
                        )
                    )
                    last = None
                elif isinstance(statement, ast.If):
                    last = execute(statement.body if evaluate(statement.test) else statement.orelse)
                elif isinstance(statement, ast.For) and isinstance(statement.target, ast.Name):
                    values = evaluate(statement.iter)
                    if not isinstance(values, (range, list, tuple, str)) or len(values) > 10_000:
                        raise ValueError("loops require a bounded range or sequence")
                    for value in values:
                        budget[0] -= 1
                        if budget[0] < 0:
                            raise ValueError("execution exceeded the operation limit")
                        environment[statement.target.id] = value
                        last = execute(statement.body)
                else:
                    raise ValueError(f"unsupported statement: {type(statement).__name__}")
            return last

        last = execute(tree.body)
        result = "\n".join(output) if output else repr(last)
        return (result.strip() or "(no output)")[:8000]
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError, KeyError, IndexError, RecursionError) as exc:
        return f"Python tool error: {exc}"


async def generate_image(prompt: str) -> str:
    import json

    import providers

    prompt = (prompt or "").strip()[:1000]
    if not prompt:
        return "Image prompt was empty."
    model = os.getenv("IMAGE_MODEL", "black-forest-labs/flux.2-schnell:free")
    cfg = providers.PROVIDERS.get("openrouter")
    if not cfg or not cfg["keys"]:
        return "Image generation needs an OpenRouter key."
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": f"Generate an image: {prompt}"}],
    }
    try:
        r = await providers.get_client().post(
            cfg["url"],
            json=payload,
            headers={"Authorization": f"Bearer {cfg['keys'][0]}", "Content-Type": "application/json"},
            timeout=60,
        )
        data = r.json()
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or json.dumps(data)[:500]
        return str(content)[:4000]
    except Exception as e:
        return f"Image generation failed: {type(e).__name__}"


async def execute(name: str, arguments: dict, mcp_url: str = "", owner_id: str = "") -> str:
    args = arguments or {}
    if name == "web_search":
        hits = await search.web_search(str(args.get("query") or ""))
        if not hits:
            return "No search results."
        return "\n".join(f"- {h['title']}\n  {h['url']}\n  {h['snippet']}" for h in hits)
    if name == "run_python":
        return await run_python(str(args.get("code") or ""))
    if name == "rag_search":
        hits = store.rag_search(owner_id, str(args.get("query") or ""))
        if not hits:
            return "No matching uploaded documents."
        return "\n\n".join(f"{h['name']}\n{h.get('text') or h.get('snippet')}" for h in hits)
    if name == "generate_image":
        return await generate_image(str(args.get("prompt") or ""))
    if mcp_url and name.startswith("mcp_"):
        import mcp_client

        return await mcp_client.call_tool(mcp_url, name[4:], args)
    if mcp_url:
        import mcp_client

        return await mcp_client.call_tool(mcp_url, name, args)
    return f"Unknown tool: {name}"


async def schemas(mcp_url: str = "") -> list[dict]:
    out = list(TOOL_SCHEMAS)
    if mcp_url:
        import mcp_client

        for t in await mcp_client.list_tools(mcp_url):
            name = t.get("name")
            if not name:
                continue
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": t.get("description") or name,
                        "parameters": t.get("inputSchema") or {"type": "object", "properties": {}},
                    },
                }
            )
    return out
