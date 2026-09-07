# Local Code Reader v2.3

ローカルOllamaを使い、機密ソースコードを外部LLMへ送らずに読むためのコード理解・引き継ぎ支援ツールです。

v2.3では v2.2 のgroundingを最終出力まで一貫して適用し、**UIと保存JSONにも検証済みの個別ファイル解析だけを残す**ようにしました。さらに、外部依存や参照関係を静的解析側へ寄せ、AI解釈との境界を明確化しています。

## v2.3の考え方

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


## v2.3で直した重要点

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
cd local_code_reader_v2_3
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

## v2.3時点の制限

- PythonはASTで詳細解析しますが、JavaScript/TypeScript/CSS/HTML等は依然として軽量解析です。
- JavaScriptのclass methodや動的importなど、すべての構文を完全には追跡しません。
- import/reference依存はbest-effortで、DI・設定経由・動的ロードは追跡しません。
- 自由文の意味解釈そのものはLLMが担当するため、固有名詞以外の誤解釈が完全になくなるわけではありません。
- プロジェクト全体への追加質問はまだ未実装です。

## テスト

```bash
python -m pytest -q
```

v2.3では、grounding済み個別解析が最終レスポンスへ反映されることまでテストします。
