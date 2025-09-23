from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Callable

from pydantic import BaseModel
from pydantic import ValidationError

from .context import use_config  # noqa: F401
from .io import load_structured_config
from .registry import REGISTRY

if TYPE_CHECKING:  # pragma: no cover
    pass


def schema_for_apps(*apps: str) -> dict:
    AppConfig = REGISTRY.build_config(REGISTRY.namespaces_for_apps(apps))
    return AppConfig.model_json_schema()


def defaults_for_apps(*apps: str) -> dict:
    AppConfig = REGISTRY.build_config(REGISTRY.namespaces_for_apps(apps))
    try:
        # JSON mode ensures Path, enums, etc. are converted to JSON-friendly forms
        return AppConfig().model_dump(mode="json")
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# AST-based namespace discovery
# ---------------------------------------------------------------------------


def _gather_called_function_names(entry_fn: Callable) -> set[str]:
    """Return set of fully qualified function names that are reachable from entry_fn's module.

    This performs a simple static AST walk starting from the entry function's
    body and collects names of function calls. It does not follow dynamic
    dispatch or conditional imports. The goal is only to approximate which
    @tunable-decorated functions may be used so we can compose an AppConfig
    without executing user code.
    """
    try:
        src = inspect.getsource(entry_fn)
    except OSError:  # source not available
        return set()

    tree = ast.parse(src)
    called: set[str] = set()

    class CallVisitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call):  # noqa: N802
            # function name patterns: foo(), module.foo(), obj.method()
            name_parts: list[str] = []
            cur = node.func
            while isinstance(cur, ast.Attribute):
                name_parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                name_parts.append(cur.id)
            fq = ".".join(reversed(name_parts))
            if fq:
                called.add(fq)
            self.generic_visit(node)

    CallVisitor().visit(tree)
    return called


def _namespaces_for_entry(entrypoint: Callable) -> list[str]:
    # Identify tunable namespaces whose original function qualified name matches
    # any of the called function names discovered statically.
    called = _gather_called_function_names(entrypoint)
    namespaces: list[str] = []
    for ns, entry in REGISTRY.by_namespace.items():
        fn = entry.fn
        qn = f"{fn.__module__}.{fn.__name__}"
        short = fn.__name__
        if short in called or qn in called:
            namespaces.append(ns)
    return namespaces


def schema_by_entry_ast(entrypoint: Callable):
    namespaces = _namespaces_for_entry(entrypoint)
    AppConfig = REGISTRY.build_config(namespaces)
    try:
        defaults = AppConfig().model_dump(mode="json")
    except Exception:
        defaults = {}
    return AppConfig.model_json_schema(), defaults, namespaces


def write_schema(prefix: str, schema: dict, defaults: dict | None = None):
    Path(f"{prefix}.schema.json").write_text(json.dumps(schema, indent=2, default=str))
    if defaults is not None:
        Path(f"{prefix}.json").write_text(json.dumps(defaults, indent=2, default=str))


def make_app_config_for(app: str) -> BaseModel:
    namespaces = REGISTRY.namespaces_for_apps([app])
    return REGISTRY.build_config(namespaces)


def load_app_config(app: str, json_path: str | Path):
    AppConfig = make_app_config_for(app)
    data = load_structured_config(json_path)
    try:
        return AppConfig.model_validate(data)
    except ValidationError as e:
        msg = f"Invalid config for app '{app}':\n{e}".rstrip()
        raise SystemExit(msg) from None


# AST-based (no app)


def make_app_config_for_entry(entrypoint: Callable, *args, **_kwargs):  # args unused for static
    namespaces = _namespaces_for_entry(entrypoint)
    return REGISTRY.build_config(namespaces)


def load_config_for_entry(entrypoint: Callable, json_path: str | Path, *args, **_kwargs):
    AppConfig = make_app_config_for_entry(entrypoint, *args)
    data = load_structured_config(json_path)
    try:
        return AppConfig.model_validate(data)
    except ValidationError as e:
        msg = f"Invalid config for entrypoint (AST):\n{e}".rstrip()
        raise SystemExit(msg) from None
