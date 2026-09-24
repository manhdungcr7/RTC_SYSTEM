#!/usr/bin/env python3
"""Stream MP4 and MOV members from remote ZIP archives into a flat S3 bucket.

This program is intended to run on an EC2 instance with an instance profile.
It stores only one ZIP at a time on EC2. Extracted videos are streamed through
stdin to the AWS CLI and are never written as local files.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.parse
import zipfile


CHUNK_SIZE = 8 * 1024 * 1024
MIN_FREE_SPACE = 2 * 1024 * 1024 * 1024
VIDEO_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:mp4|mov)\Z", re.IGNORECASE)
ARCHIVE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.zip\Z", re.IGNORECASE)


def log(*values: object) -> None:
    print(*values, flush=True)


def read_manifest(path: pathlib.Path) -> list[tuple[str, str, int | None]]:
    sources: list[tuple[str, str, int | None]] = []
    seen: set[str] = set()
    for line_number, original in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) not in (1, 2):
            raise ValueError(f"Manifest line {line_number}: expected URL<TAB>bytes")
        url = fields[0].strip()
        parsed = urllib.parse.urlsplit(url)
        archive_name = pathlib.PurePosixPath(parsed.path).name
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError(f"Manifest line {line_number}: expected an HTTPS URL")
        if not ARCHIVE_NAME.fullmatch(archive_name):
            raise ValueError(f"Manifest line {line_number}: expected a simple ZIP filename")
        if archive_name.casefold() in seen:
            raise ValueError(f"Manifest line {line_number}: duplicate ZIP name")
        seen.add(archive_name.casefold())
        expected_bytes = int(fields[1]) if len(fields) == 2 and fields[1].strip() else None
        if expected_bytes is not None and expected_bytes <= 0:
            raise ValueError(f"Manifest line {line_number}: invalid byte count")
        sources.append((url, archive_name, expected_bytes))
    if not sources:
        raise ValueError("Manifest has no ZIP URLs")
    return sources


def aws_head(bucket: str, region: str, key: str) -> dict | None:
    command = [
        "aws", "s3api", "head-object", "--bucket", bucket,
        "--key", key, "--region", region, "--output", "json",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return json.loads(result.stdout)
    if "404" in result.stderr or "Not Found" in result.stderr:
        return None
    raise RuntimeError(f"S3 head-object failed for {key}: {result.stderr.strip()}")


def video_entries(zipped: zipfile.ZipFile, archive_name: str) -> list[tuple[zipfile.ZipInfo, str]]:
    entries: list[tuple[zipfile.ZipInfo, str]] = []
    seen: set[str] = set()
    for info in zipped.infolist():
        if info.is_dir():
            continue
        raw = info.filename.replace("\\", "/")
        path = pathlib.PurePosixPath(raw)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe ZIP path in {archive_name}: {raw}")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise ValueError(f"ZIP symlink is not allowed in {archive_name}: {raw}")
        key = path.name
        if not key.lower().endswith((".mp4", ".mov")):
            continue
        if not VIDEO_NAME.fullmatch(key):
            raise ValueError(f"Unsafe video name in {archive_name}: {key}")
        if key.casefold() in seen:
            raise ValueError(f"Duplicate video name in {archive_name}: {key}")
        seen.add(key.casefold())
        entries.append((info, key))
    if not entries:
        raise ValueError(f"No MP4 or MOV files in {archive_name}")
    return entries


def verify_zip_member(zipped: zipfile.ZipFile, info: zipfile.ZipInfo) -> None:
    # ZipExtFile validates CRC when its contents have been read to EOF.
    with zipped.open(info) as source:
        while source.read(CHUNK_SIZE):
            pass


def upload_member(
    zipped: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    key: str,
    archive_name: str,
    bucket: str,
    region: str,
) -> None:
    content_type = "video/quicktime" if key.lower().endswith(".mov") else "video/mp4"
    command = [
        "aws", "s3", "cp", "-", f"s3://{bucket}/{key}",
        "--region", region,
        "--expected-size", str(info.file_size),
        "--content-type", content_type,
        "--cache-control", "public,max-age=86400",
        "--metadata", f"source-zip={archive_name}",
        "--no-progress", "--only-show-errors",
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        assert process.stdin is not None
        with zipped.open(info) as source:
            while chunk := source.read(CHUNK_SIZE):
                process.stdin.write(chunk)
        process.stdin.close()
        code = process.wait()
        if code:
            raise RuntimeError(f"S3 upload failed for {key}, exit code {code}")
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait()
        raise


def download_archive(url: str, archive: pathlib.Path, expected_bytes: int | None) -> None:
    partial = archive.with_suffix(".zip.part")
    for attempt in range(1, 7):
        command = [
            "curl", "--fail", "--location", "--silent", "--show-error",
            "--proto", "=https", "--proto-redir", "=https",
            "--connect-timeout", "30", "--output", str(partial),
        ]
        if partial.exists() and partial.stat().st_size:
            command += ["--continue-at", "-"]
        command.append(url)
        result = subprocess.run(command, check=False)
        if result.returncode == 0:
            actual = partial.stat().st_size
            if expected_bytes is None or actual == expected_bytes:
                partial.replace(archive)
                return
            log("DOWNLOAD_SIZE_MISMATCH", actual, expected_bytes, "attempt", attempt)
            if actual > expected_bytes:
                partial.unlink()
        elif result.returncode == 33:
            # The server rejected Range. Start the next attempt from byte zero.
            partial.unlink(missing_ok=True)
            log("RANGE_NOT_SUPPORTED_RESTART", attempt)
        else:
            log("DOWNLOAD_RETRY", result.returncode, attempt)
        if attempt < 6:
            time.sleep(min(2**attempt, 30))
    raise RuntimeError(f"Could not download the complete ZIP after 6 attempts: {archive.name}")


def process_source(
    url: str,
    archive_name: str,
    expected_bytes: int | None,
    archive: pathlib.Path,
    bucket: str,
    region: str,
) -> None:
    log("SOURCE_START", archive_name)
    if expected_bytes is not None:
        free = shutil.disk_usage(archive.parent).free
        if free < expected_bytes + MIN_FREE_SPACE:
            raise RuntimeError(
                f"EC2 disk too small for {archive_name}: free={free}, ZIP={expected_bytes}"
            )
    try:
        download_archive(url, archive, expected_bytes)
        actual_bytes = archive.stat().st_size
        if expected_bytes is not None and actual_bytes != expected_bytes:
            raise RuntimeError(
                f"ZIP size mismatch for {archive_name}: {actual_bytes} != {expected_bytes}"
            )
        with zipfile.ZipFile(archive) as zipped:
            entries = video_entries(zipped, archive_name)
            log("ZIP_OK", archive_name, len(entries), sum(info.file_size for info, _ in entries))
            for info, key in entries:
                old = aws_head(bucket, region, key)
                if old is not None:
                    old_source = old.get("Metadata", {}).get("source-zip")
                    if old_source != archive_name:
                        raise RuntimeError(f"S3 video name collision: {key}")
                    if old.get("ContentLength") == info.file_size:
                        log("SKIP", key)
                        continue
                verify_zip_member(zipped, info)
                upload_member(zipped, info, key, archive_name, bucket, region)
                new = aws_head(bucket, region, key)
                if (
                    new is None
                    or new.get("ContentLength") != info.file_size
                    or new.get("Metadata", {}).get("source-zip") != archive_name
                ):
                    raise RuntimeError(f"S3 verification failed for {key}")
                log("UPLOADED", key, info.file_size)
        log("SOURCE_DONE", archive_name)
    finally:
        archive.unlink(missing_ok=True)
        archive.with_suffix(".zip.part").unlink(missing_ok=True)
        log("ZIP_REMOVED_FROM_EC2", archive_name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--work-dir", type=pathlib.Path, default=pathlib.Path("/var/lib/aic-video-ingest"))
    args = parser.parse_args()
    sources = read_manifest(args.manifest)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    archive = args.work_dir / "current.zip"
    for url, archive_name, expected_bytes in sources:
        process_source(url, archive_name, expected_bytes, archive, args.bucket, args.region)
    log("ALL_DONE", len(sources))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        log("INGEST_FAILED", type(error).__name__, str(error))
        raise
