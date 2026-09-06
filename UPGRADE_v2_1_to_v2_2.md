# v2.1 → v2.2

主な変更はLLM出力のgroundingです。

- 実在しない関数/クラスを個別解析から除外
- 実在しないプロジェクトpathを全体要約から除外
- 外部依存を静的import/依存定義から生成
- JavaScriptの関数誤検出を低減
- CSS専用解析を追加
- HTMLのローカルresource参照を依存関係に利用
- `grounding.removed_claim_count` をJSONへ追加

依存パッケージはv2.1から増えていません。新規展開なら通常どおり `./setup.sh` を実行してください。
