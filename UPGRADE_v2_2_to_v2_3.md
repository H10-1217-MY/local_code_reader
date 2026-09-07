# v2.2 → v2.3

主な変更:

- `/api/project/summarize` がgrounding済み `files` を返す
- ブラウザはその `files` を最終UI/JSONへ使用
- `verified_facts` を個別ファイルへ追加
- 外部依存を静的解析セクションへ移動
- 単一ファイルでは未検証の `related_files` を事実欄として表示しない
- プロジェクトLLMへ「実在する識別子名のような新語を作らない」ルールを追加

依存パッケージはv2.2から変更ありません。既存 `.venv` を再利用できます。
