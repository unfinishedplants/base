"""Mine beginner questions and their answers from local multi-agent logs.

This is a deterministic, local-only first pass. It creates review candidates,
not publishable articles. Every candidate retains an exact source trace so a
human can return to the original exchange before promoting it to a note draft.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_DIR = SCRIPT_DIR.parent.parent
DEFAULT_OUTPUT_DIR = REPO_DIR / "workbench" / "question-leads"
DEFAULT_CHECKPOINT_FILE = DEFAULT_OUTPUT_DIR / "_state" / "checkpoint.json"

sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(REPO_DIR / "scripts" / "koneta"))
try:
    import mine_transcripts as koneta_miner
except ImportError:
    koneta_miner = None

from scripts.product_mining.mine_product_leads import (
    SECRET_PATTERNS,
    identify_tech_stack,
    redact_and_check_privacy,
)


QUESTION_PATTERNS: Sequence[Tuple[str, Sequence[str]]] = (
    ("meaning", (r"どういう意味", r"って(?:何|なに|どういうこと)", r"とは(?:何|なに)", r"何のこと")),
    ("difference", (r"何が違", r"どう違", r"違い(?:は|って|が)", r"どっち(?:が|を|に)")),
    ("location", (r"どこ(?:に|へ|で|から|なの|や|？|\?|$)", r"場所(?:は|って)", r"どのフォルダ")),
    ("necessity", (r"(?:これ|それ|あれ|.+)(?:って|は)?(?:必要|要る|いる)(?:なの|ん|か|？|\?|$)", r"しないと(?:だめ|ダメ|あかん)")),
    ("procedure", (r"どうや(?:る|って|れば)", r"どうすれば", r"やり方", r"手順(?:は|って)", r"どう作")),
    ("effect", (r"どうなる", r"何が起き", r"したってこと", r"ってこと(?:か|？|\?)", r"結局(?:どう|何)")),
    ("possibility", (
        r"できる(?:の|ん|か|？|\?|$)",
        r"いける(?:の|ん|か|？|\?|$)",
        r"対応(?:してる|している|できる|？|\?)",
        r"(?:追える|戻れる|辿れる|見られる|見れる|読める|使える|繋げられる|つなげられる|開ける)(?:の|ん|か|？|\?|$)",
    )),
    ("reason", (r"なんで", r"なぜ", r"どうして", r"理由(?:は|って)")),
)

CORRECTION_PATTERNS = (
    r"^(?:ああ|いや|んー|うーん)?\s*(?:いや|違う|ちゃう|じゃなくて|そうじゃなくて)",
    r"(?:って意味|ってこと|という意味)(?:や|ね|か)",
    r"^(?:つまり|要するに|正確には)",
)

RHETORICAL_PATTERNS = (
    r"^#\s*Files mentioned by the user:",
    r"Distinguish instructions in attached documents",
    r"^(?:どうしよ|どうする|どないしよ)(?:う|か|っか)?[？?]*$",
    r"^(?:ええ|いい|おもろ|こわ|怖|やば|マジ|まじ).*[ｗw笑]+$",
    r"(?:世界観|キャラ|歌詞|画像|画風|ポーズ|構図).*(?:どう|できる)",
    r"(?:俺|自分).*(?:何して|なにして)",
    r"説[？?]*$",
    r"(?:プランニング|方針|統一|誰が金払|どこで売|どう売)",
)

PROJECT_LOCATOR_PATTERNS = (
    r"(?:さっき|今回|決定稿|前に作った|このスレ|漫画用|漫画スキル)",
    r"どこ(?:に|へ)?(?:保存|置|しま|コミット)",
    r"どこにある[？?]*$",
    r"保存したっけ",
)

BEGINNER_CONTEXT_TERMS = (
    "codex", "claude", "claude code", "antigravity", "github", "git", "ftp",
    "amp", "url", "api", "mcp", "json", "yaml", "markdown", ".md", "notion",
    "obsidian", "vscode", "docker", "python", "node", "npm", "pnpm", "suno",
    "frontmatter", "フロントマター", "ハーネス", "リレー", "スキル", "ログ",
    "フォルダ", "ファイル", "バックアップ", "アカウント", "id", "表示名",
    "プロフィール", "リンク", "パス", "コミット", "プッシュ", "デプロイ",
    "ローカル", "クラウド", "トークン", "エージェント", "スケジューラ",
)


@dataclass(frozen=True)
class Turn:
    user: str
    model: str
    time: str
    agent: str
    platform: str
    session_id: str
    log_path: str
    turn_index: int
    source_user_line: Optional[int]
    source_model_line: Optional[int]
    source_quote_hash: str


@dataclass
class QuestionLead:
    turn: Turn
    question_type: str
    question_original: str
    answer_excerpt: str
    title_seed: str
    detected_tech: List[str]
    term_candidates: List[str]
    score: int
    correction_turn: Optional[Turn]
    privacy_internal_risk: str
    status: str


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_question(text: str) -> str:
    text = normalize_space(text).lower()
    text = re.sub(r"^[\s、。]*(?:ああ|あー|えっと|ちなみに|ていうか|そういや|ほんで|あと)\s*", "", text)
    text = re.sub(r"[\s、。！？!?ｗw笑]+", "", text)
    return re.sub(r"(?:ん|の|か)$", "", text)


def classify_question(text: str) -> Optional[str]:
    clean = normalize_space(text)
    # Longer incident narratives belong to product_mining; this pipe wants a
    # question that can become a concrete beginner-facing title by itself.
    if not clean or len(clean) < 4 or len(clean) > 240:
        return None
    for pat in RHETORICAL_PATTERNS:
        if re.search(pat, clean, flags=re.IGNORECASE):
            return None
    for question_type, patterns in QUESTION_PATTERNS:
        if any(re.search(pat, clean, flags=re.IGNORECASE) for pat in patterns):
            return question_type
    return None


def is_correction(text: str) -> bool:
    clean = normalize_space(text)
    return any(re.search(pat, clean, flags=re.IGNORECASE) for pat in CORRECTION_PATTERNS)


def extract_term_candidates(text: str) -> List[str]:
    lower = text.lower()
    found: List[str] = []
    for term in BEGINNER_CONTEXT_TERMS:
        if term.lower() in lower and term not in found:
            found.append(term)
    code_terms = re.findall(
        r"(?:/[\w./-]+/|[\w.-]+\.(?:md|json|ya?ml|py|js|ts|tsx|ps1|toml)|--[a-z0-9-]+)",
        text,
        flags=re.IGNORECASE,
    )
    for term in code_terms:
        if term not in found:
            found.append(term)
    ascii_terms = re.findall(r"(?<![\w])(?:[A-Za-z][A-Za-z0-9._/-]{2,}|\d+(?:\.\d+)+(?:[A-Za-z]+)?)(?![\w])", text)
    ignored = {"the", "and", "for", "with", "this", "that", "what", "how"}
    for term in ascii_terms:
        if term.lower() not in ignored and term not in found:
            found.append(term)
    return found[:8]


def clean_title_seed(question: str) -> str:
    title = normalize_space(question)
    title = re.sub(r"^(?:ああ|あー|えっと|ちなみに|ていうか|そういや|ほんで|あと)[、\s]*", "", title)
    title = re.sub(r"[ｗw笑]+$", "", title).strip(" 　、。")
    if not title.endswith(("？", "?")):
        title += "？"
    return title[:120]


def excerpt(text: str, limit: int = 500) -> str:
    clean = normalize_space(text)
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def turn_is_within_window(turn_time: str, session_mtime: float, cutoff_time: float) -> bool:
    """Use the turn timestamp when available; fall back to session mtime."""
    if turn_time:
        try:
            return datetime.fromisoformat(turn_time.replace("Z", "+00:00")).timestamp() >= cutoff_time
        except Exception:
            pass
    return session_mtime >= cutoff_time


def calculate_score(
    question: str,
    question_type: str,
    answer: str,
    terms: Sequence[str],
    correction_turn: Optional[Turn],
) -> int:
    score = 3
    if question_type in {"meaning", "difference", "location", "procedure"}:
        score += 2
    if terms:
        score += 2
    if 8 <= len(normalize_space(question)) <= 120:
        score += 1
    if len(normalize_space(answer)) >= 80:
        score += 1
    if correction_turn is not None:
        score += 1
    if not terms:
        score -= 3
    if any(re.search(pat, question, flags=re.IGNORECASE) for pat in PROJECT_LOCATOR_PATTERNS):
        score -= 4
    if len(question) > 300:
        score -= 2
    if not terms and question_type in {"possibility", "reason", "effect"}:
        score -= 2
    return max(score, 0)


def build_question_leads(turns: Sequence[Turn], minimum_score: int = 6) -> List[QuestionLead]:
    grouped: Dict[Tuple[str, str], List[Turn]] = {}
    for turn in turns:
        grouped.setdefault((turn.platform, turn.session_id), []).append(turn)

    leads: List[QuestionLead] = []
    seen_questions: Set[str] = set()
    for session_turns in grouped.values():
        session_turns.sort(key=lambda t: t.turn_index)
        consumed_as_correction: Set[int] = set()
        for idx, turn in enumerate(session_turns):
            if idx in consumed_as_correction:
                continue
            question_type = classify_question(turn.user)
            if question_type is None:
                continue
            normalized = normalize_question(turn.user)
            if not normalized or normalized in seen_questions:
                continue

            correction_turn = None
            if idx + 1 < len(session_turns):
                nxt = session_turns[idx + 1]
                if nxt.turn_index == turn.turn_index + 1 and is_correction(nxt.user):
                    correction_turn = nxt
                    consumed_as_correction.add(idx + 1)

            combined = f"{turn.user} {turn.model}"
            # Article discoverability must be visible in the question itself.
            # Terms present only in the answer do not make a vague question self-contained.
            terms = extract_term_candidates(turn.user)
            tech = identify_tech_stack(combined)
            score = calculate_score(turn.user, question_type, turn.model, terms, correction_turn)
            if score < minimum_score:
                continue

            redacted_question, q_sensitive = redact_and_check_privacy(turn.user)
            redacted_answer, a_sensitive = redact_and_check_privacy(turn.model)
            correction_sensitive = False
            if correction_turn:
                _, c_user_sensitive = redact_and_check_privacy(correction_turn.user)
                _, c_model_sensitive = redact_and_check_privacy(correction_turn.model)
                correction_sensitive = c_user_sensitive or c_model_sensitive
            has_sensitive = q_sensitive or a_sensitive or correction_sensitive

            leads.append(
                QuestionLead(
                    turn=turn,
                    question_type=question_type,
                    question_original=redacted_question,
                    answer_excerpt=excerpt(redacted_answer),
                    title_seed=clean_title_seed(redacted_question),
                    detected_tech=tech,
                    term_candidates=terms,
                    score=score,
                    correction_turn=correction_turn,
                    privacy_internal_risk="high" if has_sensitive else "low",
                    status="review_needed" if has_sensitive else "candidate",
                )
            )
            seen_questions.add(normalized)

    return sorted(leads, key=lambda lead: (-lead.score, lead.turn.time, lead.turn.source_quote_hash))


def collect_all_turns(cutoff_time: float) -> List[Turn]:
    if koneta_miner is None:
        print("[WARN] koneta miner parser is unavailable")
        return []

    sessions: List[Tuple[float, str, str, Path, str]] = []
    for mtime, agent, sid, path in koneta_miner.get_antigravity_sessions(cutoff_time):
        sessions.append((mtime, agent, sid, path, "antigravity"))
    for mtime, agent, sid, path in koneta_miner.get_codex_sessions(cutoff_time):
        sessions.append((mtime, agent, sid, path, "codex"))
    for mtime, agent, sid, path in koneta_miner.get_claude_sessions(cutoff_time):
        sessions.append((mtime, agent, sid, path, "claude-code"))

    print(f"  sessions: antigravity={sum(s[4] == 'antigravity' for s in sessions)} "
          f"codex={sum(s[4] == 'codex' for s in sessions)} "
          f"claude-code={sum(s[4] == 'claude-code' for s in sessions)}")

    turns: List[Turn] = []
    for session_mtime, agent, session_id, log_path, platform in sessions:
        if platform == "antigravity":
            raw_turns = koneta_miner.extract_turns_from_antigravity(log_path)
        elif platform == "codex":
            raw_turns = koneta_miner.extract_turns_from_codex(log_path)
        else:
            raw_turns = koneta_miner.extract_turns_from_claude(log_path)
        for index, raw in enumerate(raw_turns, start=1):
            if not turn_is_within_window(str(raw.get("time") or ""), session_mtime, cutoff_time):
                continue
            turns.append(
                Turn(
                    user=str(raw["user"]),
                    model=str(raw["model"]),
                    time=str(raw.get("time") or ""),
                    agent=agent,
                    platform=platform,
                    session_id=session_id,
                    log_path=str(log_path.resolve()),
                    turn_index=index,
                    source_user_line=raw.get("source_user_line"),
                    source_model_line=raw.get("source_model_line"),
                    source_quote_hash=koneta_miner.turn_quote_hash(str(raw["user"]), str(raw["model"])),
                )
            )
    return turns


def yaml_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def lead_date(lead: QuestionLead) -> str:
    try:
        return datetime.fromisoformat(lead.turn.time.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return datetime.now(timezone.utc).date().isoformat()


def trace_entry(turn: Turn, role: str) -> str:
    return "\n".join(
        [
            f"  - role_in_candidate: {yaml_value(role)}",
            f"    turn_index: {turn.turn_index}",
            f"    turn_at: {yaml_value(turn.time)}",
            f"    user_line: {turn.source_user_line or ''}",
            f"    model_line: {turn.source_model_line or ''}",
            f"    quote_hash: {yaml_value(turn.source_quote_hash)}",
        ]
    )


def format_question_lead_markdown(lead: QuestionLead, candidate_id: str) -> str:
    turn = lead.turn
    correction_user = ""
    correction_answer = ""
    source_turns = [trace_entry(turn, "question")]
    correction_status = "none"
    if lead.correction_turn:
        correction_status = "followup_correction"
        correction_user, _ = redact_and_check_privacy(lead.correction_turn.user)
        correction_answer, _ = redact_and_check_privacy(lead.correction_turn.model)
        source_turns.append(trace_entry(lead.correction_turn, "correction"))

    return f"""---
candidate_id: {yaml_value(candidate_id)}
date: {yaml_value(lead_date(lead))}
status: {yaml_value(lead.status)}
pipeline: "question-mining-v1"
question_type: {yaml_value(lead.question_type)}
score: {lead.score}
title_seed: {yaml_value(lead.title_seed)}
question_original: {yaml_value(lead.question_original)}
answer_excerpt: {yaml_value(lead.answer_excerpt)}
correction_status: {yaml_value(correction_status)}
detected_tech: {yaml_value(lead.detected_tech)}
term_candidates: {yaml_value(lead.term_candidates)}
privacy_internal_risk: {yaml_value(lead.privacy_internal_risk)}
source_trace_status: "exact"
source_platform: {yaml_value(turn.platform)}
source_agent: {yaml_value(turn.agent)}
source_session_id: {yaml_value(turn.session_id)}
source_log_path: {yaml_value(turn.log_path)}
source_turn_at: {yaml_value(turn.time)}
source_turn_index: {turn.turn_index}
source_user_line: {turn.source_user_line or ''}
source_model_line: {turn.source_model_line or ''}
source_quote_hash: {yaml_value(turn.source_quote_hash)}
source_turns:
{chr(10).join(source_turns)}
---

# {lead.title_seed}

## 初心者が止まった瞬間

> {lead.question_original}

## その場で返された答え（要約候補）

{lead.answer_excerpt}

## 後続の言い直し・訂正

{('> ' + correction_user + chr(10) + chr(10) + excerpt(correction_answer)) if correction_user else 'なし'}

## 記事へ育てる時の確認

- [ ] 元ログへ戻り、前後の文脈を読む
- [ ] 固有名・ローカルパス・秘密情報を除く
- [ ] 初心者が検索する困りごとへタイトルを直す
- [ ] 回答を現在の仕様で再検証する
- [ ] 無料用語解説 / 有料手順 / ブログのどこへ出すか決める

> このカードはローカル候補です。note公開、下書き昇格、予約投稿を承認するものではありません。
"""


def load_checkpoint(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"version": 1, "processed": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"version": 1, "processed": {}}
    except Exception:
        return {"version": 1, "processed": {}}


def save_checkpoint(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def existing_sequence(output_dir: Path, day: str) -> int:
    maximum = 0
    if output_dir.exists():
        for path in output_dir.glob(f"{day}-ql-*.md"):
            match = re.search(r"-ql-(\d+)\.md$", path.name)
            if match:
                maximum = max(maximum, int(match.group(1)))
    return maximum


def mine_question_leads(
    lookback_hours: int = 168,
    max_candidates: int = 10,
    minimum_score: int = 6,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    checkpoint_file: Path = DEFAULT_CHECKPOINT_FILE,
    dry_run: bool = False,
    force: bool = False,
) -> List[Path]:
    cutoff = time.time() - lookback_hours * 3600
    print("===================================================")
    print("  ProjectYure Beginner Question Miner")
    print("===================================================")
    print(f"lookback={lookback_hours}h max={max_candidates} min_score={minimum_score}")
    print(f"output={output_dir}")
    print(f"dry_run={dry_run}")

    turns = collect_all_turns(cutoff)
    leads = build_question_leads(turns, minimum_score=minimum_score)
    checkpoint = {"version": 1, "processed": {}} if force else load_checkpoint(checkpoint_file)
    processed = checkpoint.get("processed", {}) if isinstance(checkpoint.get("processed", {}), dict) else {}
    existing_hashes: Set[str] = set(processed.keys())
    existing_questions: Set[str] = {
        str(info.get("question_normalized"))
        for info in processed.values()
        if isinstance(info, dict) and info.get("question_normalized")
    }
    if output_dir.exists():
        for path in output_dir.glob("*.md"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            match = re.search(r'^source_quote_hash:\s*["\']?([0-9a-f]{64})', text, flags=re.MULTILINE)
            if match:
                existing_hashes.add(match.group(1))
            question_match = re.search(r"^question_original:\s*(.+)$", text, flags=re.MULTILINE)
            if question_match:
                raw_question = question_match.group(1).strip()
                try:
                    parsed_question = json.loads(raw_question)
                except Exception:
                    parsed_question = raw_question.strip("'\"")
                existing_questions.add(normalize_question(str(parsed_question)))

    selected: List[QuestionLead] = []
    for lead in leads:
        normalized = normalize_question(lead.question_original)
        if lead.turn.source_quote_hash in existing_hashes or normalized in existing_questions:
            continue
        selected.append(lead)
        existing_questions.add(normalized)
        if len(selected) >= max_candidates:
            break
    print(f"turns={len(turns)} leads={len(leads)} new={len(selected)}")

    generated: List[Path] = []
    next_by_day: Dict[str, int] = {}
    for lead in selected:
        day = lead_date(lead)
        next_by_day.setdefault(day, existing_sequence(output_dir, day))
        next_by_day[day] += 1
        seq = next_by_day[day]
        candidate_id = f"QL-{day.replace('-', '')}-{seq:03d}"
        filename = f"{day}-ql-{seq:03d}.md"
        path = output_dir / filename
        body = format_question_lead_markdown(lead, candidate_id)

        if dry_run:
            print(f"  [DRY] {candidate_id} score={lead.score} type={lead.question_type} :: {lead.title_seed}")
            continue
        if path.exists():
            print(f"  [SKIP] non-overwrite: {path.name}")
            continue
        output_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        generated.append(path)
        processed[lead.turn.source_quote_hash] = {
            "candidate_id": candidate_id,
            "path": str(path),
            "question_normalized": normalize_question(lead.question_original),
        }
        print(f"  [SAVED] {candidate_id} :: {lead.title_seed}")

    if not dry_run and generated:
        checkpoint.update({
            "version": 1,
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "processed": processed,
        })
        save_checkpoint(checkpoint_file, checkpoint)
    return generated


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine beginner questions from local agent logs")
    parser.add_argument("--lookback-hours", type=int, default=168)
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--minimum-score", type=int, default=6)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--checkpoint-file", type=Path, default=DEFAULT_CHECKPOINT_FILE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    mine_question_leads(
        lookback_hours=args.lookback_hours,
        max_candidates=args.max_candidates,
        minimum_score=args.minimum_score,
        output_dir=args.output_dir,
        checkpoint_file=args.checkpoint_file,
        dry_run=args.dry_run,
        force=args.force,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
