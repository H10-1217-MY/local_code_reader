# v2.3 → v3.0

- プロジェクト全体Q&A (`POST /api/project/ask`) を追加
- Q&A時は元ソースを再送せず、grounding済み解析結果のみ利用
- 回答を answer / evidence / confidence / limitations に構造化
- evidenceのpath/symbolをproject_indexで再照合
- Q&A履歴をproject_qa_historyとしてJSON保存可能
