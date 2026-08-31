from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


LANGUAGE_BY_SUFFIX = {
    ".py": "Python", ".pyw": "Python",
    ".c": "C", ".h": "C/C++ Header", ".cc": "C++", ".cpp": "C++", ".cxx": "C++",
    ".hpp": "C++ Header", ".hh": "C++ Header",
    ".js": "JavaScript", ".jsx": "JavaScript/JSX", ".ts": "TypeScript", ".tsx": "TypeScript/TSX",
    ".java": "Java", ".cs": "C#", ".go": "Go", ".rs": "Rust",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
    ".ini": "INI", ".cfg": "Config", ".sh": "Shell", ".bash": "Shell",
    ".ps1": "PowerShell", ".sql": "SQL", ".md": "Markdown", ".txt": "Text",
}


def detect_language(filename: str) -> str:
    return LANGUAGE_BY_SUFFIX.get(Path(filename).suffix.lower(), "Unknown")


def _python_analysis(source: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "imports": [],
        "functions": [],
        "classes": [],
        "syntax_error": None,
    }
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        result["syntax_error"] = f"line {exc.lineno}: {exc.msg}"
        return result

    imports: list[str] = []
    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = ", ".join(alias.name for alias in node.names)
            imports.append(f"from {module} import {names}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({
                "name": node.name,
                "line": node.lineno,
                "async": isinstance(node, ast.AsyncFunctionDef),
                "args": [arg.arg for arg in node.args.args],
                "docstring": ast.get_docstring(node),
            })
        elif isinstance(node, ast.ClassDef):
            classes.append({
                "name": node.name,
                "line": node.lineno,
                "bases": [ast.unparse(base) for base in node.bases],
                "docstring": ast.get_docstring(node),
            })

    result["imports"] = sorted(set(imports))
    result["functions"] = sorted(functions, key=lambda x: x["line"])
    result["classes"] = sorted(classes, key=lambda x: x["line"])
    return result


def _lightweight_analysis(source: str, language: str) -> dict[str, Any]:
    imports: list[str] = []
    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []

    patterns = [
        r"^\s*#include\s*[<\"]([^>\"]+)[>\"]",
        r"^\s*import\s+(.+?);?\s*$",
        r"^\s*from\s+([\w./@-]+)\s+import\s+(.+?);?\s*$",
        r"^\s*using\s+([\w.]+)\s*;",
        r"^\s*require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
    ]
    for line in source.splitlines():
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                imports.append(" ".join(g for g in match.groups() if g))
                break

    class_pattern = re.compile(r"\b(?:class|struct|interface|enum)\s+([A-Za-z_]\w*)")
    fn_patterns = [
        re.compile(r"\b(?:function\s+)?([A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:=>|\{)"),
        re.compile(r"\b(?:def|func|fn)\s+([A-Za-z_]\w*)\s*\("),
    ]

    for lineno, line in enumerate(source.splitlines(), start=1):
        cm = class_pattern.search(line)
        if cm:
            classes.append({"name": cm.group(1), "line": lineno})
        for pattern in fn_patterns:
            fm = pattern.search(line)
            if fm and fm.group(1) not in {"if", "for", "while", "switch", "catch"}:
                functions.append({"name": fm.group(1), "line": lineno})
                break

    return {
        "imports": sorted(set(imports))[:100],
        "functions": functions[:200],
        "classes": classes[:100],
        "syntax_error": None,
        "note": f"{language} はv1では軽量なパターン解析です。意味解析はOllamaが補完します。",
    }


def analyze_source(filename: str, source: str) -> dict[str, Any]:
    language = detect_language(filename)
    lines = source.count("\n") + 1 if source else 0
    basic = {
        "filename": filename,
        "language": language,
        "line_count": lines,
        "char_count": len(source),
    }
    if language == "Python":
        static = _python_analysis(source)
    else:
        static = _lightweight_analysis(source, language)
    return {**basic, **static}
