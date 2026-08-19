from __future__ import annotations

import multiprocessing
import sys
import types
from typing import Annotated
from typing import Literal

import pytest
from pydantic import Field

from tunablex import TunableParams
from tunablex import tunable


class TypeResolutionParams(TunableParams):
    literal: Literal["fast", "safe"] = Field("fast")
    annotated: Annotated[int | None, "metadata"] = Field(None)
    unresolved: MissingAtRuntime = Field(None)  # pyright: ignore[reportUndefinedVariable] # noqa: F821


@tunable("value", namespace="type_resolution")
def type_resolution_fn(value: str = TypeResolutionParams.literal):
    return value


def test_typing_annotations_are_resolved_and_cached():
    first = TypeResolutionParams.literal
    second = TypeResolutionParams.literal

    assert first.typ == Literal["fast", "safe"]
    assert second.typ is first.typ
    assert TypeResolutionParams.__tunable_type_hints__["literal"] is first.typ


def test_unrelated_unresolvable_annotation_is_not_evaluated():
    assert TypeResolutionParams.literal.value.default == "fast"


def test_function_rejects_tunable_param_data_without_config():
    with pytest.raises(TypeError, match="would receive TunableParamData"):
        type_resolution_fn()


def test_accessing_unresolvable_annotation_has_contextual_error():
    with pytest.raises(NameError, match=r"TypeResolutionParams.unresolved"):
        _ = TypeResolutionParams.unresolved


def _forkserver_read_type(queue):
    queue.put(TypeResolutionParams.literal.typ == Literal["fast", "safe"])


def test_type_resolution_works_in_worker():
    methods = multiprocessing.get_all_start_methods()
    if "forkserver" in methods:
        start_method = "forkserver"
    elif "spawn" in methods:
        start_method = "spawn"
    else:
        pytest.skip("Neither forkserver nor spawn is available")

    context = multiprocessing.get_context(start_method)
    queue = context.Queue()
    process = context.Process(target=_forkserver_read_type, args=(queue,))
    process.start()
    process.join(timeout=10)
    assert process.exitcode == 0
    assert queue.get(timeout=2) is True


def test_type_resolution_works_across_main_module_aliases(monkeypatch):
    """Postponed annotations can resolve values from __main__/__mp_main__."""
    module = types.ModuleType("__main__")
    module.PROBLEM_SPLITS = {"train_8": [], "valid_8": []}
    monkeypatch.setitem(sys.modules, "__main__", module)

    class MainAliasParams(TunableParams):
        split: Literal[*PROBLEM_SPLITS] = Field("train_8")  # pyright: ignore[reportUndefinedVariable, reportInvalidTypeForm] # noqa: F821

    MainAliasParams.__module__ = "mp_main"
    assert MainAliasParams.split.typ == Literal["train_8", "valid_8"]
