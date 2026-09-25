"""Shared, append-ordered question reveals for a live contest.

The official text is stored separately from search plans and personal drafts.
This database lives under artifacts/, which the Docker backend mounts persistently.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4


class LiveQuestionError(ValueError):
    pass


class LiveQuestionNotFound(LiveQuestionError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LiveQuestionRepo:
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self._lock = threading.RLock()
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS live_questions (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('kis', 'qa', 'trake')),
                    qa_question TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS live_reveals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id TEXT NOT NULL REFERENCES live_questions(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    text_vi TEXT NOT NULL DEFAULT '',
                    text_en TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(question_id, position)
                );
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.database_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _check_text(text_vi: str, text_en: str) -> tuple[str, str]:
        vi, en = text_vi.strip(), text_en.strip()
        if not vi and not en:
            raise LiveQuestionError("Cần nhập ít nhất một bản gốc tiếng Việt hoặc tiếng Anh.")
        return vi, en

    @staticmethod
    def _require(conn: sqlite3.Connection, question_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM live_questions WHERE id = ?", (question_id,)).fetchone()
        if row is None:
            raise LiveQuestionNotFound("Không tìm thấy câu hỏi trực tiếp.")
        return row

    def list_questions(self) -> list[dict]:
        with self._lock, self._connect() as conn:
            questions = [dict(row) for row in conn.execute(
                "SELECT * FROM live_questions ORDER BY created_at DESC, id DESC"
            )]
            by_id = {item["id"]: item for item in questions}
            for item in questions:
                item["reveals"] = []
            for row in conn.execute("SELECT * FROM live_reveals ORDER BY question_id, position"):
                by_id[row["question_id"]]["reveals"].append(dict(row))
            return questions

    def create_question(self, *, label: str, kind: str, qa_question: str = "") -> dict:
        label = label.strip()
        qa_question = qa_question.strip()
        if not label or len(label) > 120:
            raise LiveQuestionError("Tên câu phải dài từ 1 đến 120 ký tự.")
        if kind not in {"kis", "qa", "trake"}:
            raise LiveQuestionError("Loại câu không hợp lệ.")
        if kind != "qa" and qa_question:
            raise LiveQuestionError("Chỉ câu Q&A mới có câu hỏi cần trả lời.")
        now = _now()
        question_id = str(uuid4())
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO live_questions VALUES (?, ?, ?, ?, ?, ?)",
                (question_id, label, kind, qa_question, now, now),
            )
        return {"id": question_id, "label": label, "kind": kind,
                "qa_question": qa_question, "created_at": now, "updated_at": now, "reveals": []}

    def update_question(self, question_id: str, *, label: str, qa_question: str) -> dict:
        label, qa_question = label.strip(), qa_question.strip()
        if not label or len(label) > 120:
            raise LiveQuestionError("Tên câu phải dài từ 1 đến 120 ký tự.")
        with self._lock, self._connect() as conn:
            question = self._require(conn, question_id)
            if question["kind"] != "qa" and qa_question:
                raise LiveQuestionError("Chỉ câu Q&A mới có câu hỏi cần trả lời.")
            conn.execute("UPDATE live_questions SET label = ?, qa_question = ?, updated_at = ? WHERE id = ?",
                         (label, qa_question, _now(), question_id))
        return next(item for item in self.list_questions() if item["id"] == question_id)

    def add_reveal(self, question_id: str, *, text_vi: str, text_en: str) -> dict:
        vi, en = self._check_text(text_vi, text_en)
        with self._lock, self._connect() as conn:
            self._require(conn, question_id)
            last = conn.execute(
                "SELECT * FROM live_reveals WHERE question_id = ? ORDER BY position DESC LIMIT 1",
                (question_id,),
            ).fetchone()
            if last is not None and last["text_vi"] == vi and last["text_en"] == en:
                return dict(last)
            position = conn.execute(
                "SELECT COUNT(*) FROM live_reveals WHERE question_id = ?", (question_id,)
            ).fetchone()[0] + 1
            now = _now()
            cur = conn.execute(
                """INSERT INTO live_reveals(question_id, position, text_vi, text_en, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (question_id, position, vi, en, now, now),
            )
            conn.execute("UPDATE live_questions SET updated_at = ? WHERE id = ?", (now, question_id))
            return dict(conn.execute("SELECT * FROM live_reveals WHERE id = ?", (cur.lastrowid,)).fetchone())

    def update_reveal(self, question_id: str, reveal_id: int, *, text_vi: str, text_en: str) -> dict:
        vi, en = self._check_text(text_vi, text_en)
        with self._lock, self._connect() as conn:
            self._require(conn, question_id)
            row = conn.execute(
                "SELECT * FROM live_reveals WHERE id = ? AND question_id = ?", (reveal_id, question_id)
            ).fetchone()
            if row is None:
                raise LiveQuestionNotFound("Không tìm thấy mốc công bố.")
            now = _now()
            conn.execute("UPDATE live_reveals SET text_vi = ?, text_en = ?, updated_at = ? WHERE id = ?",
                         (vi, en, now, reveal_id))
            conn.execute("UPDATE live_questions SET updated_at = ? WHERE id = ?", (now, question_id))
            return dict(conn.execute("SELECT * FROM live_reveals WHERE id = ?", (reveal_id,)).fetchone())

    def delete_question(self, question_id: str) -> None:
        with self._lock, self._connect() as conn:
            self._require(conn, question_id)
            conn.execute("DELETE FROM live_questions WHERE id = ?", (question_id,))

    def backup(self) -> dict:
        return {"format": "aic-live-questions", "version": 1,
                "exported_at": _now(), "questions": self.list_questions()}

    def restore(self, snapshot: dict, *, replace_existing: bool = False) -> list[dict]:
        if snapshot.get("format") != "aic-live-questions" or snapshot.get("version") != 1:
            raise LiveQuestionError("Backup nhật ký không đúng định dạng v1.")
        questions = snapshot.get("questions")
        if not isinstance(questions, list) or len(questions) > 500:
            raise LiveQuestionError("Danh sách câu trong backup không hợp lệ.")
        question_rows: list[tuple] = []
        reveal_rows: list[tuple] = []
        seen_question_ids: set[str] = set()
        seen_reveal_ids: set[int] = set()
        for question in questions:
            if not isinstance(question, dict):
                raise LiveQuestionError("Câu hỏi trong backup không hợp lệ.")
            qid = question.get("id")
            label = question.get("label")
            kind = question.get("kind")
            qa_question = question.get("qa_question")
            created = question.get("created_at")
            updated = question.get("updated_at")
            reveals = question.get("reveals")
            if (not isinstance(qid, str) or not qid or len(qid) > 64 or qid in seen_question_ids
                    or not isinstance(label, str) or not label.strip() or len(label) > 120
                    or kind not in {"kis", "qa", "trake"}
                    or not isinstance(qa_question, str) or len(qa_question) > 10000
                    or (kind != "qa" and qa_question)
                    or not isinstance(created, str) or not isinstance(updated, str)
                    or not isinstance(reveals, list) or len(reveals) > 1000):
                raise LiveQuestionError("Metadata câu hỏi trong backup không hợp lệ.")
            seen_question_ids.add(qid)
            question_rows.append((qid, label.strip(), kind, qa_question.strip(), created, updated))
            for index, reveal in enumerate(reveals, 1):
                if not isinstance(reveal, dict):
                    raise LiveQuestionError("Hint trong backup không hợp lệ.")
                rid = reveal.get("id")
                vi = reveal.get("text_vi")
                en = reveal.get("text_en")
                if (not isinstance(rid, int) or rid < 1 or rid in seen_reveal_ids
                        or reveal.get("question_id") != qid or reveal.get("position") != index
                        or not isinstance(vi, str) or not isinstance(en, str)
                        or len(vi) > 30000 or len(en) > 30000
                        or not isinstance(reveal.get("created_at"), str)
                        or not isinstance(reveal.get("updated_at"), str)):
                    raise LiveQuestionError("Metadata hint trong backup không hợp lệ.")
                self._check_text(vi, en)
                seen_reveal_ids.add(rid)
                reveal_rows.append((rid, qid, index, vi, en,
                                    reveal["created_at"], reveal["updated_at"]))
        with self._lock, self._connect() as conn:
            existing = conn.execute("SELECT 1 FROM live_questions LIMIT 1").fetchone()
            if existing and not replace_existing:
                raise LiveQuestionError("Nhật ký đã có dữ liệu. Cần xác nhận thay thế khi restore.")
            if replace_existing:
                conn.execute("DELETE FROM live_questions")
            conn.executemany("INSERT INTO live_questions VALUES (?, ?, ?, ?, ?, ?)", question_rows)
            conn.executemany("INSERT INTO live_reveals VALUES (?, ?, ?, ?, ?, ?, ?)", reveal_rows)
        return self.list_questions()
