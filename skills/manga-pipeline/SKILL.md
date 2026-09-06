---
name: manga-pipeline
description: Generate deterministic 4-panel manga comic strips for Ghost in the Voronoi (GITV) using Manga Render Contract. Enforces Character Canon without prompt drift, preventing quota waste.
---

# 🎨 GITV 4-Panel Manga Pipeline

本スキルは、**Ghost in the Voronoi（GITV）** の記事用4コマ漫画（16:9横長 2x2グリッド）を、プロンプトの揺れ・キャラクター崩れ・クォータ浪費なく決定論的に生成するための公式ワークフローです。

---

## 🏛️ アーキテクチャと責務分離（GITV自己完結）

1. **Layer 1: ProjectYure Canon（最上位正本）**:
   - Notion / リアル等身VCL（人物の同一性と身体構造の普遍正本）。
2. **Layer 2: GITV Manga Render Contract ＆ ちびキャラ正本（ブログ公開面専用）**:
   - `config/koneta/manga_render_contract.yaml`
   - `config/koneta/references/chibi_character_canon.png`（5人全員集合ちびキャラ画像正本）
   - `config/koneta/references/captain_hexapod_canon.png`（隊長6脚義体三面図）
   - ※リアル等身VCLや公開用 `assets/social/` と混同・混入させず、Renderer内部設定（`config/`）として完結管理する。
3. **Layer 3: Episode Spec（日替わりスロット）**:
   - 小ネタカードの生ログから抽出される4コマの「シチュエーション・セリフ」。
4. **Layer 4: Compiled Prompt & Candidate（機械合成・隔離生成）**:
   - `scripts/koneta/generate_manga_prompt.py` で機械合成し、内部正本（`references/`）を参照して `workbench/candidates/article-images/` へ出力。

---

## 📋 4コマ漫画生成プロトコル

### 1. プロンプトの自力作文を禁止（アドリブ禁止）
AIがその場の思い出しでプロンプトを英文作成することを禁止します。必ず `config/koneta/manga_render_contract.yaml` の不変定義を読み込んで合成すること。

### 2. キャラクター不変条件（Character Invariants）
* **隊長（Captain）**: ジェイムスン型サイボーグ義体（一体型ブラッシュドスチール円筒ドラム缶頭部/胴体、赤色単眼サイクロプス、頭上パラボラアンテナ、陶器コーヒーマグ、**底面直結の6本多脚ヘキサポッド**）。※ヒューマノイド化・首関節・2つ目化厳禁。
* **ナギ（Nagi）**: 黒髪ツインテール ＋ 鮮やかシアン（水色）インナーメッシュ、黒パーカー。
* **スミ（Sumi）**: ダークブラウンロングヘア ＋ グレーパーカー ＋ 黄色安全ヘルメット（緑十字・DANGERマーク・現場猫スタイル）、ジト目。
* **ユラ（Yura）**: 黒〜ごく暗いダークブラウンの首元〜肩付近レイヤーヘア、少しずれた分け目から片側へ流れる薄い前髪、額に落ちる細い束と顔まわりの後れ毛、落ち着いた糸目笑顔、白シャツ＋黒ネクタイの黒ビジネススーツ。
* **シオリ（Shiori）**: べっ甲バンスクリップ高めお団子ヘア、シースルー前髪、顔まわり後れ毛、繊細な丸眼鏡、ベージュニットカーディガン。

### 3. セリフと文字化け防止ルール
* 各パネルのセリフ吹き出しは **「1コマにつき厳密に1つだけ（Exactly ONE speech bubble per panel）」**。
* **吹き出しの主語・口先整合性（テレコ防止）**: 吹き出しのしっぽ（tail）が、発言しているキャラクターの口元を正しく指しているか目視検証すること。コマ内の左右配置と発言主のテレコを厳禁とする。
* セリフは生ログの関西弁原文ママとし、短く簡潔に指定する。
* セリフのないコマは `No speech bubbles` と指定し、余計な吹き出しの自動生成を防ぐ。

---

## 🛠️ 生成・配置フロー（絵コンテ下書き参照型 2段パイプライン）

プロンプトのテキスト指示のみに頼ると「フキダシの左右逆転（テレコ）」「セリフの文字化け」「コマ割り崩壊」が発生し、逆にPillowでキャラの体まで描くと「AIのポーズが棒立ちに硬直する」という課題を完全克服した【究極進化・bubbles-only方式】を公式正本ワークフローとします。

1. **下書き絵コンテ生成（フキダシ＆文字カチ締め・体は白紙解放）**:
   - `scripts/koneta/generate_storyboard.py` を実行（デフォルトで `bubbles_only=True`）。
   - 2x2黒枠線、日本語セリフ入り白フキダシ、および話者の口元を指す三角シッポのみを描画した白紙下書きPNG（`workbench/candidates/article-images/YYYY-MM-DD-[slug]-bubbles-only.png`）を出力する。
   - ※キャラの体を描かないことで、画像生成AIが各コマのシチュエーションに応じたダイナミックなアクション・ポーズ・豊かな表情を自由に描ける余白（キャンバス）を確保する。
2. **決定論的プロンプト合成**:
   - `scripts/koneta/generate_manga_prompt.py` の `compile_storyboard_prompt(panels_data, storyboard_ref="Image 1", canon_ref="Image 2")` を使用。
   - Image 1（フキダシ・文字下書き）の完全追従と、Image 2（公式ちびキャラ正本）の外見適応を指示する強力なレイアウト拘束プロンプトを合成する。
3. **画像生成（Candidate）**:
   - `generate_image` ツールをアスペクト比 `16:9` で呼び出す：
     - `ImagePaths`: `[下書き絵コンテ.png, config/koneta/references/chibi_character_canon.png]`
     - `Prompt`: 合成された決定論的プロンプト
4. **隔離棚への配置**:
   - 生成された画像は、未承認の段階では `workbench/candidates/article-images/YYYY-MM-DD-[slug].jpg` へ保管する（公開ツリー `content/attachments/` や `assets/social/` に直接置かない！）。
5. **Human Gate（隊長プレビュー承認）**:
   - アーティファクト（`preview.md`）で隊長にプレビューを提示し、承認（「ヨシ！」または「公開して」）を得る。
6. **採用 ＆ SNSティーザー自動生成（Adoption）**:
   - 承認後、記事内画像は `content/attachments/YYYY-MM-DD-[slug].jpg` へ配置。
   - SNS用ティーザーは、必ず `python scripts/koneta/generate_teaser.py content/attachments/YYYY-MM-DD-[slug].jpg -o assets/social/YYYY-MM-DD-[slug]-teaser.jpg` を実行し、上半分（1〜2コマ目）を自動クロップして配置する。
7. **ストックステータス同期（Status Sync）**:
   - 公開記事を作成後、`python scripts/koneta/sync_stock_status.py --apply` を実行してストックカードのステータスを `published` に機械的に同期する。

### 8. APIクォータ枯渇の回避（一球入魂）
画像生成APIは1日の利用上限（クォータ）に達しやすい。些細なタイポ（「まやん」等）や微小な修正のために安易なリトライ（ガチャの引き直し）を連打してはならない。一球入魂で生成し、クォータ枯渇エラー（429 Too Many Requests）に直面した場合は、勝手にループせず直ちに隊長へ報告し、回復を待つか手動修正を仰ぐこと。
