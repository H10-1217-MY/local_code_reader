from __future__ import annotations

from pathlib import PurePosixPath
import shlex
from typing import Any


PYTHON_MANIFEST_PATTERNS = (
    "requirements.txt",
    "pyproject.toml",
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "uv.lock",
    ".python-version",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _paths(project_index: dict[str, Any]) -> list[str]:
    return [_text(x) for x in (project_index.get("paths") or []) if _text(x)]


def _file_map(files: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in files:
        info = item.get("file") or {}
        path = _text(info.get("path") or info.get("name"))
        if path:
            out[path] = item
    return out


def _manifest_files(paths: list[str]) -> list[str]:
    out: list[str] = []
    for path in paths:
        base = PurePosixPath(path).name
        low = base.lower()
        if (
            low == "pyproject.toml"
            or low == "pipfile"
            or low == "pipfile.lock"
            or low == "poetry.lock"
            or low == "uv.lock"
            or low == ".python-version"
            or low.startswith("requirements") and low.endswith(".txt")
        ):
            out.append(path)
    return out


def _declared_dependencies(files: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in files:
        info = item.get("file") or {}
        path = _text(info.get("path") or info.get("name"))
        base = PurePosixPath(path).name.lower()
        if not (
            base == "pyproject.toml"
            or base == "pipfile"
            or base == "pipfile.lock"
            or base == "poetry.lock"
            or base == "uv.lock"
            or base.startswith("requirements") and base.endswith(".txt")
        ):
            continue
        analysis = item.get("analysis") or {}
        for dep in analysis.get("external_dependencies") or []:
            name = _text(dep)
            key = (path, name.lower())
            if name and key not in seen:
                seen.add(key)
                rows.append({"name": name, "source": path, "basis": "dependency_manifest"})
    return rows


def _import_dependencies(files: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in files:
        info = item.get("file") or {}
        path = _text(info.get("path") or info.get("name"))
        static = item.get("static_analysis") or {}
        for dep in static.get("detected_external_dependencies") or []:
            name = _text(dep)
            key = (path, name.lower())
            if name and key not in seen:
                seen.add(key)
                rows.append({"name": name, "source": path, "basis": "static_import"})
    return rows


def _environment_variables(files: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in files:
        info = item.get("file") or {}
        path = _text(info.get("path") or info.get("name"))
        static = item.get("static_analysis") or {}
        analysis = item.get("analysis") or {}
        metadata = analysis.get("environment_metadata") or {}
        values = list(static.get("environment_variables") or []) + list(metadata.get("environment_variables") or [])
        for value in values:
            name = _text(value)
            key = (path, name)
            if name and key not in seen:
                seen.add(key)
                rows.append({"name": name, "source": path})
    return rows


def _python_version_hint(files: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    for item in files:
        info = item.get("file") or {}
        path = _text(info.get("path") or info.get("name"))
        analysis = item.get("analysis") or {}
        metadata = analysis.get("environment_metadata") or {}
        version = _text(metadata.get("python_version") or metadata.get("requires_python"))
        if version:
            return version, path
    return None, None


def _resolve_shell(target_os: str, shell: str) -> str:
    shell = _text(shell).lower() or "auto"
    if shell != "auto":
        return shell
    return "powershell" if target_os == "windows" else "bash"


def _python_commands(target_os: str, shell: str) -> tuple[str, str, str]:
    if target_os == "windows":
        python_cmd = "py"
        if shell == "powershell":
            activate = r".\.venv\Scripts\Activate.ps1"
        elif shell in {"bash", "zsh"}:
            activate = "source .venv/Scripts/activate"
        else:
            activate = r".venv\Scripts\activate.bat"
        return python_cmd, f"{python_cmd} -m venv .venv", activate
    python_cmd = "python3"
    activate = ". .venv/bin/Activate.ps1" if shell == "powershell" else "source .venv/bin/activate"
    return python_cmd, f"{python_cmd} -m venv .venv", activate


def _system_runtime_command(target_os: str, python_version: str = "") -> str | None:
    if target_os == "windows":
        match = __import__("re").search(r"(3\.\d+)", python_version or "")
        if match:
            return f"winget install -e --id Python.Python.{match.group(1)}"
        return "winget search --id Python.Python"
    commands = {
        "ubuntu_debian": "sudo apt update && sudo apt install -y python3 python3-venv python3-pip",
        "rhel_rocky_fedora": "sudo dnf install -y python3 python3-pip",
        "macos": "brew install python",
    }
    return commands.get(target_os)


def _quote_command_path(path: str, target_os: str, shell: str) -> str:
    if target_os == "windows":
        if shell == "powershell":
            return "'" + path.replace("'", "''") + "'"
        return '"' + path.replace('"', '""') + '"'
    return shlex.quote(path)


def _dependency_strategy(paths: list[str], python_cmd: str, target_os: str, shell: str) -> dict[str, str]:
    basenames = {PurePosixPath(path).name: path for path in paths}
    requirements = [p for p in paths if PurePosixPath(p).name.lower().startswith("requirements") and PurePosixPath(p).name.lower().endswith(".txt")]
    root_requirements = next((p for p in requirements if PurePosixPath(p).name.lower() == "requirements.txt"), None)

    if "uv.lock" in basenames:
        return {"kind": "uv", "source": basenames["uv.lock"], "command": "uv sync", "confidence": "high", "reason": "uv.lock を確認"}
    if "poetry.lock" in basenames:
        return {"kind": "poetry", "source": basenames["poetry.lock"], "command": "poetry install", "confidence": "high", "reason": "poetry.lock を確認"}
    if "Pipfile.lock" in basenames:
        return {"kind": "pipenv", "source": basenames["Pipfile.lock"], "command": "pipenv sync", "confidence": "high", "reason": "Pipfile.lock を確認"}
    if root_requirements:
        quoted = _quote_command_path(root_requirements, target_os, shell)
        return {"kind": "requirements", "source": root_requirements, "command": f"{python_cmd} -m pip install -r {quoted}", "confidence": "high", "reason": "requirements.txt を確認"}
    if requirements:
        first = requirements[0]
        quoted = _quote_command_path(first, target_os, shell)
        return {"kind": "requirements", "source": first, "command": f"{python_cmd} -m pip install -r {quoted}", "confidence": "medium", "reason": f"{PurePosixPath(first).name} を確認"}
    if "pyproject.toml" in basenames:
        return {"kind": "pyproject", "source": basenames["pyproject.toml"], "command": f"{python_cmd} -m pip install .", "confidence": "medium", "reason": "pyproject.toml を確認。ビルド方式の詳細は未確認"}
    if "Pipfile" in basenames:
        return {"kind": "pipenv", "source": basenames["Pipfile"], "command": "pipenv install", "confidence": "medium", "reason": "Pipfile を確認"}
    return {"kind": "import_candidates", "source": "static imports", "command": "", "confidence": "low", "reason": "依存定義ファイルが見つからないためimportから候補のみ抽出"}


def _setup_markdown(
    project_name: str,
    target: dict[str, str],
    detected: dict[str, Any],
    dependency_plan: dict[str, Any],
    commands: list[dict[str, str]],
    findings: list[dict[str, str]],
) -> str:
    command_lines = []
    for index, row in enumerate(commands, 1):
        note = f"\n   - {row['note']}" if row.get("note") else ""
        command_lines.append(f"{index}. **{row['title']}** ({row['confidence']})\n\n   ```{row.get('language', 'bash')}\n   {row['command']}\n   ```{note}")

    manifests = "\n".join(f"- `{x}`" for x in detected.get("dependency_files") or []) or "- 確認できませんでした"
    envs = "\n".join(f"- `{x['name']}` (`{x['source']}`)" for x in detected.get("environment_variables") or []) or "- 確認できませんでした"
    declared = "\n".join(f"- `{x['name']}` (`{x['source']}`)" for x in detected.get("declared_dependencies") or []) or "- 明示的な依存定義からは抽出できませんでした"
    import_only = "\n".join(f"- `{x}`" for x in dependency_plan.get("import_only_candidates") or []) or "- なし"
    finding_lines = "\n".join(f"- **{x['status'].upper()}**: {x['title']} - {x['detail']}" for x in findings) or "- 特記事項なし"

    return f"""# Setup Guide: {project_name}

> Local Code Reader v3.5 の Environment Setup Mode が、静的解析結果とユーザー指定OSから生成しました。OSコマンドは候補であり、プロジェクト固有のネイティブライブラリやドライバまでは自動確定しません。元ソース本文や環境変数の値は含めません。

## 対象環境

- OS: `{target['os_label']}`
- Shell: `{target['shell']}`
- Python指定: `{target.get('python_version') or '未指定'}`
- GPU: `{target.get('gpu') or '未指定'}`

## 確認できた依存定義ファイル

{manifests}

## 依存関係

### 明示的な依存定義から確認

{declared}

### importからのみ見つかった候補

{import_only}

> import名とPyPIパッケージ名は一致しない場合があります。上記候補をそのまま `pip install` する前に依存定義や公式ドキュメントで確認してください。

## 環境変数名

{envs}

値は安全のため資料化していません。

## 推奨セットアップ手順

{chr(10).join(command_lines) if command_lines else '自動生成できる安全なコマンドがありませんでした。'}

## 再現性チェック

{finding_lines}

## 境界

- 動的import、DI、実行時プラグイン、OSネイティブライブラリは静的解析だけでは完全に追跡できません。
- GPU/CUDA/ROCm等のバージョンはプロジェクト情報だけでは安全に確定できないため、自動インストールしません。
- `requirements*.txt` / `pyproject.toml` / lockファイルがある場合は、import推定よりそれらを優先しています。
- 生成コマンドは実行前に確認してください。v3.5はコマンドを自動実行しません。
""".strip() + "\n"


def build_environment_plan(
    project_name: str,
    project_index: dict[str, Any],
    files: list[dict[str, Any]],
    *,
    target_os: str,
    shell: str = "auto",
    python_version: str = "",
    gpu: str = "none",
) -> dict[str, Any]:
    paths = _paths(project_index)
    languages = project_index.get("languages") or []
    python_project = any(_text(row.get("language")).lower() == "python" for row in languages) or any(PurePosixPath(p).name.lower().startswith("requirements") for p in paths)
    resolved_shell = _resolve_shell(target_os, shell)
    python_cmd, create_venv, activate_venv = _python_commands(target_os, resolved_shell)
    manifests = _manifest_files(paths)
    declared = _declared_dependencies(files)
    project_external_names = {str(x).lower() for x in (project_index.get("external_dependencies") or [])}
    imported = [x for x in _import_dependencies(files) if x["name"].lower() in project_external_names]
    declared_names = {x["name"].lower() for x in declared}
    import_only = sorted({x["name"] for x in imported if x["name"].lower() not in declared_names}, key=str.lower)
    envs = _environment_variables(files)
    detected_version, version_source = _python_version_hint(files)
    dependency_plan = _dependency_strategy(paths, python_cmd, target_os, resolved_shell)
    dependency_plan["declared_dependencies"] = declared
    dependency_plan["import_only_candidates"] = import_only

    os_labels = {
        "ubuntu_debian": "Ubuntu / Debian",
        "rhel_rocky_fedora": "RHEL / Rocky / Fedora",
        "macos": "macOS",
        "windows": "Windows",
    }
    target = {
        "os": target_os,
        "os_label": os_labels.get(target_os, target_os),
        "shell": resolved_shell,
        "python_version": _text(python_version),
        "gpu": _text(gpu) or "none",
    }

    commands: list[dict[str, str]] = []
    if python_project:
        runtime_command = _system_runtime_command(target_os, _text(python_version) or detected_version or "")
        if runtime_command:
            commands.append({
                "title": "Pythonランタイムを用意",
                "command": runtime_command,
                "confidence": "medium",
                "language": "powershell" if resolved_shell == "powershell" else "bash",
                "note": "OS標準の代表的な導入例です。すでにPythonがある場合は不要です。Windowsでバージョン未確定の場合は検索コマンドだけを提示します。",
            })
        commands.append({"title": "仮想環境を作成", "command": create_venv, "confidence": "high", "language": "powershell" if resolved_shell == "powershell" else "bash", "note": "プロジェクト依存をシステムPythonから分離します。"})
        commands.append({"title": "仮想環境を有効化", "command": activate_venv, "confidence": "high", "language": "powershell" if resolved_shell == "powershell" else "bash", "note": "以降のPythonパッケージ導入はこの環境内で行います。"})
        if dependency_plan.get("command"):
            commands.append({"title": "Python依存を導入", "command": dependency_plan["command"], "confidence": dependency_plan["confidence"], "language": "powershell" if resolved_shell == "powershell" else "bash", "note": dependency_plan["reason"]})

    findings: list[dict[str, str]] = []
    if manifests:
        findings.append({"status": "ok", "title": "依存定義", "detail": f"{len(manifests)} 件の依存/バージョン管理候補ファイルを確認しました。"})
    else:
        findings.append({"status": "warning", "title": "依存定義", "detail": "requirements.txt / pyproject.toml / lockファイル等を確認できませんでした。"})
    effective_version = _text(python_version) or detected_version
    if effective_version:
        source_text = "ユーザー指定" if _text(python_version) else f"{version_source} から検出"
        findings.append({"status": "ok", "title": "Pythonバージョン", "detail": f"{effective_version} ({source_text})"})
    elif python_project:
        findings.append({"status": "warning", "title": "Pythonバージョン", "detail": "再現に必要なPythonバージョンを確定できませんでした。必要なら入力欄で指定してください。"})
    if envs and not any(PurePosixPath(p).name == ".env.example" for p in paths):
        findings.append({"status": "warning", "title": ".env.example", "detail": f"環境変数参照を {len(envs)} 件確認しましたが .env.example は解析対象にありません。"})
    elif envs:
        findings.append({"status": "ok", "title": ".env.example", "detail": "環境変数の設定例ファイルを確認しました。"})
    if import_only:
        findings.append({"status": "info", "title": "importのみの依存候補", "detail": f"{len(import_only)} 件あります。import名と配布パッケージ名の一致確認が必要です。"})
    if target["gpu"] != "none":
        findings.append({"status": "info", "title": "GPU", "detail": "GPUが指定されていますが、CUDA/ROCm/ドライバのバージョンは自動確定・自動導入しません。"})

    detected = {
        "languages": languages,
        "python_project": python_project,
        "dependency_files": manifests,
        "declared_dependencies": declared,
        "import_dependencies": imported,
        "environment_variables": envs,
        "python_version_hint": detected_version,
        "python_version_source": version_source,
        "entry_points": project_index.get("entry_point_candidates") or [],
    }

    generated_files: list[dict[str, str]] = []
    setup_md = _setup_markdown(project_name, target, detected, dependency_plan, commands, findings)
    generated_files.append({"filename": "SETUP.md", "description": "対象OS向けの環境構築手順と確認事項", "content": setup_md})
    if envs:
        env_names = list(dict.fromkeys(x["name"] for x in envs))
        env_content = "# Generated from statically detected environment variable names. Values are intentionally blank.\n" + "\n".join(f"{name}=" for name in env_names) + "\n"
        generated_files.append({"filename": ".env.example.generated", "description": "静的解析で確認した環境変数名のみ。値は空欄", "content": env_content})
    if not manifests and import_only:
        candidate_content = (
            "# Import-derived dependency candidates.\n"
            "# Import names do not always match package-index names. Verify each item before installation.\n"
            + "\n".join(f"# {name}" for name in import_only)
            + "\n"
        )
        generated_files.append({"filename": "requirements.candidates.txt", "description": "依存定義が無い場合のimport由来候補。安全のため全行コメント", "content": candidate_content})

    return {
        "project": {"name": project_name, "file_count": len(paths)},
        "target": target,
        "detected": detected,
        "dependency_plan": dependency_plan,
        "commands": commands,
        "reproducibility_findings": findings,
        "generated_files": generated_files,
        "boundaries": [
            "v3.5は環境構築コマンドを自動実行しません。",
            "import名とPython配布パッケージ名は一致しない場合があります。",
            "OSネイティブ依存、GPUドライバ、CUDA/ROCm等は静的解析だけで安全に確定できません。",
            "動的import、DI、実行時プラグインは完全には追跡できません。",
        ],
        "generation": {
            "version": "3.5",
            "source": "static_project_scan",
            "source_code_embedded": False,
            "extra_ollama_call": False,
            "auto_execute": False,
        },
    }
