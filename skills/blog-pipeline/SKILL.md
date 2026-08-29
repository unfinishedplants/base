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
- Images are optional. When the user wants an image, prefer a separate YuRelay request to Nagi with the agreed article concept and visual brief. Article authorship remains with the assigned author.
- Treat every generated image as a Candidate. Store it under the local-only `workbench/candidates/` tree until Human review explicitly adopts it. When a ProjectYure person is depicted, use the current visual Canon and approved references without modifying Canon.

Agent invocation, file writes, image adoption, commit, push, publication, and external posting keep their existing Human Gates. Approval for one transfer point does not authorize the later ones.

## Draft from evidence

1. Establish the article's author, event or question, intended scope, and whether an image is wanted.
2. Use only connected logs, files, source material, or clearly identified external research. Separate observed facts, quotations, interpretation, and reconstruction.
3. Preserve a quoted speaker's wording when the exact source is available and publication is approved. Do not manufacture dialogue or write another agent's internal perspective.
4. Choose the length and structure from the material. Do not force every article into a long-form essay, fixed word count, front/back split, or stock opening.
5. Present a readable draft before a consequential transfer unless the user's request already explicitly authorizes that exact transfer.

## Public-safety review

Before saving or publishing, inspect the actual draft for:

- secrets, tokens, private URLs, local absolute paths, unpublished infrastructure, or account details;
- personal identifiers, exact locations, third-party quotations, and material whose publication scope is unclear;
- unsupported factual claims, invented causal links, or simulated agent testimony;
- Markdown breakage, duplicate H1 titles, broken relative links, and accidental raw image syntax.

Mask or generalize only what needs protection. Do not blindly replace every internal term, acronym, place name, or technical detail when it is intentionally public and approved.

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
   - **Yura**: Black short bob hair, calm smiling/neutral expression, dark work suit/shirt.
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
4. Commit only when explicitly requested, staging only the approved article and directly related assets or pipeline changes.
5. Push only when explicitly requested. A push to `main` triggers the GitHub Pages workflow and publication.
6. After publication, verify the live article URL and the relevant `llms.txt`, RSS, sitemap, metadata, and image behavior in proportion to the change.

Do not use legacy `sync_to_quartz.py` paths or treat a local file save as proof of deployment.

## Optional promotion copy

Draft X or other promotional copy only when requested. Keep it separate from the article artifact, verify the live URL first, and never post automatically.

## Completion report

State the author, article and image paths, build result, Human Gate state, changed files, commit or push state, live verification if published, and anything still unresolved.
