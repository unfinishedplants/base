# Product Lead Mining Pipeline (`scripts/product_mining/`)

Multi-Agent（Antigravity / Codex / Claude Code）の作業セッションログから、現場のリアルなトラブルシューティング、根本原因の特定、および検証済みの修正ノウハウを決定論的（1st-stage: LLM/API不使用）に抽出・構造化し、有料記事やエージェントSkill等の商品リード候補（`workbench/product-leads/`）として採掘するパイプラインです。

---

## 1. 小ネタマイナー（`scripts/koneta/`）との分離

| 観点 | 小ネタマイナー (`koneta`) | 商品リードマイナー (`product_mining`) |
| :--- | :--- | :--- |
| **目的** | 会話の面白さ、人間味、短文インサイトの抽出 | 課題解決、トラブルシュート手順、アセット化・商品化 |
| **スコア基準** | ユーモア、会話の温度感、意外性 | 苦痛度、市場規模、再発性、**検証済み修正の確実さ** |
| **出力単位** | 単一発言・短い掛け合い | 課題発生から検証完了までの一連の**Episode** |
| **成果物形態** | Xポスト、小ネタストック | 300円有料記事、チートシート、検証スクリプト、エージェントSkill |

---

## 2. コマンドライン実行方法

### 基本実行（直近24時間のログを採掘して最大5件生成）
```bash
python scripts/product_mining/mine_product_leads.py
```

### Dry-Run（ファイル書き込み・ディレクトリ生成・チェックポイント更新を行わず、検出結果のみ確認）
```bash
python scripts/product_mining/mine_product_leads.py --dry-run
```
> **Dry-Run 保証**: `--dry-run` 実行時は出力ディレクトリ（`workbench/product-leads/`）、ログ、およびチェックポイントファイルの作成・変更は一切行われません。

### 期間・件数・出力先の指定
```bash
# 直近48時間のログから最大10件を採掘
python scripts/product_mining/mine_product_leads.py --lookback-hours 48 --max-candidates 10

# 強制再採掘（チェックポイントを無視、ただし既存カードの破壊的上書きは行わない）
python scripts/product_mining/mine_product_leads.py --force
```

### 監査（Trace Integrity & Semantic Validity）
```bash
# 生成された候補カードの trace integrity と semantic validity を両面から監査
python scripts/product_mining/audit_product_leads.py

# トレース整合性のみ監査
python scripts/product_mining/audit_product_leads.py --trace-only

# セマンティック妥当性のみ監査
python scripts/product_mining/audit_product_leads.py --semantic-only
```

---

## 3. エピソード構造化と決定論的境界制御

### (1) 時間差＋決定論的トピックシグナルによるEpisode境界切断
同一セッション（`platform` × `session_id`）であっても、固定ターン窓（3ターン）だけに頼らず、以下の2つの決定論的境界判定を行います：
1. **時間差切断（Time Gap Break）**: ターン間の時間差が **30分（1,800秒）** を超える場合、別インシデントと判定してEpisodeを強制切断します（12時間後の別作業PASSが結合することを防止）。
2. **対象シグナル切断（Target Signal Break）**: 検出された技術名（Docker, Python, Node, Git等）、ファイル名、実行コマンド等のシグナル集合に共通集合（共通要素）が存在しない場合、別インシデントと判定して結合を拒否します。

### (2) 検証証拠の同一対象バインディング（Target Binding Gate）
- `verification_evidence` の採用は、**検証候補文の対象シグナルが非空** かつ **問題/修正側のコア対象シグナルが非空** かつ **両者に非空の共通集合（共通シグナル）が存在する場合のみ** に厳格に限定されます。
- 検証候補文に対象シグナルが含まれない汎用文（例: `exit code 0。テストは通りました。`、`テスト完了`）や、対象が不一致な文（例: Dockerエラーに対して `node scripts/verify-build.mjs`）は採用されず、`fix_status` は `unverified` に保たれ、`product-ready` への昇格が阻止されます。
- 日常的な定型完了報告（「ダイヤモンドバリデーション完了」「埋め込み＆配置完了」等）は除外パターンによりパージされます。

---

## 4. スコアリング計算式と昇格ゲート

### (1) スコアリング計算式
```text
score = pain_strength + audience_breadth + recurrence + verified_fix_strength + deliverable_assetability + skill_expansion - internal_only - one_off_environment_accident
```

- `pain_strength` (0〜5): クラッシュ、ビルド破損、無限ループ、認証遮断などの苦痛度
- `audience_breadth` (0〜5): Python, Node.js, TypeScript, Git, Docker, PowerShell などの市場の広さ
- `recurrence` (0〜4): バージョンアップ、タイムゾーン、文字コード、パスの不整合など頻出するハマりどころ
- `verified_fix_strength` (0〜5): 同一対象のテスト通過ログによる解決の確実さ（※`root_cause` 未特定、対象シグナル不一致、または否定表現がある場合は付与不可）
- `deliverable_assetability` (0〜4): 有料記事（300円）やレシピ、手順書へのパッケージ化適性
- `skill_expansion` (0〜3): 自動化スクリプトやエージェントSkillへの拡張性
- `internal_only` (0〜-5): ProjectYure内部固有の設定やパスに過度に依存する問題への減点
- `one_off_environment_accident` (0〜-5): 単発のタイポや偶発的ミスへの減点

### (2) ステータス定義
| Status | 昇格条件 | 備考 |
| :--- | :--- | :--- |
| `product-ready` | **`fix_status == "verified"`** かつ **`root_cause` が具体的** かつ **`fix` が具体的** かつ **`verification_evidence` の対象シグナルが問題側と非空で合致** かつ **否定・暫定表現なし** かつ **`score >= 12`** | 修正と検証が同一対象に紐づき根本解決が確認されたもののみ |
| `candidate` | `score >= 7` （検証中または修正案あり） | 原因調査中または修正案の段階 |
| `review_needed` | 否定・暫定表現（「未解決」「対症療法」「根治してない」「推測」等）またはプライバシー懸念（`privacy_internal_risk == "high"`）が検出されたもの | 人間による確認・判断が必要 |
| `unverified` | スコア不足または検証証拠がないもの | 候補未満 |

---

## 5. Trace Integrity vs. Semantic Validity（二層監査モデル）

`audit_product_leads.py` は、以下の2つの独立した監査層を提供します。

### (1) Multi-Turn Exact Trace Integrity（複数ターン全数トレース厳格監査）
- **対象**: カードの `source_turns` に記録された全ターンの `turn_index`, `turn_at`, `user_line`, `model_line`, `quote_hash`, `role_in_episode`。
- **検証**: 寄与した各ターンについて、元ログファイル（Antigravity/Codex/Claude Code）から該当ターンの発言テキストを逆引きし、
  - `turn_index`、タイムスタンプ（`turn_at`）、および両行番号（`user_line`, `model_line`）が完全一致すること（**locator不一致時にindexだけで救済するフォールバックは排除**）。
  - SHA-256 Quote Hash が完全一致すること。
  - `role_in_episode` のトークンが許可値（`symptom`, `root_cause`, `fix`, `verification`, `context`）であり、エピソード内の位置関係（先頭が検証単独でない等）に整合すること。
  - **1ターンでもハッシュ・行番号・時刻不一致や欠落があれば `[TRACE FAIL]` と判定**し、完全な来歴監査を保証します。

> **Legacy Single-Turn Compatibility Mode**:
> `source_turns` 配列が存在しない初期カードに対しては、トップレベルの単一ターン情報（`source_turn_index`, `source_user_line`, `source_model_line`, `source_turn_at`, `source_quote_hash`）を監査する後方互換モードとして動作します。新規生成カードはすべて `source_turns` を含む Multi-Turn Exact Trace で監査されます。

### (2) Semantic Validity（セマンティック妥当性監査）
- **対象**: 候補カードの記述内容、ステータスゲートの厳格性、ターゲットバインディング、候補ID規約。
- **検証**:
  - `status: product-ready` のカードにおいて `root_cause`、`fix`、`verification_evidence` が具体的に埋まっており、かつ否定・暫定表現が含まれていないか。
  - `symptom`/`fix` の対象シグナルおよび `verification_evidence` の対象シグナルがともに非空であり、かつ両者が重複しているか（Target Binding Gate。空または不一致は `TARGET BINDING GATE VIOLATION`）。
  - プライバシーリスクが検出されたカードが正しく `review_needed` に隔離されているか。
  - 候補IDが `PL-YYYYMMDD-NNN` の命名規約に従っているか。

---

## 6. 決定論的ID採番・冪等性・非上書き保証

- **命名規約**: 候補IDは `PL-YYYYMMDD-NNN`（例: `PL-20260830-001`）の形式で採番されます。
- **非上書き保証（Non-Overwriting Guarantee）**: 既存の候補カードファイル（`YYYY-MM-DD-pl-*.md`）が存在する場合、`--force` フラグを指定しても既存ファイルを絶対に削除・上書きせず、スキップして保護します。
- **ID衝突防止**: 同一日に複数回マイナーを実行した場合でも、既存のファイルおよびチェックポイント内の最大連番（`max_seq`）を検出し、次の連番を安全に割り当てます。
- **冪等性**: 同一の発言引用ハッシュ（`source_quote_hash`）を持つエピソードには常に同一の `candidate_id` が割り当てられ、重複カードの生成を防ぎます。

---

## 7. プライバシーと秘密情報の保護（Privacy & Redaction）

以下のパターンは正規表現により自動検出され、マスクされます。
- APIキー（OpenAI `sk-...`, Google `AIza...`, GitHub `ghp_...`, Slack `xox...` 等）
- Bearer トークン、秘密鍵（RSA / EC / OPENSSH Private Key）
- パスワード指定（`password='...'` 等）
- メールアドレス

秘密情報が検出された場合：
1. 該当箇所は `[REDACTED_*]` に置換
2. `privacy_internal_risk: "high"`
3. `status: "review_needed"`（人間による目視確認が必須）

---

## 8. スケジューラ運用（Windows Task Scheduler）

- **タスク名**: `ProjectYure-GITV-ProductMiner`
- **実行頻度**: 毎日 05:20 JST（小ネタスケジューラ 05:00 JST から20分後）
- **設定**:
  - 多重起動禁止（`IgnoreNew`）
  - 開始時刻を逃した場合は次回起動時に実行（`StartWhenAvailable`）
  - 実行ログ・失敗ログ: `workbench/product-leads/_runs/product_miner_YYYYMMDD_HHMMSS.log`
- **ラッパー**: `scripts/product_mining/run_daily_product_miner.ps1`

---

## 9. ロールバック手順

万が一、採掘パイプラインに不具合が発生した場合：
1. **タスクの一時停止**:
   ```powershell
   Disable-ScheduledTask -TaskName "ProjectYure-GITV-ProductMiner"
   ```
2. **状態のリセット**:
   `workbench/product-leads/_state/checkpoint.json` を削除またはバックアップから復元。
3. **候補の削除**:
   `workbench/product-leads/` 配下の不要な `.md` 候補ファイルを削除（`README.md` は保持）。
4. **タスクの再有効化 / 登録解除**:
   ```powershell
   Enable-ScheduledTask -TaskName "ProjectYure-GITV-ProductMiner"
   # または
   Unregister-ScheduledTask -TaskName "ProjectYure-GITV-ProductMiner" -Confirm:$false
   ```
