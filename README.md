# Local Code Reader v3.5

ローカルOllamaを使い、機密ソースコードを外部LLMへ送らずに読むためのコード理解・引き継ぎ支援ツールです。


v3.5では、既存プロジェクトを静的に読み取り、ユーザーが指定したOS向けに環境構築手順を作る **Environment Setup Mode** を追加しました。環境構築モードではOllamaを呼ばず、requirements / pyproject / lock / import / 環境変数名などの確認済み情報を使います。コマンドは提案だけで、自動実行しません。

## v3.5: Environment Setup Mode

```text
プロジェクトフォルダ + 対象OS
   ↓
静的解析のみ（Ollamaなし）
   ↓
依存定義 / import / Pythonバージョン / 環境変数名を抽出
   ↓
依存定義ファイルを優先して構築方式を決定
   ↓
OS別コマンド + 再現性チェック
   ↓
SETUP.md / .env.example.generated / requirements.candidates.txt
```

- 対象OS: Ubuntu/Debian、RHEL/Rocky/Fedora、macOS、Windows
- shell: auto / bash / zsh / PowerShell / cmd
- Pythonバージョンは任意入力。`.python-version` / `pyproject.toml` からのヒントも取得
- `uv.lock` / `poetry.lock` / `Pipfile.lock` / `requirements.txt` / `pyproject.toml` を優先順位付きで利用
- importだけで見つかった依存は、配布パッケージ名と一致する保証がないため「候補」として分離
- 依存定義が無い場合は `requirements.candidates.txt` を全行コメントで生成し、自動インストール対象にはしない
- 環境変数参照を確認した場合は、値を入れず `.env.example.generated` を生成
- GPUを指定してもCUDA/ROCm/ドライバは自動確定・自動導入しない
- 生成したコマンドは一切自動実行しない
- LLMを使わない軽量スキャンなので、通常のプロジェクト要約より多い最大200ファイルまで扱う（既定値）

Environment Setup Modeは、通常のプロジェクト解析とは別タブです。環境再現に必要な事実だけを見るため、LLM個別解析やプロジェクト要約の待ち時間なしで使えます。


v3.4では、grounding済みのプロジェクト解析結果から **README.md / ARCHITECTURE.md / HANDOVER.md** を自動生成する引き継ぎ資料機能を追加しました。資料生成時に元ソースコード本文は再送せず、追加のOllama呼び出しも行いません。静的解析を文書の骨格にし、既存のgrounding済みAI解釈を補助的に利用します。

## v3.4: Grounded Handover Documents

```text
プロジェクト解析
   ↓
grounding済み files / project_index / analysis
   ↓
資料生成専用テンプレート
   ├→ README.md
   ├→ ARCHITECTURE.md
   └→ HANDOVER.md
```

- `README.md`: プロジェクト概要、構成、各ファイルの静的役割、外部依存、入口候補
- `ARCHITECTURE.md`: ローカル依存グラフ、静的APIルート、環境変数名、トップレベル定義、処理フロー
- `HANDOVER.md`: best-effortの読む順番、変更前に見る依存関係、API/設定、変更リスク、未確認事項、引き継ぎチェックリスト
- Markdown内に元ソースコード本文は埋め込まない
- 環境変数は値ではなく名前だけを資料化
- 起動コマンドは解析結果に根拠がない限り推測しない
- 目的・概要・変更リスクなどAI解釈を含む箇所は文書冒頭で明示

ブラウザのプロジェクト解析結果から **「引き継ぎ資料を生成」** を押すと3文書をプレビューでき、それぞれMarkdownとして保存できます。


v3.3では、v3.2の **Fact-grounded Answer Builder** に **Semantic Grounding** と **Intent-specific Answer Templates** を追加しました。AIによる短い結論と補足解釈の両方に `support_fact_ids` を必須化し、根拠のない意味解釈を採用しません。また、引き継ぎ順・依存関係・言語別ファイル説明などは、質問タイプごとにサーバー側で回答構造を組み立てます。

## v3.3: Semantic Grounding + Intent Templates

```text
現在の質問
   ↓
Context Router
   ↓
関連ファイル選定
   ↓
static_analysis / verified_facts
   ↓
Fact Catalog + 静的構造からの役割推定
   ↓
Ollama: fact_id + support_fact_ids を選択
   ↓
未確認の具体名・意味上の飛躍を除外
   ↓
質問タイプ別テンプレートで最終回答を構成
```

主な変更点:

- `summary` と `interpretations` を `{text, support_fact_ids}` 形式に変更し、根拠factがないAI結論・解釈は除外
- `.env` など、選定済み事実にない具体的な設定ファイル名を意味解釈から除外
- Python静的解析でトップレベル定義名、環境変数名、関数デコレータを追加抽出
- FastAPI風デコレータからAPIルートを静的fact化し、存在しないAPIパスのAI補足を除外
- Fact Catalogに関数内呼び出し候補、デコレータ、APIルート、環境変数名、トップレベル定義を追加
- full Fact Catalogはサーバー側で全件保持し、Ollamaへ渡す候補だけ最大180件へrank。巨大な1ファイルが後続ファイルのfactを押し出す問題を回避
- ファイル名・import・確認済みシンボルから `derived_role` を生成し、役割説明の骨格を静的情報側へ移動
- 「5つのPythonファイル」のような質問では各ファイルの役割と代表シンボルを定型表示
- 「引き継ぎ時の読む順番」では、小規模プロジェクトなら全ファイルを対象に、入口候補→設定→解析→クライアント→プロジェクト処理→UIの順を依存グラフからbest-effortで構成
- 依存関係・変更影響・処理フローでは、LLM自由文より静的依存エッジや確認済み関数を優先

`grounding.semantic_grounding` には、採用されたsummaryの根拠factと、採用されたAI解釈・各 `support_fact_ids` が保存されます。


v3.2では、v3.1の **Q&A Context Router** に **Answer Grounding** を追加しました。質問に関連するファイルを選んだあと、静的解析とverified_factsからサーバー側で `fact_catalog` を作り、Ollamaには回答に使う `fact_id` を選ばせます。最終回答とevidenceはそのfactから再構成するため、LLMが存在しない関数名やクラス名を本文へ混ぜる問題を抑えます。

## v3.2: Fact-grounded Answer Builder

```text
現在の質問
   ↓
v3.1 Context Router
   ↓
関連ファイルを選定
   ↓
static_analysis / verified_facts
   ↓
fact_catalogを機械生成
   ↓
Ollamaはfact_idを選択 + 短い解釈
   ↓
fact_idを再照合
   ↓
最終回答 / evidenceをサーバー側で再構成
```

たとえばLLMが `ProjectIndex` や `analyze_files()` のような未確認名称を書いても、fact_catalogに存在しない名称は回答本文から除外されます。反対に、`analyze_with_ollama` や `ask_project_with_ollama` のように静的解析で存在確認できたシンボルは、行番号付きfactとして回答根拠に利用できます。

Q&A結果には `fact_ids` と `grounding.selected_fact_count` が残るため、「何を根拠に答えたか」を後から追跡できます。


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
cd local_code_reader_v3_5
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

## v3.5時点の制限

- PythonはASTで詳細解析しますが、JavaScript/TypeScript/CSS/HTML等は依然として軽量解析です。
- JavaScriptのclass methodや動的importなど、すべての構文を完全には追跡しません。
- import/reference依存はbest-effortで、DI・設定経由・動的ロードは追跡しません。
- 自由文の意味解釈そのものはLLMが担当するため、固有名詞以外の誤解釈が完全になくなるわけではありません。
- プロジェクトQ&Aは解析済み情報だけを使うため、元ソースにしかない細かな式・条件分岐までは断定できません。必要なら1ファイルQ&Aで掘り下げます。
- Environment Setup ModeのOSコマンドは代表例です。プロジェクト固有のapt/dnf/brewパッケージまでは自動確定しません。
- import名とPyPIパッケージ名は一致しない場合があるため、依存定義がないプロジェクトでは候補だけを提示します。
- CUDA / ROCm / GPUドライバはバージョン不整合の影響が大きいため自動導入しません。

## テスト

```bash
python -m pytest -q
```

v3.5では、これらに加えてEnvironment Setup Modeの依存戦略、import由来候補の分離、`.python-version` / `pyproject.toml` のPython要件抽出、元ソース本文をSETUP資料へ混入させないことをテストします。
