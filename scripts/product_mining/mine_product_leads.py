"""Product Lead Miner for Multi-Agent session logs (Antigravity / Codex / Claude Code).

Deterministic 1st-stage pipeline:
1. Gathers session transcripts across all agents.
2. Extracts problem-solving episodes with strict time-gap and topic/target binding.
3. Scores episodes deterministically on pain, market breadth, recurrence, verified fix, deliverable assets, and skill expansion.
4. Generates structured Markdown candidate cards with full multi-turn trace provenance.
5. Idempotent candidate ID management with collision avoidance and strict non-overwriting guarantees.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Windows UTF-8 console output support
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_DIR = SCRIPT_DIR.parent.parent
WORKBENCH_DIR = REPO_DIR / "workbench"
DEFAULT_OUTPUT_DIR = WORKBENCH_DIR / "product-leads"
DEFAULT_CHECKPOINT_FILE = DEFAULT_OUTPUT_DIR / "_state" / "checkpoint.json"

# Import log extraction functions from existing koneta tools
sys.path.insert(0, str(REPO_DIR / "scripts" / "koneta"))
try:
    import mine_transcripts as koneta_miner
except ImportError:
    koneta_miner = None

MAX_EPISODE_GAP_SECONDS = 1800  # 30 minutes threshold for episode continuation

# ---------------------------------------------------------------------------
# Privacy Redaction Rules
# ---------------------------------------------------------------------------

SECRET_PATTERNS = [
    (r"\bsk-[a-zA-Z0-9]{20,}\b", "[REDACTED_OPENAI_KEY]"),
    (r"\bAIza[0-9A-Za-z-_]{30,45}\b", "[REDACTED_API_KEY]"),
    (r"\bghp_[a-zA-Z0-9]{20,40}\b", "[REDACTED_GITHUB_TOKEN]"),
    (r"\bxox[baprs]-[0-9a-zA-Z-]{10,}\b", "[REDACTED_SLACK_TOKEN]"),
    (r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+ PRIVATE KEY-----", "[REDACTED_PRIVATE_KEY]"),
    (r"(?i)\b(?:bearer\s+[a-zA-Z0-9_\-\.]{20,})\b", "Bearer [REDACTED_TOKEN]"),
    (r"(?i)\b(?:password|passwd|pwd)\s*[:=]\s*['\"][^'\"]+['\"]", "password='[REDACTED_PASSWORD]'"),
    (r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "[REDACTED_EMAIL]"),
]


def redact_and_check_privacy(text: str) -> Tuple[str, bool]:
    """Redacts secret patterns from text and flags if any sensitive data was found."""
    if not text:
        return "", False
    redacted = text
    has_sensitive = False
    for pat, repl in SECRET_PATTERNS:
        if re.search(pat, redacted, flags=re.IGNORECASE):
            has_sensitive = True
            redacted = re.sub(pat, repl, redacted, flags=re.IGNORECASE)
    return redacted, has_sensitive

# ---------------------------------------------------------------------------
# Target Signal & Topic Extraction
# ---------------------------------------------------------------------------

TECH_KEYWORDS_MAP = {
    "Docker": ["docker", "dockerfile", "container", "docker-compose"],
    "Python": ["python", "pip", "pytest", "uv", ".py", "pipenv", "poetry"],
    "Node.js": ["node", "npm", "npx", "yarn", "pnpm", "package.json", ".mjs", ".cjs"],
    "TypeScript": ["typescript", "tsc", ".ts", ".tsx", "ts-node"],
    "JavaScript": ["javascript", "js", ".js", ".jsx"],
    "Git": ["git", "commit", "branch", "merge", "rebase", "stash"],
    "PowerShell": ["powershell", "pwsh", ".ps1"],
    "GitHub Actions": ["github actions", "workflow", ".github/workflows"],
    "Quartz": ["quartz"],
    "Obsidian": ["obsidian"],
    "Markdown": ["markdown", ".md"],
    "JSON": ["json", ".json"],
    "YAML": ["yaml", ".yaml", ".yml"],
    "ESLint": ["eslint"],
    "Prettier": ["prettier"],
    "Vite": ["vite"],
    "React": ["react", ".tsx", ".jsx"],
    "RSS": ["rss", "feed", "xml"],
    "Task Scheduler": ["task scheduler", "schtasks", "scheduledtask"],
    "Windows": ["windows", "win32", "powershell"],
    "Linux": ["linux", "ubuntu", "bash"],
    "CI/CD": ["ci/cd", "continuous integration", "github actions"],
    "YuRelay": ["yurelay"],
    "Antigravity": ["antigravity"],
    "Codex": ["codex"],
    "Claude Code": ["claude code", "claude"],
    "MCP": ["mcp", "model context protocol"],
    "REST API": ["rest api", "http api", "endpoint"],
}


def extract_target_signals(text: str) -> Set[str]:
    """Extracts normalized technology, tool, script, and file signals from text."""
    signals: Set[str] = set()
    if not text:
        return signals
    text_lower = text.lower()

    for tech_name, pats in TECH_KEYWORDS_MAP.items():
        for p in pats:
            if p.startswith("."):
                if p in text_lower:
                    signals.add(tech_name.lower())
            else:
                if re.search(r"\b" + re.escape(p) + r"\b", text_lower):
                    signals.add(tech_name.lower())

    filenames = re.findall(r"[\w\.-]+\.(?:py|mjs|cjs|js|ts|tsx|jsx|json|ya?ml|ps1|md|toml|sh)\b", text, re.IGNORECASE)
    for f in filenames:
        signals.add(f.lower())

    commands = re.findall(r"\b(?:docker\s+\w+|npm\s+\w+|pytest\s+[\w\.-]+|node\s+[\w\.-]+|git\s+\w+|python\s+[\w\.-]+)\b", text_lower)
    for c in commands:
        signals.add(c.lower())

    return signals


def identify_tech_stack(text: str) -> List[str]:
    """Returns canonical display names of identified technologies."""
    found: List[str] = []
    text_lower = text.lower()
    for tech_name, patterns in TECH_KEYWORDS_MAP.items():
        for pat in patterns:
            if pat.startswith("."):
                if pat in text_lower and tech_name not in found:
                    found.append(tech_name)
            else:
                if re.search(r"\b" + re.escape(pat) + r"\b", text_lower) and tech_name not in found:
                    found.append(tech_name)
    return found


def parse_iso_time(time_str: str) -> float:
    """Parses ISO timestamp string to epoch seconds."""
    if not time_str:
        return 0.0
    try:
        clean_str = time_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean_str).timestamp()
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Problem, Fix, Verification & Negation Rules
# ---------------------------------------------------------------------------

PROBLEM_TRIGGERS = [
    r"\b(?:error|exception|failed|failure|traceback|crashed|timed out)\b",
    r"\b(?:cannot find|not found|permission denied|syntax error|assertionerror|typeerror|attributeerror)\b",
    r"\bexit code [1-9]\b",
    r"\bfatal\b",
    r"エラー",
    r"失敗",
    r"動かない",
    r"落ちる",
    r"直らない",
    r"バグ",
    r"不具合",
    r"壊れ",
]

CHECKLIST_OR_DESIGN_PATTERNS = [
    r"^[-\*]\s*(?:失敗時|エラー時|縮退動作|未完了|確認項目|どこへ戻るか|Notionへ接続|UTF-8)",
    r"チェックリスト",
    r"完成条件",
    r"設計方針",
    r"要件定義",
    r"ルー語になってるとこは直したい",
]

ROOT_CAUSE_TRIGGERS = [
    r"原因は\s*(.+)",
    r"root cause(?::|\s+is)\s*(.+)",
    r"理由は\s*(.+)",
    r"(.+?)(?:によるもの|に起因|の不整合|の未定義|の競合)",
    r"\bmismatch in\s+(.+)",
    r"\bmissing\s+(.+)",
]

FIX_TRIGGERS = [
    r"(?:修正|対応|改善|書き換え|変更)(?:した|しました|します|完了|を適用|して|中|案|自身)?",
    r"\b(?:fix|fixed|patch|patched|replaced|updated|added|add|modify|modified)\b",
]

VERIFICATION_TRIGGERS = [
    r"\bexit code 0\b",
    r"\b(?:pytest|unittest|jest|vitest)\b.*?\b(?:passed|ok|success)\b",
    r"テスト(?:を|が)?(?:通過|パス|成功|すべてパス)",
    r"\b(?:build|compilation|run)\b.*?\b(?:succeeded|success|passed)\b",
    r"正常に(?:動作|終了|ビルド|実行|完了)",
    r"(?:問題|エラー|不具合)が(?:解消|解決|直った)",
    r"動作確認(?:を?行い|完了|OK|できました)",
]

EXCLUDED_VERIFICATION_PATTERNS = [
    r"ダイヤモンドバリデーション",
    r"埋め込み＆配置完了",
    r"視認性バッチリ",
    r"未完了事項",
    r"引き継ぐ",
]

NEGATION_PATTERNS = [
    r"未解決",
    r"根治(?:は|して|してい)?(?:ない|せず|しきれてない|ません)",
    r"根治不可",
    r"対症療法",
    r"暫定(?:対応|措置|修正|回避)",
    r"ワークアラウンド\b",
    r"workaround\b",
    r"一時的(?:な|に)",
    r"推測(?:です|の域|に基づく)?",
    r"確認(?:不能|できていない|できてない|待ち|中)",
    r"未確認",
    r"未検証",
    r"再発の(?:可能性|恐れ)",
    r"治りきって(?:ない|いない)",
    r"直りきって(?:ない|いない)",
    r"再現不能",
    r"原因不明",
    r"仮対応",
    r"not fully resolved",
    r"tentative fix",
    r"unconfirmed",
]


def check_negation_or_hedging(text: str) -> Tuple[bool, List[str]]:
    """Checks if text contains negative, provisional, or hedging expressions."""
    if not text:
        return False, []
    matched = []
    for pat in NEGATION_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            matched.append(pat)
    return len(matched) > 0, matched


def is_checklist_or_false_positive(text: str) -> bool:
    """Checks whether text looks like a checklist or design discussion rather than an error."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return True
    checklist_count = sum(1 for l in lines if any(re.search(p, l) for p in CHECKLIST_OR_DESIGN_PATTERNS))
    if checklist_count >= 2 or (checklist_count == 1 and len(lines) <= 2):
        return True
    return False




# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
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
class TurnTrace:
    turn_index: int
    turn_at: str
    user_line: Optional[int]
    model_line: Optional[int]
    quote_hash: str
    role_in_episode: str


@dataclass
class Episode:
    session_id: str
    agent: str
    platform: str
    log_path: str
    start_turn_index: int
    end_turn_index: int
    start_time: str
    start_user_line: Optional[int]
    start_model_line: Optional[int]
    source_quote_hash: str
    symptom: str
    initial_suspicion: str
    investigation: str
    root_cause: str
    fix: str
    verification_evidence: str
    reusable_procedure: str
    detected_tech: List[str]
    target_signals: Set[str]
    has_privacy_risk: bool
    has_negation: bool
    raw_user_sample: str
    raw_model_sample: str
    contributing_turns: List[TurnTrace] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Episode Clustering with Time Gap and Topic Binding
# ---------------------------------------------------------------------------

def extract_episodes_from_turns(turns: List[Turn]) -> List[Episode]:
    """Clusters turns within the same session using strict time-gap and topic/target binding."""
    if not turns:
        return []

    sessions: Dict[Tuple[str, str], List[Turn]] = {}
    for t in turns:
        key = (t.platform, t.session_id)
        if key not in sessions:
            sessions[key] = []
        sessions[key].append(t)

    episodes: List[Episode] = []

    for (platform, session_id), session_turns in sessions.items():
        session_turns.sort(key=lambda x: x.turn_index)
        num_turns = len(session_turns)
        i = 0

        while i < num_turns:
            t_start = session_turns[i]
            combined_start = f"{t_start.user}\n{t_start.model}"

            is_problem = any(re.search(pat, combined_start, re.IGNORECASE) for pat in PROBLEM_TRIGGERS)
            if not is_problem or is_checklist_or_false_positive(t_start.user):
                i += 1
                continue

            episode_turns: List[Turn] = [t_start]
            ep_signals = extract_target_signals(combined_start)
            last_epoch = parse_iso_time(t_start.time)

            j = i + 1
            while j < num_turns and len(episode_turns) < 3:
                next_t = session_turns[j]
                next_epoch = parse_iso_time(next_t.time)

                if last_epoch > 0 and next_epoch > 0:
                    time_gap = next_epoch - last_epoch
                    if time_gap > MAX_EPISODE_GAP_SECONDS:
                        break

                next_signals = extract_target_signals(f"{next_t.user}\n{next_t.model}")
                if ep_signals and next_signals:
                    overlap = ep_signals & next_signals
                    if not overlap:
                        break

                episode_turns.append(next_t)
                ep_signals |= next_signals
                if next_epoch > 0:
                    last_epoch = next_epoch
                j += 1

            symptom_parts = []
            suspicion_parts = []
            investigation_parts = []
            root_cause_parts = []
            fix_parts = []
            verification_parts = []
            all_text_parts = []
            contributing_traces: List[TurnTrace] = []
            has_sensitive = False
            has_negation = False

            for turn_idx, et in enumerate(episode_turns):
                u_clean, u_sens = redact_and_check_privacy(et.user)
                m_clean, m_sens = redact_and_check_privacy(et.model)
                if u_sens or m_sens:
                    has_sensitive = True

                u_neg, _ = check_negation_or_hedging(u_clean)
                m_neg, _ = check_negation_or_hedging(m_clean)
                if u_neg or m_neg:
                    has_negation = True

                all_text_parts.append(f"Turn {et.turn_index}:\nUser: {u_clean}\nModel: {m_clean}")
                roles: List[str] = []

                for speaker_text in [u_clean, m_clean]:
                    for line in speaker_text.split("\n"):
                        l_str = line.strip()
                        if not l_str:
                            continue

                        if any(re.search(p, l_str, re.IGNORECASE) for p in PROBLEM_TRIGGERS):
                            if not any(re.search(p, l_str) for p in CHECKLIST_OR_DESIGN_PATTERNS):
                                if turn_idx <= 1 and len(symptom_parts) < 2:
                                    symptom_parts.append(l_str)
                                    if "symptom" not in roles:
                                        roles.append("symptom")

                        if any(re.search(p, l_str, re.IGNORECASE) for p in ROOT_CAUSE_TRIGGERS):
                            if not any(re.search(p, l_str) for p in CHECKLIST_OR_DESIGN_PATTERNS):
                                root_cause_parts.append(l_str)
                                if "root_cause" not in roles:
                                    roles.append("root_cause")

                        if any(re.search(p, l_str, re.IGNORECASE) for p in FIX_TRIGGERS):
                            if not any(re.search(p, l_str) for p in CHECKLIST_OR_DESIGN_PATTERNS):
                                fix_parts.append(l_str)
                                if "fix" not in roles:
                                    roles.append("fix")

                        if any(k in l_str for k in ["調査", "確認", "inspect", "check", "ログ", "stack trace"]):
                            if not any(re.search(p, l_str) for p in CHECKLIST_OR_DESIGN_PATTERNS):
                                investigation_parts.append(l_str)

                contributing_traces.append(
                    TurnTrace(
                        turn_index=et.turn_index,
                        turn_at=et.time,
                        user_line=et.source_user_line,
                        model_line=et.source_model_line,
                        quote_hash=et.source_quote_hash,
                        role_in_episode=",".join(roles) if roles else "context",
                    )
                )

            symptom = " ".join(dict.fromkeys(symptom_parts))[:250].strip()
            if not symptom or is_checklist_or_false_positive(symptom):
                i += 1
                continue

            root_cause = " ".join(dict.fromkeys(root_cause_parts))[:250].strip()
            fix = " ".join(dict.fromkeys(fix_parts))[:250].strip()
            initial_suspicion = " ".join(dict.fromkeys(suspicion_parts))[:200].strip()
            investigation = " ".join(dict.fromkeys(investigation_parts))[:250].strip()

            core_problem_signals = extract_target_signals(f"{symptom} {root_cause} {fix}")

            for trace, et in zip(contributing_traces, episode_turns):
                u_clean, _ = redact_and_check_privacy(et.user)
                m_clean, _ = redact_and_check_privacy(et.model)
                for speaker_text in [u_clean, m_clean]:
                    for line in speaker_text.split("\n"):
                        l_str = line.strip()
                        if not l_str:
                            continue
                        if any(re.search(p, l_str, re.IGNORECASE) for p in VERIFICATION_TRIGGERS):
                            if not any(re.search(p, l_str, re.IGNORECASE) for p in EXCLUDED_VERIFICATION_PATTERNS):
                                line_signals = extract_target_signals(l_str)
                                if not line_signals or not core_problem_signals or not (line_signals & core_problem_signals):
                                    continue
                                verification_parts.append(l_str)
                                if "verification" not in trace.role_in_episode:
                                    if trace.role_in_episode == "context":
                                        trace.role_in_episode = "verification"
                                    else:
                                        trace.role_in_episode = (trace.role_in_episode + ",verification").strip(",")

            verification = " ".join(dict.fromkeys(verification_parts))[:200].strip()

            if fix and root_cause:
                reusable_procedure = f"1. 症状の確認: {symptom[:80]}\n2. 原因特定: {root_cause[:80]}\n3. 修正適用: {fix[:80]}\n4. 検証: {verification[:80] if verification else '実行確認'}"
            elif fix:
                reusable_procedure = f"1. 症状の確認: {symptom[:80]}\n2. 原因特定: 設定・コードの不整合を確認\n3. 修正適用: {fix[:80]}\n4. 検証: {verification[:80] if verification else '実行確認'}"
            else:
                reusable_procedure = ""

            tech_stack = identify_tech_stack(" ".join(all_text_parts))
            first_turn = episode_turns[0]
            last_turn = episode_turns[-1]

            ep = Episode(
                session_id=first_turn.session_id,
                agent=first_turn.agent,
                platform=first_turn.platform,
                log_path=first_turn.log_path,
                start_turn_index=first_turn.turn_index,
                end_turn_index=last_turn.turn_index,
                start_time=first_turn.time,
                start_user_line=first_turn.source_user_line,
                start_model_line=first_turn.source_model_line,
                source_quote_hash=first_turn.source_quote_hash,
                symptom=symptom,
                initial_suspicion=initial_suspicion,
                investigation=investigation,
                root_cause=root_cause,
                fix=fix,
                verification_evidence=verification,
                reusable_procedure=reusable_procedure,
                detected_tech=tech_stack,
                target_signals=ep_signals,
                has_privacy_risk=has_sensitive,
                has_negation=has_negation,
                raw_user_sample=first_turn.user[:200],
                raw_model_sample=first_turn.model[:200],
                contributing_turns=contributing_traces,
            )
            episodes.append(ep)
            i += len(episode_turns)

    return episodes
# ---------------------------------------------------------------------------
# Scoring Algorithm & Status Gate
# ---------------------------------------------------------------------------

@dataclass
class ScoreBreakdown:
    pain_strength: int
    audience_breadth: int
    recurrence: int
    verified_fix_strength: int
    deliverable_assetability: int
    skill_expansion: int
    internal_only: int
    one_off_environment_accident: int
    total_score: int


def calculate_score(ep: Episode) -> Tuple[ScoreBreakdown, str, str]:
    """Calculates deterministic score and returns (breakdown, fix_status, status)."""
    full_text = f"{ep.symptom} {ep.investigation} {ep.root_cause} {ep.fix} {ep.verification_evidence} {ep.raw_user_sample} {ep.raw_model_sample}"

    pain = 1
    if any(k in full_text.lower() for k in ["fatal", "crash", "exit code 1", "assertionerror", "破損", "失敗", "cannot find"]):
        pain = 4
    if any(k in full_text.lower() for k in ["timed out", "permission denied", "無限ループ", "即死", "壊れ"]):
        pain = 5
    elif any(k in full_text.lower() for k in ["warning", "typo", "警告", "軽微"]):
        pain = 2

    audience = 1
    major_techs = ["python", "node.js", "typescript", "javascript", "powershell", "git", "github actions", "docker", "ci/cd", "react", "markdown", "windows", "linux"]
    matched_major = [t for t in ep.detected_tech if t.lower() in major_techs]
    if len(matched_major) >= 2:
        audience = 4
    elif len(matched_major) == 1:
        audience = 3
    if "ProjectYure" in full_text and len(matched_major) == 0:
        audience = 1

    recurrence = 1
    if any(k in full_text.lower() for k in ["再発", "頻出", "mismatch", "format", "timezone", "encoding", "utf-8", "path", "cache", "version"]):
        recurrence = 3
    if any(k in full_text.lower() for k in ["設定ミス", "ハマりどころ", "依存関係", "conflict"]):
        recurrence = 2

    if ep.verification_evidence and ep.fix and ep.root_cause and not ep.has_negation:
        verified_fix = 5
        fix_status = "verified"
    elif ep.fix:
        verified_fix = 2
        fix_status = "unverified"
    else:
        verified_fix = 0
        fix_status = "investigating"

    deliverable = 1
    if ep.fix and ep.root_cause:
        deliverable = 3
    if ep.reusable_procedure:
        deliverable = 4

    skill = 0
    if any(k in full_text.lower() for k in ["script", "tool", "cli", "regex", "validator", "automation", "scheduler"]):
        skill = 2
    if len(ep.detected_tech) >= 2:
        skill = 3

    internal = 0
    if "yure" in full_text.lower() or "harness" in full_text.lower() or "voronoi" in full_text.lower():
        internal = 2
    if "internal" in full_text.lower() or ".projectyure" in full_text.lower():
        internal = 3

    one_off = 0
    if any(k in full_text.lower() for k in ["typo", "誤字", "単発", "勘違い", "打ち間違い"]):
        one_off = 3

    core_signals = extract_target_signals(f"{ep.symptom} {ep.root_cause} {ep.fix}")
    verif_signals = extract_target_signals(ep.verification_evidence)

    if not core_signals or not verif_signals or not (core_signals & verif_signals):
        if fix_status == "verified":
            fix_status = "unverified"
            verified_fix = 2

    total = pain + audience + recurrence + verified_fix + deliverable + skill - internal - one_off

    if ep.has_privacy_risk or ep.has_negation:
        status = "review_needed"
    elif fix_status == "verified" and ep.root_cause and core_signals and verif_signals and (core_signals & verif_signals) and total >= 12:
        status = "product-ready"
    elif total >= 7:
        status = "candidate"
    else:
        status = "unverified"

    if status == "product-ready":
        if fix_status != "verified" or not ep.root_cause or ep.has_negation or ep.has_privacy_risk or not ep.verification_evidence or not core_signals or not verif_signals or not (core_signals & verif_signals):
            status = "review_needed" if (ep.has_negation or ep.has_privacy_risk) else "candidate"

    breakdown = ScoreBreakdown(
        pain_strength=pain,
        audience_breadth=audience,
        recurrence=recurrence,
        verified_fix_strength=verified_fix,
        deliverable_assetability=deliverable,
        skill_expansion=skill,
        internal_only=internal,
        one_off_environment_accident=one_off,
        total_score=total,
    )
    return breakdown, fix_status, status


# ---------------------------------------------------------------------------
# Title & Deliverable Synthesis
# ---------------------------------------------------------------------------

def synthesize_deliverables(ep: Episode) -> Tuple[str, str, str, str]:
    """Deterministically synthesizes (lead_title, target_user, deliverable_300, deliverable_skill)."""
    tech_str = "/".join(ep.detected_tech[:2]) if ep.detected_tech else "開発環境"

    symptom_short = ep.symptom.replace("\n", " ")[:35].strip()
    if symptom_short and symptom_short != "unverified":
        title = f"{tech_str}における「{symptom_short}」の根本原因と解消手順"
    else:
        title = f"{tech_str}トラブルシューティングと再利用可能手順"

    if ep.detected_tech:
        target_user = f"{', '.join(ep.detected_tech[:3])} を利用するエンジニア・開発者"
    else:
        target_user = "CLI/スクリプト開発を行うエンジニア"

    if ep.root_cause and ep.fix:
        deliverable_300 = f"「{tech_str}で{symptom_short[:25]}を秒で直す原因特定チェックリスト＆修正スニペット」"
    else:
        deliverable_300 = f"「{tech_str}トラブルシュート現場知見メモ」"

    deliverable_skill = f"scripts/tools/verify-{tech_str.lower().replace('/', '-')}-rules.py またはエージェントSkill化"

    return title, target_user, deliverable_300, deliverable_skill


# ---------------------------------------------------------------------------
# Output Formatter (Candidate Markdown with Multi-Turn Trace)
# ---------------------------------------------------------------------------

def escape_yaml_str(val: str) -> str:
    return val.replace('\\', '\\\\').replace('"', '\\"')


def format_product_lead_markdown(
    candidate_id: str,
    date_str: str,
    ep: Episode,
    breakdown: ScoreBreakdown,
    fix_status: str,
    status: str,
    title: str,
    target_user: str,
    deliverable_300: str,
    deliverable_skill: str,
) -> str:
    escaped_log_path = ep.log_path.replace("'", "''")
    privacy_risk_str = "high" if ep.has_privacy_risk else "low"

    p_moment = escape_yaml_str(ep.symptom[:100])
    p_symptom = escape_yaml_str(ep.symptom)
    p_suspicion = escape_yaml_str(ep.initial_suspicion)
    p_root_cause = escape_yaml_str(ep.root_cause)
    p_fix = escape_yaml_str(ep.fix)
    p_verification = escape_yaml_str(ep.verification_evidence)
    p_deliv_300 = escape_yaml_str(deliverable_300)
    p_deliv_skill = escape_yaml_str(deliverable_skill)
    p_target_user = escape_yaml_str(target_user)
    market_str = escape_yaml_str(", ".join(ep.detected_tech) if ep.detected_tech else "汎用開発")

    source_turns_yaml = "source_turns:\n"
    for t in ep.contributing_turns:
        source_turns_yaml += f"""  - turn_index: {t.turn_index}
    turn_at: "{t.turn_at}"
    user_line: "{t.user_line or ''}"
    model_line: "{t.model_line or ''}"
    quote_hash: "{t.quote_hash}"
    role_in_episode: "{t.role_in_episode}"
"""

    yaml_header = f"""---
candidate_id: "{candidate_id}"
date: "{date_str}"
status: "{status}"
target_user: "{p_target_user}"
problem_moment: "{p_moment}"
symptom: "{p_symptom}"
initial_suspicion: "{p_suspicion}"
root_cause: "{p_root_cause}"
fix: "{p_fix}"
verification_evidence: "{p_verification}"
fix_status: "{fix_status}"
market_breadth: "{market_str}"
recurrence: "環境構築や更新時に再発しやすいハマりどころ"
deliverable_300_yen: "{p_deliv_300}"
deliverable_skill: "{p_deliv_skill}"
privacy_internal_risk: "{privacy_risk_str}"
score_total: {breakdown.total_score}
score_breakdown:
  pain_strength: {breakdown.pain_strength}
  audience_breadth: {breakdown.audience_breadth}
  recurrence: {breakdown.recurrence}
  verified_fix_strength: {breakdown.verified_fix_strength}
  deliverable_assetability: {breakdown.deliverable_assetability}
  skill_expansion: {breakdown.skill_expansion}
  internal_only: {breakdown.internal_only}
  one_off_environment_accident: {breakdown.one_off_environment_accident}
related_koneta: ""
source_trace_status: "exact"
source_platform: "{ep.platform}"
source_session_id: "{ep.session_id}"
source_log_path: '{escaped_log_path}'
source_turn_at: "{ep.start_time}"
source_turn_index: "{ep.start_turn_index}"
source_user_line: "{ep.start_user_line or ''}"
source_model_line: "{ep.start_model_line or ''}"
source_quote_hash: "{ep.source_quote_hash}"
{source_turns_yaml}---

# [{candidate_id}] {title}

## 1. 困りごとと症状 (Symptom & Moment)
- **対象読者**: {target_user}
- **発生症状**: {ep.symptom or '未特定'}
- **初期仮説**: {ep.initial_suspicion or '特になし'}

## 2. 調査過程と根本原因 (Investigation & Root Cause)
- **調査ログ**: {ep.investigation or '直接特定'}
- **根本原因**: {ep.root_cause or '未特定'}

## 3. 解決策と検証証拠 (Fix & Verification)
- **修正内容**: {ep.fix or '未解決 / 調査中'}
- **検証証拠**: {ep.verification_evidence or '未検証'}
- **修正ステータス**: `{fix_status}`

## 4. 再利用可能な手順 (Reusable Procedure)
```text
{ep.reusable_procedure or '手順化準備中'}
```

## 5. 商品化・アセット化の切り口 (Deliverable Ideas)
- **300円成果物 (有料記事/レシピ)**: {deliverable_300}
- **エージェント拡張 (Skill/Tool)**: {deliverable_skill}

## 6. Exact Source Trace (元ログ逆引き情報)
- **Platform**: `{ep.platform}`
- **Session ID**: `{ep.session_id}`
- **Log Path**: `{ep.log_path}`
- **Turn Range**: `Turn {ep.start_turn_index} - Turn {ep.end_turn_index}`
- **Timestamp**: `{ep.start_time}`
- **Quote SHA-256**: `{ep.source_quote_hash}`
"""
    return yaml_header
# ---------------------------------------------------------------------------
# Checkpoint Management
# ---------------------------------------------------------------------------

def load_checkpoint(checkpoint_file: Path) -> Dict[str, Any]:
    if not checkpoint_file.is_file():
        return {"version": 1, "last_run_at": None, "processed_episodes": {}}
    try:
        data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": 1, "last_run_at": None, "processed_episodes": {}}
        return data
    except Exception as exc:
        print(f"[WARN] Failed to read checkpoint {checkpoint_file}: {exc}")
        return {"version": 1, "last_run_at": None, "processed_episodes": {}}


def save_checkpoint(checkpoint_file: Path, data: Dict[str, Any]) -> None:
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = checkpoint_file.with_suffix(".tmp")
    temp_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(checkpoint_file)


# ---------------------------------------------------------------------------
# Session Collection & Main Pipeline
# ---------------------------------------------------------------------------

def collect_all_turns(cutoff_time: float) -> List[Turn]:
    """Collects turns across Antigravity, Codex, and Claude Code sessions."""
    turns: List[Turn] = []
    if koneta_miner is None:
        print("[WARN] koneta_miner not found, cannot scan sessions.")
        return turns

    ag_sessions = koneta_miner.get_antigravity_sessions(cutoff_time)
    cx_sessions = koneta_miner.get_codex_sessions(cutoff_time)
    cl_sessions = koneta_miner.get_claude_sessions(cutoff_time)

    print(f"  • Antigravity (Nagi) : {len(ag_sessions)} sessions")
    print(f"  • Codex (Yura)       : {len(cx_sessions)} sessions")
    print(f"  • Claude Code (Sumi) : {len(cl_sessions)} sessions")

    all_session_tuples = []
    for mtime, agent, sid, p in ag_sessions:
        all_session_tuples.append((mtime, agent, sid, p, "antigravity"))
    for mtime, agent, sid, p in cx_sessions:
        all_session_tuples.append((mtime, agent, sid, p, "codex"))
    for mtime, agent, sid, p in cl_sessions:
        all_session_tuples.append((mtime, agent, sid, p, "claude-code"))

    for mtime, agent, session_id, log_path, platform in all_session_tuples:
        if platform == "antigravity":
            raw_turns = koneta_miner.extract_turns_from_antigravity(log_path)
        elif platform == "codex":
            raw_turns = koneta_miner.extract_turns_from_codex(log_path)
        elif platform == "claude-code":
            raw_turns = koneta_miner.extract_turns_from_claude(log_path)
        else:
            raw_turns = []

        for t_idx, rt in enumerate(raw_turns, start=1):
            q_hash = koneta_miner.turn_quote_hash(rt["user"], rt["model"])
            turns.append(
                Turn(
                    user=rt["user"],
                    model=rt["model"],
                    time=rt.get("time") or "",
                    agent=agent,
                    platform=platform,
                    session_id=session_id,
                    log_path=str(log_path.resolve()),
                    turn_index=t_idx,
                    source_user_line=rt.get("source_user_line"),
                    source_model_line=rt.get("source_model_line"),
                    source_quote_hash=q_hash,
                )
            )

    return turns


def mine_product_leads(
    lookback_hours: int = 24,
    max_candidates: int = 5,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    checkpoint_file: Path = DEFAULT_CHECKPOINT_FILE,
    dry_run: bool = False,
    force: bool = False,
    verbose: bool = False,
) -> List[Path]:
    """Main execution function for product lead mining."""
    cutoff_time = time.time() - (lookback_hours * 3600)
    print("===================================================")
    print("  💎 ProjectYure Product Lead Miner (GITV)")
    print("  (Deterministic First-Pass Pipeline)")
    print("===================================================")
    print(f"Target: Sessions within last {lookback_hours} hours")
    print(f"Output: {output_dir}")
    print(f"Dry Run: {dry_run}\n")

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    checkpoint = load_checkpoint(checkpoint_file) if not force else {"version": 1, "last_run_at": None, "processed_episodes": {}}
    processed_hashes: Set[str] = set(checkpoint.get("processed_episodes", {}).keys())

    hash_to_existing_id: Dict[str, str] = {}
    for h, info in checkpoint.get("processed_episodes", {}).items():
        if isinstance(info, dict) and "candidate_id" in info:
            hash_to_existing_id[h] = info["candidate_id"]

    today_str_compact = datetime.now().strftime("%Y%m%d")
    today_str = datetime.now().strftime("%Y-%m-%d")
    max_seq = 0

    for cid in hash_to_existing_id.values():
        m_id = re.match(rf"^PL-{today_str_compact}-(\d+)$", cid)
        if m_id:
            max_seq = max(max_seq, int(m_id.group(1)))

    if output_dir.exists():
        for existing_file in output_dir.glob("*.md"):
            if existing_file.name.lower() == "readme.md":
                continue
            try:
                content = existing_file.read_text(encoding="utf-8")
                m_hash = re.search(r"source_quote_hash:\s*[\"']?([0-9a-fA-F]{64})[\"']?", content)
                m_cid = re.search(r"candidate_id:\s*[\"']?(PL-\d{8}-\d+)[\"']?", content)
                if m_hash and m_cid:
                    h_val = m_hash.group(1)
                    cid_val = m_cid.group(1)
                    processed_hashes.add(h_val)
                    hash_to_existing_id[h_val] = cid_val
                    m_seq = re.match(rf"^PL-{today_str_compact}-(\d+)$", cid_val)
                    if m_seq:
                        max_seq = max(max_seq, int(m_seq.group(1)))
            except Exception:
                pass

    turns = collect_all_turns(cutoff_time)
    if not turns:
        print("[INFO] No active turns found in specified window.")
        return []

    episodes = extract_episodes_from_turns(turns)
    print(f"Found {len(episodes)} candidate episodes from raw turns.")

    scored_episodes = []
    for ep in episodes:
        if ep.source_quote_hash in processed_hashes and not force:
            continue
        breakdown, fix_status, status = calculate_score(ep)
        scored_episodes.append((breakdown.total_score, ep, breakdown, fix_status, status))

    scored_episodes.sort(key=lambda x: x[0], reverse=True)

    generated_files: List[Path] = []
    created_count = 0

    for score, ep, breakdown, fix_status, status in scored_episodes:
        if created_count >= max_candidates:
            break

        title, target_user, deliverable_300, deliverable_skill = synthesize_deliverables(ep)

        if ep.source_quote_hash in hash_to_existing_id:
            candidate_id = hash_to_existing_id[ep.source_quote_hash]
        else:
            max_seq += 1
            candidate_id = f"PL-{today_str_compact}-{max_seq:03d}"
            hash_to_existing_id[ep.source_quote_hash] = candidate_id

        slug = f"{ep.agent}-{ep.source_quote_hash[:8]}"
        filename = f"{today_str}-{candidate_id.lower()}-{slug}.md"
        card_file = output_dir / filename

        md_content = format_product_lead_markdown(
            candidate_id=candidate_id,
            date_str=today_str,
            ep=ep,
            breakdown=breakdown,
            fix_status=fix_status,
            status=status,
            title=title,
            target_user=target_user,
            deliverable_300=deliverable_300,
            deliverable_skill=deliverable_skill,
        )

        if dry_run:
            print(f"[DRY-RUN] Would write {filename} (Score: {score}, Status: {status}) -> {title}")
            created_count += 1
            generated_files.append(card_file)
            continue

        if card_file.exists():
            print(f"  [SKIP_EXISTING] {card_file.name} already exists. Preserving without overwrite.")
            generated_files.append(card_file)
            created_count += 1
            continue

        card_file.write_text(md_content, encoding="utf-8")
        print(f"  [SAVED] {card_file.name} (Score: {score}, Status: {status}) -> {title}")

        checkpoint["processed_episodes"][ep.source_quote_hash] = {
            "candidate_id": candidate_id,
            "mined_at": datetime.now(timezone.utc).isoformat(),
            "score": score,
            "status": status,
        }
        generated_files.append(card_file)
        created_count += 1

    if not dry_run and created_count > 0:
        checkpoint["last_run_at"] = datetime.now(timezone.utc).isoformat()
        save_checkpoint(checkpoint_file, checkpoint)

    print("\n===================================================")
    print(f"  [SUCCESS] {len(generated_files)} product leads processed into {output_dir}")
    print("===================================================")
    return generated_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine product lead candidates from multi-agent session logs.")
    parser.add_argument("--lookback-hours", type=int, default=24, help="Hours of log history to inspect (default: 24)")
    parser.add_argument("--max-candidates", type=int, default=5, help="Maximum candidates to generate (default: 5)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory for candidates")
    parser.add_argument("--checkpoint-file", type=Path, default=DEFAULT_CHECKPOINT_FILE, help="Checkpoint file location")
    parser.add_argument("--dry-run", action="store_true", help="Perform deterministic scan without writing files")
    parser.add_argument("--force", action="store_true", help="Ignore checkpoint and re-mine without overwriting existing files")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()
    mine_product_leads(
        lookback_hours=args.lookback_hours,
        max_candidates=args.max_candidates,
        output_dir=args.output_dir,
        checkpoint_file=args.checkpoint_file,
        dry_run=args.dry_run,
        force=args.force,
        verbose=args.verbose,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
