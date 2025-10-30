"""Tunable registry and AppConfig builder.

- Supports registering tunables per namespace and app tag.
- Merges multiple function entries that target the same namespace by combining
  their Pydantic model fields and unioning app tags.
- Builds nested models for dotted namespaces so generated JSON/schema are nested.
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

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass
class TunableEntry:
    """A registered tunable function and its default fields."""

    fields: dict[str, tuple[str, Field | Any]]
    """The fields of the model.
    The keys are the parameters names, and the items are the type (as a string) and the Field or the default value."""

    fn: Any
    namespace: str
    apps: set[str] = field(default_factory=set)


class _Node:
    """A tree node that can store the model associated to a namespace."""

    fields: dict[str, tuple[str, Field | Any]]
    """The fields of the namespace corresponding to the node."""

    children: dict[str, _Node]
    """The node's children."""

    fullpath: str
    """The node's full path."""

    def __init__(self, fullpath: str):  # noqa: D205, D212
        self.fields = {}
        self.children = {}
        self.fullpath = fullpath


class TunableRegistry:
    """Holds all registered tunables grouped by namespace, and builds AppConfig."""

    entry_dict: dict[str, TunableEntry]
    """Dict containing the namespaces and the corresponding TunableEntry."""

    def __init__(self) -> None:
        """Initialize empty registry."""
        self.entry_dict = {}

    def register(self, entry: TunableEntry) -> None:
        """Register a tunable entry, merging with an existing namespace if present."""
        existing = self.entry_dict.get(entry.namespace)
        if not existing:
            self.entry_dict[entry.namespace] = entry
            return

        # Merge apps
        existing.apps = set(existing.apps) | set(entry.apps)

        # Merge model fields while preserving Field metadata. Prefer first definition.
        for name, fld in entry.fields.items():
            if name in existing.fields:
                typ = fld[0]
                prev_typ = existing.fields[name][0]
                if prev_typ != typ:
                    msg = f"Conflicting field '{name}' in namespace '{entry.namespace}': {prev_typ} vs {typ}"
                    raise ValueError(msg)
                continue  # keep first definition
            existing.fields[name] = fld

    def namespaces_for_apps(self, apps: Iterable[str]) -> list[str]:
        """Return namespaces that have at least one of the given app tags."""
        want = set(apps)
        return [ns for ns, e in self.entry_dict.items() if (e.apps & want or not e.apps)]

    def build_node_model(self, node: _Node) -> type[BaseModel]:
        """Recursively build Pydantic models from the tree."""
        # Start from leaf fields if any
        field_defs = {}
        if node.fields is not None:
            for fname, field in node.fields.items():
                if fname in node.children:
                    msg = f"Field name '{fname}' in '{node.fullpath}' conflicts with child namespace"
                    raise ValueError(msg)
                field_defs[fname] = field

        # Add children as nested models
        for child_name, child_node in node.children.items():
            child_model = self.build_node_model(child_node)
            # If child_model() cannot instantiate, make it optional with default None
            try:
                child_model()
                field_defs[child_name] = (child_model, Field(default_factory=child_model))
            except ValidationError:
                field_defs[child_name] = (child_model | None, None)

        model_name = f"{node.fullpath.title().replace('_', '').replace('.', '_')}_Config"
        return create_model(model_name, **field_defs)  # type: ignore[return-value]

    def build_config(self, namespaces: Iterable[str]) -> type[BaseModel]:
        """Create a top-level AppConfig model from selected namespaces.

        - Dotted namespaces are nested (e.g., "a.b.c" becomes cfg.a.b.c).
        - Sections with required fields are emitted as Optional at the point they appear
          so the top-level AppConfig can instantiate without values supplied.
        """
        # Build a namespace tree where each node may have a leaf model and children.
        root = _Node("")
        # If there is no parameters at root level, or "" is not in the requested namespaces, create an empty model
        root_entry = self.entry_dict.get("")
        root.fields = {} if root_entry is None or "" not in namespaces else root_entry.fields

        namespaces = set(namespaces)
        if "" in namespaces:
            namespaces.remove("")
        for ns in sorted(namespaces):
            entry = self.entry_dict.get(ns)
            if not entry:
                continue
            parts = ns.split(".")
            # Traverse/create nodes
            node = root
            cur_path = []
            for seg in parts:
                cur_path.append(seg)
                path = ".".join(cur_path)
                if seg not in node.children:
                    node.children[seg] = _Node(path)
                node = node.children[seg]
            node.fields = entry.fields

        return self.build_node_model(root)


REGISTRY = TunableRegistry()
