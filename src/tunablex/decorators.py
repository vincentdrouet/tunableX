from __future__ import annotations

import functools
import inspect
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import get_type_hints

from pydantic import BaseModel
from pydantic import create_model

from .context import _active_cfg
from .context import _active_trace
from .naming import ns_to_field
from .registry import REGISTRY
from .registry import TunableEntry

if TYPE_CHECKING:
    from collections.abc import Iterable


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
    include_set = set(include or ())
    exclude_set = set(exclude or ())

    def decorator(fn):
        sig = inspect.signature(fn)
        hints = get_type_hints(fn)
        fields = {}
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
            ann = hints.get(name, Any)
            default = p.default if p.default is not inspect._empty else ...
            fields[name] = (ann, default)

        ns = namespace or "main"  # default to 'main' if no namespace provided
        model_name = f"{ns.title().replace('.', '').replace('_', '')}Config"
        Model = create_model(model_name, **fields)  # type: ignore

        REGISTRY.register(TunableEntry(fn=fn, model=Model, sig=sig, namespace=ns, apps=set(apps)))

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
                section_attr = ns_to_field(ns)
                if hasattr(app_cfg, section_attr):
                    section = getattr(app_cfg, section_attr)
                    if section is not None:
                        data = section if isinstance(section, dict) else section.model_dump()
                        filtered = {k: v for k, v in data.items() if k in sig.parameters and k not in kwargs}
                        return fn(*args, **filtered, **kwargs)

            return fn(*args, **kwargs)

        return wrapper

    return decorator
