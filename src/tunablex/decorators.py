"""Decorator to declare tunable function parameters and auto-inject config.

Wraps functions, registers a Pydantic model per namespace, and injects values
from the active AppConfig at call time. Supports dotted namespaces.
"""

from __future__ import annotations

import functools
import inspect
import re
from typing import TYPE_CHECKING
from typing import Any

from pydantic.fields import FieldInfo

from .context import _active_cfg
from .registry import REGISTRY
from .registry import TunableEntry

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pydantic import BaseModel


def _pascalcase_to_snake_case(ns: str) -> str:
    """Convert a namespace name from PascalCase to snake_case."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", ns).lower()


class TunableParamMeta(type):
    """A metaclass that allows to retrieve namespace and type annotation at runtime."""

    def _namespace(cls) -> str:
        parent = cls.mro()[1]
        if parent is object:
            return ""
        ns = _pascalcase_to_snake_case(super().__getattribute__("__name__"))
        if parent._namespace():
            return f"{parent._namespace()}.{ns}"
        return ns

    def __getattribute__(cls, name: str):
        if name.startswith("__"):
            return super().__getattribute__(name)
        try:
            annotations = super().__annotations__
            typ = annotations[name]
            return super().__getattribute__(name), typ, TunableParamMeta._namespace(cls)
        except Exception:  # noqa: BLE001
            return super().__getattribute__(name)


def _resolve_nested_section(cfg_model: BaseModel, dotted_ns: str):
    if not dotted_ns:  # main namespace
        return cfg_model
    obj = cfg_model
    for seg in dotted_ns.split("."):
        if obj is None or not hasattr(obj, seg):
            return None
        obj = getattr(obj, seg)
    return obj


def tunable(
    *include: str,
    namespace: str = "",
    exclude: str | Iterable[str] = (),
    apps: str | Iterable[str] = (),
):
    """Mark a function's selected parameters as user-tunable.

    - include: names to include. If empty, include all params that have defaults
      (unless mode='exclude' with an explicit exclude list).
    - namespace: JSON section name; defaults to an empty namespace.
    - apps: optional tags to group functions per executable/app.
    """
    include_set = set(include or ())
    exclude_set = {exclude} if isinstance(exclude, str) else set(exclude)
    if include_set and exclude_set:
        msg = "Cannot pass both `include` and `exclude` arguments."
        raise ValueError(msg)
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

        ns = namespace
        namespaces = {}
        for name, p in sig.parameters.items():
            if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                continue
            if include_set:
                selected = name in include_set
            elif exclude_set:
                selected = (p.default is not inspect._empty) and (name not in exclude_set)
            else:
                selected = p.default is not inspect._empty
            if not selected:
                continue
            typ_str = raw_anns.get(name, Any)
            default = p.default if p.default is not inspect._empty else ...
            if isinstance(default, tuple) and isinstance(default[0], FieldInfo):
                # The default value is a pydantic Field; retrieve type and namespace
                default, typ_str, ns = default
            typ = _eval_ann(typ_str)
            ns_dict = namespaces.setdefault(ns, {})
            ns_dict.update({name: (typ, default)})

        for ns, fields in namespaces.items():
            REGISTRY.register(TunableEntry(fn=fn, fields=fields, sig=sig, namespace=ns, apps=set(apps)))

        @functools.wraps(fn)
        def wrapper(*args, cfg: BaseModel | dict | None = None, **kwargs):
            if cfg is not None:
                data = cfg if isinstance(cfg, dict) else cfg.model_dump()
                filtered = {k: v for k, v in data.items() if k in sig.parameters}
                return fn(*args, **filtered, **kwargs)

            app_cfg = _active_cfg.get()
            if app_cfg is not None:
                filtered = {}
                for ns in namespaces:
                    section = _resolve_nested_section(app_cfg, ns)
                    if section is not None:
                        data = section if isinstance(section, dict) else section.model_dump()
                        filtered.update({k: v for k, v in data.items() if k in sig.parameters and k not in kwargs})
                return fn(*args, **filtered, **kwargs)

            return fn(*args, **kwargs)

        return wrapper

    return decorator
