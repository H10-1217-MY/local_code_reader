# Upgrade: v3.3 → v3.4

v3.4は、v3.3のgrounding済みプロジェクト解析をそのまま引き継ぎ資料へ変換する更新です。

## 追加機能

- プロジェクト解析後に `README.md` / `ARCHITECTURE.md` / `HANDOVER.md` を生成
- 新API: `POST /api/project/generate-docs`
- 資料生成時にクライアントから渡された `project_index` を盲信せず、`files` から再構築・再grounding
- Pythonデコレータから静的に確認できるAPIルートを `ARCHITECTURE.md` に掲載
- 環境変数は値を保存せず、参照名だけを掲載
- 引き継ぎ順は入口候補とローカル依存グラフからbest-effortで構成
- 資料生成のための追加Ollama呼び出しは行わない
- 元ソースコード本文は生成資料へ埋め込まない

## UI

プロジェクト結果上部の「引き継ぎ資料を生成」から3資料を生成し、プレビュー後に個別保存できます。

## 設計意図

LLMにREADME全文を書かせるのではなく、すでに検証済みの静的情報を文書の骨格として利用します。目的・概要・変更リスクなどの意味情報だけ、プロジェクト解析時にgroundingされたAI解釈を補助的に利用します。
