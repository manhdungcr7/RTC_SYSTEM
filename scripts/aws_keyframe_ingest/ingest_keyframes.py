"""Download public Kaggle keyframe datasets on EC2 and upload normalized S3 keys.

No dataset is downloaded to the user's PC. Each Kaggle bundle is removed from
the instance after its objects have been uploaded; the instance terminates via
the launcher user data. Re-running is safe: equal-sized existing keys are skipped.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
import re
import shutil
import sys
import time
from contextlib import redirect_stderr
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import boto3
import kagglehub
import requests
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


VIDEO = re.compile(r"^[A-Za-z0-9_-]+$")
IMAGE = re.compile(r"^[0-9]{6,}\.webp$", re.IGNORECASE)
TYPES = {"keyframes": "image/webp", "maps": "text/csv; charset=utf-8", "audio": "audio/ogg"}


def s3_key(path: Path) -> tuple[str, str] | None:
    parent = path.parent
    kind = parent.parent.name if path.suffix.lower() == ".webp" else parent.name
    if kind == "keyframes":
        video = parent.name
        if not VIDEO.fullmatch(video) or not IMAGE.fullmatch(path.name):
            raise ValueError(f"Invalid keyframe path: {path}")
        return f"keyframes/{video}/{path.name}", TYPES[kind]
    if kind in ("maps", "audio"):
        ext = ".csv" if kind == "maps" else ".opus"
        if path.suffix.lower() != ext or not VIDEO.fullmatch(path.stem):
            raise ValueError(f"Invalid {kind} path: {path}")
        return f"{kind}/{path.name}", TYPES[kind]
    return None


def listed_sizes(client, bucket: str) -> dict[str, int]:
    sizes: dict[str, int] = {}
    pages = client.get_paginator("list_objects_v2")
    for prefix in ("keyframes/", "maps/", "audio/"):
        for page in pages.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                sizes[obj["Key"]] = obj["Size"]
    print(f"EXISTING_OBJECTS {len(sizes)}", flush=True)
    return sizes


def put_file(client, bucket: str, path: Path, key: str, content_type: str) -> tuple[str, int]:
    content = path.read_bytes()
    checksum = base64.b64encode(hashlib.md5(content).digest()).decode("ascii")
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        ContentLength=len(content),
        ContentMD5=checksum,
        ContentType=content_type,
        CacheControl="public, max-age=31536000, immutable",
    )
    return key, len(content)


def upload_dataset(client, bucket: str, root: Path, known: dict[str, int], workers: int) -> None:
    scheduled: dict[str, int] = {}
    pending = set()
    uploaded = skipped = image_count = map_count = audio_count = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for folder, _, files in os.walk(root):
            for filename in files:
                path = Path(folder) / filename
                normalized = s3_key(path)
                if normalized is None:
                    continue
                key, content_type = normalized
                size = path.stat().st_size
                if size <= 0:
                    raise ValueError(f"Empty source file: {path}")
                if key.startswith("keyframes/"):
                    image_count += 1
                elif key.startswith("maps/"):
                    map_count += 1
                else:
                    audio_count += 1
                old = known.get(key, scheduled.get(key))
                if old is not None:
                    if old != size:
                        raise ValueError(f"S3 key collision with different size: {key} ({old} != {size})")
                    skipped += 1
                    continue
                scheduled[key] = size
                pending.add(pool.submit(put_file, client, bucket, path, key, content_type))
                if len(pending) >= workers * 8:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for task in done:
                        uploaded_key, uploaded_size = task.result()
                        known[uploaded_key] = uploaded_size
                        uploaded += 1
                        if uploaded % 10000 == 0:
                            print(f"UPLOADED {uploaded} source_objects", flush=True)
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for task in done:
                uploaded_key, uploaded_size = task.result()
                known[uploaded_key] = uploaded_size
                uploaded += 1
                if uploaded % 10000 == 0:
                    print(f"UPLOADED {uploaded} source_objects", flush=True)
    if image_count == 0 or map_count == 0:
        raise ValueError(f"Dataset lacks keyframes/maps: images={image_count} maps={map_count}")
    print(
        f"SOURCE_DONE images={image_count} maps={map_count} audio={audio_count} "
        f"uploaded={uploaded} skipped={skipped}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 64:
        raise ValueError("workers must be between 1 and 64")
    handles = [line.strip() for line in args.manifest.read_text().splitlines() if line.strip() and not line.startswith("#")]
    if not handles or any(not re.fullmatch(r"[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+/versions/[0-9]+", h) for h in handles):
        raise ValueError("Manifest must contain version-pinned Kaggle dataset handles")
    client = boto3.client(
        "s3", region_name=args.region,
        config=Config(max_pool_connections=args.workers + 8, retries={"max_attempts": 10, "mode": "adaptive"}),
    )
    # CloudShell launcher validates the bucket region before creating EC2.
    # The existing instance role deliberately has only ListBucket/Get/Put;
    # GetBucketLocation would require expanding that role.
    known = listed_sizes(client, args.bucket)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    for i, handle in enumerate(handles, 1):
        target = args.work_dir / f"source_{i:02d}"
        if target.exists():
            raise FileExistsError(f"Temporary directory is not empty: {target}")
        print(f"SOURCE_START {i}/{len(handles)} {handle}", flush=True)
        try:
            for attempt in range(1, 6):
                try:
                    # tqdm fills EC2's small console buffer with progress lines.
                    # The exception is still logged by cloud-init if all retries fail.
                    with open(os.devnull, "w") as sink, redirect_stderr(sink):
                        downloaded = Path(kagglehub.dataset_download(handle, output_dir=str(target)))
                    break
                except (requests.exceptions.RequestException, ConnectionError, TimeoutError) as exc:
                    if target.exists():
                        shutil.rmtree(target)
                    if attempt == 5:
                        raise
                    delay = min(60, attempt * 10)
                    print(f"KAGGLE_RETRY {i}/{len(handles)} attempt={attempt} "
                          f"delay={delay} error={type(exc).__name__}: {exc}", flush=True)
                    time.sleep(delay)
            if downloaded != target:
                raise ValueError(f"Unexpected Kaggle output path: {downloaded}")
            print(f"KAGGLE_OK {i}/{len(handles)}", flush=True)
            for attempt in range(1, 6):
                try:
                    upload_dataset(client, args.bucket, target, known, args.workers)
                    break
                except (BotoCoreError, ClientError, OSError) as exc:
                    if attempt == 5:
                        raise
                    delay = min(60, attempt * 10)
                    print(f"UPLOAD_RETRY {i}/{len(handles)} attempt={attempt} "
                          f"delay={delay} error={type(exc).__name__}: {exc}", flush=True)
                    known = listed_sizes(client, args.bucket)
                    time.sleep(delay)
        finally:
            if target.exists():
                shutil.rmtree(target)
            print(f"TEMP_REMOVED {i}/{len(handles)}", flush=True)
    print(f"ALL_DONE datasets={len(handles)} known_objects={len(known)}", flush=True)


if __name__ == "__main__":
    main()
