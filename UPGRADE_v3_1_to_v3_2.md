# v3.1 → v3.2

v3.2はプロジェクトQ&Aの **Answer Grounding** を強化した版です。

v3.1で質問意図・関連ファイル・会話履歴の選定は安定しましたが、LLMの回答本文には、静的解析で存在しない `ProjectIndex` / `analyze_files()` / `LLMConfig` のような名称が残る場合がありました。

v3.2では次の順序へ変更しています。

```text
質問
  ↓
Context Router (v3.1)
  ↓
関連ファイルの static_analysis / verified_facts
  ↓
サーバーが fact_catalog を生成
  ↓
Ollamaは使用する fact_id を選択
  ↓
fact_idをサーバー側で再照合
  ↓
最終回答・evidenceをfactから再構成
```

## 主な変更

- Q&A用 `fact_catalog` をサーバー側で生成
- LLMはファイル名・関数名そのものを自由生成するのではなく、`fact_id` を選ぶ
- `evidence` はLLM出力ではなく、選択済みfactからサーバー側で生成
- 回答本文中の未確認な `.py` 名、関数形式 `foo()`、CamelCaseコード名などを検出して除外
- 未確認名称が混ざった場合はconfidenceを自動的に1段階下げる
- `grounding.selected_fact_count / selected_fact_ids` をJSONへ保存
- プロジェクトQ&A履歴にも `fact_ids` を保存

元ソースコードはプロジェクトQ&A時には再送しません。関数内部の細かい分岐など、解析済み情報だけで足りない詳細参照は次段階の候補です。
