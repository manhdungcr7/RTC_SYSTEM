"""Đổi đúng một dòng bản nháp thành một lần nộp DRES vòng chung kết."""
from __future__ import annotations

from bisect import bisect_left
from math import isfinite

from core import submit
from core.media_index import MediaIndex


class InvalidAnswer(ValueError):
    pass


def frame_time_ms(media_index: MediaIndex, video: str, frame_idx: int) -> int:
    """Ưu tiên PTS đo thật, nội suy giữa keyframe; chỉ dùng FPS ngoài khoảng map."""
    rows = sorted(media_index.full_map(video), key=lambda item: item["frame_idx"])
    if not rows:
        raise InvalidAnswer(f"Không có map thời gian cho video {video}.")
    positions = [item["frame_idx"] for item in rows]
    at = bisect_left(positions, frame_idx)
    if at < len(rows) and positions[at] == frame_idx:
        seconds = rows[at]["pts_time"]
    elif 0 < at < len(rows):
        left, right = rows[at - 1], rows[at]
        part = (frame_idx - left["frame_idx"]) / (right["frame_idx"] - left["frame_idx"])
        seconds = left["pts_time"] + part * (right["pts_time"] - left["pts_time"])
    else:
        nearest = rows[0] if at == 0 else rows[-1]
        fps = next((item["fps"] for item in rows if item.get("fps", 0) > 0), 0)
        if not fps:
            raise InvalidAnswer(f"Không có FPS để quy đổi frame {frame_idx} của {video}.")
        seconds = nearest["pts_time"] + (frame_idx - nearest["frame_idx"]) / fps
    if not isfinite(seconds) or seconds < 0:
        raise InvalidAnswer("Không quy đổi được thời gian video hợp lệ.")
    return round(seconds * 1000)


def build_answer(kind: str, row: list, n_events: int | None,
                 media_index: MediaIndex) -> dict:
    """DRES nhận đúng một answerSet và một answer cho câu hiện tại."""
    if kind not in ("kis", "qa", "trake"):
        raise InvalidAnswer("Loại truy vấn không hợp lệ.")
    if kind == "trake" and (n_events is None or n_events < 1):
        raise InvalidAnswer("TRAKE cần số sự kiện.")
    errors = submit.validate([row], kind, n_events)
    if errors:
        raise InvalidAnswer("; ".join(errors))
    video = row[0].strip()
    frame_values = row[1:2] if kind in ("kis", "qa") else row[1:]
    if any(not str(value).strip().isdigit() or int(value) < 1 for value in frame_values):
        raise InvalidAnswer("frame_idx phải là số nguyên từ 1.")
    frames = [int(value) for value in frame_values]
    if kind == "kis":
        ms = frame_time_ms(media_index, video, frames[0])
        answer = {"mediaItemName": video, "start": ms, "end": ms}
    elif kind == "qa":
        answer_text = str(row[2]).strip()
        if not answer_text:
            raise InvalidAnswer("QA cần câu trả lời.")
        ms = frame_time_ms(media_index, video, frames[0])
        answer = {"text": f"QA-{answer_text}-{video}-{ms}"}
    else:
        answer = {"text": f"TR-{video}-{','.join(map(str, frames))}"}
    return {"answerSets": [{"answers": [answer]}]}
