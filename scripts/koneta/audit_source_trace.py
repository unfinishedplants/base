"""Audit exact source traces stored in local koneta cards.

The audit is read-only.  It checks that each exact trace points to an existing
raw log turn and that the stored quote hash can be reproduced from that turn.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import mine_transcripts as miner


TRACE_FIELDS = (
    "source_trace_status",
    "source_platform",
    "source_session_id",
    "source_log_path",
    "source_turn_at",
    "source_turn_index",
    "source_user_line",
    "source_model_line",
    "source_quote_hash",
)


def parse_trace(card_text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for field in TRACE_FIELDS:
        match = re.search(rf"(?m)^{re.escape(field)}:\s*(.*?)\s*$", card_text)
        if not match:
            values[field] = ""
            continue
        raw = match.group(1)
        if raw.startswith('"') and raw.endswith('"'):
            try:
                values[field] = str(json.loads(raw))
                continue
            except json.JSONDecodeError:
                pass
        raw = re.sub(r"\s+#.*$", "", raw)
        values[field] = raw.strip("'\"")
    return values


def extract_turns(platform: str, log_path: Path) -> list[dict[str, object]]:
    if platform == "antigravity":
        return miner.extract_turns_from_antigravity(log_path)
    if platform == "codex":
        return miner.extract_turns_from_codex(log_path)
    if platform == "claude-code":
        return miner.extract_turns_from_claude(log_path)
    raise ValueError(f"unsupported source platform: {platform}")


def audit_exact(card_path: Path, trace: dict[str, str]) -> list[str]:
    errors: list[str] = []
    required = [field for field in TRACE_FIELDS if field != "source_trace_status"]
    missing = [field for field in required if not trace[field]]
    if missing:
        errors.append("empty exact fields: " + ", ".join(missing))

    log_text = trace["source_log_path"]
    if not log_text:
        return ["source_log_path is empty"]

    log_path = Path(log_text)
    if not log_path.is_file():
        return [f"source log does not exist: {log_path}"]

    if trace["source_platform"] == "antigravity":
        expected_session = miner.extract_full_session_id(log_path.parents[2].name)
    else:
        expected_session = miner.extract_full_session_id(log_path.stem)
    if trace["source_session_id"] != expected_session:
        errors.append(
            f"session mismatch: stored={trace['source_session_id']} actual={expected_session}"
        )

    try:
        turns = extract_turns(trace["source_platform"], log_path)
    except ValueError as exc:
        return errors + [str(exc)]

    matching: list[tuple[int, dict[str, object]]] = []
    for index, turn in enumerate(turns, start=1):
        user_line = str(turn.get("source_user_line") or "")
        model_line = str(turn.get("source_model_line") or "")
        if (
            user_line == trace["source_user_line"]
            and model_line == trace["source_model_line"]
        ):
            matching.append((index, turn))

    if len(matching) != 1:
        return errors + [f"line locator matched {len(matching)} turns"]

    turn_index, turn = matching[0]
    if trace["source_turn_index"] and trace["source_turn_index"] != str(turn_index):
        errors.append(
            f"turn index mismatch: stored={trace['source_turn_index']} actual={turn_index}"
        )

    actual_hash = miner.turn_quote_hash(str(turn["user"]), str(turn["model"]))
    if trace["source_quote_hash"] != actual_hash:
        errors.append(
            f"quote hash mismatch: stored={trace['source_quote_hash']} actual={actual_hash}"
        )

    actual_time = str(turn.get("time") or "")
    if trace["source_turn_at"] and trace["source_turn_at"] != actual_time:
        errors.append(
            f"turn time mismatch: stored={trace['source_turn_at']} actual={actual_time}"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "stock_dirs",
        nargs="*",
        type=Path,
        default=[miner.STOCK_DIR],
        help="stock directories to audit (default: current GITV workbench stock)",
    )
    args = parser.parse_args()

    counts: Counter[str] = Counter()
    failures: list[tuple[Path, list[str]]] = []
    for stock_dir in args.stock_dirs:
        for card_path in sorted(stock_dir.glob("*.md")):
            if card_path.name.lower() == "readme.md":
                counts["skipped"] += 1
                continue
            trace = parse_trace(card_path.read_text(encoding="utf-8"))
            status = trace["source_trace_status"] or "untraced"
            counts[status] += 1
            if status != "exact":
                continue
            errors = audit_exact(card_path, trace)
            if errors:
                failures.append((card_path, errors))

    for card_path, errors in failures:
        print(f"[FAIL] {card_path}")
        for error in errors:
            print(f"  - {error}")

    ordered = " ".join(f"{key}={counts[key]}" for key in sorted(counts))
    print(f"[SUMMARY] {ordered} exact_failures={len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
