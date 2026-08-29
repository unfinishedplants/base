"""Audit exact source traces and semantic validity for product lead cards.

Read-only auditor verifying:
1. Trace Integrity:
   - Exact source trace pointers map to verifiable turns with reproducible SHA-256 quote hashes.
   - Multi-turn episodes: all contributing turns (source_turns) are individually resolved and verified.
2. Semantic Validity:
   - Verified gate: status "product-ready" requires fix_status == "verified".
   - Root cause gate: status "product-ready" requires non-empty, specific root_cause.
   - Fix & Verification gate: status "product-ready" requires non-empty fix and concrete verification_evidence.
   - Target binding gate: verification_evidence must bind to the same technology/command/script as the symptom/fix.
   - Negation / Provisional gate: status "product-ready" must NOT contain negation, workaround, or provisional phrases.
   - Privacy gate: cards with detected privacy risks have status "review_needed".
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Windows UTF-8 console output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_DIR = SCRIPT_DIR.parent.parent
DEFAULT_LEADS_DIR = REPO_DIR / "workbench" / "product-leads"

sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(REPO_DIR / "scripts" / "koneta"))
try:
    import mine_transcripts as koneta_miner
except ImportError:
    koneta_miner = None

from scripts.product_mining.mine_product_leads import extract_target_signals, NEGATION_PATTERNS

REQUIRED_TRACE_FIELDS = (
    "source_platform",
    "source_session_id",
    "source_log_path",
    "source_turn_at",
    "source_turn_index",
    "source_user_line",
    "source_model_line",
    "source_quote_hash",
)

REQUIRED_TURN_FIELDS = (
    "turn_index",
    "turn_at",
    "user_line",
    "model_line",
    "quote_hash",
    "role_in_episode",
)

ALLOWED_ROLE_TOKENS = {"symptom", "root_cause", "fix", "verification", "context"}


def parse_card_fields(card_text: str) -> Dict[str, Any]:
    """Parses frontmatter fields and source_turns list from markdown card."""
    values: Dict[str, Any] = {}
    lines = card_text.splitlines()
    in_source_turns = False
    current_turn: Optional[Dict[str, str]] = None
    source_turns: List[Dict[str, str]] = []

    for line in lines:
        if line.strip() == "---":
            continue

        if line.startswith("source_turns:"):
            in_source_turns = True
            continue

        if in_source_turns:
            if line.startswith("  - "):
                if current_turn:
                    source_turns.append(current_turn)
                current_turn = {}
                m = re.match(r"^\s*-\s*([a-zA-Z0-9_-]+):\s*(.*?)\s*$", line)
                if m:
                    current_turn[m.group(1)] = m.group(2).strip("'\"")
            elif line.startswith("    ") and current_turn is not None:
                m = re.match(r"^\s*([a-zA-Z0-9_-]+):\s*(.*?)\s*$", line)
                if m:
                    current_turn[m.group(1)] = m.group(2).strip("'\"")
            elif not line.startswith(" ") and line.strip():
                if current_turn:
                    source_turns.append(current_turn)
                    current_turn = None
                in_source_turns = False

        if not in_source_turns:
            match = re.match(r"^([a-zA-Z0-9_-]+):\s*(.*?)\s*$", line)
            if match:
                k = match.group(1)
                v = match.group(2).strip("'\"")
                values[k] = v

    if in_source_turns and current_turn:
        source_turns.append(current_turn)

    if source_turns:
        values["source_turns"] = source_turns

    return values

def audit_trace_integrity(card_path: Path, fields: Dict[str, Any]) -> List[str]:
    """Audits exact source trace pointers and hash reproducibility for all contributing turns."""
    errors: List[str] = []
    trace_status = fields.get("source_trace_status", "untraced")
    if trace_status != "exact":
        return errors

    missing_fields = [f for f in REQUIRED_TRACE_FIELDS if not fields.get(f)]
    if missing_fields:
        errors.append("Missing required trace fields: " + ", ".join(missing_fields))

    log_path_str = str(fields.get("source_log_path", ""))
    if not log_path_str:
        errors.append("source_log_path is empty")
        return errors

    log_path = Path(log_path_str)
    if not log_path.is_file():
        errors.append(f"source log does not exist on disk: {log_path}")
        return errors

    platform = str(fields.get("source_platform", ""))
    if koneta_miner is None:
        errors.append("koneta_miner module not available for turn extraction")
        return errors

    if platform == "antigravity":
        expected_session = koneta_miner.extract_full_session_id(log_path.parents[2].name)
        turns = koneta_miner.extract_turns_from_antigravity(log_path)
    elif platform == "codex":
        expected_session = koneta_miner.extract_full_session_id(log_path.stem)
        turns = koneta_miner.extract_turns_from_codex(log_path)
    elif platform == "claude-code":
        expected_session = koneta_miner.extract_full_session_id(log_path.stem)
        turns = koneta_miner.extract_turns_from_claude(log_path)
    else:
        errors.append(f"Unsupported source platform: {platform}")
        return errors

    stored_session = str(fields.get("source_session_id", ""))
    if stored_session != expected_session:
        errors.append(f"session mismatch: stored={stored_session} actual={expected_session}")

    # Check multi-turn traces if present
    source_turns = fields.get("source_turns")
    if source_turns and isinstance(source_turns, list):
        seen_roles_in_episode: List[Set[str]] = []
        for t_idx_seq, t_info in enumerate(source_turns, start=1):
            missing_turn_fields = [f for f in REQUIRED_TURN_FIELDS if not t_info.get(f)]
            if missing_turn_fields:
                errors.append(f"Turn entry #{t_idx_seq} is missing required fields: {', '.join(missing_turn_fields)}")
                continue

            t_idx_str = str(t_info.get("turn_index", "")).strip()
            stored_hash = str(t_info.get("quote_hash", "")).strip()
            u_line_str = str(t_info.get("user_line", "")).strip()
            m_line_str = str(t_info.get("model_line", "")).strip()
            turn_at = str(t_info.get("turn_at", "")).strip()
            role_in_episode = str(t_info.get("role_in_episode", "")).strip()

            role_tokens = set(r.strip() for r in role_in_episode.split(",") if r.strip())
            if not role_tokens:
                errors.append(f"role_in_episode is empty in contributing turn #{t_idx_seq}")
            invalid_tokens = role_tokens - ALLOWED_ROLE_TOKENS
            if invalid_tokens:
                errors.append(f"Invalid role_in_episode tokens in turn #{t_idx_seq}: {invalid_tokens}")

            seen_roles_in_episode.append(role_tokens)

            if not t_idx_str.isdigit():
                errors.append(f"turn_index must be integer in turn entry #{t_idx_seq}: '{t_idx_str}'")
                continue

            t_idx = int(t_idx_str)
            if t_idx < 1 or t_idx > len(turns):
                errors.append(f"Turn index {t_idx} out of range (1..{len(turns)}) in log {log_path.name}")
                continue

            matched_turn = turns[t_idx - 1]
            actual_u_line = str(matched_turn.get("source_user_line") or "")
            actual_m_line = str(matched_turn.get("source_model_line") or "")
            actual_time = str(matched_turn.get("time") or "")

            # Strict locator and timestamp verification - NO index-only fallback!
            if actual_u_line != u_line_str:
                errors.append(f"user_line mismatch in contributing turn {t_idx}: stored={u_line_str} actual={actual_u_line}")
            if actual_m_line != m_line_str:
                errors.append(f"model_line mismatch in contributing turn {t_idx}: stored={m_line_str} actual={actual_m_line}")
            if actual_time and turn_at and actual_time != turn_at:
                errors.append(f"turn_at mismatch in contributing turn {t_idx}: stored={turn_at} actual={actual_time}")

            actual_hash = koneta_miner.turn_quote_hash(str(matched_turn["user"]), str(matched_turn["model"]))
            if stored_hash != actual_hash:
                errors.append(f"Quote hash mismatch in contributing turn {t_idx}: stored={stored_hash} actual={actual_hash}")

        if seen_roles_in_episode:
            first_turn_roles = seen_roles_in_episode[0]
            if "verification" in first_turn_roles and len(seen_roles_in_episode) > 1 and "symptom" not in first_turn_roles and "fix" not in first_turn_roles:
                errors.append("Positional role error: first turn in multi-turn episode cannot be verification-only without symptom or fix")
    else:
        # Legacy Single-Turn Compatibility Mode
        u_line_str = str(fields.get("source_user_line", ""))
        m_line_str = str(fields.get("source_model_line", ""))
        turn_idx_str = str(fields.get("source_turn_index", ""))
        turn_at = str(fields.get("source_turn_at", ""))
        stored_hash = str(fields.get("source_quote_hash", ""))

        if not turn_idx_str.isdigit():
            errors.append(f"Legacy trace: invalid source_turn_index: '{turn_idx_str}'")
            return errors

        target_idx = int(turn_idx_str)
        if target_idx < 1 or target_idx > len(turns):
            errors.append(f"Legacy trace: Turn index {target_idx} out of range (1..{len(turns)})")
            return errors

        turn = turns[target_idx - 1]
        actual_u_line = str(turn.get("source_user_line") or "")
        actual_m_line = str(turn.get("source_model_line") or "")
        actual_time = str(turn.get("time") or "")

        if actual_u_line and u_line_str and actual_u_line != u_line_str:
            errors.append(f"Legacy trace: user_line mismatch: stored={u_line_str} actual={actual_u_line}")
        if actual_m_line and m_line_str and actual_m_line != m_line_str:
            errors.append(f"Legacy trace: model_line mismatch: stored={m_line_str} actual={actual_m_line}")
        if actual_time and turn_at and actual_time != turn_at:
            errors.append(f"Legacy trace: turn_at mismatch: stored={turn_at} actual={actual_time}")

        actual_hash = koneta_miner.turn_quote_hash(str(turn["user"]), str(turn["model"]))
        if stored_hash != actual_hash:
            errors.append(f"Legacy trace: Quote hash mismatch: stored={stored_hash} actual={actual_hash}")

    return errors


def audit_semantic_validity(card_path: Path, fields: Dict[str, Any], full_text: str) -> List[str]:
    """Audits semantic constraints, root cause requirement, target binding, and gate integrity."""
    errors: List[str] = []
    status = str(fields.get("status", ""))
    fix_status = str(fields.get("fix_status", ""))
    privacy_risk = str(fields.get("privacy_internal_risk", ""))
    root_cause = str(fields.get("root_cause", "")).strip()
    fix = str(fields.get("fix", "")).strip()
    verification = str(fields.get("verification_evidence", "")).strip()
    symptom = str(fields.get("symptom", "")).strip()
    candidate_id = str(fields.get("candidate_id", ""))

    if candidate_id and not re.match(r"^PL-\d{8}-\d{3,}$", candidate_id):
        errors.append(f"INVALID CANDIDATE ID FORMAT: '{candidate_id}' (expected PL-YYYYMMDD-NNN)")

    if privacy_risk == "high" and status != "review_needed":
        errors.append(f"PRIVACY GATE VIOLATION: privacy_internal_risk is 'high' but status is '{status}'")

    if status == "product-ready":
        if fix_status != "verified":
            errors.append(f"VERIFIED GATE VIOLATION: status is 'product-ready' but fix_status is '{fix_status}'")

        if not root_cause or root_cause in ("未特定", "unverified", "未確認"):
            errors.append(f"ROOT CAUSE GATE VIOLATION: status is 'product-ready' but root_cause is empty or unspecified ('{root_cause}')")

        if not fix or fix in ("未解決", "未特定", "unverified", "調査中"):
            errors.append(f"FIX GATE VIOLATION: status is 'product-ready' but fix is empty or unverified ('{fix}')")

        if not verification or verification in ("未検証", "unverified"):
            errors.append("VERIFICATION GATE VIOLATION: status is 'product-ready' but verification_evidence is empty or unverified")

        for pat in NEGATION_PATTERNS:
            if re.search(pat, full_text, flags=re.IGNORECASE):
                errors.append(f"NEGATION GATE VIOLATION: status is 'product-ready' but contains negative/provisional expression matching '{pat}'")
                break

        # Target binding check
        prob_signals = extract_target_signals(f"{symptom} {root_cause} {fix}")
        verif_signals = extract_target_signals(verification)
        if not prob_signals:
            errors.append("TARGET BINDING GATE VIOLATION: status is 'product-ready' but problem target signals are empty")
        elif not verif_signals:
            errors.append("TARGET BINDING GATE VIOLATION: status is 'product-ready' but verification target signals are empty")
        elif not (prob_signals & verif_signals):
            errors.append(f"TARGET BINDING GATE VIOLATION: verification targets {verif_signals} do not overlap with problem targets {prob_signals}")

    return errors


def audit_card_detailed(card_path: Path) -> Tuple[List[str], List[str]]:
    """Returns (trace_errors, semantic_errors) for a given card."""
    card_text = card_path.read_text(encoding="utf-8")
    fields = parse_card_fields(card_text)
    trace_errors = audit_trace_integrity(card_path, fields)
    semantic_errors = audit_semantic_validity(card_path, fields, card_text)
    return trace_errors, semantic_errors


def audit_card(card_path: Path) -> List[str]:
    """Combined audit error list for backwards compatibility."""
    trace_errors, semantic_errors = audit_card_detailed(card_path)
    return trace_errors + semantic_errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit product lead cards (Trace Integrity & Semantic Validity).")
    parser.add_argument(
        "leads_dirs",
        nargs="*",
        type=Path,
        default=[DEFAULT_LEADS_DIR],
        help="Directories containing product lead markdown cards",
    )
    parser.add_argument("--trace-only", action="store_true", help="Audit only trace integrity")
    parser.add_argument("--semantic-only", action="store_true", help="Audit only semantic validity")
    args = parser.parse_args()

    counts: Counter[str] = Counter()
    trace_failures: List[Tuple[Path, List[str]]] = []
    semantic_failures: List[Tuple[Path, List[str]]] = []
    total_cards = 0

    for leads_dir in args.leads_dirs:
        if not leads_dir.exists():
            continue
        for card_path in sorted(leads_dir.glob("*.md")):
            if card_path.name.lower() == "readme.md":
                counts["skipped"] += 1
                continue

            total_cards += 1
            fields = parse_card_fields(card_path.read_text(encoding="utf-8"))
            status = str(fields.get("status", "unknown"))
            counts[status] += 1

            t_errs, s_errs = audit_card_detailed(card_path)
            if t_errs and not args.semantic_only:
                trace_failures.append((card_path, t_errs))
            if s_errs and not args.trace_only:
                semantic_failures.append((card_path, s_errs))

    print("===================================================")
    print("  🔍 ProjectYure Product Lead Audit Report")
    print("===================================================")
    print(f"Total cards audited: {total_cards}")
    print(f"Status breakdown: {dict(counts)}\n")

    if not args.semantic_only:
        trace_pass_count = total_cards - len(trace_failures)
        print(f"[TRACE INTEGRITY] passed={trace_pass_count}/{total_cards} failures={len(trace_failures)}")
        for card_path, errors in trace_failures:
            print(f"  [TRACE FAIL] {card_path.name}")
            for err in errors:
                print(f"    - {err}")
        print()

    if not args.trace_only:
        semantic_pass_count = total_cards - len(semantic_failures)
        print(f"[SEMANTIC VALIDITY] passed={semantic_pass_count}/{total_cards} failures={len(semantic_failures)}")
        for card_path, errors in semantic_failures:
            print(f"  [SEMANTIC FAIL] {card_path.name}")
            for err in errors:
                print(f"    - {err}")
        print()

    has_failures = False
    if not args.semantic_only and trace_failures:
        has_failures = True
    if not args.trace_only and semantic_failures:
        has_failures = True

    ordered = " ".join(f"{k}={counts[k]}" for k in sorted(counts))
    print(f"[SUMMARY] {ordered} trace_fails={len(trace_failures)} semantic_fails={len(semantic_failures)}")
    return 1 if has_failures else 0


if __name__ == "__main__":
    sys.exit(main())
