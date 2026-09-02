# Local Code Reader v2.1

ローカルOllamaを使い、機密ソースコードを外部LLMへ送らずに読むためのコード理解・引き継ぎ支援ツールです。

v2.1では、v1.2の「1ファイル解析 + 追加質問」を残したまま、**プロジェクトフォルダ単位の解析**を追加しました。

## v2.1でできること

### 1ファイル解析

- Pythonは `ast` でimport、関数、クラス、行範囲、呼び出し先を静的解析
- その他の言語は軽量パターン解析
- 静的解析結果とOllama解釈を分離表示
- 解析したファイルについて追加質問
- JSON保存

### プロジェクト解析

ブラウザでフォルダを選ぶと次の順番で処理します。

```text
project/
  app/main.py
  app/analyzer.py
  config.yaml
  README.md
       ↓
対象ファイル抽出
       ↓
各ファイルを1つずつ静的解析 + Ollama要約
       ↓
解析結果だけを集約
       ↓
import/includeからローカル依存関係をbest-effortで照合
       ↓
Ollamaがプロジェクト全体を要約
```

画面には次を表示します。

- プロジェクトの目的・概要
- 総ファイル数 / 総行数 / 言語内訳
- プロジェクト内のローカル依存関係
- 処理・データフロー
- 入口になりそうなファイル
- 主要コンポーネント
- 引き継ぎ時に最初に読むファイル候補
- 設定・データ・資料
- 外部依存
- 変更時の注意
- まだ判断できない点
- 各ファイルの個別要約

## 機密コードの扱い

v2.1でもアプリ側にソースコードを保存しません。

プロジェクト解析では、ブラウザが対象ファイルを1つずつ `localhost` のFastAPIへ送信し、各ファイルの解析が終わると、プロジェクト全体の要約には**元ソースではなく個別解析結果だけ**を送ります。

```text
Browser File API
     ↓ 1 fileずつ
FastAPI (memory)
     ↓
Ollama localhost
     ↓
個別解析JSON
     ↓
Project index + project summary
```

JSON保存にもソースコード本体は含めません。

ただし、OS・ブラウザ・プロキシ・Ollamaの設定やログなど別レイヤーまで含めて痕跡ゼロを保証するものではありません。機密用途では `127.0.0.1` のまま外部公開せず運用してください。

## v2.1の対象除外

ブラウザ側で代表的な生成物・環境フォルダを除外します。

- `.git`
- `.venv` / `venv` / `env`
- `node_modules`
- `__pycache__`
- `build` / `dist`
- `.idea` / `.vscode`
- pytest / mypy / ruff系キャッシュ

対象ファイル数の初期上限は40ファイルです。環境変数 `MAX_PROJECT_FILES` で変更できます。

## セットアップ

```bash
cd local_code_reader_v2_0
./setup.sh
./run.sh
```

ブラウザ:

```text
http://127.0.0.1:8000
```

Ollamaが既に動いているかは次で確認できます。

```bash
curl http://127.0.0.1:11434/api/tags
```

## 設定

`.env.example` または環境変数で変更できます。

```text
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:8b
MAX_FILE_BYTES=2097152
MAX_PROJECT_FILES=40
REQUEST_TIMEOUT_SECONDS=300
```

## v2.1時点の制限

- プロジェクト解析はファイルごとにOllamaを呼ぶため、大きなプロジェクトでは時間がかかります。
- Python以外の静的解析はまだ簡易版です。
- import/includeによる依存関係はbest-effortであり、動的import、DI、設定経由の参照などは追跡しません。
- v2.1では**プロジェクト全体への追加質問**はまだありません。次段階で追加予定です。

## 次の候補

v2.1では、プロジェクト解析結果に対して次のような質問ができる形へ発展できます。

```text
「このシステムの起動点は？」
「Ollamaとの通信はどこ？」
「この変更はどのファイルへ影響しそう？」
「新人が最初に読む順番を詳しく教えて」
```


## v2.1 smart filtering

プロジェクトフォルダを選択したあと、ファイルを次のように振り分けます。

- `llm`: コードやREADMEなど。静的解析 + Ollama個別要約
- `structure`: 依存定義、lock、ignore、単純な `__init__.py` など。LLMを使わずメタデータだけ抽出
- `skip`: 空/空白のみのファイルなど
- `exclude`: キャッシュ/生成物/未対応形式/上限超過など

`__init__.py` はファイル名だけで一律除外しません。空ならskip、importや `__all__` 等だけならstructure、実行ロジックがあればllmへ回します。
