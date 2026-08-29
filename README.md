# Ghost in the Voronoi (GITV)

Ghost in the Voronoi is the public observation log for ProjectYure: production accidents, agent drift, repairs, and technical discoveries become readable artifacts here.

The site is built with [Quartz](https://quartz.jzhao.xyz/) and published at <https://ghost.voronoi.works/>.

## Repository map

- `content/` — published article sources and adopted article images
- `assets/social/` — adopted promotional assets that are intentionally kept outside the Quartz public tree
- `workbench/` — local-only drafts, raw logs, Candidates, and legacy tools; ignored by Git except for its boundary document
- `scripts/` — deterministic generation, verification, and local-preview tools
- `custom-plugins/` — GITV-owned Quartz plugins
- `quartz/` and `docs/` — the Quartz engine and upstream documentation

## Publication boundaries

- `content/attachments/` contains adopted public images only.
- Generated Candidates stay under `workbench/candidates/` until explicit human adoption.
- `content/llms.txt`, `public/`, RSS, and the sitemap are generated artifacts and are not edited by hand.
- Saving, adopting an image, committing, pushing, and publishing are separate approval gates.
- A push to `main` starts the GitHub Pages deployment workflow.

## Local commands

```sh
npm install
npm run build
```

On Windows, `scripts/preview-quartz.bat` starts the local Quartz preview server.

The shared editorial and manga workflows are maintained in the sibling
`projectyure-skills` repository. Product-specific contracts, scripts, and
references remain in GITV.
