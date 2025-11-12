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
from pydantic import create_model

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class TunableArg:
    """A registered tunable argument."""

    name: str
    typ: Any
    default: Field | Any
    fn: Callable
    namespace: str
    apps: set[str] = field(default_factory=set)


class Node:
    """A tree node that can store the TunableArgs associated to a namespace."""

    entries: dict[str, TunableArg]
    """The entries of the namespace corresponding to the node."""

    children: dict[str, Node]
    """The node's children."""

    path: str
    """The node's full path."""

    def __init__(self, path: str):  # noqa: D107
        self.entries = {}
        self.children = {}
        self.path = path


class TunableRegistry:
    """Holds all registered tunables grouped by namespace, and builds AppConfig."""

    entry_tree: Node
    """Tree containing the namespaces and the corresponding TunableEntry."""

    def __init__(self) -> None:
        """Initialize empty registry."""
        self.entry_tree = Node("")

    def register(self, entry: TunableArg) -> None:
        """Register a tunable entry, merging with an existing namespace if present."""
        node = self.entry_tree
        if entry.namespace:
            fullpath = entry.namespace.split(".")
            path = []
            for p in fullpath:
                path.append(p)
                node = node.children.setdefault(p, Node(".".join(path)))
        existing_entry = node.entries.get(entry.name)
        if not existing_entry:
            node.entries[entry.name] = entry
            return

        # Ensure the type and default are the same for already existing entries
        if existing_entry.typ != entry.typ:
            msg = f"Conflicting type for arg '{entry.name}' in namespace '{entry.namespace}': "
            f"{existing_entry.typ} vs {entry.typ}"
            raise ValueError(msg)
        if existing_entry.default != entry.default:
            msg = f"Conflicting default value for arg '{entry.name}' in namespace '{entry.namespace}': "
            f"{existing_entry.default} vs {entry.default}"
            raise ValueError(msg)

    def build_config(self, app: str, node: dict[str, TunableArg | dict] | None = None) -> type[BaseModel]:
        """Recursively create an AppConfig model for a given app."""
        node = self.entry_tree if node is None else node
        fields = {}
        for name, entry in node.entries.items():
            fields[name] = (entry.typ, entry.default)
        for name, child in node.children.items():
            child_model = self.build_config(app, child)
            fields[name] = (child_model, Field(default_factory=child_model))

        model_name = f"{node.path.title().replace('_', '').replace('.', '_')}_Config"
        return create_model(model_name, **fields)


REGISTRY = TunableRegistry()
