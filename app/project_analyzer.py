from __future__ import annotations

import ast
import json
import re
import tomllib
from collections import Counter
from pathlib import PurePosixPath
from typing import Any

from .analyzer import extract_external_dependencies
from .config import PROJECT_EXCLUDED_FILENAMES, PROJECT_STRUCTURE_ONLY_FILENAMES


PATH_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:py|pyw|js|jsx|ts|tsx|html?|css|scss|json|ya?ml|toml|ini|cfg|md|txt|xml|sh|bash|ps1|sql|java|cs|go|rs|c|cc|cpp|cxx|h|hh|hpp)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


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
            continue
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


def _path_aliases(path: str) -> set[str]:
    p = PurePosixPath(path)
    aliases = {path, p.name}
    # static/app.js -> app.js and static/app.js. Unique-basename resolution is handled later.
    return aliases


def _resolve_reference_path(source_path: str, reference: str, actual_paths: set[str]) -> str | None:
    ref = reference.strip().split("?", 1)[0].split("#", 1)[0]
    if not ref or re.match(r"^[a-z]+://", ref, re.IGNORECASE) or ref.startswith("//"):
        return None
    if ref.startswith("/"):
        ref = ref.lstrip("/")
        return ref if ref in actual_paths else None
    candidate = str((PurePosixPath(source_path).parent / ref))
    parts: list[str] = []
    for part in PurePosixPath(candidate).parts:
        if part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    normalized = "/".join(parts)
    return normalized if normalized in actual_paths else None


def _canonical_path(value: str, actual_paths: set[str], basename_map: dict[str, list[str]]) -> str | None:
    raw = value.strip().replace("\\", "/").strip("`'\" ")
    if raw in actual_paths:
        return raw
    name = PurePosixPath(raw).name
    matches = basename_map.get(name, [])
    if len(matches) == 1:
        return matches[0]
    return None


def _unsupported_path_tokens(text: str, actual_paths: set[str], basename_map: dict[str, list[str]]) -> list[str]:
    bad: list[str] = []
    for token in PATH_TOKEN_RE.findall(text or ""):
        if _canonical_path(token, actual_paths, basename_map) is None:
            bad.append(token)
    return list(dict.fromkeys(bad))


def _extract_project_external_dependencies(files: list[dict[str, Any]], local_module_roots: set[str]) -> list[str]:
    deps: list[str] = []
    for item in files:
        static = item.get("static_analysis") or {}
        for dep in extract_external_dependencies(static):
            root = dep.split(".", 1)[0]
            if root in local_module_roots:
                continue
            deps.append(dep)
        # structure-only files (requirements/package.json/etc.) are also mechanically parsed.
        processing = (item.get("processing") or {}).get("mode")
        analysis = item.get("analysis") or {}
        if processing == "structure":
            for dep in analysis.get("external_dependencies") or []:
                deps.append(str(dep))
    return list(dict.fromkeys(deps))[:240]


def build_project_index(files: list[dict[str, Any]]) -> dict[str, Any]:
    """LLMを使わず、個別解析結果だけからプロジェクトの確定情報を集約する。"""
    language_counter: Counter[str] = Counter()
    processing_counter: Counter[str] = Counter()
    total_lines = 0
    total_chars = 0
    module_to_paths: dict[str, list[str]] = {}
    basenames: dict[str, list[str]] = {}
    actual_paths: set[str] = set()
    symbols_by_file: dict[str, dict[str, list[str]]] = {}

    for item in files:
        file_info = item.get("file", {})
        path = str(file_info.get("path") or file_info.get("name") or "")
        language = str(file_info.get("language") or "Unknown")
        mode = str((item.get("processing") or {}).get("mode") or "llm")
        static = item.get("static_analysis") or {}
        language_counter[language] += 1
        processing_counter[mode] += 1
        total_lines += int(file_info.get("line_count") or 0)
        total_chars += int(file_info.get("char_count") or 0)
        if path:
            actual_paths.add(path)
            basenames.setdefault(PurePosixPath(path).name, []).append(path)
            for alias in _python_module_aliases(path):
                module_to_paths.setdefault(alias, []).append(path)
            symbols_by_file[path] = {
                "functions": [str(f.get("qualified_name") or f.get("name")) for f in (static.get("functions") or []) if f.get("name")],
                "classes": [str(c.get("qualified_name") or c.get("name")) for c in (static.get("classes") or []) if c.get("name")],
            }

    local_module_roots = {alias.split(".", 1)[0] for alias in module_to_paths}
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

        # HTML/CSS/JS local path references are static evidence too.
        for reference in static.get("references") or []:
            target = _resolve_reference_path(source_path, str(reference), actual_paths)
            if not target or target == source_path:
                continue
            text = str(reference)
            key = (source_path, target, text)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append({"source": source_path, "target": target, "evidence": text})

    external_dependencies = _extract_project_external_dependencies(files, local_module_roots)

    likely_entry_candidates: list[dict[str, str]] = []
    entry_names = {"main.py", "app.py", "__main__.py", "manage.py", "index.js", "main.js", "server.js", "index.ts", "main.ts", "server.ts"}
    for path in sorted(actual_paths):
        name = PurePosixPath(path).name
        if name in entry_names:
            likely_entry_candidates.append({"path": path, "evidence": "代表的なエントリポイント名"})
        elif path.endswith("/index.html") or path == "index.html":
            likely_entry_candidates.append({"path": path, "evidence": "Web UIのindex HTML"})

    return {
        "file_count": len(files),
        "total_lines": total_lines,
        "total_chars": total_chars,
        "processing_counts": dict(processing_counter),
        "languages": [
            {"language": language, "files": count}
            for language, count in language_counter.most_common()
        ],
        "paths": sorted(actual_paths),
        "symbols_by_file": symbols_by_file,
        "local_dependency_edges": edges,
        "external_dependencies": external_dependencies,
        "entry_point_candidates": likely_entry_candidates,
        "note": "paths/symbols/external_dependenciesは静的情報から生成。依存関係はimport/include/HTML・CSS・JSのローカル参照から機械的に推定したbest-effort結果で、動的import/DI/設定経由は含みません。",
    }


def sanitize_project_files(files: list[dict[str, Any]], project_index: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """個別LLM解析のファイル名・関数名・クラス名の幻覚をプロジェクト事実で落とす。"""
    actual_paths = set(project_index.get("paths") or [])
    basenames: dict[str, list[str]] = {}
    for path in actual_paths:
        basenames.setdefault(PurePosixPath(path).name, []).append(path)

    sanitized: list[dict[str, Any]] = []
    removed: list[dict[str, str]] = []

    for item in files:
        copy = {
            "file": dict(item.get("file") or {}),
            "processing": dict(item.get("processing") or {}),
            "static_analysis": dict(item.get("static_analysis") or {}),
            "analysis": dict(item.get("analysis") or {}),
        }
        path = str(copy["file"].get("path") or copy["file"].get("name") or "")
        static = copy["static_analysis"]
        analysis = copy["analysis"]
        fn_names = {str(f.get("name")) for f in (static.get("functions") or []) if f.get("name")}
        fn_names |= {str(f.get("qualified_name")) for f in (static.get("functions") or []) if f.get("qualified_name")}
        class_names = {str(c.get("name")) for c in (static.get("classes") or []) if c.get("name")}
        class_names |= {str(c.get("qualified_name")) for c in (static.get("classes") or []) if c.get("qualified_name")}

        good_functions: list[dict[str, Any]] = []
        for row in analysis.get("key_functions") or []:
            name = str((row or {}).get("name") or "").strip().removesuffix("()")
            if name in fn_names:
                good_functions.append(row)
            elif name:
                removed.append({"path": path, "field": "key_functions", "claim": name})
        analysis["key_functions"] = good_functions

        good_classes: list[dict[str, Any]] = []
        for row in analysis.get("key_classes") or []:
            name = str((row or {}).get("name") or "").strip()
            if name in class_names:
                good_classes.append(row)
            elif name:
                removed.append({"path": path, "field": "key_classes", "claim": name})
        analysis["key_classes"] = good_classes

        good_related: list[str] = []
        for raw in analysis.get("related_files") or []:
            value = str(raw).strip()
            canonical = _canonical_path(value, actual_paths, basenames)
            if canonical:
                good_related.append(canonical)
            else:
                # "config.py（設定）"のような付記がある場合もbasenameを探す。
                matched = None
                for token in PATH_TOKEN_RE.findall(value):
                    matched = _canonical_path(token, actual_paths, basenames)
                    if matched:
                        break
                if matched:
                    good_related.append(matched)
                elif value:
                    removed.append({"path": path, "field": "related_files", "claim": value})
        analysis["related_files"] = list(dict.fromkeys(good_related))

        # 外部依存はLLM自由回答ではなく、静的import/構造ファイルの結果を採用する。
        if (copy["processing"].get("mode") or "llm") == "structure":
            grounded_deps = [str(x) for x in analysis.get("external_dependencies") or []]
        else:
            grounded_deps = extract_external_dependencies(static)
        for old in analysis.get("external_dependencies") or []:
            if str(old) not in grounded_deps:
                removed.append({"path": path, "field": "external_dependencies", "claim": str(old)})
        analysis["external_dependencies"] = grounded_deps

        copy["analysis"] = analysis
        sanitized.append(copy)

    return sanitized, {
        "removed_claim_count": len(removed),
        "removed_claims": removed[:300],
        "note": "個別LLM解析の関数・クラス・関連ファイル・外部依存を静的情報と実在pathで照合し、未確認の主張をプロジェクト要約入力から除外しました。",
    }


def sanitize_project_analysis(analysis: dict[str, Any], project_index: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """プロジェクトLLM出力のpathを実在ファイルに限定し、自由文中の架空pathも除く。"""
    actual_paths = set(project_index.get("paths") or [])
    basenames: dict[str, list[str]] = {}
    for path in actual_paths:
        basenames.setdefault(PurePosixPath(path).name, []).append(path)

    out = dict(analysis)
    removed: list[dict[str, str]] = []

    for field in ("entry_points", "components", "read_first"):
        rows: list[dict[str, Any]] = []
        for row in out.get(field) or []:
            if not isinstance(row, dict):
                continue
            raw_path = str(row.get("path") or "")
            canonical = _canonical_path(raw_path, actual_paths, basenames)
            if canonical:
                new_row = dict(row)
                new_row["path"] = canonical
                rows.append(new_row)
            elif raw_path:
                removed.append({"field": field, "claim": raw_path})
        # path重複を落とす
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for row in rows:
            if row["path"] not in seen:
                seen.add(row["path"])
                deduped.append(row)
        out[field] = deduped

    config_files: list[str] = []
    for raw in out.get("config_and_data_files") or []:
        value = str(raw)
        canonical = _canonical_path(value, actual_paths, basenames)
        if canonical:
            config_files.append(canonical)
        else:
            matched = None
            for token in PATH_TOKEN_RE.findall(value):
                matched = _canonical_path(token, actual_paths, basenames)
                if matched:
                    break
            if matched:
                config_files.append(matched)
            elif value:
                removed.append({"field": "config_and_data_files", "claim": value})
    out["config_and_data_files"] = list(dict.fromkeys(config_files))

    # 外部依存は機械抽出結果を正とする。
    out["external_dependencies"] = list(project_index.get("external_dependencies") or [])

    # architecture_flow/change_risksは、存在しない具体的なファイル名を含む行を丸ごと落とす。
    for field in ("architecture_flow", "change_risks"):
        cleaned: list[str] = []
        for text in out.get(field) or []:
            value = str(text)
            bad = _unsupported_path_tokens(value, actual_paths, basenames)
            if bad:
                removed.append({"field": field, "claim": value})
            else:
                cleaned.append(value)
        out[field] = cleaned

    # purpose/overviewに架空pathが混じった場合はその文章を信用しない。安全なフォールバックへ。
    for field in ("purpose", "overview"):
        value = str(out.get(field) or "")
        bad = _unsupported_path_tokens(value, actual_paths, basenames)
        if bad:
            removed.append({"field": field, "claim": value})
            out[field] = "静的解析で確認できたプロジェクト構造を基に整理しています。詳細はコンポーネントと依存関係を参照してください。"

    return out, {
        "removed_claim_count": len(removed),
        "removed_claims": removed[:300],
        "note": "プロジェクトLLM出力に含まれるpathを実在ファイルへ正規化し、未確認ファイル名を含む主張を除外しました。外部依存は静的抽出結果で置換しています。",
    }
