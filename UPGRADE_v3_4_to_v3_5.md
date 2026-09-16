# Upgrade: v3.4 → v3.5

v3.5は、コード理解・Q&A・引き継ぎ資料生成に加えて、既存プロジェクトの環境再現を支援する **Environment Setup Mode** を追加する更新です。

## 追加したもの

- UIに「環境構築」タブを追加
- 対象OS / shell / Pythonバージョン / GPUをユーザーが指定
- `/api/project/environment/analyze-file` でOllamaを呼ばず静的スキャン
- `/api/project/environment-plan` でOS別の環境構築計画を生成
- requirements / pyproject / lockファイルをimport推定より優先
- `.python-version` と `pyproject.toml` のPython要件を構造解析
- `SETUP.md` を自動生成
- 環境変数名を確認した場合は `.env.example.generated` を生成
- 依存定義が無い場合は `requirements.candidates.txt` を全行コメントで生成

## 安全側の制約

- コマンドは自動実行しません。
- import名をそのままpipパッケージ名と断定しません。
- GPUドライバ / CUDA / ROCmは自動導入しません。
- Environment Setup Modeは追加のOllama呼び出しを行いません。
- 元ソースコード本文は生成した環境構築資料へ埋め込みません。
