# v2.0 → v2.1

プロジェクト解析の前処理を改善しました。

- 空/空白のみのファイルはエラーではなく `skip`
- 空の `__init__.py` も自動スキップ
- import / `__all__` / 定数中心の `__init__.py` は `structure` としてLLM個別解析を省略
- requirements / pyproject / package.json / lock / ignore / `.env.example` などは構造のみ解析
- `.DS_Store` / `.gitkeep` / minified JS/CSS などは除外
- 画面に `LLM解析 / 構造のみ / スキップ / 除外` 件数を表示
- JSONに各ファイルの `processing.mode` と、skip/exclude一覧を保存

既存の起動方法は変わりません。
