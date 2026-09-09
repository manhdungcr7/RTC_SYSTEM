"""Luu bang chia se bai nop cua nhom tren mot SQLite database nhe.

Du lieu nay doc lap voi ban nhap localStorage cua frontend. SQLite phu hop cho
mot backend duy nhat, duoc bind-mount qua ``artifacts/`` va khong can dich vu DB
bo sung. Moi thao tac ghi dung transaction nguyen tu va khoa trong tien trinh.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
import tempfile
import threading
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core import submit as submit_core


QUESTION_NAME_RE = re.compile(
    r"^query-([a-z0-9]+)-([1-9][0-9]*)-(kis|qa|trake)\.txt$", re.IGNORECASE
)
MEMBER_ID_RE = re.compile(r"^[a-z0-9_-]{4,64}$")
CHECK_STATUSES = {"unchecked", "checked", "needs_rework"}
MAX_QUESTION_ZIP_BYTES = 5 * 1024 * 1024
MAX_BACKUP_ZIP_BYTES = 10 * 1024 * 1024
MAX_ZIP_ENTRIES = 250
MAX_ENTRY_BYTES = 512 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 10 * 1024 * 1024
MAX_CSV_BYTES = 1024 * 1024


class TeamSubmissionError(ValueError):
    """Loi du lieu do client gui len, an toan de hien thi cho nguoi dung."""


class BatchConflictError(TeamSubmissionError):
    """Batch da ton tai nhung cau truc de khac."""


class TeamSubmissionNotFoundError(TeamSubmissionError):
    """Khong tim thay batch/cau/bai chia se."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_member_id(value: str) -> str:
    member_id = value.strip().lower()
    if not MEMBER_ID_RE.fullmatch(member_id):
        raise TeamSubmissionError(
            "Member ID phai dai 4-64 ky tu va chi gom a-z, 0-9, dau gach ngang hoac gach duoi."
        )
    return member_id


def normalize_display_name(value: str) -> str:
    name = value.strip()
    if not 1 <= len(name) <= 60:
        raise TeamSubmissionError("Ten hien thi phai dai 1-60 ky tu.")
    return name


def normalize_note(value: str) -> str:
    if len(value) > 2_000:
        raise TeamSubmissionError("Ghi chu toi da 2000 ky tu.")
    return value.strip()


def _safe_zip_entries(raw: bytes, *, expected_suffix: str) -> list[zipfile.ZipInfo]:
    if not raw:
        raise TeamSubmissionError("File ZIP rong.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise TeamSubmissionError("File tai len khong phai ZIP hop le.") from exc
    try:
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
        if not entries:
            raise TeamSubmissionError("ZIP khong co file nao.")
        if len(entries) > MAX_ZIP_ENTRIES:
            raise TeamSubmissionError("ZIP co qua nhieu file.")
        total = 0
        for entry in entries:
            path = Path(entry.filename)
            if "/" in entry.filename or "\\" in entry.filename or path.name != entry.filename:
                raise TeamSubmissionError("ZIP khong duoc chua file trong thu muc con.")
            if path.suffix.lower() != expected_suffix:
                raise TeamSubmissionError(f"ZIP chi duoc chua file {expected_suffix}.")
            if entry.file_size > MAX_ENTRY_BYTES:
                raise TeamSubmissionError(f"File {entry.filename} qua lon.")
            total += entry.file_size
            if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise TeamSubmissionError("Tong dung luong sau giai nen vuot gioi han.")
        return entries
    finally:
        archive.close()


def parse_question_zip(raw: bytes) -> tuple[str, str, list[dict[str, Any]]]:
    """Doc va validate question.zip, tra ve batch, fingerprint va cac cau hoi."""
    if len(raw) > MAX_QUESTION_ZIP_BYTES:
        raise TeamSubmissionError("question.zip vuot gioi han 5 MB.")
    entries = _safe_zip_entries(raw, expected_suffix=".txt")
    archive = zipfile.ZipFile(io.BytesIO(raw))
    try:
        questions: list[dict[str, Any]] = []
        batch_ids: set[str] = set()
        seen_numbers: set[int] = set()
        for entry in entries:
            match = QUESTION_NAME_RE.fullmatch(entry.filename)
            if match is None:
                raise TeamSubmissionError(
                    f"Ten file de khong dung mau query-<batch>-<so>-<kis|qa|trake>.txt: {entry.filename}"
                )
            batch_id, number_text, kind = match.groups()
            batch_id = batch_id.lower()
            number = int(number_text)
            if number in seen_numbers:
                raise TeamSubmissionError(f"Trung so cau {number} trong question.zip.")
            try:
                description = archive.read(entry).decode("utf-8-sig").strip()
            except UnicodeDecodeError as exc:
                raise TeamSubmissionError(f"File de {entry.filename} phai ma hoa UTF-8.") from exc
            if not description:
                raise TeamSubmissionError(f"File de {entry.filename} dang rong.")
            if len(description) > 30_000:
                raise TeamSubmissionError(f"File de {entry.filename} qua dai.")
            batch_ids.add(batch_id)
            seen_numbers.add(number)
            questions.append({
                "number": number,
                "filename": entry.filename[:-4] + ".csv",
                "kind": kind.lower(),
                "description": description,
                "trake_event_count": None,
            })
    finally:
        archive.close()
    if len(batch_ids) != 1:
        raise TeamSubmissionError("question.zip chi duoc chua mot batch de.")
    questions.sort(key=lambda item: item["number"])
    expected = list(range(1, len(questions) + 1))
    actual = [item["number"] for item in questions]
    if actual != expected:
        raise TeamSubmissionError("So cau trong question.zip phai lien tuc tu 1 den N.")
    canonical = json.dumps(questions, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return next(iter(batch_ids)), hashlib.sha256(canonical.encode("utf-8")).hexdigest(), questions


def _parse_csv_text(csv_text: str) -> list[list[str]]:
    if len(csv_text.encode("utf-8")) > MAX_CSV_BYTES:
        raise TeamSubmissionError("CSV vuot gioi han 1 MB.")
    try:
        rows = list(csv.reader(io.StringIO(csv_text, newline="")))
    except csv.Error as exc:
        raise TeamSubmissionError(f"Khong doc duoc CSV: {exc}") from exc
    if not rows:
        raise TeamSubmissionError("CSV khong co dong du lieu nao.")
    return [[cell.strip() for cell in row] for row in rows]


def normalize_submission_csv(csv_text: str, kind: str, n_events: int | None) -> tuple[str, int | None]:
    """Kiem tra bang validator dung chung va tra ve CSV da chuan hoa."""
    rows = _parse_csv_text(csv_text)
    if kind not in {"kis", "qa", "trake"}:
        raise TeamSubmissionError("Loai cau hoi khong hop le.")
    if kind == "trake":
        if n_events is None:
            n_events = len(rows[0]) - 1
        if not isinstance(n_events, int) or n_events < 1:
            raise TeamSubmissionError("TRAKE phai co it nhat mot frame su kien.")
        # core.submit.validate so sanh int() o TRAKE. Kiem tra som de no khong nem 500.
        invalid = [
            f"dong {idx + 1}" for idx, row in enumerate(rows)
            if len(row) > 1 and any(not value.isdigit() for value in row[1:])
        ]
        if invalid:
            raise TeamSubmissionError(f"Frame TRAKE khong phai so nguyen o {', '.join(invalid[:5])}.")
    errors = submit_core.validate(rows, kind, n_events)
    if errors:
        raise TeamSubmissionError("CSV khong hop le: " + "; ".join(errors[:8]))
    return submit_core.to_csv_text(rows), n_events if kind == "trake" else None


class TeamSubmissionRepo:
    """Repository SQLite cho mot backend duy nhat."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self._lock = threading.RLock()
        self._init_schema()

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

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript("""
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS batches (
                    id TEXT PRIMARY KEY,
                    question_count INTEGER NOT NULL,
                    source_fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS questions (
                    batch_id TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
                    number INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('kis', 'qa', 'trake')),
                    description TEXT NOT NULL,
                    trake_event_count INTEGER,
                    PRIMARY KEY (batch_id, number),
                    UNIQUE (batch_id, filename)
                );
                CREATE TABLE IF NOT EXISTS shared_answers (
                    batch_id TEXT NOT NULL,
                    question_number INTEGER NOT NULL,
                    member_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    csv_text TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    check_status TEXT NOT NULL DEFAULT 'unchecked'
                        CHECK(check_status IN ('unchecked', 'checked', 'needs_rework')),
                    checked_by_member_id TEXT,
                    checked_by_name TEXT,
                    checked_at TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (batch_id, question_number, member_id),
                    FOREIGN KEY (batch_id, question_number)
                        REFERENCES questions(batch_id, number) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS submission_choices (
                    batch_id TEXT NOT NULL,
                    question_number INTEGER NOT NULL,
                    member_id TEXT NOT NULL,
                    chosen_by_member_id TEXT,
                    chosen_by_name TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (batch_id, question_number),
                    FOREIGN KEY (batch_id, question_number, member_id)
                        REFERENCES shared_answers(batch_id, question_number, member_id)
                        ON DELETE CASCADE
                );
            """)

    def import_questions(self, raw: bytes, *, replace_existing: bool = False) -> tuple[dict[str, Any], bool]:
        batch_id, fingerprint, questions = parse_question_zip(raw)
        with self._lock, self._connect() as conn:
            existing = conn.execute("SELECT source_fingerprint FROM batches WHERE id = ?", (batch_id,)).fetchone()
            if existing is not None:
                if existing["source_fingerprint"] == fingerprint:
                    return self._get_batch_with_conn(conn, batch_id), False
                if not replace_existing:
                    raise BatchConflictError(
                        f"Batch '{batch_id}' da ton tai voi question.zip khac. Can xac nhan thay the."
                    )
                conn.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
            created_at = utc_now()
            conn.execute(
                "INSERT INTO batches(id, question_count, source_fingerprint, created_at) VALUES (?, ?, ?, ?)",
                (batch_id, len(questions), fingerprint, created_at),
            )
            conn.executemany(
                """INSERT INTO questions(batch_id, number, filename, kind, description, trake_event_count)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (batch_id, item["number"], item["filename"], item["kind"], item["description"], None)
                    for item in questions
                ],
            )
            return self._get_batch_with_conn(conn, batch_id), True

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            return self._get_batch_with_conn(conn, batch_id.lower())

    def list_batches(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT id, question_count, created_at FROM batches ORDER BY created_at DESC, id"
            ).fetchall()]

    def delete_batch(self, batch_id: str) -> dict[str, Any]:
        """Xoa mot dot de va toan bo du lieu CHIA SE cua no.

        Ban nhap local cua frontend khong nam trong SQLite nay, nen khong bi anh huong.
        Foreign-key cascade xoa questions, shared_answers va submission_choices trong cung
        mot transaction.
        """
        batch_id = batch_id.lower().strip()
        with self._lock, self._connect() as conn:
            batch = conn.execute(
                "SELECT id, question_count FROM batches WHERE id = ?", (batch_id,)
            ).fetchone()
            if batch is None:
                raise TeamSubmissionNotFoundError(f"Khong tim thay batch '{batch_id}'.")
            conn.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
            return {"id": batch["id"], "question_count": batch["question_count"], "deleted": True}

    def _get_batch_with_conn(self, conn: sqlite3.Connection, batch_id: str) -> dict[str, Any]:
        batch = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
        if batch is None:
            raise TeamSubmissionNotFoundError(f"Khong tim thay batch '{batch_id}'.")
        questions = [dict(row) for row in conn.execute(
            "SELECT * FROM questions WHERE batch_id = ? ORDER BY number", (batch_id,)
        ).fetchall()]
        answers = [dict(row) for row in conn.execute(
            """SELECT * FROM shared_answers WHERE batch_id = ?
               ORDER BY question_number, updated_at DESC, member_id""", (batch_id,)
        ).fetchall()]
        choices = {
            row["question_number"]: dict(row)
            for row in conn.execute("SELECT * FROM submission_choices WHERE batch_id = ?", (batch_id,))
        }
        by_question: dict[int, list[dict[str, Any]]] = {}
        for answer in answers:
            by_question.setdefault(answer["question_number"], []).append(answer)
        for question in questions:
            question["answers"] = by_question.get(question["number"], [])
            choice = choices.get(question["number"])
            question["selected_member_id"] = choice["member_id"] if choice else None
            question["chosen_by_member_id"] = choice["chosen_by_member_id"] if choice else None
            question["chosen_by_name"] = choice["chosen_by_name"] if choice else None
            question["choice_updated_at"] = choice["updated_at"] if choice else None
        return {"id": batch["id"], "question_count": batch["question_count"],
                "source_fingerprint": batch["source_fingerprint"], "created_at": batch["created_at"],
                "questions": questions}

    def _question_with_conn(self, conn: sqlite3.Connection, batch_id: str, number: int) -> sqlite3.Row:
        question = conn.execute(
            "SELECT * FROM questions WHERE batch_id = ? AND number = ?", (batch_id, number)
        ).fetchone()
        if question is None:
            raise TeamSubmissionNotFoundError(f"Khong tim thay cau {number} cua batch '{batch_id}'.")
        return question

    def upsert_answer(self, *, batch_id: str, question_number: int, member_id: str,
                      display_name: str, csv_text: str, note: str) -> dict[str, Any]:
        batch_id = batch_id.lower().strip()
        member_id = normalize_member_id(member_id)
        display_name = normalize_display_name(display_name)
        note = normalize_note(note)
        with self._lock, self._connect() as conn:
            question = self._question_with_conn(conn, batch_id, question_number)
            canonical_csv, n_events = normalize_submission_csv(
                csv_text, question["kind"], question["trake_event_count"]
            )
            if question["kind"] == "trake" and question["trake_event_count"] is None:
                conn.execute(
                    "UPDATE questions SET trake_event_count = ? WHERE batch_id = ? AND number = ?",
                    (n_events, batch_id, question_number),
                )
            now = utc_now()
            conn.execute(
                """INSERT INTO shared_answers(
                    batch_id, question_number, member_id, display_name, csv_text, note,
                    check_status, checked_by_member_id, checked_by_name, checked_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'unchecked', NULL, NULL, NULL, ?)
                ON CONFLICT(batch_id, question_number, member_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    csv_text = excluded.csv_text,
                    -- Ghi chu co the la nhan xet cua nguoi check; cap nhat CSV
                    -- khong duoc lam mat no. Tac gia van sua ghi chu truc tiep tren bang.
                    note = CASE
                        WHEN shared_answers.note = '' THEN excluded.note
                        ELSE shared_answers.note
                    END,
                    check_status = 'unchecked',
                    checked_by_member_id = NULL,
                    checked_by_name = NULL,
                    checked_at = NULL,
                    updated_at = excluded.updated_at""",
                (batch_id, question_number, member_id, display_name, canonical_csv, note, now),
            )
            row = conn.execute(
                """SELECT * FROM shared_answers WHERE batch_id = ? AND question_number = ? AND member_id = ?""",
                (batch_id, question_number, member_id),
            ).fetchone()
            return dict(row)

    def patch_answer(self, *, batch_id: str, question_number: int, member_id: str,
                     actor_member_id: str, actor_display_name: str,
                     note: str | None = None, check_status: str | None = None) -> dict[str, Any]:
        batch_id = batch_id.lower().strip()
        member_id = normalize_member_id(member_id)
        actor_member_id = normalize_member_id(actor_member_id)
        actor_display_name = normalize_display_name(actor_display_name)
        if note is not None:
            note = normalize_note(note)
        if check_status is not None and check_status not in CHECK_STATUSES:
            raise TeamSubmissionError("Trang thai kiem tra khong hop le.")
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM shared_answers WHERE batch_id = ? AND question_number = ? AND member_id = ?",
                (batch_id, question_number, member_id),
            ).fetchone()
            if row is None:
                raise TeamSubmissionNotFoundError("Khong tim thay bai chia se can cap nhat.")
            if note is None and check_status is None:
                return dict(row)
            fields: list[str] = []
            values: list[Any] = []
            if note is not None:
                fields.append("note = ?")
                values.append(note)
            if check_status is not None:
                if check_status == "unchecked":
                    fields.extend(["check_status = ?", "checked_by_member_id = NULL", "checked_by_name = NULL", "checked_at = NULL"])
                    values.append(check_status)
                else:
                    fields.extend(["check_status = ?", "checked_by_member_id = ?", "checked_by_name = ?", "checked_at = ?"])
                    values.extend([check_status, actor_member_id, actor_display_name, utc_now()])
            values.extend([batch_id, question_number, member_id])
            conn.execute(
                f"UPDATE shared_answers SET {', '.join(fields)} WHERE batch_id = ? AND question_number = ? AND member_id = ?",
                values,
            )
            return dict(conn.execute(
                "SELECT * FROM shared_answers WHERE batch_id = ? AND question_number = ? AND member_id = ?",
                (batch_id, question_number, member_id),
            ).fetchone())

    def delete_answer(self, *, batch_id: str, question_number: int, member_id: str) -> dict[str, Any]:
        """Xoa mot bai chia se; khong dong vao ban nhap local cua bat ky may nao."""
        batch_id = batch_id.lower().strip()
        member_id = normalize_member_id(member_id)
        with self._lock, self._connect() as conn:
            answer = conn.execute(
                """SELECT 1 FROM shared_answers
                   WHERE batch_id = ? AND question_number = ? AND member_id = ?""",
                (batch_id, question_number, member_id),
            ).fetchone()
            if answer is None:
                raise TeamSubmissionNotFoundError("Khong tim thay bai chia se can xoa.")
            # FK ON DELETE CASCADE tu submission_choices dam bao dap an da chon
            # khong the tro thanh mot tham chieu mo sau khi xoa bai nay.
            conn.execute(
                "DELETE FROM shared_answers WHERE batch_id = ? AND question_number = ? AND member_id = ?",
                (batch_id, question_number, member_id),
            )
            return {
                "batch_id": batch_id,
                "question_number": question_number,
                "member_id": member_id,
                "deleted": True,
            }

    def choose_answer(self, *, batch_id: str, question_number: int, member_id: str,
                      actor_member_id: str, actor_display_name: str) -> dict[str, Any]:
        batch_id = batch_id.lower().strip()
        member_id = normalize_member_id(member_id)
        actor_member_id = normalize_member_id(actor_member_id)
        actor_display_name = normalize_display_name(actor_display_name)
        with self._lock, self._connect() as conn:
            self._question_with_conn(conn, batch_id, question_number)
            answer = conn.execute(
                "SELECT 1 FROM shared_answers WHERE batch_id = ? AND question_number = ? AND member_id = ?",
                (batch_id, question_number, member_id),
            ).fetchone()
            if answer is None:
                raise TeamSubmissionNotFoundError("Thanh vien nay chua chia se dap an cho cau nay.")
            now = utc_now()
            conn.execute(
                """INSERT INTO submission_choices(batch_id, question_number, member_id, chosen_by_member_id, chosen_by_name, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(batch_id, question_number) DO UPDATE SET
                     member_id = excluded.member_id, chosen_by_member_id = excluded.chosen_by_member_id,
                     chosen_by_name = excluded.chosen_by_name, updated_at = excluded.updated_at""",
                (batch_id, question_number, member_id, actor_member_id, actor_display_name, now),
            )
            return {"question_number": question_number, "member_id": member_id, "updated_at": now}

    def clear_choice(self, *, batch_id: str, question_number: int) -> dict[str, Any]:
        """Bo dap an tong hop cua mot cau de nguoi dung chon lai."""
        batch_id = batch_id.lower().strip()
        with self._lock, self._connect() as conn:
            self._question_with_conn(conn, batch_id, question_number)
            deleted = conn.execute(
                "DELETE FROM submission_choices WHERE batch_id = ? AND question_number = ?",
                (batch_id, question_number),
            ).rowcount
            return {"question_number": question_number, "cleared": bool(deleted)}

    def backup_batch(self, batch_id: str) -> dict[str, Any]:
        return {"format": "aic-team-submission-backup", "version": 1,
                "exported_at": utc_now(), "batch": self.get_batch(batch_id)}

    def restore_batch(self, snapshot: dict[str, Any], *, replace_existing: bool = False) -> dict[str, Any]:
        if snapshot.get("format") != "aic-team-submission-backup" or snapshot.get("version") != 1:
            raise TeamSubmissionError("Backup khong dung dinh dang aic-team-submission-backup v1.")
        batch = snapshot.get("batch")
        if not isinstance(batch, dict):
            raise TeamSubmissionError("Backup khong co du lieu batch.")
        batch_id = str(batch.get("id", "")).strip().lower()
        questions = batch.get("questions")
        if not QUESTION_NAME_RE.fullmatch(f"query-{batch_id}-1-kis.txt"):
            raise TeamSubmissionError("Batch ID trong backup khong hop le.")
        if not isinstance(questions, list) or not questions:
            raise TeamSubmissionError("Backup khong co danh sach cau hoi.")
        definitions: list[dict[str, Any]] = []
        all_answers: list[dict[str, Any]] = []
        for item in questions:
            if not isinstance(item, dict):
                raise TeamSubmissionError("Cau hoi trong backup khong hop le.")
            number = item.get("number")
            filename = item.get("filename")
            kind = item.get("kind")
            description = item.get("description")
            if not isinstance(number, int) or number < 1 or not isinstance(filename, str) or not isinstance(kind, str) or not isinstance(description, str):
                raise TeamSubmissionError("Cau hoi trong backup thieu truong bat buoc.")
            expected_name = f"query-{batch_id}-{number}-{kind}.csv"
            if filename != expected_name or kind not in {"kis", "qa", "trake"} or not description.strip():
                raise TeamSubmissionError("Cau hoi trong backup khong dung cau truc batch.")
            n_events = item.get("trake_event_count")
            if n_events is not None and (not isinstance(n_events, int) or n_events < 1):
                raise TeamSubmissionError("So su kien TRAKE trong backup khong hop le.")
            definitions.append({"number": number, "filename": filename, "kind": kind,
                                "description": description.strip(), "trake_event_count": n_events})
            answers = item.get("answers", [])
            if not isinstance(answers, list):
                raise TeamSubmissionError("Danh sach bai chia se trong backup khong hop le.")
            for answer in answers:
                if not isinstance(answer, dict):
                    raise TeamSubmissionError("Bai chia se trong backup khong hop le.")
                answer = dict(answer)
                answer["question_number"] = number
                all_answers.append(answer)
        definitions.sort(key=lambda item: item["number"])
        if [item["number"] for item in definitions] != list(range(1, len(definitions) + 1)):
            raise TeamSubmissionError("Cau hoi trong backup phai lien tuc tu 1 den N.")
        if batch.get("question_count") != len(definitions):
            raise TeamSubmissionError("So luong cau hoi trong backup khong khop danh sach cau hoi.")
        created_at = batch.get("created_at")
        if created_at is not None and not isinstance(created_at, str):
            raise TeamSubmissionError("Thoi gian tao batch trong backup khong hop le.")
        answer_keys: set[tuple[int, str]] = set()
        for answer in all_answers:
            key = (answer["question_number"], normalize_member_id(str(answer.get("member_id", ""))))
            if key in answer_keys:
                raise TeamSubmissionError("Backup co hai bai cung Member ID cho mot cau hoi.")
            answer_keys.add(key)
        fingerprint = hashlib.sha256(json.dumps(definitions, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        with self._lock, self._connect() as conn:
            existing = conn.execute("SELECT 1 FROM batches WHERE id = ?", (batch_id,)).fetchone()
            if existing is not None and not replace_existing:
                raise BatchConflictError(f"Batch '{batch_id}' da ton tai. Can xac nhan restore de thay the.")
            if existing is not None:
                conn.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
            conn.execute("INSERT INTO batches(id, question_count, source_fingerprint, created_at) VALUES (?, ?, ?, ?)",
                         (batch_id, len(definitions), fingerprint, created_at or utc_now()))
            conn.executemany(
                "INSERT INTO questions(batch_id, number, filename, kind, description, trake_event_count) VALUES (?, ?, ?, ?, ?, ?)",
                [(batch_id, d["number"], d["filename"], d["kind"], d["description"], d["trake_event_count"]) for d in definitions],
            )
            by_number = {item["number"]: item for item in definitions}
            for answer in all_answers:
                number = answer["question_number"]
                question = by_number[number]
                member_id = normalize_member_id(str(answer.get("member_id", "")))
                display_name = normalize_display_name(str(answer.get("display_name", "")))
                csv_text, derived_events = normalize_submission_csv(str(answer.get("csv_text", "")), question["kind"], question["trake_event_count"])
                if question["kind"] == "trake" and question["trake_event_count"] is None:
                    question["trake_event_count"] = derived_events
                    conn.execute("UPDATE questions SET trake_event_count = ? WHERE batch_id = ? AND number = ?", (derived_events, batch_id, number))
                status = str(answer.get("check_status", "unchecked"))
                if status not in CHECK_STATUSES:
                    raise TeamSubmissionError("Trang thai review trong backup khong hop le.")
                checked_id = answer.get("checked_by_member_id")
                checked_name = answer.get("checked_by_name")
                if checked_id is not None:
                    checked_id = normalize_member_id(str(checked_id))
                if checked_name is not None:
                    checked_name = normalize_display_name(str(checked_name))
                checked_at = answer.get("checked_at")
                updated_at = answer.get("updated_at")
                if checked_at is not None and not isinstance(checked_at, str):
                    raise TeamSubmissionError("Thoi gian review trong backup khong hop le.")
                if updated_at is not None and not isinstance(updated_at, str):
                    raise TeamSubmissionError("Thoi gian cap nhat CSV trong backup khong hop le.")
                if status == "unchecked":
                    checked_id = checked_name = checked_at = None
                conn.execute(
                    """INSERT INTO shared_answers(batch_id, question_number, member_id, display_name, csv_text, note,
                       check_status, checked_by_member_id, checked_by_name, checked_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (batch_id, number, member_id, display_name, csv_text, normalize_note(str(answer.get("note", ""))),
                     status, checked_id, checked_name, checked_at, updated_at or utc_now()),
                )
            for item in questions:
                selected = item.get("selected_member_id")
                if selected is not None:
                    selected = normalize_member_id(str(selected))
                    found = conn.execute("SELECT 1 FROM shared_answers WHERE batch_id = ? AND question_number = ? AND member_id = ?",
                                         (batch_id, item["number"], selected)).fetchone()
                    if found is None:
                        raise TeamSubmissionError("Backup chon dap an khong ton tai trong cau hoi.")
                    chosen_by_id = item.get("chosen_by_member_id")
                    chosen_by_name = item.get("chosen_by_name")
                    choice_updated_at = item.get("choice_updated_at")
                    if chosen_by_id is not None:
                        chosen_by_id = normalize_member_id(str(chosen_by_id))
                    if chosen_by_name is not None:
                        chosen_by_name = normalize_display_name(str(chosen_by_name))
                    if choice_updated_at is not None and not isinstance(choice_updated_at, str):
                        raise TeamSubmissionError("Thoi gian chon dap an trong backup khong hop le.")
                    conn.execute(
                        """INSERT INTO submission_choices(
                            batch_id, question_number, member_id, chosen_by_member_id, chosen_by_name, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?)""",
                        (batch_id, item["number"], selected, chosen_by_id, chosen_by_name,
                         choice_updated_at or utc_now()),
                    )
            return self._get_batch_with_conn(conn, batch_id)

    def export_submission_zip(self, batch_id: str) -> bytes:
        with self._lock, self._connect() as conn:
            board = self._get_batch_with_conn(conn, batch_id.lower().strip())
        with tempfile.TemporaryDirectory(prefix="aic_submission_") as temp_dir:
            csv_dir = Path(temp_dir) / "csv"
            csv_dir.mkdir()
            for question in board["questions"]:
                selected = question["selected_member_id"]
                if not selected:
                    raise TeamSubmissionError(f"Cau {question['number']} chua chon dap an tong hop.")
                answer = next((item for item in question["answers"] if item["member_id"] == selected), None)
                if answer is None:
                    raise TeamSubmissionError(f"Cau {question['number']} khong con bai da chon.")
                canonical, _ = normalize_submission_csv(answer["csv_text"], question["kind"], question["trake_event_count"])
                filename = Path(question["filename"]).name
                (csv_dir / filename).write_text(canonical, encoding="utf-8", newline="\n")
            zip_path = Path(temp_dir) / "submission.zip"
            submit_core.pack(csv_dir, zip_path)
            return zip_path.read_bytes()
