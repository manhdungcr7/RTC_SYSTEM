"""Xuất kết quả ra CSV + đóng gói zip đúng chuẩn Codabench. Port NGUYÊN 1:1 từ
`system/aic/submit.py` (đã đúng chuẩn, không đổi logic — chỉ đổi nguồn config).

Chuẩn (theo quy chế BTC):
  - File .csv thuần, UTF-8, phân cách bằng dấu phẩy, KHÔNG header.
  - Tối đa 100 dòng / truy vấn.
  - Tên file kết quả trùng tên file truy vấn: query-p1-1-kis.txt -> query-p1-1-kis.csv
  - Tên video KHÔNG có đuôi .mp4; frame_idx là số nguyên.
  - QA: answer <= 100 ký tự; bọc ngoặc kép khi chứa dấu phẩy/ngoặc kép/xuống dòng.
  - Zip phải chứa thư mục `submission/`, không nén trực tiếp các .csv.
"""
from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

from core import config as C


def rows_kis(hits, limit: int = C.MAX_SUBMIT_ROWS) -> list[list]:
    return [[h.video, int(h.frame_idx)] for h in hits[:limit]]


def rows_qa(hits, answers, limit: int = C.MAX_SUBMIT_ROWS) -> list[list]:
    """answers: list song song với hits (1 đáp án / hit)."""
    out = []
    for h, a in zip(hits[:limit], answers[:limit]):
        a = str(a)[:C.MAX_ANSWER_LEN]
        out.append([h.video, int(h.frame_idx), a])
    return out


def rows_trake(candidates, limit: int = C.MAX_SUBMIT_ROWS) -> list[list]:
    """candidates: list các chuỗi Hit (mỗi chuỗi = 1 ứng viên gồm N sự kiện)."""
    out = []
    for hits in candidates[:limit]:
        out.append([hits[0].video] + [int(h.frame_idx) for h in hits])
    return out


def write_csv(path: Path, rows: list[list]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)


def to_csv_text(rows: list[list]) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue()


def validate(rows: list[list], kind: str, n_events: int | None = None) -> list[str]:
    """Trả về danh sách lỗi ('' rỗng = hợp lệ). Chạy TRƯỚC khi nộp."""
    errs = []
    if len(rows) == 0:
        errs.append("không có dòng nào")
    if len(rows) > C.MAX_SUBMIT_ROWS:
        errs.append(f"{len(rows)} dòng > tối đa {C.MAX_SUBMIT_ROWS}")

    for i, r in enumerate(rows, 1):
        if not r or not isinstance(r[0], str) or not r[0].strip():
            errs.append(f"dòng {i}: thiếu tên video")
            continue
        if r[0].endswith(".mp4"):
            errs.append(f"dòng {i}: tên video còn đuôi .mp4")

        if kind == "kis":
            if len(r) != 2:
                errs.append(f"dòng {i}: KIS cần đúng 2 cột, có {len(r)}")
        elif kind == "qa":
            if len(r) != 3:
                errs.append(f"dòng {i}: QA cần đúng 3 cột, có {len(r)}")
            elif len(str(r[2])) > C.MAX_ANSWER_LEN:
                errs.append(f"dòng {i}: answer dài {len(str(r[2]))} > {C.MAX_ANSWER_LEN}")
        elif kind == "trake":
            if n_events and len(r) != n_events + 1:
                errs.append(f"dòng {i}: TRAKE cần {n_events} frame, có {len(r)-1}")
            frames = r[1:]
            if any(int(a) > int(b) for a, b in zip(frames, frames[1:])):
                errs.append(f"dòng {i}: frame không tăng dần theo thời gian")

        idx_cols = r[1:2] if kind in ("kis", "qa") else r[1:]
        for c in idx_cols:
            if not isinstance(c, (int,)) and not str(c).strip().isdigit():
                errs.append(f"dòng {i}: frame_idx '{c}' không phải số nguyên")
    return errs


def pack(csv_dir: Path, zip_path: Path):
    """Nén thư mục chứa .csv thành zip có cấu trúc submission/<file>.csv."""
    csvs = sorted(Path(csv_dir).glob("*.csv"))
    if not csvs:
        raise FileNotFoundError(f"không có .csv nào trong {csv_dir}")
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in csvs:
            z.write(f, arcname=f"submission/{f.name}")
    return zip_path, len(csvs)
