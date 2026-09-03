"""Comprehensive unit and adversarial test suite for deterministic product lead miner & auditor."""

import json
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from scripts.product_mining.mine_product_leads import (
    Episode,
    Turn,
    TurnTrace,
    calculate_score,
    check_negation_or_hedging,
    extract_episodes_from_turns,
    extract_target_signals,
    format_product_lead_markdown,
    is_checklist_or_false_positive,
    mine_product_leads,
    redact_and_check_privacy,
    synthesize_deliverables,
    load_checkpoint,
    save_checkpoint,
)
from scripts.product_mining.audit_product_leads import (
    audit_card,
    audit_card_detailed,
    audit_trace_integrity,
    audit_semantic_validity,
    downgrade_failed_product_ready,
    main as audit_main,
    parse_card_fields,
)
import scripts.koneta.mine_transcripts as koneta_miner
import scripts.koneta.audit_source_trace as koneta_audit


class TestProductMining(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="product_lead_test_"))
        self.output_dir = self.test_dir / "product-leads"
        self.checkpoint_file = self.output_dir / "_state" / "checkpoint.json"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_privacy_redaction(self):
        sample = "Here is my secret sk-123456789012345678901234 and AIzaSyD9ABC1234567890123456789012345 with password='supersecretpassword' and admin@example.com."
        redacted, has_sensitive = redact_and_check_privacy(sample)
        self.assertTrue(has_sensitive)
        self.assertNotIn("sk-1234567890", redacted)
        self.assertNotIn("AIzaSyD9", redacted)
        self.assertNotIn("supersecretpassword", redacted)
        self.assertNotIn("admin@example.com", redacted)
        self.assertIn("[REDACTED_OPENAI_KEY]", redacted)
        self.assertIn("[REDACTED_API_KEY]", redacted)
        self.assertIn("[REDACTED_PASSWORD]", redacted)
        self.assertIn("[REDACTED_EMAIL]", redacted)

    def test_episode_extraction(self):
        turns = [
            Turn(
                user="npm run build で verify-build.mjs failed with AssertionError: newest date mismatch エラーが出ます。",
                model="原因はタイムゾーンオフセットによるDate.parseの比較ズレです。タイムスタンプをISO形式に正規化して修正します。",
                time="2026-08-29T10:00:00Z",
                agent="yura",
                platform="codex",
                session_id="test-session-001",
                log_path=str(self.test_dir / "dummy.jsonl"),
                turn_index=1,
                source_user_line=1,
                source_model_line=2,
                source_quote_hash="dummyhash123",
            ),
            Turn(
                user="修正して再実行しました。node scripts/verify-build.mjs で exit code 0 で passed しました！",
                model="検証確認しました。ビルドが正常に通過するようになりました。",
                time="2026-08-29T10:05:00Z",
                agent="yura",
                platform="codex",
                session_id="test-session-001",
                log_path=str(self.test_dir / "dummy.jsonl"),
                turn_index=2,
                source_user_line=3,
                source_model_line=4,
                source_quote_hash="dummyhash456",
            ),
        ]
        episodes = extract_episodes_from_turns(turns)
        self.assertEqual(len(episodes), 1)
        ep = episodes[0]
        self.assertIn("AssertionError", ep.symptom)
        self.assertIn("原因は", ep.root_cause)
        self.assertIn("修正", ep.fix)
        self.assertIn("exit code 0", ep.verification_evidence)
        self.assertIn("Node.js", ep.detected_tech)
        self.assertEqual(len(ep.contributing_turns), 2)

    def test_false_positive_filtering(self):
        checklist_text = "- 失敗時の縮退動作: ログに記録して継続\n- エラー時の再試行: 最大3回\n- 確認項目: UTF-8エンコーディング確認"
        self.assertTrue(is_checklist_or_false_positive(checklist_text))

        turns = [
            Turn(
                user=checklist_text,
                model="設計方針を確認しました。チェックリストに沿って実装します。",
                time="2026-08-29T10:00:00Z",
                agent="nagi",
                platform="antigravity",
                session_id="test-checklist-001",
                log_path=str(self.test_dir / "dummy.jsonl"),
                turn_index=1,
                source_user_line=1,
                source_model_line=2,
                source_quote_hash="checklisthash",
            )
        ]
        episodes = extract_episodes_from_turns(turns)
        self.assertEqual(len(episodes), 0)

    def test_documentation_and_meta_false_positives_are_excluded(self):
        false_positive_samples = [
            "## Failure Modes and Guards\n- build failure is retried three times",
            "Explicit design decision, not an error: missing IDs are excluded from the catalog.",
            "免責事項：自動売買にはプログラムの不具合による誤発注リスクがあります。",
            "今のバグっぽい会話を商品リード候補として採掘するマイナーを確認する。",
            "# ProjectYure v5 Current Load Order\nRelease: v5.1.3_20260819\n- 失敗を観測する",
            "画面上のエラーが増えてる感じの絵にして。赤いダイアログを描いて。",
            "catch (e) { /* error path, re-enables button */ }",
        ]
        for sample in false_positive_samples:
            with self.subTest(sample=sample):
                self.assertTrue(is_checklist_or_false_positive(sample))

    def test_false_positive_context_does_not_create_episode(self):
        turn = Turn(
            user="Explicit design decision, not an error: missing IDs stay out of the catalog.",
            model="The failure mode is documented and no fix is required.",
            time="2026-09-03T10:00:00Z",
            agent="sumi",
            platform="claude-code",
            session_id="false-positive-context",
            log_path=str(self.test_dir / "dummy.jsonl"),
            turn_index=1,
            source_user_line=1,
            source_model_line=2,
            source_quote_hash="falsepositivehash",
        )
        self.assertEqual(extract_episodes_from_turns([turn]), [])

    def test_model_only_problem_language_does_not_create_episode(self):
        turn = Turn(
            user="この設計案について説明して。",
            model="想定される failure は build error です。修正例も記載します。",
            time="2026-09-03T10:00:00Z",
            agent="yura",
            platform="codex",
            session_id="model-only-problem",
            log_path=str(self.test_dir / "dummy.jsonl"),
            turn_index=1,
            source_user_line=1,
            source_model_line=2,
            source_quote_hash="modelonlyhash",
        )
        self.assertEqual(extract_episodes_from_turns([turn]), [])

    def test_collect_all_turns_filters_by_utterance_timestamp(self):
        now_epoch = datetime.fromisoformat("2026-09-03T12:00:00+00:00").timestamp()
        cutoff_epoch = now_epoch - 24 * 3600
        log_path = self.test_dir / "recently-touched-session.jsonl"
        log_path.write_text("{}\n", encoding="utf-8")
        raw_turns = [
            {"user": "old", "model": "old answer", "time": "2026-09-02T11:59:59Z"},
            {"user": "boundary", "model": "kept", "time": "2026-09-02T12:00:00Z"},
            {"user": "recent", "model": "kept", "time": "2026-09-03T11:59:59Z"},
            {"user": "missing", "model": "excluded", "time": ""},
            {"user": "future", "model": "excluded", "time": "2026-09-03T12:00:01Z"},
        ]
        session = [(now_epoch, "yura", "session-1", log_path)]
        with (
            patch("scripts.product_mining.mine_product_leads.koneta_miner.get_antigravity_sessions", return_value=[]),
            patch("scripts.product_mining.mine_product_leads.koneta_miner.get_codex_sessions", return_value=session),
            patch("scripts.product_mining.mine_product_leads.koneta_miner.get_claude_sessions", return_value=[]),
            patch("scripts.product_mining.mine_product_leads.koneta_miner.extract_turns_from_codex", return_value=raw_turns),
        ):
            from scripts.product_mining.mine_product_leads import collect_all_turns

            turns = collect_all_turns(cutoff_epoch, current_time=now_epoch)

        self.assertEqual([turn.user for turn in turns], ["boundary", "recent"])
        self.assertEqual([turn.turn_index for turn in turns], [2, 3])

    def test_negation_expressions_drop_status(self):
        has_neg, matches = check_negation_or_hedging("対症療法として一時的に回避しましたが、根治はしていない状態です。")
        self.assertTrue(has_neg)
        self.assertTrue(len(matches) >= 2)

        ep_negation = Episode(
            session_id="sess-neg-001",
            agent="nagi",
            platform="antigravity",
            log_path=str(self.test_dir / "dummy.jsonl"),
            start_turn_index=1,
            end_turn_index=2,
            start_time="2026-08-29T10:00:00Z",
            start_user_line=1,
            start_model_line=2,
            source_quote_hash="neghash001",
            symptom="Docker build failed with fatal error",
            initial_suspicion="Missing dependency",
            investigation="Checked logs",
            root_cause="原因は pip cache の不整合",
            fix="対症療法としてキャッシュ削除を適用",
            verification_evidence="exit code 0 passed",
            reusable_procedure="1. check 2. fix 3. verify",
            detected_tech=["Docker", "Python"],
            target_signals={"docker", "python"},
            has_privacy_risk=False,
            has_negation=True,
            raw_user_sample="user msg",
            raw_model_sample="model msg 対症療法で根治はしていない",
        )
        bd, fix_status, status = calculate_score(ep_negation)
        self.assertEqual(fix_status, "unverified")
        self.assertEqual(status, "review_needed")

    def test_adversarial_time_gap_episode_splitting(self):
        """Turn 1 (Docker error) and Turn 2 (12 hours later, unrelated verify-build) must be split."""
        turns = [
            Turn(
                user="Docker build failed with fatal error in pip cache.",
                model="原因は pip cache の不整合です。Dockerfile を修正して --no-cache-dir を追加します。",
                time="2026-08-29T10:00:00Z",
                agent="yura",
                platform="codex",
                session_id="test-time-gap-001",
                log_path=str(self.test_dir / "dummy.jsonl"),
                turn_index=1,
                source_user_line=1,
                source_model_line=2,
                source_quote_hash="dockerhash1",
            ),
            Turn(
                user="12時間後の別件作業です。node scripts/verify-build.mjs で exit code 0 passed しました！",
                model="ビルド確認しました。",
                time="2026-08-29T22:00:00Z",
                agent="yura",
                platform="codex",
                session_id="test-time-gap-001",
                log_path=str(self.test_dir / "dummy.jsonl"),
                turn_index=2,
                source_user_line=3,
                source_model_line=4,
                source_quote_hash="markdownhash2",
            ),
        ]
        episodes = extract_episodes_from_turns(turns)
        self.assertEqual(len(episodes), 1)
        docker_ep = episodes[0]
        self.assertEqual(docker_ep.end_turn_index, 1)
        self.assertEqual(docker_ep.verification_evidence, "")
        _, fix_status, status = calculate_score(docker_ep)
        self.assertEqual(fix_status, "unverified")
        self.assertNotEqual(status, "product-ready")

    def test_adversarial_disjoint_tech_verification_rejected(self):
        """Turn 2 immediately follows Turn 1, but its verification target is disjoint (Node vs Docker)."""
        turns = [
            Turn(
                user="Docker build failed with fatal error in pip cache.",
                model="原因は pip cache の不整合です。Dockerfile を修正して --no-cache-dir を追加します。",
                time="2026-08-29T10:00:00Z",
                agent="yura",
                platform="codex",
                session_id="test-disjoint-001",
                log_path=str(self.test_dir / "dummy.jsonl"),
                turn_index=1,
                source_user_line=1,
                source_model_line=2,
                source_quote_hash="dockerhashA",
            ),
            Turn(
                user="node scripts/verify-build.mjs exit code 0 passed",
                model="完了しました。",
                time="2026-08-29T10:05:00Z",
                agent="yura",
                platform="codex",
                session_id="test-disjoint-001",
                log_path=str(self.test_dir / "dummy.jsonl"),
                turn_index=2,
                source_user_line=3,
                source_model_line=4,
                source_quote_hash="nodehashB",
            ),
        ]
        episodes = extract_episodes_from_turns(turns)
        self.assertEqual(len(episodes), 1)
        docker_ep = episodes[0]
        self.assertEqual(docker_ep.verification_evidence, "")
        _, fix_status, status = calculate_score(docker_ep)
        self.assertEqual(fix_status, "unverified")
        self.assertNotEqual(status, "product-ready")

    def test_adversarial_same_turn_unrelated_pass_rejected(self):
        turns = [
            Turn(
                user="スクリプト実行で TypeError: undefined is not a function が発生しました。",
                model="ダイヤモンドバリデーションを実行し、埋め込み＆配置完了しました。視認性バッチリです。",
                time="2026-08-29T10:00:00Z",
                agent="sumi",
                platform="claude-code",
                session_id="test-sess-unrelated",
                log_path=str(self.test_dir / "dummy.jsonl"),
                turn_index=1,
                source_user_line=1,
                source_model_line=2,
                source_quote_hash="unrelatedhash",
            )
        ]
        episodes = extract_episodes_from_turns(turns)
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0].verification_evidence, "")

    def test_root_cause_required_for_product_ready(self):
        ep_no_rc = Episode(
            session_id="sess-norc-001",
            agent="yura",
            platform="codex",
            log_path=str(self.test_dir / "dummy.jsonl"),
            start_turn_index=1,
            end_turn_index=2,
            start_time="2026-08-29T10:00:00Z",
            start_user_line=1,
            start_model_line=2,
            source_quote_hash="norchash001",
            symptom="Docker build failed with fatal error in Python script",
            initial_suspicion="",
            investigation="",
            root_cause="",
            fix="--no-cache-dir を追加して修正",
            verification_evidence="exit code 0 passed successfully",
            reusable_procedure="1. add flag 2. rebuild",
            detected_tech=["Docker", "Python"],
            target_signals={"docker", "python"},
            has_privacy_risk=False,
            has_negation=False,
            raw_user_sample="user msg",
            raw_model_sample="model msg",
        )
        bd, fix_status, status = calculate_score(ep_no_rc)
        self.assertNotEqual(status, "product-ready")
        self.assertEqual(status, "candidate")

    def test_verified_gate_strictness(self):
        ep_verified = Episode(
            session_id="sess-001",
            agent="nagi",
            platform="antigravity",
            log_path=str(self.test_dir / "dummy.jsonl"),
            start_turn_index=1,
            end_turn_index=2,
            start_time="2026-08-29T10:00:00Z",
            start_user_line=1,
            start_model_line=2,
            source_quote_hash="hash001",
            symptom="Docker build failed with fatal error in Python script",
            initial_suspicion="Missing dependency",
            investigation="Checked Dockerfile and requirements",
            root_cause="原因は pip cache の不整合による mismatch",
            fix="--no-cache-dir を追加して Dockerfile を修正自身",
            verification_evidence="docker build successfully completed with exit code 0",
            reusable_procedure="1. check cache 2. add flag 3. rebuild",
            detected_tech=["Docker", "Python"],
            target_signals={"docker", "python"},
            has_privacy_risk=False,
            has_negation=False,
            raw_user_sample="user msg",
            raw_model_sample="model msg",
        )
        bd, fix_status, status = calculate_score(ep_verified)
        self.assertEqual(fix_status, "verified")
        self.assertEqual(status, "product-ready")
        self.assertGreaterEqual(bd.total_score, 12)

        ep_unverified = Episode(
            session_id="sess-002",
            agent="sumi",
            platform="claude-code",
            log_path=str(self.test_dir / "dummy.jsonl"),
            start_turn_index=1,
            end_turn_index=1,
            start_time="2026-08-29T10:00:00Z",
            start_user_line=1,
            start_model_line=2,
            source_quote_hash="hash002",
            symptom="Docker build failed with fatal error in Python script",
            initial_suspicion="Missing dependency",
            investigation="Checked Dockerfile and requirements",
            root_cause="原因は pip cache の不整合による mismatch",
            fix="--no-cache-dir を追加して Dockerfile を修正",
            verification_evidence="",
            reusable_procedure="",
            detected_tech=["Docker", "Python"],
            target_signals={"docker", "python"},
            has_privacy_risk=False,
            has_negation=False,
            raw_user_sample="user msg",
            raw_model_sample="model msg",
        )
        bd2, fix_status2, status2 = calculate_score(ep_unverified)
        self.assertEqual(fix_status2, "unverified")
        self.assertNotEqual(status2, "product-ready")
        self.assertEqual(status2, "candidate")

    def test_multiturn_source_trace_audit(self):
        """Auditor must independently resolve and verify quote hashes for all contributing turns."""
        ag_logs_dir = self.test_dir / "sessions" / "test_session_id" / ".system_generated" / "logs"
        ag_logs_dir.mkdir(parents=True, exist_ok=True)
        dummy_log = ag_logs_dir / "transcript.jsonl"
        t1_u, t1_m = "turn 1 user error message", "turn 1 model fix explanation"
        t2_u, t2_m = "turn 2 user verification message", "turn 2 model confirmation"
        h1 = koneta_miner.turn_quote_hash(t1_u, t1_m)
        h2 = koneta_miner.turn_quote_hash(t2_u, t2_m)

        log_lines = [
            f'{{"type":"USER_INPUT","content":"{t1_u}"}}',
            f'{{"type":"PLANNER_RESPONSE","content":"{t1_m}"}}',
            f'{{"type":"USER_INPUT","content":"{t2_u}"}}',
            f'{{"type":"PLANNER_RESPONSE","content":"{t2_m}"}}',
        ]
        dummy_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

        card_content_valid = f"""---
candidate_id: "PL-20260830-001"
date: "2026-08-30"
status: "candidate"
source_trace_status: "exact"
source_platform: "antigravity"
source_session_id: "test_session_id"
source_log_path: '{str(dummy_log)}'
source_turn_at: "2026-08-30T10:00:00Z"
source_turn_index: "1"
source_user_line: "1"
source_model_line: "2"
source_quote_hash: "{h1}"
source_turns:
  - turn_index: 1
    turn_at: "2026-08-30T10:00:00Z"
    user_line: "1"
    model_line: "2"
    quote_hash: "{h1}"
    role_in_episode: "symptom,fix"
  - turn_index: 2
    turn_at: "2026-08-30T10:05:00Z"
    user_line: "3"
    model_line: "4"
    quote_hash: "{h2}"
    role_in_episode: "verification"
---
# Test Multi-Turn Card
"""
        card_file_valid = self.output_dir / "valid_multiturn.md"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        card_file_valid.write_text(card_content_valid, encoding="utf-8")

        trace_errs, _ = audit_card_detailed(card_file_valid)
        self.assertEqual(len(trace_errs), 0)

        card_content_corrupted = card_content_valid.replace(h2, "corruptedhash99999999999999999999999999999999999999999999999999999999")
        card_file_corrupted = self.output_dir / "corrupted_multiturn.md"
        card_file_corrupted.write_text(card_content_corrupted, encoding="utf-8")

        trace_errs_corrupted, _ = audit_card_detailed(card_file_corrupted)
        self.assertTrue(any("Quote hash mismatch in contributing turn 2" in e for e in trace_errs_corrupted))

    def test_true_dry_run_no_side_effects(self):
        non_existent_dir = self.test_dir / "non_existent_output_dir"
        non_existent_checkpoint = non_existent_dir / "checkpoint.json"

        files = mine_product_leads(
            lookback_hours=1,
            max_candidates=3,
            output_dir=non_existent_dir,
            checkpoint_file=non_existent_checkpoint,
            dry_run=True,
        )
        self.assertFalse(non_existent_dir.exists())
        self.assertFalse(non_existent_checkpoint.exists())

    def test_e2e_id_collision_avoidance_and_idempotence_mining(self):
        dummy_log = self.test_dir / "e2e_session.jsonl"
        t1_u = "Docker fatal error: pip cache mismatch"
        t1_m = "原因は pip cache 不整合。Dockerfile を修正して --no-cache-dir を追加。"
        h1 = koneta_miner.turn_quote_hash(t1_u, t1_m)

        dummy_log.write_text(f'{{"type":"USER_INPUT","content":"{t1_u}"}}\n{{"type":"PLANNER_RESPONSE","content":"{t1_m}"}}\n', encoding="utf-8")

        mock_turn_1 = Turn(
            user=t1_u,
            model=t1_m,
            time="2026-08-30T10:00:00Z",
            agent="nagi",
            platform="antigravity",
            session_id="e2e-session-001",
            log_path=str(dummy_log),
            turn_index=1,
            source_user_line=1,
            source_model_line=2,
            source_quote_hash=h1,
        )

        with patch("scripts.product_mining.mine_product_leads.collect_all_turns", return_value=[mock_turn_1]):
            files1 = mine_product_leads(output_dir=self.output_dir, checkpoint_file=self.checkpoint_file)
            self.assertEqual(len(files1), 1)
            today_str_compact = datetime.now().strftime("%Y%m%d")
            self.assertTrue(files1[0].name.startswith(f"{datetime.now().strftime('%Y-%m-%d')}-pl-{today_str_compact}-001"))

            files2 = mine_product_leads(output_dir=self.output_dir, checkpoint_file=self.checkpoint_file)
            all_mds_run2 = [f for f in self.output_dir.glob("*.md") if f.name.lower() != "readme.md"]
            self.assertEqual(len(all_mds_run2), 1)

        t2_u = "Python script error: cannot find module config.py"
        t2_m = "原因は sys.path の未定義です。sys.path.append を追加して修正します。"
        h2 = koneta_miner.turn_quote_hash(t2_u, t2_m)

        mock_turn_2 = Turn(
            user=t2_u,
            model=t2_m,
            time="2026-08-30T10:10:00Z",
            agent="yura",
            platform="codex",
            session_id="e2e-session-002",
            log_path=str(dummy_log),
            turn_index=2,
            source_user_line=1,
            source_model_line=2,
            source_quote_hash=h2,
        )

        with patch("scripts.product_mining.mine_product_leads.collect_all_turns", return_value=[mock_turn_1, mock_turn_2]):
            files3 = mine_product_leads(output_dir=self.output_dir, checkpoint_file=self.checkpoint_file)
            all_mds_run3 = sorted([f for f in self.output_dir.glob("*.md") if f.name.lower() != "readme.md"])
            self.assertEqual(len(all_mds_run3), 2)
            self.assertTrue(all_mds_run3[0].name.startswith(f"{datetime.now().strftime('%Y-%m-%d')}-pl-{today_str_compact}-001"))
            self.assertTrue(all_mds_run3[1].name.startswith(f"{datetime.now().strftime('%Y-%m-%d')}-pl-{today_str_compact}-002"))

            cp = load_checkpoint(self.checkpoint_file)
            self.assertIn(h1, cp["processed_episodes"])
            self.assertIn(h2, cp["processed_episodes"])
            self.assertEqual(cp["processed_episodes"][h1]["candidate_id"], f"PL-{today_str_compact}-001")
            self.assertEqual(cp["processed_episodes"][h2]["candidate_id"], f"PL-{today_str_compact}-002")

    def test_no_overwrite_guarantee(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        today_str_compact = datetime.now().strftime("%Y%m%d")
        today_str = datetime.now().strftime("%Y-%m-%d")
        slug = f"nagi-11223344"
        card_name = f"{today_str}-pl-{today_str_compact}-001-{slug}.md"
        card_path = self.output_dir / card_name
        original_content = "ORIGINAL_UNTOUCHED_CONTENT"
        card_path.write_text(original_content, encoding="utf-8")

        mock_turn = Turn(
            user="Docker build failed with fatal error",
            model="原因は pip cache 不整合。Dockerfile を修正。",
            time="2026-08-30T10:00:00Z",
            agent="nagi",
            platform="antigravity",
            session_id="test-sess",
            log_path=str(self.test_dir / "dummy.jsonl"),
            turn_index=1,
            source_user_line=1,
            source_model_line=2,
            source_quote_hash="1122334455667788990011223344556677889900112233445566778899001122",
        )

        with patch("scripts.product_mining.mine_product_leads.collect_all_turns", return_value=[mock_turn]):
            mine_product_leads(output_dir=self.output_dir, checkpoint_file=self.checkpoint_file, force=True)
            self.assertEqual(card_path.read_text(encoding="utf-8"), original_content)

    def test_semantic_target_binding_audit(self):
        ag_logs_dir = self.test_dir / "sessions" / "test_session_id" / ".system_generated" / "logs"
        ag_logs_dir.mkdir(parents=True, exist_ok=True)
        dummy_log = ag_logs_dir / "transcript.jsonl"
        dummy_log.write_text('{"type":"USER_INPUT","content":"err"}\n{"type":"PLANNER_RESPONSE","content":"ans"}\n', encoding="utf-8")

        card_content = f"""---
candidate_id: "PL-20260830-001"
date: "2026-08-30"
status: "product-ready"
fix_status: "verified"
symptom: "Docker build failed with fatal error in Dockerfile"
root_cause: "原因は Dockerfile 内の pip cache の不整合"
fix: "Dockerfile に --no-cache-dir を追加して修正"
verification_evidence: "node scripts/verify-build.mjs exit code 0 passed"
privacy_internal_risk: "low"
source_trace_status: "exact"
source_platform: "antigravity"
source_session_id: "test_session_id"
source_log_path: '{str(dummy_log)}'
source_turn_at: "2026-08-30T10:00:00Z"
source_turn_index: "1"
source_user_line: "1"
source_model_line: "2"
source_quote_hash: "abc"
---
# Card
"""
        card_file = self.output_dir / "target_binding_test.md"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        card_file.write_text(card_content, encoding="utf-8")

        _, semantic_errs = audit_card_detailed(card_file)
        self.assertTrue(any("TARGET BINDING GATE VIOLATION" in e for e in semantic_errs))

    def test_failed_product_ready_downgrade_changes_only_status_bytes(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        card_file = self.output_dir / "failing_product_ready.md"
        original = (
            b"---\r\n"
            b'candidate_id: "PL-20260903-001"\r\n'
            b'status: "product-ready"\r\n'
            b'root_cause: ""\r\n'
            b"---\r\n"
            + "# 日本語の本文\r\n本文は保持する。\r\n".encode("utf-8")
        )
        card_file.write_bytes(original)

        self.assertTrue(downgrade_failed_product_ready(card_file))
        updated = card_file.read_bytes()
        self.assertEqual(
            updated,
            original.replace(b'status: "product-ready"', b'status: "review_needed"', 1),
        )
        self.assertFalse(downgrade_failed_product_ready(card_file))

    def test_auto_downgrade_cli_repairs_card_and_checkpoint(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        source_hash = "a" * 64
        card_file = self.output_dir / "failing_product_ready.md"
        card_file.write_text(
            f'''---
candidate_id: "PL-20260903-001"
status: "product-ready"
fix_status: "verified"
symptom: "Docker build failed"
root_cause: ""
fix: "Dockerfile fixed"
verification_evidence: "docker build exit code 0"
privacy_internal_risk: "low"
source_trace_status: "untraced"
source_quote_hash: "{source_hash}"
---
# Keep this body
''',
            encoding="utf-8",
        )
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "processed_episodes": {
                        source_hash: {"candidate_id": "PL-20260903-001", "status": "product-ready"}
                    },
                }
            ),
            encoding="utf-8",
        )

        with patch("sys.argv", ["audit_product_leads.py", str(self.output_dir), "--auto-downgrade"]):
            self.assertEqual(audit_main(), 0)

        fields = parse_card_fields(card_file.read_text(encoding="utf-8"))
        checkpoint = json.loads(self.checkpoint_file.read_text(encoding="utf-8"))
        self.assertEqual(fields["status"], "review_needed")
        self.assertEqual(
            checkpoint["processed_episodes"][source_hash]["status"], "review_needed"
        )

    def test_reproduced_turn2_no_target_signal_unverified_regression(self):
        """Regression test for reproduction:
        Turn 1: Docker build failed / fix Dockerfile
        Turn 2: "結果どう？" / "exit code 0。テストは通りました。" (No target signal in Turn 2)
        Must remain fix_status: unverified and NOT become product-ready.
        """
        turns = [
            Turn(
                user="Docker build failed with fatal error in pip cache.",
                model="原因は pip cache の不整合です。Dockerfile を修正して --no-cache-dir を追加します。",
                time="2026-08-30T10:00:00Z",
                agent="nagi",
                platform="antigravity",
                session_id="reproduce-sess-001",
                log_path=str(self.test_dir / "dummy.jsonl"),
                turn_index=1,
                source_user_line=1,
                source_model_line=2,
                source_quote_hash="dockerpip1",
            ),
            Turn(
                user="結果どう？",
                model="exit code 0。テストは通りました。",
                time="2026-08-30T10:05:00Z",
                agent="nagi",
                platform="antigravity",
                session_id="reproduce-sess-001",
                log_path=str(self.test_dir / "dummy.jsonl"),
                turn_index=2,
                source_user_line=3,
                source_model_line=4,
                source_quote_hash="genericpass2",
            ),
        ]
        episodes = extract_episodes_from_turns(turns)
        self.assertEqual(len(episodes), 1)
        ep = episodes[0]

        # Verification evidence MUST be empty because Turn 2 has no target signals
        self.assertEqual(ep.verification_evidence, "")
        bd, fix_status, status = calculate_score(ep)
        self.assertEqual(fix_status, "unverified")
        self.assertNotEqual(status, "product-ready")
        self.assertEqual(status, "candidate")

        # Semantic audit must fail if card is forced to product-ready with empty verif signals
        ag_logs_dir = self.test_dir / "sessions" / "test_session_id" / ".system_generated" / "logs"
        ag_logs_dir.mkdir(parents=True, exist_ok=True)
        dummy_log = ag_logs_dir / "transcript.jsonl"
        dummy_log.write_text('{"type":"USER_INPUT","content":"err"}\n{"type":"PLANNER_RESPONSE","content":"ans"}\n', encoding="utf-8")

        forged_card = f"""---
candidate_id: "PL-20260830-001"
date: "2026-08-30"
status: "product-ready"
fix_status: "verified"
symptom: "Docker build failed with fatal error in pip cache"
root_cause: "原因は pip cache の不整合"
fix: "Dockerfile を修正して --no-cache-dir を追加"
verification_evidence: "exit code 0。テストは通りました。"
privacy_internal_risk: "low"
source_trace_status: "exact"
source_platform: "antigravity"
source_session_id: "test_session_id"
source_log_path: '{str(dummy_log)}'
source_turn_at: "2026-08-30T10:00:00Z"
source_turn_index: "1"
source_user_line: "1"
source_model_line: "2"
source_quote_hash: "abc"
---
# Card
"""
        card_file = self.output_dir / "forged_empty_verif_target.md"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        card_file.write_text(forged_card, encoding="utf-8")

        _, semantic_errs = audit_card_detailed(card_file)
        self.assertTrue(any("TARGET BINDING GATE VIOLATION" in e for e in semantic_errs))

    def test_empty_problem_target_signals_prevents_product_ready(self):
        """If problem text contains no specific target signals, status cannot be product-ready."""
        ep_no_prob_signals = Episode(
            session_id="sess-noprob-001",
            agent="nagi",
            platform="antigravity",
            log_path=str(self.test_dir / "dummy.jsonl"),
            start_turn_index=1,
            end_turn_index=2,
            start_time="2026-08-30T10:00:00Z",
            start_user_line=1,
            start_model_line=2,
            source_quote_hash="noprobsignalshash",
            symptom="処理が異常終了してクラッシュしました",
            initial_suspicion="設定不備",
            investigation="ログ確認",
            root_cause="原因は 内部フラグの競合",
            fix="フラグの初期化順序を修正しました",
            verification_evidence="docker build exit code 0 passed",
            reusable_procedure="1. 確認 2. 修正",
            detected_tech=[],
            target_signals=set(),
            has_privacy_risk=False,
            has_negation=False,
            raw_user_sample="user msg",
            raw_model_sample="model msg",
        )
        bd, fix_status, status = calculate_score(ep_no_prob_signals)
        self.assertEqual(fix_status, "unverified")
        self.assertNotEqual(status, "product-ready")

    def test_strict_multiturn_trace_audit_locator_and_time_failures(self):
        """Trace audit must fail without fallback if turn_at, user_line, model_line, required fields, or role are corrupted."""
        ag_logs_dir = self.test_dir / "sessions" / "strict_session_id" / ".system_generated" / "logs"
        ag_logs_dir.mkdir(parents=True, exist_ok=True)
        dummy_log = ag_logs_dir / "transcript.jsonl"
        t1_u, t1_m = "turn 1 user error message", "turn 1 model fix explanation"
        t2_u, t2_m = "turn 2 user verification message", "turn 2 model confirmation"
        h1 = koneta_miner.turn_quote_hash(t1_u, t1_m)
        h2 = koneta_miner.turn_quote_hash(t2_u, t2_m)

        log_lines = [
            f'{{"type":"USER_INPUT","content":"{t1_u}","created_at":"2026-08-30T10:00:00Z"}}',
            f'{{"type":"PLANNER_RESPONSE","content":"{t1_m}","created_at":"2026-08-30T10:00:00Z"}}',
            f'{{"type":"USER_INPUT","content":"{t2_u}","created_at":"2026-08-30T10:05:00Z"}}',
            f'{{"type":"PLANNER_RESPONSE","content":"{t2_m}","created_at":"2026-08-30T10:05:00Z"}}',
        ]
        dummy_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

        base_valid_yaml = f"""---
candidate_id: "PL-20260830-001"
date: "2026-08-30"
status: "candidate"
source_trace_status: "exact"
source_platform: "antigravity"
source_session_id: "strict_session_id"
source_log_path: '{str(dummy_log)}'
source_turn_at: "2026-08-30T10:00:00Z"
source_turn_index: "1"
source_user_line: "1"
source_model_line: "2"
source_quote_hash: "{h1}"
source_turns:
  - turn_index: 1
    turn_at: "2026-08-30T10:00:00Z"
    user_line: "1"
    model_line: "2"
    quote_hash: "{h1}"
    role_in_episode: "symptom,fix"
  - turn_index: 2
    turn_at: "2026-08-30T10:05:00Z"
    user_line: "3"
    model_line: "4"
    quote_hash: "{h2}"
    role_in_episode: "verification"
---
# Test Card
"""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Corrupt turn_at in Turn 2 -> Must fail with turn_at mismatch!
        card_bad_time = base_valid_yaml.replace('turn_at: "2026-08-30T10:05:00Z"', 'turn_at: "2026-08-30T99:99:99Z"')
        f_bad_time = self.output_dir / "bad_time.md"
        f_bad_time.write_text(card_bad_time, encoding="utf-8")
        errs_time, _ = audit_card_detailed(f_bad_time)
        self.assertTrue(any("turn_at mismatch in contributing turn 2" in e for e in errs_time))

        # 2. Corrupt user_line in Turn 1
        card_bad_uline = base_valid_yaml.replace('user_line: "1"', 'user_line: "999"')
        f_bad_uline = self.output_dir / "bad_uline.md"
        f_bad_uline.write_text(card_bad_uline, encoding="utf-8")
        errs_uline, _ = audit_card_detailed(f_bad_uline)
        self.assertTrue(any("user_line mismatch in contributing turn 1" in e for e in errs_uline))

        # 3. Corrupt model_line in Turn 2
        card_bad_mline = base_valid_yaml.replace('model_line: "4"', 'model_line: "888"')
        f_bad_mline = self.output_dir / "bad_mline.md"
        f_bad_mline.write_text(card_bad_mline, encoding="utf-8")
        errs_mline, _ = audit_card_detailed(f_bad_mline)
        self.assertTrue(any("model_line mismatch in contributing turn 2" in e for e in errs_mline))

        # 4. Missing required field in source_turns
        card_missing_field = base_valid_yaml.replace('role_in_episode: "verification"', '')
        f_missing = self.output_dir / "missing_field.md"
        f_missing.write_text(card_missing_field, encoding="utf-8")
        errs_missing, _ = audit_card_detailed(f_missing)
        self.assertTrue(any("missing required fields" in e for e in errs_missing))

        # 5. Invalid role_in_episode token
        card_bad_role = base_valid_yaml.replace('role_in_episode: "verification"', 'role_in_episode: "unauthorized_role"')
        f_bad_role = self.output_dir / "bad_role.md"
        f_bad_role.write_text(card_bad_role, encoding="utf-8")
        errs_role, _ = audit_card_detailed(f_bad_role)
        self.assertTrue(any("Invalid role_in_episode tokens" in e for e in errs_role))

    def test_koneta_compatibility(self):
        self.assertTrue(hasattr(koneta_miner, "turn_quote_hash"))
        self.assertTrue(hasattr(koneta_miner, "extract_turns_from_antigravity"))
        self.assertTrue(hasattr(koneta_miner, "extract_turns_from_codex"))
        self.assertTrue(hasattr(koneta_miner, "extract_turns_from_claude"))
        self.assertTrue(hasattr(koneta_audit, "audit_exact"))


if __name__ == "__main__":
    unittest.main()
