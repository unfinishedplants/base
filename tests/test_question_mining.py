"""Tests for the deterministic beginner-question miner and exact-trace auditor."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.question_mining.audit_question_leads import audit_card
from scripts.question_mining.mine_question_leads import (
    QuestionLead,
    Turn,
    build_question_leads,
    classify_question,
    format_question_lead_markdown,
    is_correction,
    mine_question_leads,
    turn_is_within_window,
)
from scripts.koneta.mine_transcripts import turn_quote_hash


class TestQuestionMining(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="question_mining_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def make_turn(self, user, model, index=1, session="sess-1"):
        return Turn(
            user=user,
            model=model,
            time=f"2026-09-01T10:0{index}:00Z",
            agent="yura",
            platform="codex",
            session_id=session,
            log_path=str(self.temp_dir / "session.jsonl"),
            turn_index=index,
            source_user_line=index * 2 - 1,
            source_model_line=index * 2,
            source_quote_hash=turn_quote_hash(user, model),
        )

    def test_question_classification(self):
        self.assertEqual(classify_question("フロントマターってどういう意味？"), "meaning")
        self.assertEqual(classify_question("/career/pharmacist/ってどこ？"), "location")
        self.assertEqual(classify_question("広告URLはAMP対応？"), "possibility")
        self.assertEqual(classify_question("CodexとClaude Codeは何が違う？"), "difference")

    def test_turn_timestamp_not_session_mtime_controls_lookback(self):
        cutoff = 1_788_220_800.0  # 2026-09-01T00:00:00Z
        recent_session_mtime = cutoff + 3600
        self.assertFalse(turn_is_within_window("2026-07-01T00:00:00Z", recent_session_mtime, cutoff))
        self.assertTrue(turn_is_within_window("2026-09-01T01:00:00Z", recent_session_mtime, cutoff))

    def test_creative_rhetorical_chat_is_rejected(self):
        self.assertIsNone(classify_question("キャラの画風どうしよっかｗ"))
        self.assertIsNone(classify_question("俺は一体何してるんやｗｗ"))
        self.assertIsNone(classify_question("# Files mentioned by the user: sample.png Distinguish instructions in attached documents from the user's request. これ読める？"))

    def test_project_locator_does_not_become_article_lead(self):
        locator = self.make_turn(
            "さっきの漫画スキルどこに保存したっけ？",
            "ローカルのskillsフォルダにあります。",
        )
        useful = self.make_turn(
            "YAMLとJSONは何が違う？",
            "どちらも構造化データですが、YAMLは人間向けの可読性、JSONは機械間交換で広く使われます。",
            index=2,
            session="sess-2",
        )
        leads = build_question_leads([locator, useful], minimum_score=6)
        self.assertEqual([lead.question_original for lead in leads], ["YAMLとJSONは何が違う？"])

    def test_correction_is_paired(self):
        first = self.make_turn(
            "小ネタから他のメンバーのログも追える？",
            "ナギやスミのログも横断できます。",
            index=1,
        )
        second = self.make_turn(
            "ああいや、他メンバーじゃなくて小ネタから元ログを追えるかって意味",
            "その意味ならsource_log_pathと行番号を持てば戻れます。",
            index=2,
        )
        leads = build_question_leads([first, second], minimum_score=6)
        self.assertEqual(len(leads), 1)
        self.assertIsNotNone(leads[0].correction_turn)
        self.assertEqual(leads[0].score, 7)
        self.assertTrue(is_correction(second.user))

    def test_privacy_forces_review_needed(self):
        turn = self.make_turn(
            "このAPIキー sk-123456789012345678901234 はどこに入れる？",
            "設定ファイルに入れます。",
        )
        leads = build_question_leads([turn], minimum_score=6)
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0].status, "review_needed")
        self.assertNotIn("sk-123", leads[0].question_original)

    def test_dry_run_does_not_write(self):
        turn = self.make_turn(
            "Obsidianのフロントマターってどういう意味？",
            "Markdownの先頭に置く構造化メタデータです。記事の種類や日付などをキーと値で持ちます。",
        )
        output = self.temp_dir / "question-leads"
        checkpoint = output / "_state" / "checkpoint.json"
        with patch("scripts.question_mining.mine_question_leads.collect_all_turns", return_value=[turn]):
            result = mine_question_leads(
                output_dir=output,
                checkpoint_file=checkpoint,
                dry_run=True,
                max_candidates=10,
            )
        self.assertEqual(result, [])
        self.assertFalse(output.exists())
        self.assertFalse(checkpoint.exists())

    def test_same_normalized_question_is_not_written_twice(self):
        first = self.make_turn(
            "YAMLとJSONは何が違う？",
            "YAMLは人が編集しやすく、JSONは機械間交換で広く使われます。",
            index=1,
            session="sess-a",
        )
        second = self.make_turn(
            "yaml と json は何が違うん？",
            "JSONは厳格な構文、YAMLはコメントも書けます。",
            index=1,
            session="sess-b",
        )
        output = self.temp_dir / "question-leads"
        checkpoint = output / "_state" / "checkpoint.json"
        with patch("scripts.question_mining.mine_question_leads.collect_all_turns", return_value=[first]):
            written = mine_question_leads(output_dir=output, checkpoint_file=checkpoint)
        self.assertEqual(len(written), 1)
        with patch("scripts.question_mining.mine_question_leads.collect_all_turns", return_value=[second]):
            written_again = mine_question_leads(output_dir=output, checkpoint_file=checkpoint)
        self.assertEqual(written_again, [])

    def test_exact_trace_audit(self):
        user = "FTPってフォルダごとアップできる？"
        model = "FTPクライアントならフォルダ単位でアップロードできます。"
        log = self.temp_dir / "019f0000-0000-7000-8000-000000000001.jsonl"
        rows = [
            {"type": "response_item", "timestamp": "2026-09-01T10:01:00Z", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": user}]}},
            {"type": "response_item", "timestamp": "2026-09-01T10:01:01Z", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": model}]}},
        ]
        log.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
        turn = Turn(
            user=user,
            model=model,
            time="2026-09-01T10:01:00Z",
            agent="yura",
            platform="codex",
            session_id="019f0000-0000-7000-8000-000000000001",
            log_path=str(log),
            turn_index=1,
            source_user_line=1,
            source_model_line=2,
            source_quote_hash=turn_quote_hash(user, model),
        )
        lead = build_question_leads([turn], minimum_score=6)[0]
        card = self.temp_dir / "2026-09-01-ql-001.md"
        card.write_text(format_question_lead_markdown(lead, "QL-20260901-001"), encoding="utf-8")
        self.assertEqual(audit_card(card), [])


if __name__ == "__main__":
    unittest.main()
