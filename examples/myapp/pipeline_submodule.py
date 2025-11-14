# Copyright 2025 ICON Technology & Process Consulting SAS
"""Module to test schema generation from AST."""

from tunablex import tunable


@tunable("arg1", "arg2", namespace="model.preprocess.submodule_fun")
def submodule_fun(arg1: int = 0, arg2: bool = True):
    print("submodule_fun", arg1, arg2)


class SubmoduleClass:
    @tunable("arg1", "arg2", namespace="model.preprocess.submodule_class")
    @staticmethod
    def fun(arg1: int = 1, arg2: bool = False):
        print("submodule_class", arg1, arg2)
