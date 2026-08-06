"""Static scope check for jd_scraper — catches NameError before a run does.

2026-07-28: a completed scrape crashed at the very END of main() with
`NameError: name 'per_company' is not defined`. `per_company` is a local of
scan(); main() only ever sees it through the returned `diagnostics` dict. The
reference sat in the coverage-audit block that runs AFTER the scan JSON is
written but BEFORE the markdown write, the checkpoint clear, and the worklist
rebuild — so the scrape looked like it had worked (scan_*.json was on disk)
while the 3395 scraped rows never reached the worklist and the stale
checkpoint stayed behind.

Nothing caught it because no test invokes jd_scraper.main() — it needs network
and a full target list. This test doesn't run main(); it reads the AST and
asserts every name a function LOADS is either bound somewhere in that function
or a real module/builtin attribute. Cheap, deterministic, and it fails on
exactly the mistake above.
"""
from __future__ import annotations

import ast
import builtins
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
sys.path.insert(0, str(AUTO))

import jd_scraper  # noqa: E402

SOURCE = Path(jd_scraper.__file__).with_suffix(".py")


def _bound_names(fn: ast.AST) -> set[str]:
    """Every name bound anywhere inside `fn` (including nested scopes).

    Deliberately permissive — a nested def may legally read an enclosing
    local, so treating the whole subtree as one bag of names avoids false
    positives. It still catches a name that is bound in a DIFFERENT
    top-level function, which is the bug this guards.
    """
    bound: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                bound.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Global):
            bound.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            bound.update(node.names)
    return bound


def _loaded_names(fn: ast.AST) -> list[tuple[str, int]]:
    return [(n.id, n.lineno) for n in ast.walk(fn)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)]


def _top_level_functions():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    return [n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


@pytest.mark.parametrize(
    "fn", _top_level_functions(), ids=lambda f: f.name)
def test_function_references_no_undefined_names(fn):
    """Every loaded name resolves to a local, a module attribute, or a builtin."""
    module_attrs = set(dir(jd_scraper))
    builtin_attrs = set(dir(builtins))
    bound = _bound_names(fn)
    undefined = sorted({
        (name, lineno) for name, lineno in _loaded_names(fn)
        if name not in bound
        and name not in module_attrs
        and name not in builtin_attrs
    })
    assert not undefined, (
        f"{fn.name}() references name(s) that exist in no enclosing scope — "
        f"this raises NameError at runtime: "
        + ", ".join(f"{n!r} (line {ln})" for n, ln in undefined))


def test_main_reads_per_company_via_diagnostics():
    """Pins the specific 2026-07-28 regression.

    scan() returns per-company stats inside `diagnostics`; main() must go
    through that dict rather than reaching for scan()'s local by name.
    """
    main_fn = next(f for f in _top_level_functions() if f.name == "main")
    bare = [ln for name, ln in _loaded_names(main_fn)
            if name == "per_company"]
    assert not bare, (
        f"main() references scan()'s local `per_company` at line(s) {bare}; "
        "use diagnostics.get('per_company') instead")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
