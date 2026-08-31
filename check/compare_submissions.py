"""So sanh bai nop AIC trong ZIP theo nguong key-frame alpha.

Vi du:
  python check/compare_submissions.py --me check/me/me.zip --targets check/target --alpha 50

Moi ZIP duoc giai nen an toan vao thu muc tam. Ket qua viet ra <out>/comparison.md
va <out>/comparison.csv; mac dinh la check/output.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Answer:
    video: str
    frames: tuple[int, ...]
    answer: str = ""


def extract_zip(zip_path: Path, destination: Path) -> None:
    """Giai nen ZIP, chan duong dan thoat ra ngoai destination (Zip Slip)."""
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            output = (destination / member.filename).resolve()
            if not output.is_relative_to(destination.resolve()):
                raise ValueError(f"ZIP co duong dan khong an toan: {member.filename}")
        archive.extractall(destination)


def kind_from_name(name: str) -> str | None:
    match = re.search(r"-(kis|qa|trake)\.csv$", name.lower())
    return match.group(1) if match else None


def parse_csv(path: Path, kind: str) -> list[Answer]:
    answers: list[Answer] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for line_no, row in enumerate(csv.reader(handle), start=1):
            row = [cell.strip() for cell in row]
            if not row or not any(row):
                continue
            min_columns = 3 if kind == "qa" else 2
            if len(row) < min_columns:
                raise ValueError(f"{path.name}: dong {line_no} khong du cot cho {kind.upper()}")
            try:
                frames = tuple(int(value) for value in (row[1:-1] if kind == "qa" else row[1:]))
            except ValueError as error:
                raise ValueError(f"{path.name}: dong {line_no} co frame khong hop le") from error
            if not frames:
                raise ValueError(f"{path.name}: dong {line_no} khong co frame")
            answers.append(Answer(video=row[0], frames=frames, answer=row[-1] if kind == "qa" else ""))
    return answers


def load_submission(extracted: Path) -> dict[str, tuple[str, list[Answer]]]:
    result: dict[str, tuple[str, list[Answer]]] = {}
    for file in extracted.rglob("*.csv"):
        kind = kind_from_name(file.name)
        if kind:
            result[file.name] = (kind, parse_csv(file, kind))
    return result


def render_answers(items: list[Answer]) -> str:
    if not items:
        return "—"
    return " ; ".join(
        f"{item.video}|{','.join(map(str, item.frames))}" + (f"|{item.answer}" if item.answer else "")
        for item in items
    )


def render_closest_answers(mine: list[Answer], other: list[Answer]) -> str:
    """Hien thi mot ung vien gan nhat, tranh lam vo bang voi KIS 100 dong."""
    if not other:
        return "—"
    comparable = [
        (sum(abs(a - b) for a, b in zip(my.frames, candidate.frames)), candidate)
        for my in mine for candidate in other
        if my.video == candidate.video and len(my.frames) == len(candidate.frames)
    ]
    selected = min(comparable, key=lambda item: item[0])[1] if comparable else other[0]
    text = render_answers([selected])
    if len(other) > 1:
        text += f" (+{len(other) - 1} ung vien)"
    return text


def compare_pair(kind: str, mine: Answer, other: Answer, alpha: int) -> tuple[bool, str, str]:
    """Tra ve (dung, lech_video, lech_frame). QA phai trung answer sau strip/casefold."""
    if mine.video != other.video:
        return False, "KHAC", "—"
    if len(mine.frames) != len(other.frames):
        return False, "TRUNG", f"SO_FRAME {len(mine.frames)} != {len(other.frames)}"
    deltas = tuple(abs(a - b) for a, b in zip(mine.frames, other.frames))
    frame_text = ", ".join(map(str, deltas))
    frames_ok = all(delta <= alpha for delta in deltas)
    # QA can only be called correct when its textual answer is exactly identical
    # after trimming accidental whitespace; case/accent differences are retained.
    answer_ok = kind != "qa" or mine.answer.strip() == other.answer.strip()
    if kind == "qa" and not answer_ok:
        frame_text += " | DAP_AN_KHAC"
    return frames_ok and answer_ok, "TRUNG", frame_text


def compare_file(kind: str, mine: list[Answer], other: list[Answer], alpha: int) -> tuple[str, str, str]:
    """Tim moi cap trung video. KIS/QA dung neu co it nhat mot cap dung.

    TRAKE thuong chi co mot dong; quy tac van ap dung tren tung dong va tat ca event
    trong dong phai nam trong alpha.
    """
    if not mine:
        return "THIEU_BAI_TOI", "—", "—"
    if not other:
        return "THIEU_BAI_NHOM", "—", "—"
    checks = [compare_pair(kind, a, b, alpha) for a in mine for b in other]
    exact = [check for check in checks if check[0]]
    same_video = [check for check in checks if check[1] == "TRUNG"]
    if exact:
        _, video, delta = exact[0]
        return "DUNG", video, delta
    if same_video:
        _, video, delta = min(same_video, key=lambda item: sum(int(x) for x in re.findall(r"\d+", item[2])))
        return "SAI_FRAME_HOAC_DAP_AN", video, delta
    return "SAI_VIDEO", "KHAC", "—"


def correct_ranks(kind: str, mine: list[Answer], other: list[Answer], alpha: int) -> str:
    """Vi tri (top) cua moi dong bai nhom thoa dieu kien dung.

    ZIP giu nguyen thu tu CSV, nen dong dau tien la Top 1. Chi hien toi da 20 top
    de bang Markdown van doc duoc; phan con lai duoc dem ro rang.
    """
    matches: list[str] = []
    for rank, candidate in enumerate(other, start=1):
        valid = [compare_pair(kind, answer, candidate, alpha) for answer in mine]
        exact = [item for item in valid if item[0]]
        if exact:
            matches.append(f"Top {rank} (Δ {exact[0][2]})")
    if not matches:
        return "—"
    shown = matches[:20]
    if len(matches) > len(shown):
        shown.append(f"+{len(matches) - len(shown)} top khac")
    return ", ".join(shown)


def markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def main() -> int:
    parser = argparse.ArgumentParser(description="So sanh ZIP bai nop AIC")
    parser.add_argument("--me", type=Path, required=True, help="ZIP bai cua toi")
    parser.add_argument("--targets", type=Path, required=True, help="Thu muc chua ZIP bai nhom khac")
    parser.add_argument("--alpha", type=int, default=50, help="Lech frame toi da de coi la dung (mac dinh: 50)")
    parser.add_argument("--out", type=Path, default=Path("check/output"), help="Thu muc xuat ket qua")
    args = parser.parse_args()
    if args.alpha < 0:
        parser.error("--alpha phai >= 0")
    if not args.me.is_file() or args.me.suffix.lower() != ".zip":
        parser.error("--me phai la mot file .zip")
    targets = sorted(path for path in args.targets.glob("*.zip") if path.resolve() != args.me.resolve())
    if not targets:
        parser.error("Khong tim thay ZIP nao trong --targets")

    args.out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="aic_compare_") as temp:
        root = Path(temp)
        my_dir = root / "me"
        my_dir.mkdir()
        extract_zip(args.me, my_dir)
        mine = load_submission(my_dir)

        for target_zip in targets:
            target_dir = root / target_zip.stem
            target_dir.mkdir()
            extract_zip(target_zip, target_dir)
            target = load_submission(target_dir)
            for filename in sorted(set(mine) | set(target)):
                my_kind, my_answers = mine.get(filename, (kind_from_name(filename) or "?", []))
                target_kind, target_answers = target.get(filename, (my_kind, []))
                if my_kind != target_kind:
                    status, video_diff, frame_diff = "KHAC_LOAI_CAU", "—", "—"
                else:
                    status, video_diff, frame_diff = compare_file(my_kind, my_answers, target_answers, args.alpha)
                rows.append({
                    "target": target_zip.name, "question": filename, "kind": my_kind.upper(),
                    "bai_toi": render_answers(my_answers),
                    "bai_nhom": render_closest_answers(my_answers, target_answers),
                    "video": video_diff, "lech_keyframe": frame_diff,
                    "top_dung": correct_ranks(my_kind, my_answers, target_answers, args.alpha),
                    "ket_qua": status,
                })

    csv_path = args.out / "comparison.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)

    md_path = args.out / "comparison.md"
    lines = [f"# So sanh bai nop (alpha = {args.alpha} frame)", ""]
    for target in sorted({row["target"] for row in rows}):
        lines += [f"## So voi {target}", "",
                  "`Bai nhom` chi hien thi ung vien gan nhat; phan trong ngoac la so ung vien con lai.", "",
                  "| Cau hoi | Loai | Bai toi | Bai nhom (gan nhat) | Video | Lech key frame | Top dung | Ket qua |",
                  "|---|---|---|---|---|---|---|---|"]
        for row in (item for item in rows if item["target"] == target):
            lines.append("| " + " | ".join(markdown_cell(row[key]) for key in
                         ("question", "kind", "bai_toi", "bai_nhom", "video", "lech_keyframe", "top_dung", "ket_qua")) + " |")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["ket_qua"]] = counts.get(row["ket_qua"], 0) + 1
    print(f"Da so sanh {len(rows)} cap cau hoi, alpha={args.alpha}.")
    print(" · ".join(f"{key}: {value}" for key, value in sorted(counts.items())))
    print(f"Bang Markdown: {md_path}")
    print(f"Bang CSV     : {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
