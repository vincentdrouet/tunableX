from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Iterable
import inspect
from pydantic import BaseModel, Field, create_model
from .naming import ns_to_field

@dataclass
class TunableEntry:
    fn: Any
    model: type[BaseModel]
    sig: inspect.Signature
    namespace: str
    apps: set[str] = field(default_factory=set)

class TunableRegistry:
    def __init__(self):
        self.by_namespace: dict[str, TunableEntry] = {}

    def register(self, entry: TunableEntry):
        self.by_namespace[entry.namespace] = entry

    def namespaces_for_apps(self, apps: Iterable[str]) -> list[str]:
        want = set(apps)
        return [ns for ns, e in self.by_namespace.items() if e.apps & want]

    def build_config(self, namespaces: Iterable[str]):
        from typing import Optional as TypingOptional
        fields: dict[str, tuple[type[BaseModel] | Any, Any]] = {}
        for ns in sorted(set(list(namespaces))):
            if ns not in self.by_namespace:
                continue
            entry = self.by_namespace[ns]
            Model = entry.model
            field_name = ns_to_field(ns)
            try:
                Model()  # no required fields
                fields[field_name] = (Model, Field(default_factory=Model))
            except Exception:
                fields[field_name] = (TypingOptional[Model], None)
        if not fields:
            return create_model("AppConfigEmpty")  # type: ignore
        return create_model("AppConfig", **fields)  # type: ignore

REGISTRY = TunableRegistry()
