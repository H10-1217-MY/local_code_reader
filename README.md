# Local Code Reader v3.1

ローカルOllamaを使い、機密ソースコードを外部LLMへ送らずに読むためのコード理解・引き継ぎ支援ツールです。


v3.1では、v3.0のプロジェクトQ&Aに **質問意図判定・関連ファイル選定・関連会話選定** を追加しました。
質問のたびにプロジェクト全体や過去会話を丸ごとOllamaへ渡すのではなく、現在の質問を優先して必要なコンテキストだけを構成します。

## v3.1: Q&A Context Router

```text
現在の質問
   ↓
質問意図を判定
   ↓
関連ファイルを選定
   ↓
必要なら依存関係の隣接ファイルを追加
   ↓
明示的なfollow-upの場合だけ関連会話を選定
   ↓
絞り込んだproject_index / verified_facts / 要約
   ↓
Ollama Q&A
   ↓
evidenceを再grounding
```

代表的な質問意図は、指定言語ファイル群、特定ファイル、関数・クラス、依存関係、変更影響、処理フロー、設定、テスト、読む順番、全体概要です。

特に、`5つのPythonファイルを詳しく` のように現在の質問だけで対象が明示されている場合は、直前の会話に `もう少し` が含まれていても過去会話を再利用しません。これにより、前の質問で貼り付けたテストコードが次の回答を支配する問題を抑えます。

過去会話は `それ / そこ / 前回 / 続き` など、明示的に会話継続が必要な質問だけで利用します。長いコード断片は履歴からそのまま再送せず、プレースホルダへ置き換えます。

Q&A応答には `context_selection` を追加し、次を確認できます。

- 判定した質問意図
- 選択したファイル
- 言語フィルタ
- 過去会話を何ターン使ったか
- 選定理由


v3.0では、v2.3のgrounding済みプロジェクト解析を土台に、**プロジェクト全体について追加質問できるQ&A機能**を追加しました。Q&A時は元ソースコードを再送せず、project_index・verified_facts・各ファイル要約だけをOllamaへ渡します。



## v3.0から継続: プロジェクト全体Q&A

プロジェクト解析後、次のような質問を横断的にできます。

- このプロジェクトをどの順番で読めばよいか
- Ollamaとの通信はどのファイル・関数が担当しているか
- `main.py`変更時にどこへ影響しそうか
- 入口から結果表示までの処理フロー

Q&AのOllama入力には元ソースを含めません。

```text
Project summary / project_index / verified_facts
                  ↓
             Ollama Q&A
                  ↓
         evidenceを静的照合
                  ↓
      回答 + 根拠 + confidence + limitations
```

回答の `evidence.path` は実在path、`evidence.symbol` は静的解析済み関数・クラスと照合します。未確認の根拠は除外して `grounding` に記録します。Q&A履歴はブラウザ側だけで保持し、JSON保存すると `project_qa_history` に含まれます。

## v3.0の考え方

```text
静的解析 = 事実の境界
      ↓
Ollama = 意味・役割の解釈
      ↓
静的解析で再照合
      ↓
未確認の固有名詞を除外
```

LLMに「全部を正しく当ててもらう」のではなく、ファイル名・関数名・クラス名・importなど機械的に確認できる情報は静的解析側を正とします。


## v2.3から引き継いだ重要点

### Grounding済み個別解析を最終JSON/UIへ反映

v2.2では `sanitize_project_files()` で未確認主張を除外していましたが、その結果はプロジェクト要約入力にだけ使われ、ブラウザが保存する `files[]` にはgrounding前の個別解析が残る経路がありました。

v2.3では `/api/project/summarize` が `files` としてgrounding済み個別解析を返し、UIもその値へ置き換えます。

```text
個別解析
  ↓
grounding
  ├→ プロジェクト要約
  ├→ 画面表示
  └→ 保存JSON
```

### 事実とAI解釈の表示分離

- 外部依存: import / require 等から静的抽出
- ローカル依存: プロジェクト内pathとの照合
- 関数・クラス: AST/軽量解析
- purpose / overview / change_risks 等: Ollamaによる意味解釈

プロジェクト個別ファイルには `verified_facts` を追加し、確認済みの外部依存・関連ファイル・関数・クラスを明示します。

## 主な変更

### 1. 個別ファイルのLLM出力を静的解析で照合

`key_functions` / `key_classes` は、静的解析に存在する名前だけ残します。

例:

```text
LLM: analyze_single_file_with_ollama()
AST: その関数は存在しない
→ 解析結果から除外
```

外部依存も、Python/JavaScriptについては import / require から機械的に抽出します。Python標準ライブラリやNode.js built-inは外部依存から除外します。

### 2. プロジェクト全体のpathを実在ファイルに限定

プロジェクト要約の次の項目は `project_index.paths` と照合します。

- `entry_points`
- `components`
- `read_first`
- `config_and_data_files`

存在しない `README.md` や `frontend.js` などをLLMが返しても、最終結果には残しません。

`architecture_flow` / `change_risks` に存在しない具体的なファイル名が混入した場合も、その項目を除外します。

### 3. Grounding report

JSONには次のような検証結果を追加します。

```json
{
  "grounding": {
    "removed_claim_count": 5,
    "file_analysis": {
      "removed_claims": []
    },
    "project_analysis": {
      "removed_claims": []
    }
  }
}
```

画面にも「静的照合で除外したLLM主張」の件数を表示します。

### 4. JavaScript静的解析改善

v2.1の汎用正規表現では、次のようなメソッド呼び出しを関数定義として誤検出することがありました。

```text
forEach
byId
querySelectorAll
```

v2.2ではJavaScript/TypeScript専用の宣言パターンを使い、主に次を取得します。

- `function foo()`
- `async function foo()`
- `const foo = () => ...`
- `const foo = async () => ...`
- `class Foo`
- `import` / `require`

### 5. CSS静的解析改善

`@media`を関数として扱わなくなりました。

代わりに次を取得します。

- CSS selector
- `@media` / `@supports` / `@keyframes` 等
- CSS custom property (`--variable`)
- `@import`

### 6. HTML参照解析

HTMLから次のローカル参照候補を取得します。

- `<script src="...">`
- `<link href="...">`
- `<img src="...">`
- `<source src="...">`

これらもプロジェクト内依存エッジの静的根拠として使います。

## セットアップ

```bash
cd local_code_reader_v3_1
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

## 機密コードの扱い

これまでと同じく、アプリ側に元ソースコードを保存しません。

```text
Browser File API
     ↓ 1 fileずつ
FastAPI (memory)
     ↓
Ollama localhost
     ↓
静的解析 + 個別要約
     ↓
Grounding
     ↓
Project summary
```

JSON保存にも元ソースコードは含みません。

ただし、OS・ブラウザ・プロキシ・Ollamaの設定やログなど別レイヤーまで含めた痕跡ゼロを保証するものではありません。機密用途では `127.0.0.1` のまま外部公開せず運用してください。

## v3.1時点の制限

- PythonはASTで詳細解析しますが、JavaScript/TypeScript/CSS/HTML等は依然として軽量解析です。
- JavaScriptのclass methodや動的importなど、すべての構文を完全には追跡しません。
- import/reference依存はbest-effortで、DI・設定経由・動的ロードは追跡しません。
- 自由文の意味解釈そのものはLLMが担当するため、固有名詞以外の誤解釈が完全になくなるわけではありません。
- プロジェクトQ&Aは解析済み情報だけを使うため、元ソースにしかない細かな式・条件分岐までは断定できません。必要なら1ファイルQ&Aで掘り下げます。

## テスト

```bash
python -m pytest -q
```

v3.1では、これらに加えて質問意図判定、指定言語ファイル全件選定、変更影響時の依存隣接選定、独立質問で過去会話を混ぜないこと、長い過去コードを再送しないことをテストします。
