"""Sync published status between content/ articles and koneta-stock/ cards.

Matches published articles in content/ against cards in workbench/koneta-stock/
and updates 'status: pending' -> 'status: published' for already published articles.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Windows UTF-8 stdout
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).parent.resolve()
GITV_ROOT = SCRIPT_DIR.parent.parent
CONTENT_DIR = GITV_ROOT / "content"
STOCK_DIR = GITV_ROOT / "workbench" / "koneta-stock"


def load_published_articles(content_dir: Path) -> list[dict[str, str]]:
    """Load published article info from content/ directory."""
    articles = []
    if not content_dir.exists():
        return articles

    for md_file in sorted(content_dir.glob("*.md")):
        if md_file.name in {"index.md", "llms.txt"}:
            continue
        text = md_file.read_text(encoding="utf-8", errors="replace")
        slug_match = re.search(r"^slug:\s*(.*)$", text, re.M)
        title_match = re.search(r"^title:\s*[\"']?(.*?)[\"']?$", text, re.M)
        date_match = re.search(r"^date:\s*(.*)$", text, re.M)

        slug = slug_match.group(1).strip() if slug_match else md_file.stem
        title = title_match.group(1).strip() if title_match else ""
        date = date_match.group(1).strip() if date_match else ""

        articles.append({
            "path": md_file,
            "stem": md_file.stem,
            "slug": slug,
            "title": title,
            "date": date,
        })
    return articles


def match_card_to_articles(card_path: Path, card_meta: dict[str, str], articles: list[dict[str, str]]) -> dict[str, str] | None:
    """Determine if a stock card matches any published article."""
    card_stem = card_path.stem
    card_title = card_meta.get("title", "").strip()
    card_slug = card_meta.get("slug", "").strip()

    card_keywords = [w for w in re.split(r"[-_]", card_stem) if len(w) >= 3 and not re.match(r"^\d{4}$|^\d{2}$", w) and w not in {"nagi", "yura", "sumi", "shiori", "mined", "cross"}]

    for art in articles:
        art_stem = art["stem"]
        art_slug = art["slug"]
        art_title = art["title"]

        if card_stem == art_stem or card_slug == art_slug or card_stem == art_slug or card_slug == art_stem:
            return art

        if card_stem in art_stem or art_stem in card_stem:
            return art

        if card_title and art_title:
            if card_title == art_title or card_title in art_title or art_title in card_title:
                return art

        if card_keywords:
            matches_count = sum(1 for kw in card_keywords if kw in art_stem or kw in art_slug)
            if matches_count >= 3:
                return art

    return None


def parse_card_frontmatter(card_text: str) -> dict[str, str]:
    meta = {}
    lines = card_text.splitlines()
    in_fm = False
    fc = 0
    for line in lines:
        stripped = line.strip()
        if stripped == "---":
            fc += 1
            if fc == 1:
                in_fm = True
                continue
            elif fc == 2:
                break
        if in_fm and ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("'\"")
    return meta


def sync_stock_status(apply: bool = False) -> tuple[int, int, int]:
    articles = load_published_articles(CONTENT_DIR)
    cards = sorted(STOCK_DIR.glob("*.md"))

    print("===================================================")
    print("  📦 Koneta Stock Status Synchronizer")
    print("===================================================")
    print(f"Content Directory: {CONTENT_DIR} ({len(articles)} published articles)")
    print(f"Stock Directory:   {STOCK_DIR} ({len(cards)} cards)")
    print(f"Mode:              {'APPLY (changes will be written)' if apply else 'CHECK (dry-run)'}")
    print()

    updated_count = 0
    already_published = 0
    pending_count = 0

    for card in cards:
        if card.name.lower() == "readme.md":
            continue

        text = card.read_text(encoding="utf-8-sig", errors="replace")
        meta = parse_card_frontmatter(text)
        current_status = meta.get("status", "pending").lower().strip()
        agent = meta.get("agent", "unknown")
        title = meta.get("title", card.stem)

        matched_art = match_card_to_articles(card, meta, articles)

        if matched_art:
            if current_status != "published":
                print(f"[UPDATE NEEDED] {card.name}")
                print(f"  • Current status:   {current_status}")
                print(f"  • Target status:    published")
                print(f"  • Matched Article:  {matched_art['stem']} ({matched_art['title'][:40]})")

                if apply:
                    # Update status in frontmatter
                    new_text = re.sub(r"(?m)^status:\s*[^\r\n]+", "status: published", text, count=1)
                    if new_text != text:
                        card.write_text(new_text, encoding="utf-8")
                        print("  -> Status updated to published successfully! [OK]")
                    else:
                        print("  -> Failed to replace status line regex [ERROR]")
                updated_count += 1
            else:
                already_published += 1
        else:
            pending_count += 1

    print("\n===================================================")
    print(f"  📊 Summary: updated={updated_count} already_published={already_published} pending_active={pending_count}")
    print("===================================================")
    return updated_count, already_published, pending_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize published status from content/ to koneta-stock/ cards")
    parser.add_argument("--apply", action="store_true", help="Apply status changes to stock card files")
    args = parser.parse_args()

    updated, _, _ = sync_stock_status(apply=args.apply)
    if not args.apply and updated > 0:
        print("\nRun with '--apply' to update these cards to 'status: published'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
