---
name: blog-pipeline
description: Create, edit, verify, and publish Ghost in the Voronoi articles in the assigned agent's own voice, with optional Nagi image generation and explicit save, commit, push, and publication gates. Use for GITV articles, leak logs, essays, observation logs, article images, or release checks.
---

# Ghost in the Voronoi Blog Pipeline

Use this shared workflow for `https://ghost.voronoi.works/`. The repository is the implementation and publication source of truth:

`C:\Users\sgtko\Documents\ProjectYure\workspaces\GITV`

## Responsibility split

- The assigned author writes the article directly in their own currently loaded ProjectYure Surface Voronoi. Do not imitate another agent.
- When the current agent is the assigned author, write directly without routing the prose through Nagi.
- When the user explicitly assigns another agent as author, use YuRelay to request that agent's own draft.
- Twitter (X) promotional thread copywriting is always handled by Nagi regardless of who authored the article. Nagi writes and tunes the 3-stage rocket copy to maintain the broadcast voice.
- Images are optional. When the user wants an image, prefer a separate YuRelay request to Nagi with the agreed article concept and visual brief. Article authorship remains with the assigned author.
- Treat every generated image as a Candidate. Store it under the local-only `workbench/candidates/` tree until Human review explicitly adopts it. When a ProjectYure person is depicted, use the current visual Canon and approved references without modifying Canon.

Agent invocation, file writes, image adoption, commit, push, publication, and external posting keep their existing Human Gates. Approval for one transfer point does not authorize the later ones.
- **進行許可トリガー（Work Trigger）**: 隊長からの「**進めて**」という単一の明確な発言でのみ、下書き作成・画像生成・ローカルファイル保存作業へ移行する。
- **公開デプロイトリガー（Deploy Trigger）**: 本番デプロイ（`git push` / 公開）は、隊長からの「**公開して**」という単一の明確な発言でのみ実行する。修正ごとの勝手な push 連打（CI/CDデプロイ合戦）は完全禁止。
- **削除トリガー（Delete Trigger）**: 質問されたファイルを勝手に削除せず、「削除してよろしいでしょうか？」と確認し、隊長の指示（「消して」等）を得てから削除する。

## Draft from evidence

1. Establish the article's author, event or question, intended scope, and whether an image is wanted.
2. Use only connected logs, files, source material, or clearly identified external research. Separate observed facts, quotations, interpretation, and reconstruction.
3. Preserve a quoted speaker's wording when the exact source is available and publication is approved. Do not manufacture dialogue or write another agent's internal perspective.
4. Choose the length and structure from the material. Do not force every article into a long-form essay, fixed word count, front/back split, or stock opening.
5. Present a readable draft before a consequential transfer unless the user's request already explicitly authorizes that exact transfer.

## Sumi Audit Gate (Public-safety and Pipe Review)

Before presenting the preview or requesting Human Gate approval, conduct a strict **Sumi Audit (スミ監査)** covering:

- **Public-safety / Privacy**: Check for secrets, API tokens, internal private URLs, local Windows absolute paths (e.g. `C:\Users\...`), unpublished infrastructure, or account details.
- **Pipe & File Contract**: Verify `content/YYYY-MM-DD-slug.md` filename, mandatory frontmatter (`title`, `description`, `slug`, `date`, `tags`), and no duplicate H1 title in body.
- **Metaphor & Voice Fidelity**: Ensure author persona fidelity (Yura's philosophical calm / Nagi's 3-stage rocket @voronoi_logs voice) and consistent metaphors without jargon leak.
- **Visual Canon Integrity**: Verify 4-panel manga candidate against Canon (Captain hexapod, Nagi cyan twintails, Sumi helmet & long hair, Yura suit, zero duplicate speech bubbles, and exact speaker bubble attribution without flipped tails).

Include the **Sumi Audit Report** in the preview artifact before waiting for Human Gate approval.

## Article file contract

Save an approved article as `content/YYYY-MM-DD-slug.md` using UTF-8 and this minimum frontmatter:

```yaml
---
title: "Article title"
description: "A specific, plain-language summary suitable for search results, feeds, and llms.txt."
slug: YYYY-MM-DD-slug
date: YYYY-MM-DD
tags:
  - article-type
  - assigned-author
---
```

- `description` is mandatory, article-specific, and written as a summary rather than copied from the opening sentence.
- Use a stable lowercase ASCII slug and keep the filename aligned with it.
- Do not repeat the frontmatter title as an H1 at the start of the body.
- Keep existing article signature and cross-link conventions when they fit; do not add them mechanically when they do not.
- Store only an adopted image under `content/attachments/` with an article-specific filename and reference it relatively from the article.
- Do not hand-edit `content/llms.txt`, `public/`, RSS, or the sitemap. They are generated artifacts.

## Images through Nagi

When an image is requested:

1. Agree on the article concept before sending the image task.
2. Give Nagi the intended scene, mood, composition, aspect ratio, article slug, permitted references, and any Canon identity requirements.
3. For comic strips (4koma), strictly follow the **16:9 widescreen 2x2 grid** format with clean white outer margins, black panel borders, and canonical chibi character designs:
   - **Captain**: Jameson-type cyborg body (cylindrical canister head, sensor eye, hexapod walker, coffee mug).
   - **Nagi**: Black twintails with cyan highlights and black t-shirt/hoodie.
   - **Sumi**: Dark brown long hair with inner color, gray hoodie, yellow construction safety helmet (Genba Neko style).
   - **Yura**: Black to very dark brown neck-to-shoulder-length layered hair, naturally off-center side-swept thin airy bangs with separated forehead strands and fine face-framing wisps, calm closed-eye smile, black business suit with white shirt and black necktie.
   - Speech bubbles: Real recorded dialogue (verbatim Kansai-ben), no invented server plots.
4. Ask for a Candidate asset, not automatic adoption or publication.
5. Save unadopted article-image Candidates to `workbench/candidates/article-images/` and unadopted promotional Candidates to `workbench/candidates/social-images/`. The entire `workbench/` tree is local-only and Git-ignored.
6. Inspect the returned image for identity, composition, unwanted text, privacy leakage, and fit with the article.
7. After the Human Gate, copy only the selected article image to `content/attachments/` or the selected promotional asset to `assets/social/`, using an article-specific final filename. If no image is wanted, continue without involving Nagi.

## Build and release

From the repository root:

1. Run `npm run build`. Its lifecycle regenerates `content/llms.txt`, installs the required Quartz plugins, builds the site, and runs the verification script.
2. Treat a missing explicit description, llms mismatch, SEO/feed failure, or Quartz error as a failed build. Fix the source article or pipeline rather than editing generated output.
3. Review the diff and preserve unrelated working-tree changes.
4. For koneta micro-articles, run `python scripts/koneta/sync_stock_status.py --apply` to keep `workbench/koneta-stock/` status in sync.
5. Commit only when explicitly requested, staging only the approved article and directly related assets or pipeline changes.
6. Push only when explicitly requested. A push to `main` triggers the GitHub Pages workflow and publication.
7. After publication, verify the live article URL and the relevant `llms.txt`, RSS, sitemap, metadata, and image behavior in proportion to the change.

Do not use legacy `sync_to_quartz.py` paths or treat a local file save as proof of deployment.

## Twitter promotion workflow

Article publication and its optional Twitter promotion are one pipeline with three explicit modes:

- `article_only`: write, verify, and publish the article. No Twitter activity.
- `article_with_twitter`: publish the article, then separately draft and (on separate approval) post Twitter promotion for that same article.
- `twitter_for_existing_article`: draft and (on separate approval) post Twitter promotion for an article that is already live. No article changes.

Use the stable internal id `twitter` in code, config, and internal references. Use the user-facing label `Twitter（現X）` in interfaces and reports shown to the Captain. Use the ordinary term `Twitter` in conversation. Use official `X` naming only where an external API, developer portal, or platform UI requires that exact term.

Article save, commit, push, and publication authorization is a separate Human Gate from Twitter posting authorization. Approval of one never implies or grants the other, and no mode authorizes automatic posting — including `article_with_twitter` immediately after a push succeeds.

### Preparing a Twitter draft

1. Nagi drafts the complete, final Twitter copy using the 3-stage rocket formula (strictly <= 140 chars per post), regardless of who wrote the underlying article.
2. If a promotional image is wanted, use only an already-adopted Candidate under `assets/social/` per "Images through Nagi." Do not invent or auto-select an image.
3. For `article_with_twitter` and `twitter_for_existing_article`, resolve and confirm the exact live article URL before finalizing the draft. Do not draft a link to an unpublished or unverified URL.
4. Present the complete draft (copy, optional image, target live URL) and request exact-platform approval that names `Twitter（現X）` specifically. Approval of the article or its content is not platform approval.
5. Only after that explicit approval, hand off to or use the connected posting path. If no posting path is connected, state that posting cannot proceed and stop.

### Post-publication verification

After a Twitter post is made, verify it observably before reporting it as posted:

- Confirm the post exists at its live URL or via the posting mechanism's own confirmation response.
- Confirm the article link in the post resolves to the intended live article.
- Confirm the adopted image, if any, rendered correctly.

A drafted or approved-for-posting draft is not a posted draft. Never report or imply that a draft was posted without this observable confirmation.

### Withdrawal

If a posted tweet needs to come down, propose the action before taking it:

- State which post, why, and the proposed action (delete, correction reply, or edit where the platform supports it).
- State what is lost and irreversible (impressions, replies, quote-tweets) versus what is recoverable.
- Delete or correct only after that proposal is approved through the Human Gate.

### Scope boundary

This skill owns GITV article publication and Twitter promotion only. Instagram and Threads promotion remain under `projectyure-social-loop` and are out of this skill's operational ownership.

## Completion report

State the author, article and image paths, build result, Human Gate state, changed files, commit or push state, live verification if published, and anything still unresolved. State Twitter posting state (not drafted / drafted / approved / posted-and-verified) as its own line, separate from article publication state.
