"""Decorator to declare tunable function parameters and auto-inject config.

Wraps functions, registers a Pydantic model per namespace, and injects values
from the active AppConfig at call time. Supports dotted namespaces.
"""

from __future__ import annotations

import functools
import inspect
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import create_model

from .context import _active_cfg
from .registry import REGISTRY
from .registry import TunableEntry

if TYPE_CHECKING:
    from collections.abc import Iterable


def tunable(
    *include: str,
    namespace: str = "main",
    mode: Literal["include", "exclude"] = "include",
    exclude: Iterable[str] | None = None,
    apps: str | Iterable[str] = (),
):
    """Mark a function's selected parameters as user-tunable.

    - include: names to include. If empty, include all params that have defaults
      (unless mode='exclude' with an explicit exclude list).
    - namespace: JSON section name; defaults to "main".
    - apps: optional tags to group functions per executable/app.
    """
    include_set = set(include or ())
    exclude_set = set(exclude or ())
    apps = (apps,) if isinstance(apps, str) else apps

    def decorator(fn):
        sig = inspect.signature(fn)
        raw_anns = inspect.get_annotations(fn, eval_str=False)

        def _eval_ann(value: Any) -> Any:
            if isinstance(value, str):  # deferred annotation (from __future__ import annotations)
                try:
                    return eval(value, fn.__globals__, {})  # noqa: S307 - controlled eval
                except (NameError, AttributeError, SyntaxError):  # pragma: no cover - fallback path
                    return Any
            return value

        fields: dict[str, tuple[type[Any], Any]] = {}
        for name, p in sig.parameters.items():
            if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                continue
            if include_set:
                selected = name in include_set
            elif mode == "exclude" and exclude_set:
                selected = (p.default is not inspect._empty) and (name not in exclude_set)
            else:
                selected = p.default is not inspect._empty
            if not selected:
                continue
            ann = _eval_ann(raw_anns.get(name, Any))
            default = p.default if p.default is not inspect._empty else ...
            fields[name] = (ann, default)

        model_name = f"{namespace.title().replace('.', '').replace('_', '')}Config"
        model_type = create_model(model_name, **fields)  # type: ignore[assignment]

        REGISTRY.register(TunableEntry(fn=fn, model=model_type, sig=sig, namespace=namespace, apps=set(apps)))

        def _resolve_nested_section(cfg_model: BaseModel, dotted_ns: str):
            obj: Any = cfg_model
            for seg in dotted_ns.split("."):
                if obj is None or not hasattr(obj, seg):
                    return None
                obj = getattr(obj, seg)
            return obj

        @functools.wraps(fn)
        def wrapper(*args, cfg: BaseModel | dict | None = None, **kwargs):
            if cfg is not None:
                data = cfg if isinstance(cfg, dict) else cfg.model_dump()
                filtered = {k: v for k, v in data.items() if k in sig.parameters}
                return fn(*args, **filtered, **kwargs)

            app_cfg = _active_cfg.get()
            if app_cfg is not None:
                section = _resolve_nested_section(app_cfg, namespace)
                if section is not None:
                    data = section if isinstance(section, dict) else section.model_dump()
                    filtered = {k: v for k, v in data.items() if k in sig.parameters}
                    return fn(*args, **filtered, **kwargs)

            return fn(*args, **kwargs)

        return wrapper

    return decorator
