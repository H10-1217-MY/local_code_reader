# v1.2 → v2.0

依存Pythonパッケージは増えていません。既存の `.venv` を再利用できます。

主な変更ファイル:

- `app/main.py`
- `app/config.py`
- `app/analyzer.py`
- `app/ollama_client.py`
- `app/project_analyzer.py` (new)
- `app/templates/index.html`
- `app/static/app.js` (new)
- `app/static/style.css`

新規フォルダで試す場合は通常どおり:

```bash
./setup.sh
./run.sh
```
