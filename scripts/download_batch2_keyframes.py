"""Download AIC Batch 2 keyframes into the layout read by RTC MediaIndex.

Run from the repository root with a Python environment containing kagglehub.
KaggleHub extracts the public dataset directly under data/raw_batch2. The
existing KEYFRAME_GLOB/MAPS_GLOB already scan its nested group folders.
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import kagglehub
import requests


ROOT = Path(__file__).resolve().parents[1]
DATASET = "dngomnh/aic2026-batch2-keyframes-all/versions/1"
DEST = ROOT / "data" / "raw_batch2"
CACHE = ROOT / "data" / ".kagglehub_batch2"
CACHE_ARCHIVE = CACHE / "datasets" / "dngomnh" / "aic2026-batch2-keyframes-all" / "1.archive"
REPORT = ROOT / "artifacts" / "batch2_keyframes_verified.json"
VIDEO_NAME = re.compile(r"^[MNS]\d{2,3}_V\d{3}$")
FRAME_NAME = re.compile(r"^\d{6,}\.webp$", re.IGNORECASE)


def verify() -> dict:
    videos: dict[str, tuple[Path, int]] = {}
    maps: dict[str, Path] = {}
    image_count = image_bytes = 0

    for folder, dirs, files in os.walk(DEST):
        path = Path(folder)
        if path.parent.name == "keyframes" and VIDEO_NAME.fullmatch(path.name):
            count = 0
            for name in files:
                if not FRAME_NAME.fullmatch(name):
                    raise ValueError(f"Invalid keyframe filename: {path / name}")
                source = path / name
                if source.stat().st_size <= 0:
                    raise ValueError(f"Empty keyframe: {source}")
                count += 1
                image_bytes += source.stat().st_size
            if count == 0 or path.name in videos:
                raise ValueError(f"Missing or duplicate video folder: {path}")
            videos[path.name] = (path, count)
            image_count += count
        elif path.name == "maps":
            for name in files:
                source = path / name
                if source.suffix.lower() != ".csv" or not VIDEO_NAME.fullmatch(source.stem):
                    continue
                if source.stem in maps:
                    raise ValueError(f"Duplicate map: {source.stem}")
                maps[source.stem] = source

    if not videos or not maps or set(videos) != set(maps):
        missing_maps = sorted(set(videos) - set(maps))[:10]
        missing_images = sorted(set(maps) - set(videos))[:10]
        raise ValueError(
            f"Incomplete dataset: videos={len(videos)} maps={len(maps)} "
            f"missing_maps={missing_maps} missing_images={missing_images}"
        )

    for video, source in maps.items():
        frame_dir, _ = videos[video]
        with source.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not {"n", "frame_idx", "pts_time", "fps"}.issubset(reader.fieldnames or []):
                raise ValueError(f"Invalid map columns: {source}")
            first = next(reader, None)
            if first is None or not (frame_dir / f"{int(first['n']):06d}.webp").is_file():
                raise ValueError(f"Map has no matching first image: {source}")

    return {
        "source": DATASET,
        "directory": str(DEST),
        "videos": len(videos),
        "maps": len(maps),
        "keyframes": image_count,
        "keyframe_bytes": image_bytes,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    print(f"DOWNLOAD_START {DATASET} -> {DEST}", flush=True)
    # KaggleHub refuses a nonempty output_dir after an interrupted download.
    # Its normal cache can resume a partial archive using HTTP Range instead.
    os.environ["KAGGLEHUB_CACHE"] = str(CACHE)
    partial = DEST / "1.archive"
    if partial.exists():
        CACHE_ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
        if CACHE_ARCHIVE.exists():
            raise FileExistsError(f"Both partial archives exist: {partial} and {CACHE_ARCHIVE}")
        partial.replace(CACHE_ARCHIVE)
        print(f"RESUME_FROM_BYTES {CACHE_ARCHIVE.stat().st_size}", flush=True)
    for attempt in range(1, 21):
        try:
            downloaded = Path(kagglehub.dataset_download(DATASET)).resolve()
            break
        except (requests.exceptions.RequestException, ConnectionError, TimeoutError) as exc:
            if attempt == 20:
                raise
            delay = min(60, 5 * attempt)
            size = CACHE_ARCHIVE.stat().st_size if CACHE_ARCHIVE.exists() else 0
            print(
                f"DOWNLOAD_RETRY attempt={attempt} partial_bytes={size} "
                f"sleep_seconds={delay} error={type(exc).__name__}: {exc}",
                flush=True,
            )
            time.sleep(delay)
    expected = CACHE / "datasets" / "dngomnh" / "aic2026-batch2-keyframes-all" / "versions" / "1"
    if downloaded != expected.resolve():
        raise RuntimeError(f"Unexpected Kaggle output directory: {downloaded}")
    if DEST.exists():
        if any(DEST.iterdir()):
            raise FileExistsError(f"Destination is not empty: {DEST}")
        DEST.rmdir()
    downloaded.replace(DEST)
    print("DOWNLOAD_DONE; VERIFY_START", flush=True)
    result = verify()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("VERIFY_DONE " + json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
