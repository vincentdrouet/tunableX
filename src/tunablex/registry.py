"""Tunable registry and AppConfig builder.

- Supports registering tunables per namespace and app tag.
- Merges multiple function entries that target the same namespace by combining
  their Pydantic model fields and unioning app tags.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import Any

from pydantic import BaseModel
from pydantic import Field
from pydantic import ValidationError
from pydantic import create_model

from .naming import ns_to_field

if TYPE_CHECKING:  # typing-only imports
    import inspect
    from collections.abc import Iterable


@dataclass
class TunableEntry:
    """A registered tunable function and its Pydantic model."""

    fn: Any
    model: type[BaseModel]
    sig: inspect.Signature
    namespace: str
    apps: set[str] = field(default_factory=set)


class TunableRegistry:
    """Holds all registered tunables grouped by namespace, and builds AppConfig."""

    def __init__(self) -> None:
        """Initialize empty registry."""
        self.by_namespace: dict[str, TunableEntry] = {}

    def register(self, entry: TunableEntry) -> None:
        """Register a tunable entry, merging with an existing namespace if present."""
        existing = self.by_namespace.get(entry.namespace)
        if not existing:
            self.by_namespace[entry.namespace] = entry
            return

        # Merge apps
        apps_merged = set(existing.apps) | set(entry.apps)

        # Merge model fields while preserving Field metadata. Prefer first definition.
        merged_fields: dict[str, tuple[type[Any] | Any, Any]] = {}
        for name, fld in existing.model.model_fields.items():
            ann = fld.annotation
            merged_fields[name] = (ann, fld)
        for name, fld in entry.model.model_fields.items():
            ann = fld.annotation
            if name in merged_fields:
                prev_ann, _prev_def = merged_fields[name]
                if prev_ann != ann:
                    msg = (
                        f"Conflicting field '{name}' in namespace '{entry.namespace}': "
                        f"{prev_ann} vs {ann}"
                    )
                    raise ValueError(msg)
                continue  # keep first definition
            merged_fields[name] = (ann, fld)

        model_name = f"{entry.namespace.title().replace('.', '').replace('_', '')}Config"
        merged_model: type[BaseModel] = create_model(model_name, **merged_fields)  # type: ignore[assignment]

        # Keep original fn/sig (arbitrary); update model and apps.
        self.by_namespace[entry.namespace] = TunableEntry(
            fn=existing.fn,
            model=merged_model,
            sig=existing.sig,
            namespace=entry.namespace,
            apps=apps_merged,
        )

    def namespaces_for_apps(self, apps: Iterable[str]) -> list[str]:
        """Return namespaces that have at least one of the given app tags."""
        want = set(apps)
        return [ns for ns, e in self.by_namespace.items() if e.apps & want]

    def build_config(self, namespaces: Iterable[str]):
        """Create a top-level AppConfig model from selected namespaces.

        Sections with required fields are emitted as Optional[SectionModel] with default None
        so the top-level AppConfig can instantiate without values supplied.
        """
        fields: dict[str, tuple[type[BaseModel] | Any, Any]] = {}
        for ns in sorted(set(namespaces)):
            if ns not in self.by_namespace:
                continue
            entry = self.by_namespace[ns]
            model = entry.model
            field_name = ns_to_field(ns)
            try:
                model()  # raises ValidationError if required fields exist
                fields[field_name] = (model, Field(default_factory=model))
            except ValidationError:
                fields[field_name] = (model | None, None)
        if not fields:
            return create_model("AppConfigEmpty")
        return create_model("AppConfig", **fields)


REGISTRY = TunableRegistry()
