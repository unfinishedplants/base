"""Backfill verifiable source traces for existing local koneta cards.

Only exact, unique matches are promoted to ``source_trace_status: exact``.
Ambiguous or missing traces keep all unverified locator fields empty.
The script defaults to a dry run; pass ``--write`` to update cards.
"""

from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass
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

PLATFORM_BY_AGENT = {
    "yura": "codex",
    "sumi": "claude-code",
    "nagi": "antigravity",
}

DISPLAY_TO_AGENT = {
    "ユラ": "yura",
    "スミ": "sumi",
    "ナギ": "nagi",
}


@dataclass(frozen=True)
class SourceTurn:
    agent: str
    platform: str
    session_id: str
    log_path: Path
    turn_index: int
    user: str
    model: str
    turn_at: str
    user_line: int | str
    model_line: int | str
    quote_hash: str


def normalize_quote(text: str) -> str:
    text = text.replace("**", "").replace("`", "")
    text = text.replace("：", ":")
    text = re.sub(r"[「」『』]", "", text)
    return re.sub(r"\s+", "", text).strip()


def extract_highlight(card_text: str) -> tuple[str, str, str] | None:
    match = re.search(
        r"(?ms)^###\s+💬[^\n]*\n(?P<body>.*?)(?=^###\s+|\Z)",
        card_text,
    )
    if not match:
        return None

    body = match.group("body")
    user_match = re.search(r"(?m)^>\s*隊長\s*(?:[：:]\s*|「)(.+?)」?\s{0,2}$", body)
    model_match = re.search(
        r"(?m)^>\s*(ユラ|スミ|ナギ)\s*(?:[：:]\s*|「)(.+?)」?\s{0,2}$",
        body,
    )
    if not user_match or not model_match:
        return None

    source_agent = DISPLAY_TO_AGENT[model_match.group(1)]
    return user_match.group(1).strip(), model_match.group(2).strip(), source_agent


def collect_turns(days: int) -> list[SourceTurn]:
    cutoff = time.time() - days * 86400
    sessions = []
    sessions.extend(miner.get_antigravity_sessions(cutoff))
    sessions.extend(miner.get_codex_sessions(cutoff))
    sessions.extend(miner.get_claude_sessions(cutoff))

    found: list[SourceTurn] = []
    seen: set[tuple[str, str, int | str, int | str, str]] = set()
    for _, agent, session_id, log_path in sessions:
        if agent == "nagi":
            turns = miner.extract_turns_from_antigravity(log_path)
        elif agent == "yura":
            turns = miner.extract_turns_from_codex(log_path)
        elif agent == "sumi":
            turns = miner.extract_turns_from_claude(log_path)
        else:
            continue

        for turn_index, turn in enumerate(turns, start=1):
            quote_hash = miner.turn_quote_hash(turn["user"], turn["model"])
            key = (
                agent,
                session_id,
                turn.get("source_user_line", ""),
                turn.get("source_model_line", ""),
                quote_hash,
            )
            if key in seen:
                continue
            seen.add(key)
            found.append(
                SourceTurn(
                    agent=agent,
                    platform=PLATFORM_BY_AGENT[agent],
                    session_id=session_id,
                    log_path=log_path.resolve(),
                    turn_index=turn_index,
                    user=turn["user"],
                    model=turn["model"],
                    turn_at=turn.get("time") or "",
                    user_line=turn.get("source_user_line") or "",
                    model_line=turn.get("source_model_line") or "",
                    quote_hash=quote_hash,
                )
            )
    return found


def find_matches(
    turns: list[SourceTurn], user_quote: str, model_quote: str, source_agent: str
) -> list[SourceTurn]:
    wanted_user = normalize_quote(user_quote)
    wanted_model = normalize_quote(model_quote)
    matches = []
    for turn in turns:
        if turn.agent != source_agent:
            continue
        full_user = normalize_quote(turn.user)
        full_model = normalize_quote(turn.model)
        user_matches = wanted_user in full_user or full_user in wanted_user
        model_matches = wanted_model in full_model or full_model in wanted_model
        if user_matches and model_matches:
            matches.append(turn)
    return matches


def yaml_string(value: object) -> str:
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def trace_block(status: str, turn: SourceTurn | None) -> str:
    values: dict[str, object] = {field: "" for field in TRACE_FIELDS}
    values["source_trace_status"] = status
    if turn is not None:
        values.update(
            {
                "source_platform": turn.platform,
                "source_session_id": turn.session_id,
                "source_log_path": str(turn.log_path),
                "source_turn_at": turn.turn_at,
                "source_turn_index": turn.turn_index,
                "source_user_line": turn.user_line,
                "source_model_line": turn.model_line,
                "source_quote_hash": turn.quote_hash,
            }
        )
    return "\n".join(f"{field}: {yaml_string(values[field])}" for field in TRACE_FIELDS)


def replace_trace(card_text: str, block: str) -> str:
    trace_pattern = re.compile(
        r"(?m)^(?:" + "|".join(map(re.escape, TRACE_FIELDS)) + r"):.*(?:\r?\n)?"
    )
    without_trace = trace_pattern.sub("", card_text)
    status_match = re.search(r"(?m)^status:.*$", without_trace)
    if not status_match:
        raise ValueError("front matter has no status field")
    return (
        without_trace[: status_match.end()]
        + "\n"
        + block
        + without_trace[status_match.end() :]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-dir", type=Path, default=miner.STOCK_DIR)
    parser.add_argument("--days", type=int, default=45)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    turns = collect_turns(args.days)
    counts = {"exact": 0, "ambiguous": 0, "missing": 0, "skipped": 0}
    for card_path in sorted(args.stock_dir.glob("*.md")):
        card_text = card_path.read_text(encoding="utf-8")
        if not args.force and re.search(
            r'(?m)^source_trace_status:\s*["\']?exact\b', card_text
        ):
            counts["skipped"] += 1
            continue

        highlight = extract_highlight(card_text)
        if highlight is None:
            status = "missing"
            matches: list[SourceTurn] = []
        else:
            user_quote, model_quote, source_agent = highlight
            matches = find_matches(turns, user_quote, model_quote, source_agent)
            status = "exact" if len(matches) == 1 else ("ambiguous" if matches else "missing")

        turn = matches[0] if status == "exact" else None
        counts[status] += 1
        print(f"[{status.upper():9}] {card_path.name}" + (f" -> {turn.session_id}" if turn else ""))
        if args.write:
            updated = replace_trace(card_text, trace_block(status, turn))
            card_path.write_text(updated, encoding="utf-8")

    print(
        "SUMMARY "
        + " ".join(f"{key}={value}" for key, value in counts.items())
        + f" scanned_turns={len(turns)} write={args.write}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
