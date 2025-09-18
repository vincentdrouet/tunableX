"""Decorator to declare tunable function parameters and auto-inject config.

Wraps functions, registers a Pydantic model per namespace, and injects values
from the active AppConfig at call time. Supports dotted namespaces.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Iterable
from typing import Any, Literal, get_type_hints

from pydantic import BaseModel, create_model

from .context import _active_cfg, _active_trace
from .registry import REGISTRY, TunableEntry


def tunable(
    *include: str,
    namespace: str | None = None,
    mode: Literal["include", "exclude"] = "include",
    exclude: Iterable[str] | None = None,
    apps: Iterable[str] = (),
):
    """Mark a function's selected parameters as user-tunable.

    - include: names to include. If empty, include all params that have defaults
      (unless mode='exclude' with an explicit exclude list).
    - namespace: JSON section name; defaults to 'module.function'.
    - apps: optional tags to group functions per executable/app.
    """
    include_set = set(include) if include else None
    exclude_set = set(exclude or ())

    def decorator(fn):
        sig = inspect.signature(fn)
        hints = get_type_hints(fn)
        fields: dict[str, tuple[type[Any], Any]] = {}
        for name, p in sig.parameters.items():
            if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                continue
            if include_set is not None:
                selected = name in include_set
            elif mode == "exclude" and exclude_set:
                selected = (p.default is not inspect._empty) and (name not in exclude_set)
            else:
                selected = (p.default is not inspect._empty)
            if not selected:
                continue
            ann = hints.get(name, Any)
            default = p.default if p.default is not inspect._empty else ...
            fields[name] = (ann, default)

        ns = namespace or "main"  # default to 'main' if no namespace provided
        model_name = f"{ns.title().replace('.', '').replace('_', '')}Config"
        model_type: type[BaseModel] = create_model(model_name, **fields)  # type: ignore[assignment]

        REGISTRY.register(TunableEntry(fn=fn, model=model_type, sig=sig, namespace=ns, apps=set(apps)))

        def _resolve_nested_section(cfg_model: BaseModel, dotted_ns: str):
            obj: Any = cfg_model
            for seg in dotted_ns.split("."):
                if obj is None or not hasattr(obj, seg):
                    return None
                obj = getattr(obj, seg)
            return obj

        @functools.wraps(fn)
        def wrapper(*args, cfg: BaseModel | dict | None = None, **kwargs):
            tracer = _active_trace.get()
            if tracer is not None:
                tracer.namespaces.add(ns)
                if tracer.noop:
                    return None

            if cfg is not None:
                data = cfg if isinstance(cfg, dict) else cfg.model_dump()
                filtered = {k: v for k, v in data.items() if k in sig.parameters}
                return fn(*args, **filtered, **kwargs)

            app_cfg = _active_cfg.get()
            if app_cfg is not None:
                section = _resolve_nested_section(app_cfg, ns)
                if section is not None:
                    data = section if isinstance(section, dict) else section.model_dump()
                    filtered = {k: v for k, v in data.items() if k in sig.parameters}
                    return fn(*args, **filtered, **kwargs)

            return fn(*args, **kwargs)

        return wrapper

    return decorator
