#!/usr/bin/env python3
"""\file tools/metrics.py
\brief Сбор метрик кода проекта (аналог Visual Studio Code Metrics для Python).

Метрики:
  - Cyclomatic Complexity (radon, по модулям и функциям);
  - Maintainability Index (radon);
  - Lines of Code: LOC/SLOC/LLOC/комментарии (radon raw);
  - Метрики Холстеда: volume, difficulty, effort, оценка дефектов (radon hal);
  - Depth of Inheritance (AST);
  - Class Coupling (AST, уникальные внешние классы в теле класса).

Использование: python tools/metrics.py [путь] [--json]
"""
import ast
import json
import sys
from pathlib import Path

from radon.complexity import cc_visit
from radon.metrics import h_visit, mi_visit
from radon.raw import analyze

ROOT = Path(__file__).resolve().parent.parent


def iter_py_files(base):
    return sorted(p for p in Path(base).rglob("*.py") if ".venv" not in p.parts)


def module_metrics(path):
    code = path.read_text(encoding="utf-8")
    raw = analyze(code)
    cc_blocks = cc_visit(code)
    total_cc = sum(b.complexity for b in cc_blocks)
    worst = max(cc_blocks, key=lambda b: b.complexity, default=None)
    hal = h_visit(code)
    return {
        "module": str(path.relative_to(ROOT)),
        "loc": raw.loc,
        "sloc": raw.sloc,
        "lloc": raw.lloc,
        "comments": raw.comments,
        "blank": raw.blank,
        "mi": round(mi_visit(code, multi=True), 2),
        "cc_total": total_cc,
        "cc_avg": round(total_cc / len(cc_blocks), 2) if cc_blocks else 0.0,
        "cc_max": worst.complexity if worst else 0,
        "cc_worst": worst.name if worst else "-",
        "halstead_volume": round(hal.total.volume, 1),
        "halstead_difficulty": round(hal.total.difficulty, 1),
        "halstead_effort": round(hal.total.effort, 1),
        "halstead_bugs": round(hal.total.bugs, 3),
    }


def class_metrics(path):
    """DIT и Class Coupling по классам модуля (AST)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    rows = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        dit = _depth(node, tree)
        used = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name):
                used.add(sub.id)
            elif isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
                used.add(sub.value.id)
        coupling = len((used & defined) - {node.name})
        rows.append({
            "class": f"{path.relative_to(ROOT)}::{node.name}",
            "dit": dit,
            "coupling": coupling,
        })
    return rows


def _depth(node, tree):
    depth = 0
    current = node
    names = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    while current.bases:
        base = current.bases[0]
        base_name = base.id if isinstance(base, ast.Name) else None
        if base_name not in names:
            depth += 1  # внешний базовый класс (BaseModel, Exception, ...)
            break
        depth += 1
        current = names[base_name]
    return depth


def collect(base):
    modules = [module_metrics(p) for p in iter_py_files(base)]
    classes = []
    for p in iter_py_files(base):
        classes.extend(class_metrics(p))
    return {"modules": modules, "classes": classes}


def main():
    base = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "backend"
    report = collect(ROOT / base)
    if "--json" in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    hdr = ("Модуль", "SLOC", "CCΣ", "CCavg", "CCmax", "MI", "V(H)", "D(H)", "E(H)", "B(H)")
    print(("{:<38} {:>5} {:>5} {:>6} {:>6} {:>7} {:>9} {:>6} {:>9} {:>6}").format(*hdr))
    for m in report["modules"]:
        print(("{:<38} {:>5} {:>5} {:>6} {:>6} {:>7} {:>9} {:>6} {:>9} {:>6}").format(
            m["module"], m["sloc"], m["cc_total"], m["cc_avg"], m["cc_max"],
            m["mi"], m["halstead_volume"], m["halstead_difficulty"],
            m["halstead_effort"], m["halstead_bugs"]))
    print("\nКлассы (DIT = глубина наследования, CBO = связанность):")
    for c in sorted(report["classes"], key=lambda r: (-r["dit"], -r["coupling"])):
        print(f"  {c['class']:<55} DIT={c['dit']} CBO={c['coupling']}")


if __name__ == "__main__":
    main()
