from __future__ import annotations
from typing import Callable
import json
from pathlib import Path
from pydantic import ValidationError
from .io import load_structured_config
from .registry import REGISTRY
from .context import use_config, trace_tunables  # noqa: F401

def schema_for_apps(*apps: str) -> dict:
    AppConfig = REGISTRY.build_config(REGISTRY.namespaces_for_apps(apps))
    return AppConfig.model_json_schema()

def defaults_for_apps(*apps: str) -> dict:
    AppConfig = REGISTRY.build_config(REGISTRY.namespaces_for_apps(apps))
    try:
        return AppConfig().model_dump()
    except Exception:
        return {}

def schema_by_trace(run_callable: Callable, *args, **kwargs):
    with trace_tunables(noop=True) as t:
        run_callable(*args, **kwargs)
    AppConfig = REGISTRY.build_config(t.namespaces)
    try:
        defaults = AppConfig().model_dump()
    except Exception:
        defaults = {}
    return AppConfig.model_json_schema(), defaults, t.namespaces

def write_schema(prefix: str, schema: dict, defaults: dict|None=None):
    Path(f"{prefix}.schema.json").write_text(json.dumps(schema, indent=2))
    if defaults is not None:
        Path(f"{prefix}.json").write_text(json.dumps(defaults, indent=2))

def make_app_config_for(app: str):
    namespaces = REGISTRY.namespaces_for_apps([app])
    return REGISTRY.build_config(namespaces)

def load_app_config(app: str, json_path: str | Path):
    AppConfig = make_app_config_for(app)
    data = load_structured_config(json_path)
    try:
        return AppConfig.model_validate(data)
    except ValidationError as e:
        raise SystemExit(f"Invalid config for app '{app}':\n{e}") from None

# Tracing-based (no app)
def make_app_config_for_entry(entrypoint: Callable, *args, **kwargs):
    with trace_tunables(noop=True) as t:
        entrypoint(*args, **kwargs)
    return REGISTRY.build_config(t.namespaces)

def load_config_for_entry(entrypoint: Callable, json_path: str | Path, *args, **kwargs):
    AppConfig = make_app_config_for_entry(entrypoint, *args, **kwargs)
    data = load_structured_config(json_path)
    try:
        return AppConfig.model_validate(data)
    except ValidationError as e:
        raise SystemExit(f"Invalid config for traced entrypoint:\n{e}") from None
