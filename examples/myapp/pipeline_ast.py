# Copyright 2025 ICON Technology & Process Consulting SAS
"""Module with a single function used to test schema generation from AST."""

from tunablex import tunable


@tunable("arg1", "arg2", namespace="preprocess.ast_test_fun")
def ast_test_fun(arg1: int = 0, arg2: bool = True):
    print("ast_test_fun", arg1, arg2)


class ASTTestClass:
    @tunable("arg1", "arg2", namespace="preprocess.ast_test_class")
    def fun(self: int = 1, arg2: bool = False):
        print("ast_test_class", self, arg2)
