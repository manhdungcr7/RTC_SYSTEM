#!/usr/bin/env python3
"""Download, extract, and remove the requested video ZIP archives.

Run from the repository root:

    python scripts/download_video_archives.py

The script is safe to run again:
  - interrupted downloads resume from ``*.zip.part`` when the server supports it;
  - completed archives are tracked in ``data/videos_full/.extracted``;
  - ZIP files are deleted only after every video has been extracted successfully.

Storage layout:
  - temporary ZIP files: data/videos_full/Videos_*.zip
  - extracted videos:    data/videos_full/videos/*.mp4
"""

from __future__ import annotations

import json
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from pathlib import Path, PurePosixPath


URLS = (
    "https://aic-data.ledo.io.vn/Video_S01.zip",
    "https://aic-data.ledo.io.vn/Video_N001-N010.zip",
    "https://aic-data.ledo.io.vn/Video_N011-N020.zip",
    "https://aic-data.ledo.io.vn/Video_N021-N030.zip",
    "https://aic-data.ledo.io.vn/Video_N031-N040.zip",
    "https://aic-data.ledo.io.vn/Video_N041-N050.zip",
    "https://aic-data.ledo.io.vn/Video_N051-N060.zip",
    "https://aic-data.ledo.io.vn/Video_N061-N070.zip",
    "https://aic-data.ledo.io.vn/Video_N071-N080.zip",
    "https://aic-data.ledo.io.vn/Video_N081-N090.zip",
    "https://aic-data.ledo.io.vn/Video_N091-N100.zip",
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DIR = REPOSITORY_ROOT / "data" / "videos_full"
VIDEO_DIR = ARCHIVE_DIR / "videos"
MARKER_DIR = ARCHIVE_DIR / ".extracted"

CHUNK_SIZE = 8 * 1024 * 1024
MAX_RETRIES = 5
VIDEO_EXTENSIONS = {".mp4"}
USER_AGENT = "RTC-System-video-downloader/1.0"


def format_bytes(value: int) -> str:
    """Return a compact human-readable byte count."""
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.2f} {unit}"
        size /= 1024
    raise AssertionError("unreachable")


def marker_path(archive_name: str) -> Path:
    return MARKER_DIR / f"{archive_name}.json"


def extraction_is_complete(archive_name: str) -> bool:
    """Verify that all files recorded by a previous run still exist."""
    marker = marker_path(archive_name)
    if not marker.is_file():
        return False

    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        files = data["files"]
        if not isinstance(files, list) or not files:
            return False

        for item in files:
            video_path = VIDEO_DIR / item["name"]
            if not video_path.is_file() or video_path.stat().st_size != item["size"]:
                return False
        return True
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def print_progress(filename: str, downloaded: int, total: int | None) -> None:
    if total:
        percent = min(downloaded / total * 100, 100.0)
        message = (
            f"\r  {filename}: {format_bytes(downloaded)} / "
            f"{format_bytes(total)} ({percent:5.1f}%)"
        )
    else:
        message = f"\r  {filename}: {format_bytes(downloaded)}"
    print(message, end="", flush=True)


def download_once(url: str, archive: Path) -> None:
    """Download one archive, resuming its .part file when possible."""
    partial = archive.with_suffix(archive.suffix + ".part")

    # A process may have finished the bytes but stopped before renaming the file.
    if partial.is_file() and zipfile.is_zipfile(partial):
        partial.replace(archive)
        return

    downloaded = partial.stat().st_size if partial.is_file() else 0
    headers = {"User-Agent": USER_AGENT}
    if downloaded:
        headers["Range"] = f"bytes={downloaded}-"

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        status = response.getcode()
        content_range = response.headers.get("Content-Range", "")
        resume_accepted = (
            downloaded > 0
            and status == 206
            and content_range.startswith(f"bytes {downloaded}-")
        )

        # Some servers ignore Range. Restart instead of appending duplicate bytes.
        if downloaded and not resume_accepted:
            downloaded = 0
            mode = "wb"
        else:
            mode = "ab" if resume_accepted else "wb"

        remaining_header = response.headers.get("Content-Length")
        total = downloaded + int(remaining_header) if remaining_header else None

        with partial.open(mode) as output:
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                print_progress(archive.name, downloaded, total)

    print()
    if total is not None and downloaded != total:
        raise OSError(
            f"Kết nối kết thúc sớm: nhận {downloaded} / {total} byte"
        )
    partial.replace(archive)


def download(url: str, archive: Path) -> None:
    """Download with retries while preserving partial data between attempts."""
    if archive.is_file():
        if zipfile.is_zipfile(archive):
            print("  ZIP đã tồn tại, bỏ qua bước tải.")
            return
        print("  ZIP hiện có không hợp lệ, tải lại.")
        archive.unlink()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            download_once(url, archive)
            return
        except (OSError, urllib.error.URLError) as error:
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"Tải thất bại sau {MAX_RETRIES} lần: {error}"
                ) from error
            delay = min(2 ** attempt, 30)
            print(
                f"\n  Lỗi tải lần {attempt}/{MAX_RETRIES}: {error}. "
                f"Thử lại sau {delay} giây..."
            )
            time.sleep(delay)


def video_members(zipped: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """Select video members and reject unsafe or ambiguous member names."""
    selected: list[zipfile.ZipInfo] = []
    output_names: set[str] = set()

    for member in zipped.infolist():
        if member.is_dir():
            continue

        member_path = PurePosixPath(member.filename.replace("\\", "/"))
        if member_path.is_absolute() or ".." in member_path.parts:
            raise ValueError(f"Đường dẫn không an toàn trong ZIP: {member.filename}")

        output_name = member_path.name
        if Path(output_name).suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        if output_name.lower() in output_names:
            raise ValueError(f"Tên video bị trùng trong ZIP: {output_name}")

        output_names.add(output_name.lower())
        selected.append(member)

    if not selected:
        raise ValueError("ZIP không chứa file MP4 nào")
    return selected


def file_crc32(path: Path) -> int:
    """Calculate the ZIP-compatible CRC32 of an existing file."""
    checksum = 0
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            checksum = zlib.crc32(chunk, checksum)
    return checksum & 0xFFFFFFFF


def extract_videos(archive: Path) -> list[dict[str, int | str]]:
    """Extract MP4 files flat into VIDEO_DIR and verify their ZIP CRC values."""
    extracted: list[dict[str, int | str]] = []

    with zipfile.ZipFile(archive) as zipped:
        members = video_members(zipped)
        print(f"  Tìm thấy {len(members)} video trong ZIP.")

        for index, member in enumerate(members, start=1):
            output_name = PurePosixPath(member.filename.replace("\\", "/")).name
            destination = VIDEO_DIR / output_name
            temporary = destination.with_suffix(destination.suffix + ".extracting")

            destination_is_valid = (
                destination.is_file()
                and destination.stat().st_size == member.file_size
                and file_crc32(destination) == member.CRC
            )
            if destination_is_valid:
                print(f"  [{index}/{len(members)}] Đã có: {output_name}")
            else:
                print(f"  [{index}/{len(members)}] Giải nén: {output_name}")
                try:
                    with zipped.open(member) as source, temporary.open("wb") as target:
                        # Reading to EOF makes zipfile verify the member's CRC.
                        shutil.copyfileobj(source, target, length=CHUNK_SIZE)

                    if temporary.stat().st_size != member.file_size:
                        raise OSError(
                            f"Sai kích thước {output_name}: "
                            f"{temporary.stat().st_size} != {member.file_size}"
                        )
                    temporary.replace(destination)
                except Exception:
                    temporary.unlink(missing_ok=True)
                    raise

            extracted.append({"name": output_name, "size": member.file_size})

    return extracted


def write_completion_marker(
    archive_name: str, extracted: list[dict[str, int | str]]
) -> None:
    marker = marker_path(archive_name)
    temporary = marker.with_suffix(marker.suffix + ".tmp")
    payload = {"archive": archive_name, "files": extracted}
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(marker)


def process_archive(index: int, total: int, url: str) -> None:
    archive_name = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name
    archive = ARCHIVE_DIR / archive_name

    print(f"\n[{index}/{total}] {archive_name}")
    if extraction_is_complete(archive_name):
        # Clean up a leftover archive from an interrupted finalization step.
        archive.unlink(missing_ok=True)
        print("  Đã giải nén đầy đủ ở lần chạy trước, bỏ qua.")
        return

    print("  Đang tải...")
    download(url, archive)

    print("  Đang giải nén vào thư mục videos...")
    extracted = extract_videos(archive)

    # The archive is removed only after all members were read and verified.
    write_completion_marker(archive_name, extracted)
    archive.unlink()
    print("  Giải nén thành công; đã xóa file ZIP.")


def main() -> int:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    MARKER_DIR.mkdir(parents=True, exist_ok=True)

    failures: list[tuple[str, str]] = []
    total = len(URLS)

    for index, url in enumerate(URLS, start=1):
        try:
            process_archive(index, total, url)
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
            archive_name = Path(
                urllib.parse.unquote(urllib.parse.urlparse(url).path)
            ).name
            failures.append((archive_name, str(error)))
            print(f"  LỖI: {error}", file=sys.stderr)
            print("  Giữ lại dữ liệu tải dở/ZIP để có thể tiếp tục khi chạy lại.")

    print("\n" + "=" * 72)
    print(f"Thư mục video: {VIDEO_DIR}")
    if failures:
        print(f"Có {len(failures)} archive chưa hoàn thành:", file=sys.stderr)
        for archive_name, error in failures:
            print(f"  - {archive_name}: {error}", file=sys.stderr)
        return 1

    print(f"Hoàn tất {total}/{total} archive. Tất cả ZIP đã được xóa.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
