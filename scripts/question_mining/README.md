# Beginner Question Mining Pipeline

隊長が作業中に発した「これどういう意味？」「どこにある？」「何が違う？」のような質問を、回答と後続訂正つきでローカル候補へ戻す独立配管です。

## 責務境界

- 入力: Antigravity / Codex / Claude Code のローカル会話ログ
- 出力: `workbench/question-leads/*.md`
- 目的: 無料の初心者向け用語解説、具体的な困りごと記事の素材採掘
- 非目的: noteへの公開、下書き昇格、予約投稿、商品化判定
- 小ネタ採掘・商品採掘とはチェックポイントも出力先も共有しません

各カードは元ログのパス、ターン番号、行番号、SHA-256引用ハッシュを持ちます。回答は当時の回答候補であり、記事化前に現在の仕様で再検証します。

## 手動dry-run

```powershell
python scripts/question_mining/mine_question_leads.py --lookback-hours 168 --max-candidates 10 --dry-run
```

または:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/question_mining/run_question_miner.ps1 -DryRun
```

dry-runは出力ディレクトリ、カード、チェックポイントを作りません。

## 候補を書き出す

```powershell
python scripts/question_mining/mine_question_leads.py --lookback-hours 168 --max-candidates 10
```

## exact trace監査

```powershell
python scripts/question_mining/audit_question_leads.py
```

## Human Gate

1. カードから元ログへ戻る
2. 説明が現在も正しいか再検証する
3. 固有情報を匿名化する
4. 記事タイトルと無料/有料の置き場を人が決める
5. 選んだものだけ `voronoi-note/articles/drafts/` へ移す

Windows Task Schedulerへの登録はこの配管に含めていません。

