# v1 → v1.1 更新メモ

主な変更ファイル:

- `app/analyzer.py`
- `app/ollama_client.py`
- `app/main.py`
- `app/templates/index.html`
- `app/static/style.css`
- `run.sh`
- `setup.sh`
- `tests/test_analyzer.py`
- `README.md`

既存v1へ上書きする場合、`.venv` や解析対象コードをコピーする必要はありません。
`run.sh` の修正だけでも、Condaの `(base)` が有効な状態で `.venv` のUvicornを確実に使えるようになります。

更新後は一度サーバーを停止し、次で再起動してください。

```bash
./run.sh
```

依存ライブラリはv1から追加していないため、通常は `./setup.sh` の再実行は不要です。
