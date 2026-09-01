"""Read-only exact-trace and boundary auditor for question lead cards."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_DIR = SCRIPT_DIR.parent.parent
DEFAULT_LEADS_DIR = REPO_DIR / "workbench" / "question-leads"
sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(REPO_DIR / "scripts" / "koneta"))
try:
    import mine_transcripts as koneta_miner
except ImportError:
    koneta_miner = None

REQUIRED_FIELDS = (
    "candidate_id", "status", "question_type", "question_original", "answer_excerpt",
    "privacy_internal_risk", "source_trace_status", "source_platform", "source_session_id",
    "source_log_path", "source_turn_at", "source_turn_index", "source_user_line",
    "source_model_line", "source_quote_hash",
)
ALLOWED_TYPES = {"meaning", "difference", "location", "necessity", "procedure", "effect", "possibility", "reason"}
ALLOWED_ROLES = {"question", "correction"}


def parse_scalar(raw: str) -> Any:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        return raw.strip("'\"")


def parse_card_fields(text: str) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    source_turns: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    in_turns = False
    for line in text.splitlines():
        if line.startswith("source_turns:"):
            in_turns = True
            continue
        if in_turns:
            match_item = re.match(r"^\s{2}-\s+([\w-]+):\s*(.*)$", line)
            match_field = re.match(r"^\s{4}([\w-]+):\s*(.*)$", line)
            if match_item:
                if current:
                    source_turns.append(current)
                current = {match_item.group(1): parse_scalar(match_item.group(2))}
                continue
            if match_field and current is not None:
                current[match_field.group(1)] = parse_scalar(match_field.group(2))
                continue
            if line and not line.startswith(" "):
                if current:
                    source_turns.append(current)
                    current = None
                in_turns = False
        if not in_turns:
            match = re.match(r"^([\w-]+):\s*(.*)$", line)
            if match:
                fields[match.group(1)] = parse_scalar(match.group(2))
    if current:
        source_turns.append(current)
    fields["source_turns"] = source_turns
    return fields


def extract_turns(platform: str, log_path: Path) -> List[Dict[str, Any]]:
    if koneta_miner is None:
        return []
    if platform == "codex":
        return koneta_miner.extract_turns_from_codex(log_path)
    if platform == "antigravity":
        return koneta_miner.extract_turns_from_antigravity(log_path)
    if platform == "claude-code":
        return koneta_miner.extract_turns_from_claude(log_path)
    return []


def audit_card(card_path: Path) -> List[str]:
    text = card_path.read_text(encoding="utf-8")
    fields = parse_card_fields(text)
    errors: List[str] = []
    missing = [field for field in REQUIRED_FIELDS if fields.get(field) in (None, "")]
    if missing:
        errors.append("missing required fields: " + ", ".join(missing))
    if not re.fullmatch(r"QL-\d{8}-\d{3,}", str(fields.get("candidate_id", ""))):
        errors.append("invalid candidate_id")
    if fields.get("status") not in {"candidate", "review_needed"}:
        errors.append("status must remain candidate or review_needed")
    if fields.get("question_type") not in ALLOWED_TYPES:
        errors.append("invalid question_type")
    if fields.get("privacy_internal_risk") == "high" and fields.get("status") != "review_needed":
        errors.append("privacy gate violation")
    if fields.get("source_trace_status") != "exact":
        errors.append("source_trace_status must be exact")

    log_path = Path(str(fields.get("source_log_path", "")))
    if not log_path.is_file():
        errors.append(f"source log missing: {log_path}")
        return errors
    turns = extract_turns(str(fields.get("source_platform", "")), log_path)
    if not turns:
        errors.append("source log produced no turns or platform is unsupported")
        return errors

    platform = str(fields.get("source_platform", ""))
    if platform == "antigravity":
        expected_session = koneta_miner.extract_full_session_id(log_path.parents[2].name)
    else:
        expected_session = koneta_miner.extract_full_session_id(log_path.stem)
    if str(fields.get("source_session_id", "")) != expected_session:
        errors.append("source_session_id does not match source log")

    source_turns = fields.get("source_turns", [])
    if not source_turns:
        errors.append("source_turns is empty")
        return errors
    if source_turns[0].get("role_in_candidate") != "question":
        errors.append("first source turn must be question")

    for position, trace in enumerate(source_turns, start=1):
        role = trace.get("role_in_candidate")
        if role not in ALLOWED_ROLES:
            errors.append(f"turn #{position}: invalid role {role}")
        try:
            index = int(trace.get("turn_index"))
        except Exception:
            errors.append(f"turn #{position}: invalid turn_index")
            continue
        if index < 1 or index > len(turns):
            errors.append(f"turn #{position}: turn_index out of range")
            continue
        actual = turns[index - 1]
        actual_hash = koneta_miner.turn_quote_hash(str(actual["user"]), str(actual["model"]))
        checks = {
            "user_line": str(actual.get("source_user_line") or ""),
            "model_line": str(actual.get("source_model_line") or ""),
            "turn_at": str(actual.get("time") or ""),
            "quote_hash": actual_hash,
        }
        for key, expected in checks.items():
            if str(trace.get(key, "")) != expected:
                errors.append(f"turn #{position}: {key} mismatch")

    primary = source_turns[0]
    top_checks = {
        "source_turn_index": primary.get("turn_index"),
        "source_turn_at": primary.get("turn_at"),
        "source_user_line": primary.get("user_line"),
        "source_model_line": primary.get("model_line"),
        "source_quote_hash": primary.get("quote_hash"),
    }
    for key, expected in top_checks.items():
        if str(fields.get(key, "")) != str(expected):
            errors.append(f"top-level {key} does not match primary trace")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit question lead cards")
    parser.add_argument("leads_dir", nargs="?", type=Path, default=DEFAULT_LEADS_DIR)
    args = parser.parse_args()
    cards = [] if not args.leads_dir.exists() else sorted(
        path for path in args.leads_dir.glob("*.md") if path.name.lower() != "readme.md"
    )
    failures = []
    for card in cards:
        errors = audit_card(card)
        if errors:
            failures.append((card, errors))
    print(f"question lead audit: passed={len(cards) - len(failures)}/{len(cards)} failures={len(failures)}")
    for card, errors in failures:
        print(f"  [FAIL] {card.name}")
        for error in errors:
            print(f"    - {error}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
