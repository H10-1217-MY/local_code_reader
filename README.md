# Local Code Reader v1

ソースコードを外部のLLMサービスへ送らず、ローカルのOllamaで「このファイルは何をしているか」を説明するための最小構成です。

## v1でできること

- 1ファイルをブラウザから読み込み
- Pythonは `ast` で関数・クラス・importを静的解析
- その他の言語は軽量なパターン解析
- 静的解析結果 + ソースコードをローカルOllamaへ渡して意味解析
- 役割、処理フロー、主要関数・クラス、入出力、依存、変更時の注意点、不明点を表示
- 解析結果だけをJSONとしてブラウザから保存
- multipart一時ファイルを避け、ソースコードはHTTP本文をメモリ上で処理
- アプリ側ではソースコードをファイル保存しない

## 対応拡張子

Python / C / C++ / JavaScript / TypeScript / Java / C# / Go / Rust / JSON / YAML / TOML / INI / Shell / PowerShell / SQL / Markdown / Text など。

Python以外の静的解析はv1では簡易版です。LLM側の意味解析と組み合わせて使います。

## 前提

- Python 3.11+ 推奨
- Ollamaがローカルで起動していること
- 使用するモデルが `ollama list` に存在すること

例:

```bash
ollama list
```

モデルがなければ例として:

```bash
ollama pull qwen3:8b
```

より丁寧なコード説明を優先する場合は、手元のGPU/RAMに余裕があれば `qwen3:14b` などへ変更できます。

## セットアップ

一括セットアップ:

```bash
cd local_code_reader_v1
./setup.sh
```

手動で行う場合:

```bash
cd local_code_reader_v1
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Ollamaを起動しておきます。

```bash
ollama serve
```

別ターミナルでアプリを起動します。

```bash
./run.sh
```

または:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

ブラウザで `http://127.0.0.1:8000` を開きます。

## モデル変更

画面上でモデル名を変更できます。環境変数でデフォルトを変える場合:

```bash
export OLLAMA_MODEL=qwen3:14b
./run.sh
```

`.env.example` は設定例です。v1は追加ライブラリを増やさないため `.env` 自動読込はしていません。

## データの流れ

```text
ブラウザでファイル選択
        ↓
FastAPI（生のHTTP本文をメモリ上で読込）
        ↓
静的解析
        ↓
localhost:11434 / Ollama
        ↓
構造化JSON
        ↓
ブラウザへ解析結果を表示
```

このアプリ自身にはソースコードをディスク保存する処理を入れておらず、アップロードも multipart/UploadFile を避けて生のHTTP本文として読みます。ただし、OS、ブラウザ、プロキシ、ログ設定など別レイヤーの運用条件まで含めた「絶対に痕跡が残らない」という保証ではありません。機密コードで使う場合は `127.0.0.1` のまま運用し、外部公開しないでください。

## v2以降の想定

### v2: フォルダ解析

```text
project/
  main.py
  detector.py
  config.yaml
      ↓
各ファイルを個別解析
      ↓
.project_reader/index.json
```

各ファイルのソース全文ではなく、次のような構造化メタデータを保存します。

```json
{
  "file": "detector.py",
  "language": "Python",
  "purpose": "...",
  "functions": [],
  "classes": [],
  "imports": [],
  "related_files": [],
  "change_risks": []
}
```

### v3: プロジェクト構造

- import / include 関係
- エントリーポイント候補
- 設定ファイル
- データの流れ
- 外部サービス
- ファイル依存グラフ

### v4: プロジェクトQ&A

- 「最初に読むべきファイルは？」
- 「CSV出力を変更するならどこ？」
- 「この関数を変えるとどこに影響する？」
- 「このシステムの起動処理は？」

### v5: 引き継ぎ資料生成

- `README.md`
- `ARCHITECTURE.md`
- `SETUP.md`
- `HANDOVER.md`

をコード・設定・既存ドキュメントから生成する方向へ拡張します。

## セキュリティ上の意図

LLMへの送信先はデフォルトで `http://127.0.0.1:11434` のOllamaだけです。また、コード中のコメント等をLLMへの命令として扱わないよう、システムプロンプトで「解析対象データ」と明示しています。

ただし、将来フォルダ読み込みやGit連携を足す場合は、`.env`、秘密鍵、認証情報、巨大ファイル、`.git`、ビルド生成物などを確実に除外する仕組みを先に入れるのがおすすめです。
