"""Decorator to declare tunable function parameters and auto-inject config.

Wraps functions, registers a Pydantic model per namespace, and injects values
from the active AppConfig at call time. Supports dotted namespaces.
"""

from __future__ import annotations

import builtins
import functools
import inspect
import re
import sys
import typing
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Any
from typing import get_type_hints

from pydantic.fields import FieldInfo

from .context import _active_cfg
from .registry import REGISTRY
from .registry import TunableArg

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pydantic import BaseModel


def _pascalcase_to_snake_case(ns: str) -> str:
    """Convert a namespace name from PascalCase to snake_case."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", ns).lower()


def _get_description(cls: type, name: str) -> str | None:
    """Get a parameter's description from its docstring.

    Args:
        cls: TunableParams class containing the parameter.
        name: Parameter's name

    Returns:
        Parameter's docstring, or None if it does not exist.
    """
    try:
        source = inspect.getsource(cls)
        i1 = source.index(name)
        s1 = source[i1:]
        i2 = s1.index('"""') + 3
        s2 = s1[i2:]
        i3 = s2.index('"""')
        return s2[:i3]
    except Exception:  # noqa: BLE001
        return None


@dataclass
class TunableParamData:
    """Class containing the data of a tunable parameter."""

    value: Any
    typ: type
    namespace: str
    name: str


class TunableParamsMeta(type):
    """A metaclass that allows to retrieve namespace and type annotation at runtime."""

    def __init__(cls, name, bases, attrs):  # noqa: D107
        super().__init__(name, bases, attrs)
        cls.namespace = None
        type.__setattr__(cls, "__tunable_type_hints__", {})

    @staticmethod
    def _declaring_class(cls, name: str):
        """Return the MRO class that declares ``name``'s annotation."""
        for candidate in type.__getattribute__(cls, "__mro__"):
            annotations = vars(candidate).get("__annotations__", {})
            if name in annotations:
                return candidate
        return None

    @staticmethod
    def _resolve_type(name: str, declaring_cls: type) -> type:
        """Resolve one annotation using the declaring class's namespaces."""
        annotations = inspect.get_annotations(declaring_cls, eval_str=False)
        raw_annotation = annotations[name]
        cache = type.__getattribute__(declaring_cls, "__tunable_type_hints__")
        if name in cache:
            return cache[name]

        module_name = declaring_cls.__module__
        module_globals: dict[str, Any] = {}

        # A script launched directly is imported under different names by
        # multiprocessing (for example ``__main__``, ``__mp_main__`` or
        # ``mp_main``). The class may retain one name while the runtime
        # values used by its postponed annotations are available from another
        # main-module alias. Merge all known aliases first, then overlay the
        # declaring module below so its globals remain authoritative.
        for alias in ("__main__", "__mp_main__", "mp_main"):
            alias_module = sys.modules.get(alias)
            if alias_module is not None:
                module_globals.update(vars(alias_module))

        module = sys.modules.get(module_name)
        if module is not None:
            module_globals.update(vars(module))
        globalns = dict(vars(typing))
        globalns.update(vars(builtins))
        globalns.update(module_globals)
        localns = dict(vars(declaring_cls))
        localns[declaring_cls.__name__] = declaring_cls

        # get_type_hints resolves all annotations on its target.
        # Give it a one-field proxy so an unrelated unresolved annotation cannot break access to this field.
        proxy = type(
            "_TunableAnnotationProxy",
            (),
            {"__annotations__": {name: raw_annotation}},
        )
        try:
            resolved = get_type_hints(
                proxy,
                globalns=globalns,
                localns=localns,
                include_extras=True,
            )[name]
        except NameError as exc:
            missing = exc.name or str(exc)
            msg = (
                f"Unable to resolve annotation for tunable field "
                f"'{declaring_cls.__module__}.{declaring_cls.__qualname__}.{name}' "
                f"(raw annotation: {raw_annotation!r}); missing name: {missing}. "
                "The name must be available at runtime, not only under TYPE_CHECKING."
            )
            raise NameError(msg) from exc

        cache[name] = resolved
        return resolved

    @staticmethod
    def _process_name(name: str) -> str:
        """Process a class name to turn it into a namespace."""
        name = _pascalcase_to_snake_case(name).replace("_params", "")
        if name == "main" or name == "root":
            name = ""
        return name

    def __getattribute__(cls, name: str) -> Any | tuple[Any, str, str, str]:
        """Override that returns additional informations when the attribute is a FieldInfo.

        Store the classes that are accessed and use them to build the final namespace.
        """
        value = super().__getattribute__(name)
        if not isinstance(cls, TunableParamsMeta):
            return value

        if super().__getattribute__("namespace") is None:
            cls.namespace = TunableParamsMeta._process_name(super().__getattribute__("__name__"))

        # If value is a class with this metaclass, update its parent namespace
        if isinstance(value, type) and isinstance(value, TunableParamsMeta):
            value.namespace = (
                f"{cls.namespace}.{TunableParamsMeta._process_name(name)}"
                if cls.namespace
                else TunableParamsMeta._process_name(name)  # for cases like main.advanced
            )
            return value

        if isinstance(value, FieldInfo):
            declaring_cls = TunableParamsMeta._declaring_class(cls, name)
            typ = Any if declaring_cls is None else TunableParamsMeta._resolve_type(name, declaring_cls)
            if value.description is None:
                value.description = _get_description(cls, name)
            return TunableParamData(value, typ, cls.namespace, name)

        return value


class TunableParams(metaclass=TunableParamsMeta):
    """A class containing tunable parameters.

    Inherit from this class to declare tunable parameters globally.
    If the class name contains `Params`, it will be removed from the namespace for brevity.
    If the resulting namespace is `main` or `root`, the parameters will be stored at the root level.

    When using several levels of namespaces, it is possible to declare the parameters in a class at the root level
    and to reference this class in the namespace, to avoid having too many indentations in the lower levels.

    Docstrings enclosed in triple double-quotes will be used as parameter's description
    if none is provided in the Field definition.

    Example:
        # This is root level
        class AdvancedParams(TunableParams):
            param1: ...
            param2: ...

        class GeneralParams(TunableParams):
            Advanced = AdvancedParams

    In this case, the namespace for param1 and param2 is `general.advanced`.
    """


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
    apps = {apps} if isinstance(apps, str) else set(apps)

    def decorator(fn):
        sig = inspect.signature(fn)
        namespaces = {}
        global_names = {}
        tunable_param_defaults = set()
        for name, p in sig.parameters.items():
            global_name = name
            if name == "mro":
                msg = "`mro` is a protected name, please use an other name for your tunable parameters."
                raise ValueError(msg)
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
            default = p.default if p.default is not inspect._empty else ...
            if isinstance(default, TunableParamData):
                tunable_param_defaults.add(name)
                # The parameter is declared in a TunableParam class; retrieve type, namespace and reference name
                default, typ, ns, global_name = (
                    default.value,
                    default.typ,
                    default.namespace,
                    default.name,
                )
            else:
                typ = inspect.get_annotations(fn, eval_str=False)[name]
                typ = eval(typ, fn.__globals__) if isinstance(typ, str) else typ
                ns = namespace
            namespaces.setdefault(ns, []).append(name)
            if global_name != name:
                # Store the global name for later look-up (allows different local names for the same parameter)
                global_names[name] = global_name
                name = global_name
            REGISTRY.register(
                TunableArg(
                    name=name,
                    typ=typ,
                    default=default,
                    namespace=ns,
                    fn_names={fn.__qualname__, f"{fn.__module__}.{fn.__qualname__}"},
                    apps=set(apps),
                )
            )

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Handle static methods called from instances
            if isinstance(fn, staticmethod) and args[0].__class__.__name__ == fn.__qualname__.split(".")[0]:
                args = args[1:]
            cfg = _active_cfg.get()
            if cfg is not None:
                filtered = {}
                for ns, ns_vars in namespaces.items():
                    section = _resolve_nested_section(cfg, ns)
                    data = section if isinstance(section, dict) else section.model_dump()
                    filtered.update({
                        # Get the tunable arguments from the config and retrieve the original name
                        k: data[global_names.get(k, k)]
                        for k in ns_vars
                        if global_names.get(k, k) in data and k not in kwargs
                    })
                call_kwargs = {**filtered, **kwargs}
            else:
                call_kwargs = kwargs

            bound = sig.bind_partial(*args, **call_kwargs)
            for name in tunable_param_defaults:
                value = bound.arguments.get(name, inspect.Parameter.empty)
                if value is inspect.Parameter.empty or isinstance(value, TunableParamData):
                    msg = (
                        f"Function '{fn.__qualname__}' would receive TunableParamData "
                        f"for parameter '{name}'. Activate a config with use_config() "
                        "or provide an explicit value."
                    )
                    raise TypeError(msg)

            return fn(*args, **call_kwargs)

        return wrapper

    return decorator
