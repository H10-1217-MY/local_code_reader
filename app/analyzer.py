from __future__ import annotations

import ast
import re
import sys
from html.parser import HTMLParser
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
    ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".scss": "SCSS", ".xml": "XML",
}

# Node.js built-in modules. External package extraction should not report these as npm dependencies.
NODE_BUILTINS = {
    "assert", "buffer", "child_process", "cluster", "console", "constants", "crypto", "dgram", "diagnostics_channel",
    "dns", "domain", "events", "fs", "http", "http2", "https", "module", "net", "os", "path", "perf_hooks",
    "process", "punycode", "querystring", "readline", "repl", "stream", "string_decoder", "sys", "timers", "tls",
    "trace_events", "tty", "url", "util", "v8", "vm", "wasi", "worker_threads", "zlib", "test",
}


def detect_language(filename: str) -> str:
    return LANGUAGE_BY_SUFFIX.get(Path(filename).suffix.lower(), "Unknown")


def _call_name(node: ast.AST) -> str | None:
    """Best-effort readable name for a Python call target."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        if base:
            return f"{base}.{node.attr}"
    return None


def _python_analysis(source: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "imports": [],
        "functions": [],
        "classes": [],
        "top_level_assignments": [],
        "environment_variables": [],
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

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.class_stack: list[str] = []

        def visit_Import(self, node: ast.Import) -> None:
            imports.extend(alias.name for alias in node.names)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            module = ("." * node.level) + (node.module or "")
            names = ", ".join(alias.name for alias in node.names)
            imports.append(f"from {module} import {names}")

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            qualified_name = ".".join([*self.class_stack, node.name])
            classes.append({
                "name": node.name,
                "qualified_name": qualified_name,
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
                "bases": [ast.unparse(base) for base in node.bases],
                "docstring": ast.get_docstring(node),
            })
            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()

        def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            qualified_name = ".".join([*self.class_stack, node.name])
            calls: list[str] = []
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    name = _call_name(child.func)
                    if name:
                        calls.append(name)

            positional_args = [arg.arg for arg in node.args.posonlyargs + node.args.args]
            keyword_only_args = [arg.arg for arg in node.args.kwonlyargs]
            functions.append({
                "name": node.name,
                "qualified_name": qualified_name,
                "kind": "method" if self.class_stack else "function",
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
                "async": isinstance(node, ast.AsyncFunctionDef),
                "args": positional_args,
                "keyword_only_args": keyword_only_args,
                "docstring": ast.get_docstring(node),
                "calls": sorted(set(calls))[:50],
                "decorators": [ast.unparse(dec) for dec in node.decorator_list],
            })
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_function(node)

    Visitor().visit(tree)

    top_level_assignments: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    top_level_assignments.append(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            top_level_assignments.append(node.target.id)

    environment_variables: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in {"os.getenv", "os.environ.get"} and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                environment_variables.append(node.args[0].value)
        elif isinstance(node, ast.Subscript) and _call_name(node.value) == "os.environ":
            slice_node = node.slice
            if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
                environment_variables.append(slice_node.value)

    result["imports"] = sorted(set(imports))
    result["functions"] = sorted(functions, key=lambda x: x["line"])
    result["classes"] = sorted(classes, key=lambda x: x["line"])
    result["top_level_assignments"] = list(dict.fromkeys(top_level_assignments))[:200]
    result["environment_variables"] = list(dict.fromkeys(environment_variables))[:100]
    return result


def _javascript_analysis(source: str, language: str) -> dict[str, Any]:
    imports: list[str] = []
    references: list[str] = []
    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []

    import_patterns = [
        re.compile(r"^\s*import\s+.+?\s+from\s+['\"]([^'\"]+)['\"]\s*;?"),
        re.compile(r"^\s*import\s*['\"]([^'\"]+)['\"]\s*;?"),
        re.compile(r"\brequire\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    ]
    fn_patterns = [
        re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("),
        re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"),
        re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function\b"),
    ]
    class_pattern = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)\b")

    for lineno, line in enumerate(source.splitlines(), start=1):
        for pattern in import_patterns:
            match = pattern.search(line)
            if match:
                target = match.group(1)
                imports.append(target)
                if target.startswith(("./", "../", "/")):
                    references.append(target)
                break

        cm = class_pattern.search(line)
        if cm:
            classes.append({"name": cm.group(1), "qualified_name": cm.group(1), "line": lineno, "end_line": None})

        for pattern in fn_patterns:
            fm = pattern.search(line)
            if fm:
                name = fm.group(1)
                functions.append({
                    "name": name,
                    "qualified_name": name,
                    "kind": "function",
                    "line": lineno,
                    "end_line": None,
                    "calls": [],
                })
                break

    return {
        "imports": sorted(set(imports))[:120],
        "references": sorted(set(references))[:120],
        "functions": functions[:250],
        "classes": classes[:120],
        "syntax_error": None,
        "note": f"{language} はv3.1で宣言ベースの軽量解析です。メソッド呼び出しを関数定義として数えないようにしています。",
    }


def _css_analysis(source: str, language: str) -> dict[str, Any]:
    imports: list[str] = []
    references: list[str] = []
    selectors: list[str] = []
    at_rules: list[str] = []
    custom_properties: list[str] = []

    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith("/*") or line.startswith("*"):
            continue

        im = re.match(r"@import\s+(?:url\()?\s*['\"]?([^'\")\s;]+)", line, re.IGNORECASE)
        if im:
            target = im.group(1)
            imports.append(target)
            if not re.match(r"^[a-z]+://", target, re.IGNORECASE):
                references.append(target)

        arm = re.match(r"@(media|supports|keyframes|font-face|layer|container)\b(?:\s+([^\{]+))?", line, re.IGNORECASE)
        if arm:
            detail = (arm.group(2) or "").strip()
            at_rules.append(f"@{arm.group(1)}" + (f" {detail}" if detail else ""))

        for prop in re.findall(r"(--[A-Za-z0-9_-]+)\s*:", line):
            custom_properties.append(prop)

        # セレクタ行だけを拾う。@media等を関数扱いしない。
        if "{" in line and not line.startswith("@"):
            head = line.split("{", 1)[0].strip()
            if head and not re.search(r"\b(?:from|to|\d+%)\b", head):
                for selector in head.split(","):
                    selector = selector.strip()
                    if selector:
                        selectors.append(selector)

    return {
        "imports": sorted(set(imports))[:100],
        "references": sorted(set(references))[:100],
        "functions": [],
        "classes": [],
        "css_selectors": list(dict.fromkeys(selectors))[:250],
        "css_at_rules": list(dict.fromkeys(at_rules))[:120],
        "css_custom_properties": list(dict.fromkeys(custom_properties))[:120],
        "syntax_error": None,
        "note": f"{language} はv3.1でCSS専用の軽量解析です。セレクタ/@規則/CSS変数を取得し、@mediaを関数として誤検出しません。",
    }


class _HTMLReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []
        self.ids: list[str] = []
        self.classes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "script" and data.get("src"):
            self.references.append(data["src"])
        if tag.lower() == "link" and data.get("href"):
            self.references.append(data["href"])
        if tag.lower() in {"img", "source"} and data.get("src"):
            self.references.append(data["src"])
        if data.get("id"):
            self.ids.append(data["id"])
        if data.get("class"):
            self.classes.extend(x for x in data["class"].split() if x)


def _html_analysis(source: str) -> dict[str, Any]:
    parser = _HTMLReferenceParser()
    try:
        parser.feed(source)
    except Exception:
        # HTMLParser is lenient, but malformed input should not break the whole reader.
        pass
    refs = [r for r in parser.references if r and not r.startswith(("data:", "javascript:"))]
    return {
        "imports": [],
        "references": list(dict.fromkeys(refs))[:160],
        "functions": [],
        "classes": [],
        "html_ids": list(dict.fromkeys(parser.ids))[:200],
        "html_classes": list(dict.fromkeys(parser.classes))[:300],
        "syntax_error": None,
        "note": "HTML はv3.3でscript/link/img等の参照とid/classを軽量解析します。",
    }


def _lightweight_analysis(source: str, language: str) -> dict[str, Any]:
    imports: list[str] = []
    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []

    patterns = [
        r"^\s*#include\s*[<\"]([^>\"]+)[>\"]",
        r"^\s*import\s+(.+?);?\s*$",
        r"^\s*from\s+([\w./@-]+)\s+import\s+(.+?);?\s*$",
        r"^\s*using\s+([\w.]+)\s*;",
    ]
    for line in source.splitlines():
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                imports.append(" ".join(g for g in match.groups() if g))
                break

    class_pattern = re.compile(r"\b(?:class|struct|interface|enum)\s+([A-Za-z_]\w*)")
    fn_patterns = [
        re.compile(r"\b(?:def|func|fn)\s+([A-Za-z_]\w*)\s*\("),
        re.compile(r"^\s*(?:[A-Za-z_][\w:<>,\[\]*&?\s]+\s+)+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{")
    ]

    for lineno, line in enumerate(source.splitlines(), start=1):
        cm = class_pattern.search(line)
        if cm:
            classes.append({"name": cm.group(1), "qualified_name": cm.group(1), "line": lineno, "end_line": None})
        for pattern in fn_patterns:
            fm = pattern.search(line)
            if fm and fm.group(1) not in {"if", "for", "while", "switch", "catch"}:
                functions.append({
                    "name": fm.group(1),
                    "qualified_name": fm.group(1),
                    "kind": "function",
                    "line": lineno,
                    "end_line": None,
                    "calls": [],
                })
                break

    return {
        "imports": sorted(set(imports))[:100],
        "functions": functions[:200],
        "classes": classes[:100],
        "syntax_error": None,
        "note": f"{language} はv3.1では軽量な宣言パターン解析です。意味解析はOllamaが補完します。",
    }


def _document_analysis(language: str) -> dict[str, Any]:
    return {
        "imports": [],
        "functions": [],
        "classes": [],
        "syntax_error": None,
        "note": f"{language} は構造化データ/文書として扱い、関数・クラスの正規表現推定は行いません。",
    }


def _import_target(import_text: str, language: str) -> str | None:
    text = import_text.strip()
    if not text:
        return None
    if language == "Python":
        m = re.match(r"^from\s+([^\s]+)\s+import\s+", text)
        if m:
            return m.group(1)
        if text.startswith("import "):
            text = text[7:].strip()
        return text.split(",", 1)[0].strip().split(" as ", 1)[0].strip()
    if language.startswith(("JavaScript", "TypeScript")):
        return text
    if language in {"C", "C++", "C/C++ Header", "C++ Header"}:
        return text.strip('<>"')
    return text


def extract_external_dependencies(static_analysis: dict[str, Any]) -> list[str]:
    """静的import情報だけから外部依存候補を機械抽出する。推測はしない。"""
    language = str(static_analysis.get("language") or "Unknown")
    deps: list[str] = []
    for raw in static_analysis.get("imports") or []:
        target = _import_target(str(raw), language)
        if not target or target.startswith((".", "/")):
            continue

        if language == "Python":
            root = target.split(".", 1)[0]
            if root in sys.stdlib_module_names or root == "__future__":
                continue
            deps.append(root)
            continue

        if language.startswith(("JavaScript", "TypeScript")):
            if target.startswith(("./", "../")):
                continue
            root = "/".join(target.split("/")[:2]) if target.startswith("@") else target.split("/", 1)[0]
            if root.removeprefix("node:") in NODE_BUILTINS:
                continue
            deps.append(root)
            continue

        # C/C++等は標準/外部の厳密判定が難しいため、include名をbest-effort候補として残す。
        if language in {"C", "C++", "C/C++ Header", "C++ Header"}:
            deps.append(target)

    return list(dict.fromkeys(deps))[:160]


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
    elif language.startswith(("JavaScript", "TypeScript")):
        static = _javascript_analysis(source, language)
    elif language in {"CSS", "SCSS"}:
        static = _css_analysis(source, language)
    elif language == "HTML":
        static = _html_analysis(source)
    elif language in {"JSON", "YAML", "TOML", "INI", "Config", "Markdown", "Text", "XML"}:
        static = _document_analysis(language)
    else:
        static = _lightweight_analysis(source, language)

    result = {**basic, **static}
    result["detected_external_dependencies"] = extract_external_dependencies(result)
    return result
