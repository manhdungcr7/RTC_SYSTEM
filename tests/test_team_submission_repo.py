"""Regression tests for the shared-submission SQLite repository.

Run without model/index services:
    python -m unittest tests.test_team_submission_repo
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.repositories.team_submission_repo import (
    BatchConflictError,
    TeamSubmissionError,
    TeamSubmissionRepo,
)


def question_zip(entries: dict[str, str]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in entries.items():
            archive.writestr(name, text)
    return out.getvalue()


VALID_QUESTIONS = {
    "query-p9-1-kis.txt": "Tìm một cảnh bất kỳ.",
    "query-p9-2-qa.txt": "Câu hỏi có đáp án chữ.",
    "query-p9-3-trake.txt": "Sự kiện đầu.\nSự kiện cuối.",
}


class TeamSubmissionRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = TeamSubmissionRepo(Path(self.temp.name) / "team.sqlite3")
        self.repo.import_questions(question_zip(VALID_QUESTIONS))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_import_builds_fixed_question_list(self) -> None:
        board = self.repo.get_batch("p9")
        self.assertEqual(board["question_count"], 3)
        self.assertEqual([item["number"] for item in board["questions"]], [1, 2, 3])
        self.assertEqual([item["kind"] for item in board["questions"]], ["kis", "qa", "trake"])
        self.assertEqual(board["questions"][1]["filename"], "query-p9-2-qa.csv")

    def test_same_member_updates_own_record_without_touching_other_member(self) -> None:
        self.repo.upsert_answer(
            batch_id="p9", question_number=1, member_id="huy-a1b2", display_name="Huy",
            csv_text="L01_V001,100\n", note="bản đầu",
        )
        self.repo.upsert_answer(
            batch_id="p9", question_number=1, member_id="dung-c3d4", display_name="Dũng",
            csv_text="L01_V002,200\n", note="",
        )
        self.repo.patch_answer(
            batch_id="p9", question_number=1, member_id="huy-a1b2",
            actor_member_id="dung-c3d4", actor_display_name="Dũng",
            check_status="checked", note="Kiểm tra lại frame.",
        )
        updated = self.repo.upsert_answer(
            batch_id="p9", question_number=1, member_id="huy-a1b2", display_name="Huy",
            csv_text="L01_V001,101\n", note="đã sửa",
        )
        self.assertEqual(updated["check_status"], "unchecked")
        self.assertEqual(updated["note"], "Kiểm tra lại frame.")
        answers = self.repo.get_batch("p9")["questions"][0]["answers"]
        self.assertEqual(len(answers), 2)
        self.assertEqual(next(item for item in answers if item["member_id"] == "dung-c3d4")["csv_text"], "L01_V002,200\n")
        cleared = self.repo.patch_answer(
            batch_id="p9", question_number=1, member_id="huy-a1b2",
            actor_member_id="dung-c3d4", actor_display_name="Dũng", check_status="unchecked",
        )
        self.assertIsNone(cleared["checked_by_member_id"])
        self.assertIsNone(cleared["checked_at"])

    def test_validate_all_kinds_and_export_selected_answers(self) -> None:
        self.repo.upsert_answer(
            batch_id="p9", question_number=1, member_id="huy-a1b2", display_name="Huy",
            csv_text="L01_V001,100\n", note="",
        )
        self.repo.upsert_answer(
            batch_id="p9", question_number=2, member_id="huy-a1b2", display_name="Huy",
            csv_text='L01_V002,200,"đáp án, có dấu phẩy"\n', note="",
        )
        self.repo.upsert_answer(
            batch_id="p9", question_number=3, member_id="huy-a1b2", display_name="Huy",
            csv_text="L01_V003,100,200\n", note="",
        )
        for number in (1, 2, 3):
            self.repo.choose_answer(
                batch_id="p9", question_number=number, member_id="huy-a1b2",
                actor_member_id="huy-a1b2", actor_display_name="Huy",
            )
        payload = self.repo.export_submission_zip("p9")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertEqual(sorted(archive.namelist()), [
                "submission/query-p9-1-kis.csv",
                "submission/query-p9-2-qa.csv",
                "submission/query-p9-3-trake.csv",
            ])
            self.assertIn('"đáp án, có dấu phẩy"', archive.read("submission/query-p9-2-qa.csv").decode("utf-8"))

    def test_backup_restore_preserves_identity_review_and_choice(self) -> None:
        self.repo.upsert_answer(
            batch_id="p9", question_number=1, member_id="huy-a1b2", display_name="Huy",
            csv_text="L01_V001,100\n", note="xem kỹ",
        )
        self.repo.patch_answer(
            batch_id="p9", question_number=1, member_id="huy-a1b2",
            actor_member_id="dung-c3d4", actor_display_name="Dũng", check_status="needs_rework",
        )
        self.repo.choose_answer(
            batch_id="p9", question_number=1, member_id="huy-a1b2",
            actor_member_id="dung-c3d4", actor_display_name="Dũng",
        )
        snapshot = json.loads(json.dumps(self.repo.backup_batch("p9"), ensure_ascii=False))
        target = TeamSubmissionRepo(Path(self.temp.name) / "restored.sqlite3")
        board = target.restore_batch(snapshot)
        answer = board["questions"][0]["answers"][0]
        self.assertEqual(answer["member_id"], "huy-a1b2")
        self.assertEqual(answer["check_status"], "needs_rework")
        self.assertEqual(answer["checked_by_member_id"], "dung-c3d4")
        self.assertEqual(board["questions"][0]["selected_member_id"], "huy-a1b2")
        self.assertEqual(board["questions"][0]["chosen_by_member_id"], "dung-c3d4")

    def test_rejects_incomplete_questions_and_conflicting_batch(self) -> None:
        with self.assertRaises(TeamSubmissionError):
            self.repo.import_questions(question_zip({"query-p8-2-kis.txt": "Thiếu câu 1"}))
        changed = dict(VALID_QUESTIONS)
        changed["query-p9-1-kis.txt"] = "Mô tả khác"
        with self.assertRaises(BatchConflictError):
            self.repo.import_questions(question_zip(changed))
        with self.assertRaises(TeamSubmissionError):
            self.repo.import_questions(question_zip({"folder\\query-p8-1-kis.txt": "Không hợp lệ"}))

    def test_delete_batch_removes_only_shared_batch_data(self) -> None:
        self.repo.upsert_answer(
            batch_id="p9", question_number=1, member_id="huy-a1b2", display_name="Huy",
            csv_text="L01_V001,100\n", note="",
        )
        deleted = self.repo.delete_batch("P9")
        self.assertEqual(deleted, {"id": "p9", "question_count": 3, "deleted": True})
        self.assertEqual(self.repo.list_batches(), [])
        with self.assertRaises(TeamSubmissionError):
            self.repo.get_batch("p9")


if __name__ == "__main__":
    unittest.main()
