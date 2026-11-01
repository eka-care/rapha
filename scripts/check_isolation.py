"""Run: python3 scripts/check_isolation.py

No check writes the developer's own demo day.

WHAT THIS EXISTS FOR
--------------------
`scripts/check_directory.py` registered a patient through the real route and
never set `PHC_DB`, so run from the repository it wrote `./phc.sqlite3`: one
patient per gate run, accumulating in the database a person opens the app
against. It looked exactly like the duplicate-patient defect that had just
been fixed, which is the expensive part -- a check that corrupts the thing it
is checking sends somebody hunting a bug that is not there.

THE RULE. A script that reaches the store at all says WHERE: its own
temporary file, `:memory:`, or a path it made. Importing `api.main`, or
constructing a `SqliteStore`, without choosing is what this refuses.

WHY IT READS THE SYNTAX AND NOT THE TEXT. Written first as a pair of regular
expressions over the source, it passed on a check whose isolation had been
deleted, because the COMMENT explaining why that check sets `PHC_DB` still
mentioned it, and so did the module docstring. A check that passes because
somebody wrote about the bug is worse than no check. `ast` sees the
assignment or it does not, and prose is not an assignment.
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"


def imports_the_app(tree: ast.AST) -> bool:
    """Does it import api.main, whose module level store opens PHC_DB?"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "api.main" for a in node.names):
                return True
        if isinstance(node, ast.ImportFrom):
            if node.module == "api.main" or (
                    node.module == "api" and any(a.name == "main" for a in node.names)):
                return True
    return False


def sets_the_env(tree: ast.AST) -> bool:
    """Does it name PHC_DB where naming it decides the file?

    Three spellings, all of them real in this repository: the assignment,
    the env dict a runner hands a server it starts, and `setdefault`, which
    says the same thing while leaving an explicit PHC_DB alone. Only these:
    a mention in prose is not one, which is the whole reason this reads the
    syntax.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and _const(target.slice) == "PHC_DB":
                    return True
        if (isinstance(node, ast.Call) and _named(node.func) == "setdefault"
                and node.args and _const(node.args[0]) == "PHC_DB"):
            return True
    return False


def opens_a_store(tree: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and _named(n.func) == "SqliteStore"]


def store_says_where(tree: ast.AST, call: ast.Call) -> bool:
    """`:memory:`, or a path this script made for itself."""
    if call.args and _const(call.args[0]) == ":memory:":
        return True
    return any(isinstance(n, ast.Call) and _named(n.func) == "mkdtemp"
               for n in ast.walk(tree))


def _named(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _const(node: ast.AST):
    return node.value if isinstance(node, ast.Constant) else None


bad, checked = [], 0
for path in sorted(SCRIPTS.glob("*.py")):
    tree = ast.parse(path.read_text(), filename=str(path))
    app, stores = imports_the_app(tree), opens_a_store(tree)
    if not app and not stores:
        continue
    checked += 1
    # TWO MECHANISMS, TWO ANSWERS, and this is where the first draft was
    # wrong: check_directory.py makes its own `SqliteStore(":memory:")` AND
    # imports api.main, whose module level store opens PHC_DB. The in-memory
    # one said "where" for a store that was never the problem, and the app it
    # imported wrote the developer's file anyway.
    if app and not sets_the_env(tree):
        bad.append("%s imports api.main without setting PHC_DB" % path.name)
    for call in stores:
        if not store_says_where(tree, call):
            bad.append("%s opens a SqliteStore at line %d without saying where"
                       % (path.name, call.lineno))
            break

assert checked >= 8, (
    "this is not reading the scripts any more: only %d of them reach a store, "
    "which is fewer than the gate has" % checked)
assert not bad, (
    "these write wherever PHC_DB happens to point, which from the repository "
    "is a developer's own demo day: %s" % ", ".join(bad))

print("ok   %d checks reach a store and every one of them says WHERE: its own "
      "temporary file, :memory:, or a path it made" % checked)
print("ok   and it reads the syntax, so a comment about PHC_DB cannot stand "
      "in for setting it")
