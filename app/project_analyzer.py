from __future__ import annotations

import ast
import json
import re
import tomllib
from collections import Counter
from pathlib import PurePosixPath
from typing import Any

from .config import PROJECT_EXCLUDED_FILENAMES, PROJECT_STRUCTURE_ONLY_FILENAMES


def _python_module_aliases(path: str) -> set[str]:
    p = PurePosixPath(path)
    if p.suffix != ".py":
        return set()

    parts = list(p.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return set()

    full = ".".join(parts)
    aliases = {full, parts[-1]}
    return aliases


def _resolve_relative_module(current_path: str, module: str) -> str:
    if not module.startswith("."):
        return module

    dots = len(module) - len(module.lstrip("."))
    tail = module[dots:]
    package_parts = list(PurePosixPath(current_path).parent.parts)
    # from .foo は現在package、from ..foo は1階層上。
    up = max(0, dots - 1)
    if up:
        package_parts = package_parts[:-up] if up <= len(package_parts) else []
    if tail:
        package_parts.extend(tail.split("."))
    return ".".join(package_parts)


def _extract_import_module(import_text: str) -> str | None:
    text = import_text.strip()
    match = re.match(r"^from\s+([^\s]+)\s+import\s+", text)
    if match:
        return match.group(1)
    if text.startswith("import "):
        text = text[7:].strip()
    first = text.split(",", 1)[0].strip().split(" as ", 1)[0].strip()
    if re.fullmatch(r"\.?\.?[A-Za-z_][\w.]*", first) or first.startswith("."):
        return first
    return None


def is_generated_or_junk_path(path: str) -> tuple[bool, str | None]:
    """名前だけで安全に除外できる生成物・ゴミファイルを判定する。"""
    name = PurePosixPath(path).name
    lower = name.lower()
    if name in PROJECT_EXCLUDED_FILENAMES:
        return True, "OS/保持用の補助ファイル"
    if lower.endswith((".min.js", ".min.css")):
        return True, "minify済み生成物"
    if lower.endswith((".map", ".pyc", ".pyo", ".class", ".o", ".obj")):
        return True, "ビルド・生成物"
    return False, None


def _init_is_structure_only(source: str) -> bool:
    """__init__.py が公開API/定数の宣言中心ならLLMを使わず構造解析だけにする。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    allowed = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.Pass)
    for node in tree.body:
        if isinstance(node, allowed):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue  # module docstring
        return False
    return True


def classify_project_content(path: str, source: str) -> dict[str, str]:
    """プロジェクト内ファイルを llm / structure / skip のいずれかに分類する。"""
    name = PurePosixPath(path).name
    if not source.strip():
        return {"mode": "skip", "reason": "空または空白のみのファイル"}

    excluded, reason = is_generated_or_junk_path(path)
    if excluded:
        return {"mode": "skip", "reason": reason or "解析対象外"}

    lower = name.lower()
    if name == "__init__.py" and _init_is_structure_only(source):
        return {"mode": "structure", "reason": "Pythonパッケージ初期化/公開API定義として構造のみ解析"}
    if name in PROJECT_STRUCTURE_ONLY_FILENAMES or re.fullmatch(r"requirements(?:[-_.][\w.-]+)?\.txt", lower):
        return {"mode": "structure", "reason": "依存・設定メタデータとして構造のみ解析"}
    return {"mode": "llm", "reason": "コード/文書としてOllama解析"}


def _requirement_names(source: str) -> list[str]:
    names: list[str] = []
    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(("-r", "--", "git+", "http://", "https://")):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)", line)
        if match:
            names.append(match.group(1))
    return list(dict.fromkeys(names))[:120]


def _env_keys(source: str) -> list[str]:
    keys: list[str] = []
    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            keys.append(key)
    return list(dict.fromkeys(keys))[:120]


def _toml_metadata(source: str) -> tuple[list[str], list[str]]:
    try:
        data = tomllib.loads(source)
    except (tomllib.TOMLDecodeError, ValueError):
        return [], []
    top_keys = [str(k) for k in data.keys()][:80]
    dependencies: list[str] = []
    project = data.get("project")
    if isinstance(project, dict):
        deps = project.get("dependencies")
        if isinstance(deps, list):
            for dep in deps:
                match = re.match(r"([A-Za-z0-9_.-]+)", str(dep))
                if match:
                    dependencies.append(match.group(1))
    poetry = ((data.get("tool") or {}).get("poetry") if isinstance(data.get("tool"), dict) else None)
    if isinstance(poetry, dict) and isinstance(poetry.get("dependencies"), dict):
        dependencies.extend(str(k) for k in poetry["dependencies"].keys() if str(k).lower() != "python")
    return top_keys, list(dict.fromkeys(dependencies))[:120]


def _json_metadata(source: str) -> tuple[list[str], list[str], list[str]]:
    try:
        data = json.loads(source)
    except (json.JSONDecodeError, ValueError):
        return [], [], []
    if not isinstance(data, dict):
        return [], [], []
    top_keys = [str(k) for k in data.keys()][:80]
    deps: list[str] = []
    scripts: list[str] = []
    for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        values = data.get(field)
        if isinstance(values, dict):
            deps.extend(str(k) for k in values.keys())
    if isinstance(data.get("scripts"), dict):
        scripts = [str(k) for k in data["scripts"].keys()][:80]
    return top_keys, list(dict.fromkeys(deps))[:160], scripts


def build_structure_only_analysis(path: str, source: str, static_analysis: dict[str, Any]) -> dict[str, Any]:
    """LLMを呼ばず、依存/設定ファイルから引き継ぎに必要なメタ情報だけ作る。"""
    name = PurePosixPath(path).name
    lower = name.lower()
    deps: list[str] = []
    facts: list[str] = []

    if re.fullmatch(r"requirements(?:[-_.][\w.-]+)?\.txt", lower):
        deps = _requirement_names(source)
        facts.append(f"Python依存候補 {len(deps)} 件")
    elif name in {"pyproject.toml", "Cargo.toml"}:
        keys, deps = _toml_metadata(source)
        if keys:
            facts.append("トップレベルキー: " + ", ".join(keys[:20]))
    elif name in {"package.json", "package-lock.json", "tsconfig.json"}:
        keys, deps, scripts = _json_metadata(source)
        if keys:
            facts.append("トップレベルキー: " + ", ".join(keys[:20]))
        if scripts:
            facts.append("scripts: " + ", ".join(scripts[:20]))
    elif name == ".env.example":
        keys = _env_keys(source)
        facts.append(f"環境変数キー {len(keys)} 件: " + ", ".join(keys[:40]))
    elif name in {".gitignore", ".dockerignore"}:
        patterns = [line.strip() for line in source.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        facts.append(f"除外パターン {len(patterns)} 件")
    elif name == "__init__.py":
        imports = static_analysis.get("imports") or []
        facts.append(f"パッケージ初期化/公開API。import {len(imports)} 件")
    else:
        nonempty = sum(1 for line in source.splitlines() if line.strip())
        facts.append(f"非空行 {nonempty} 行")

    purpose_map = {
        "requirements.txt": "Python依存パッケージ定義",
        "pyproject.toml": "Pythonプロジェクト/ビルド設定",
        "package.json": "Node.jsプロジェクト/依存・スクリプト設定",
        "package-lock.json": "Node.js依存関係ロック",
        "tsconfig.json": "TypeScriptコンパイラ設定",
        ".env.example": "環境変数の設定例",
        ".gitignore": "Git除外設定",
        ".dockerignore": "Dockerビルドコンテキスト除外設定",
        "Cargo.toml": "Rustパッケージ/依存設定",
        "Cargo.lock": "Rust依存関係ロック",
        "go.mod": "Goモジュール/依存設定",
        "go.sum": "Go依存整合性情報",
        "__init__.py": "Pythonパッケージ初期化・公開API定義",
    }
    purpose = purpose_map.get(name, "プロジェクトの依存・設定メタデータ")
    return {
        "purpose": purpose + "（LLM解析なし）",
        "overview": " / ".join(facts) if facts else "構造情報のみを保持しています。",
        "main_flow": [],
        "key_functions": [],
        "key_classes": [],
        "inputs": [],
        "outputs": [],
        "external_dependencies": deps,
        "related_files": [],
        "change_risks": ["このファイルは構造のみ解析しており、値や設定の意味まではLLM解釈していません。"],
        "unknowns": ["個々の設定値の意図や運用上の意味は、この構造解析だけでは判断できません。"],
        "metadata_facts": facts,
    }


def build_project_index(files: list[dict[str, Any]]) -> dict[str, Any]:
    """LLMを使わず、個別解析結果だけからプロジェクトの確定情報を集約する。"""
    language_counter: Counter[str] = Counter()
    processing_counter: Counter[str] = Counter()
    total_lines = 0
    total_chars = 0
    module_to_paths: dict[str, list[str]] = {}
    basenames: dict[str, list[str]] = {}

    for item in files:
        file_info = item.get("file", {})
        path = str(file_info.get("path") or file_info.get("name") or "")
        language = str(file_info.get("language") or "Unknown")
        mode = str((item.get("processing") or {}).get("mode") or "llm")
        language_counter[language] += 1
        processing_counter[mode] += 1
        total_lines += int(file_info.get("line_count") or 0)
        total_chars += int(file_info.get("char_count") or 0)
        if path:
            basenames.setdefault(PurePosixPath(path).name, []).append(path)
            for alias in _python_module_aliases(path):
                module_to_paths.setdefault(alias, []).append(path)

    edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str, str]] = set()

    for item in files:
        file_info = item.get("file", {})
        source_path = str(file_info.get("path") or file_info.get("name") or "")
        static = item.get("static_analysis", {})
        imports = static.get("imports") or []

        for import_text in imports:
            text = str(import_text)
            module = _extract_import_module(text)
            candidates: list[str] = []
            if module:
                resolved = _resolve_relative_module(source_path, module)
                candidates.extend(module_to_paths.get(resolved, []))
                if not candidates and resolved:
                    candidates.extend(module_to_paths.get(resolved.split(".")[-1], []))

            if not candidates:
                include_name = text.strip().strip('<>"\'')
                candidates.extend(basenames.get(PurePosixPath(include_name).name, []))

            for target in candidates:
                if not target or target == source_path:
                    continue
                key = (source_path, target, text)
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edges.append({"source": source_path, "target": target, "evidence": text})

    return {
        "file_count": len(files),
        "total_lines": total_lines,
        "total_chars": total_chars,
        "processing_counts": dict(processing_counter),
        "languages": [
            {"language": language, "files": count}
            for language, count in language_counter.most_common()
        ],
        "local_dependency_edges": edges,
        "note": "依存関係はimport/includeとプロジェクト内ファイル名の一致から機械的に推定したbest-effort結果です。動的import等は含みません。",
    }
