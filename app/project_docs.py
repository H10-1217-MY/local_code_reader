from __future__ import annotations

import re
from typing import Any

from .ollama_client import _derive_static_file_role, _handover_reading_order

DOCUMENT_FILENAMES = ("README.md", "ARCHITECTURE.md", "HANDOVER.md")
_ROUTE_RE = re.compile(r"(?:^|\.)?(get|post|put|patch|delete|options|head)\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _code(value: Any) -> str:
    return f"`{_text(value).replace('`', "'")}`"


def _bullet(values: list[str], empty: str = "確認できませんでした。") -> str:
    cleaned = [_text(x) for x in values if _text(x)]
    if not cleaned:
        return f"- {empty}"
    return "\n".join(f"- {x}" for x in cleaned)


def _numbered(values: list[str], empty: str = "確認できませんでした。") -> str:
    cleaned = [_text(x) for x in values if _text(x)]
    if not cleaned:
        return f"1. {empty}"
    return "\n".join(f"{i}. {x}" for i, x in enumerate(cleaned, start=1))


def _file_map(files: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in files:
        file_info = item.get("file") or {}
        path = _text(file_info.get("path") or file_info.get("name"))
        if path:
            result[path] = item
    return result


def _role_for(path: str, item: dict[str, Any], project_index: dict[str, Any]) -> str:
    file_info = item.get("file") or {}
    static = item.get("static_analysis") or {}
    verified = item.get("verified_facts") or {}
    role = _derive_static_file_role(
        path,
        _text(file_info.get("language")),
        static,
        verified,
        project_index,
    )
    return _text(role) or "役割は静的情報だけでは特定できません。"


def _roles(files: list[dict[str, Any]], project_index: dict[str, Any]) -> list[dict[str, str]]:
    by_path = _file_map(files)
    rows: list[dict[str, str]] = []
    for path in project_index.get("paths") or []:
        p = _text(path)
        item = by_path.get(p)
        if not item:
            continue
        rows.append({"path": p, "role": _role_for(p, item, project_index)})
    return rows


def _tree(paths: list[str]) -> str:
    root: dict[str, Any] = {}
    for raw in paths:
        parts = [p for p in _text(raw).split("/") if p]
        cursor = root
        for part in parts:
            cursor = cursor.setdefault(part, {})

    lines: list[str] = []

    def walk(node: dict[str, Any], prefix: str = "") -> None:
        items = list(node.items())
        for i, (name, child) in enumerate(items):
            last = i == len(items) - 1
            lines.append(f"{prefix}{'└── ' if last else '├── '}{name}")
            if child:
                walk(child, prefix + ("    " if last else "│   "))

    walk(root)
    return "\n".join(lines) if lines else "(解析対象なし)"


def _routes(files: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in files:
        file_info = item.get("file") or {}
        path = _text(file_info.get("path") or file_info.get("name"))
        static = item.get("static_analysis") or {}
        for fn in static.get("functions") or []:
            symbol = _text(fn.get("qualified_name") or fn.get("name"))
            for decorator in fn.get("decorators") or []:
                match = _ROUTE_RE.search(_text(decorator))
                if not match:
                    continue
                method, route = match.group(1).upper(), match.group(2)
                key = (path, method, route, symbol)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"path": path, "method": method, "route": route, "symbol": symbol})
    return rows


def _environment_variables(files: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in files:
        file_info = item.get("file") or {}
        path = _text(file_info.get("path") or file_info.get("name"))
        static = item.get("static_analysis") or {}
        for name in static.get("environment_variables") or []:
            key = (path, _text(name))
            if key[1] and key not in seen:
                seen.add(key)
                rows.append({"path": path, "name": key[1]})
    return rows


def _top_level_definitions(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in files:
        file_info = item.get("file") or {}
        path = _text(file_info.get("path") or file_info.get("name"))
        static = item.get("static_analysis") or {}
        names = [_text(x) for x in (static.get("top_level_assignments") or []) if _text(x)]
        if names:
            rows.append({"path": path, "names": names})
    return rows


def _setup_related_files(paths: list[str]) -> list[str]:
    hints = (
        "requirements.txt", "requirements-dev.txt", "requirements-test.txt", "pyproject.toml",
        "setup.py", "setup.cfg", "package.json", "Dockerfile", "Makefile", "CMakeLists.txt",
        "Pipfile", "poetry.lock", "uv.lock", "run.sh", "setup.sh", ".env.example",
    )
    result: list[str] = []
    for path in paths:
        base = _text(path).rsplit("/", 1)[-1]
        if base in hints:
            result.append(_text(path))
    return result


def _reading_order(files: list[dict[str, Any]], project_index: dict[str, Any]) -> list[dict[str, str]]:
    paths = [_text(x) for x in (project_index.get("paths") or []) if _text(x)]
    raw = _handover_reading_order(paths, project_index)
    by_path = _file_map(files)
    result: list[dict[str, str]] = []
    for row in raw:
        if isinstance(row, dict):
            path = _text(row.get("path"))
            reason = _text(row.get("reason"))
        elif isinstance(row, (tuple, list)) and row:
            path = _text(row[0])
            reason = _text(row[1] if len(row) > 1 else "")
        else:
            path, reason = _text(row), ""
        if not path or path not in by_path:
            continue
        role = _role_for(path, by_path[path], project_index)
        result.append({"path": path, "reason": reason, "role": role})
    return result


def _dependency_lines(project_index: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for edge in project_index.get("local_dependency_edges") or []:
        source = _text(edge.get("source"))
        target = _text(edge.get("target"))
        evidence = _text(edge.get("evidence"))
        if source and target:
            suffix = f"  根拠: {evidence}" if evidence else ""
            result.append(f"{_code(source)} → {_code(target)}{suffix}")
    return result


def _language_lines(project_index: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for row in project_index.get("languages") or []:
        language = _text(row.get("language"))
        count = row.get("files")
        if language:
            result.append(f"{language}: {count} files")
    return result


def _project_note() -> str:
    return (
        "> この文書は Local Code Reader v3.5 がプロジェクト解析結果から生成しました。"
        "ファイル名・言語・関数/クラス・依存関係・APIルート・環境変数名などは静的解析を優先し、"
        "目的・概要・変更リスクなどには解析時のAI解釈が含まれます。元ソースコード本文は文書へ埋め込みません。"
    )


def _readme(project_name: str, project_index: dict[str, Any], project_analysis: dict[str, Any], files: list[dict[str, Any]]) -> str:
    paths = [_text(x) for x in (project_index.get("paths") or []) if _text(x)]
    roles = _roles(files, project_index)
    setup_files = _setup_related_files(paths)
    purpose = _text(project_analysis.get("purpose")) or "この解析結果だけではプロジェクト目的を確定できません。"
    overview = _text(project_analysis.get("overview"))
    deps = [_text(x) for x in (project_index.get("external_dependencies") or []) if _text(x)]
    role_lines = [f"{_code(row['path'])}: {row['role']}" for row in roles]
    setup_text = _bullet([_code(x) for x in setup_files], "解析対象内にセットアップ/起動候補ファイルは確認できませんでした。起動コマンドは元リポジトリ側で確認してください。")

    return f"""# {project_name}

{_project_note()}

## 概要

{purpose}

{overview}

## 解析時点の規模

- 解析対象ファイル: {project_index.get('file_count', len(paths))}
- 総行数: {project_index.get('total_lines', 0)}
- 言語:
{_bullet(_language_lines(project_index))}

## プロジェクト構成

```text
{_tree(paths)}
```

### ファイルの役割

{_bullet(role_lines)}

## 外部依存

{_bullet([_code(x) for x in deps], "静的解析で外部依存は確認できませんでした。")}

## セットアップ・起動

解析結果だけから実行コマンドを推測していません。確認できたセットアップ/起動候補ファイルは次の通りです。

{setup_text}

## 主要な入口

{_bullet([f"{_code(row.get('path'))}: {_text(row.get('evidence'))}" for row in (project_index.get('entry_point_candidates') or []) if _text(row.get('path'))], "静的解析で入口候補は確認できませんでした。")}

## 詳細資料

- `ARCHITECTURE.md`: 依存関係、APIルート、設定、処理フロー
- `HANDOVER.md`: 引き継ぎ時の読む順番、変更リスク、未確認事項
""".strip() + "\n"


def _architecture(project_name: str, project_index: dict[str, Any], project_analysis: dict[str, Any], files: list[dict[str, Any]]) -> str:
    routes = _routes(files)
    envs = _environment_variables(files)
    top_defs = _top_level_definitions(files)
    roles = _roles(files, project_index)
    route_lines = [f"`{r['method']} {r['route']}` → {_code(r['path'])} / {_code(r['symbol'])}" for r in routes]
    env_lines = [f"{_code(row['name'])} 参照元: {_code(row['path'])}" for row in envs]
    top_lines = [f"{_code(row['path'])}: {', '.join(_code(x) for x in row['names'])}" for row in top_defs]
    component_lines = [f"{_code(row['path'])}: {row['role']}" for row in roles]
    flow = [_text(x) for x in (project_analysis.get("architecture_flow") or []) if _text(x)]
    config_files = [_text(x) for x in (project_analysis.get("config_and_data_files") or []) if _text(x)]

    return f"""# Architecture: {project_name}

{_project_note()}

## コンポーネント

{_bullet(component_lines)}

## ローカル依存関係

{_bullet(_dependency_lines(project_index), "静的import/include/HTML参照によるローカル依存エッジは確認できませんでした。")}

## APIルート

{_bullet(route_lines, "静的解析でAPIルートは確認できませんでした。")}

## 環境変数名

値は記録せず、参照される変数名だけを掲載しています。

{_bullet(env_lines, "静的解析で環境変数参照は確認できませんでした。")}

## トップレベル定義

{_bullet(top_lines, "静的解析でトップレベル定義名は確認できませんでした。")}

## 処理・データフロー

以下はプロジェクト解析時のAI解釈です。静的依存グラフと併せて確認してください。

{_numbered(flow)}

## 外部依存

{_bullet([_code(x) for x in (project_index.get('external_dependencies') or []) if _text(x)], "静的解析で外部依存は確認できませんでした。")}

## 設定・データ・資料候補

{_bullet([_code(x) for x in config_files], "プロジェクト解析結果では重要な設定・データ・資料ファイルを特定できませんでした。")}

## 解析上の境界

- ローカル依存関係は静的import/include/HTML・CSS・JS参照によるbest-effortです。
- 動的import、DI、設定経由の結線、実行時に生成される依存関係は完全には追跡できません。
- APIルートは静的に読めるデコレータ等から抽出したものだけです。
- 目的や処理フローの文章にはAI解釈を含むため、重要な変更前には元コードで確認してください。
""".strip() + "\n"


def _handover(project_name: str, project_index: dict[str, Any], project_analysis: dict[str, Any], files: list[dict[str, Any]]) -> str:
    order = _reading_order(files, project_index)
    order_lines = [f"{_code(row['path'])}  \n   理由: {row['reason'] or '依存関係と入口候補からのbest-effort'}  \n   役割: {row['role']}" for row in order]
    risks = [_text(x) for x in (project_analysis.get("change_risks") or []) if _text(x)]
    unknowns = [_text(x) for x in (project_analysis.get("unknowns") or []) if _text(x)]
    envs = _environment_variables(files)
    routes = _routes(files)
    env_lines = [f"{_code(x['name'])} ({_code(x['path'])})" for x in envs]
    route_lines = [f"`{x['method']} {x['route']}` ({_code(x['path'])} / {_code(x['symbol'])})" for x in routes]

    return f"""# Handover Guide: {project_name}

{_project_note()}

## まず読む順番

{_numbered(order_lines, "読む順番を静的情報から構成できませんでした。")}

## 変更前に確認する依存関係

{_bullet(_dependency_lines(project_index), "ローカル依存エッジは確認できませんでした。")}

## API・外部入口

{_bullet(route_lines, "静的解析でAPIルートは確認できませんでした。")}

## 設定・環境変数

{_bullet(env_lines, "静的解析で環境変数参照は確認できませんでした。")}

## 変更時の注意

以下は解析時のAI解釈を含みます。実変更前には該当コードで再確認してください。

{_bullet(risks)}

## まだ確認できていないこと

{_bullet(unknowns)}

## 引き継ぎチェックリスト

- [ ] `README.md` の概要と解析対象範囲を確認する
- [ ] `ARCHITECTURE.md` の入口・依存関係・APIルートを確認する
- [ ] 上記の読む順番で主要ファイルを開き、静的解析結果と元コードを照合する
- [ ] 変更対象ファイルについて、依存エッジの上流・下流を確認する
- [ ] 環境変数は値ではなく名前だけが資料化されているため、実運用値は安全な管理元で確認する
- [ ] 「まだ確認できていないこと」を担当者へ確認し、必要なら資料を追記する
- [ ] 細かな条件分岐や実行時挙動は、Local Code Readerの1ファイルQ&Aまたは元コードで再確認する
""".strip() + "\n"


def generate_project_documents(
    project_name: str,
    project_index: dict[str, Any],
    project_analysis: dict[str, Any],
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    """Grounding済み解析結果から、元ソース本文なしで3種のMarkdown資料を生成する。"""
    docs = [
        {"filename": "README.md", "description": "プロジェクト概要・構成・入口・外部依存", "content": _readme(project_name, project_index, project_analysis, files)},
        {"filename": "ARCHITECTURE.md", "description": "依存関係・API・設定・処理フロー", "content": _architecture(project_name, project_index, project_analysis, files)},
        {"filename": "HANDOVER.md", "description": "読む順番・変更注意点・未確認事項・引き継ぎチェック", "content": _handover(project_name, project_index, project_analysis, files)},
    ]
    return {
        "project": {"name": project_name, "file_count": len(project_index.get("paths") or [])},
        "documents": docs,
        "generation": {
            "version": "3.5",
            "source": "grounded_project_analysis",
            "document_count": len(docs),
            "source_code_embedded": False,
            "extra_ollama_call": False,
            "note": "静的解析を骨格にし、既存のgrounding済みAI解釈だけを補助的に利用しています。資料生成時の追加LLM呼び出しはありません。",
        },
    }
