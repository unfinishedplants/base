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

## 🛠️ 生成・配置フロー

1. **プロンプト合成**:
   `scripts/koneta/generate_manga_prompt.py` の `compile_prompt` を使用して確定プロンプトを取得。
2. **画像生成（Candidate）**:
   `generate_image` ツールをアスペクト比 `16:9`、`ImagePaths: ["config/koneta/references/chibi_character_canon.png"]` を参照して呼び出す。
3. **隔離棚への配置**:
   生成された画像は、未承認の段階では `workbench/candidates/article-images/YYYY-MM-DD-[slug].jpg` へ保管する（公開ツリー `content/attachments/` や `assets/social/` に直接置かない！）。
4. **Human Gate（隊長プレビュー承認）**:
   アーティファクトで隊長にプレビューを提示し、承認（「ヨシ！」）を得る。
5. **採用（Adoption）**:
   承認後、記事内画像なら `content/attachments/YYYY-MM-DD-[slug].jpg`、SNS用画像なら `assets/social/YYYY-MM-DD-[slug]-teaser.jpg` へ配置する。
6. **ストックステータス同期（Status Sync）**:
   公開記事を作成後、`python scripts/koneta/sync_stock_status.py --apply` を実行してストックカードのステータスを `published` に機械的に同期する。

### 7. APIクォータ枯渇の回避（一球入魂）
画像生成APIは1日の利用上限（クォータ）に達しやすい。些細なタイポ（「まやん」等）や微小な修正のために安易なリトライ（ガチャの引き直し）を連打してはならない。一球入魂で生成し、クォータ枯渇エラー（429 Too Many Requests）に直面した場合は、勝手にループせず直ちに隊長へ報告し、回復を待つか手動修正を仰ぐこと。
