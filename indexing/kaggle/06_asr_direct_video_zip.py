"""Kaggle notebook: run Vietnamese ChunkFormer ASR directly on remote video ZIPs.

The remote server must support HTTP Range requests.  Only one ZIP member is
downloaded/extracted at a time, so the whole archive does not occupy Kaggle's
working disk.

Kaggle settings:
  - Accelerator: one GPU (T4/P100 or better)
  - Internet: ON

Edit SOURCE_INDEX, START and END before running.  Split a large archive across
multiple committed notebook versions by using non-overlapping [START, END)
ranges.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import nullcontext
from pathlib import Path, PurePosixPath


URLS = [
    "https://aic-data.ledo.io.vn/Video_S01.zip",
]

# Values can be edited here or supplied as environment variables. Environment
# variables make it easy to launch one worker per Kaggle GPU.
SOURCE_INDEX = int(os.environ.get("SOURCE_INDEX", "1"))
START = int(os.environ.get("START", "0"))
_end = os.environ.get("END", "").strip()
END = int(_end) if _end else None
JOB_NAME = os.environ.get("JOB_NAME", f"source{SOURCE_INDEX}_{START}_{END or 'end'}")
TOTAL_BATCH_DURATION = int(os.environ.get("TOTAL_BATCH_DURATION", "1800"))
USE_FP16 = os.environ.get("USE_FP16", "1") == "1"
INSTALL_DEPS = os.environ.get("INSTALL_DEPS", "1") == "1"
WORKER_INDEX = int(os.environ.get("WORKER_INDEX", "0"))
WORKER_COUNT = int(os.environ.get("WORKER_COUNT", "1"))
# --------------------------------------------------------------------

if WORKER_COUNT < 1 or not 0 <= WORKER_INDEX < WORKER_COUNT:
    raise ValueError("Require WORKER_COUNT >= 1 and 0 <= WORKER_INDEX < WORKER_COUNT")

MODEL_ID = "khanhld/chunkformer-ctc-large-vie"
WORK = Path("/kaggle/working")
OUT = WORK / "asr" / JOB_NAME
TMP = WORK / "asr_tmp" / JOB_NAME
OUT.mkdir(parents=True, exist_ok=True)
TMP.mkdir(parents=True, exist_ok=True)


def run(command: list[str]) -> None:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:] or "Command failed")


def timestamp_to_seconds(value: str) -> float:
    hours, minutes, seconds, milliseconds = value.split(":")
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(milliseconds) / 1000
    )


print("[1/4] Installing dependencies", flush=True)
if INSTALL_DEPS:
    subprocess.run(
        ["apt-get", "-qq", "install", "-y", "ffmpeg"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    run([sys.executable, "-m", "pip", "install", "-q", "chunkformer", "remotezip"])
else:
    print("Dependency installation skipped by INSTALL_DEPS=0", flush=True)

import torch
from chunkformer import ChunkFormerModel
from remotezip import RemoteZip


device = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"[2/4] Loading {MODEL_ID} on {device}", flush=True)
model = ChunkFormerModel.from_pretrained(MODEL_ID).to(device)
model.eval()

url = URLS[SOURCE_INDEX]
source_tag = PurePosixPath(url).stem.removeprefix("Video_")
stats = {
    "url": url,
    "source": source_tag,
    "start": START,
    "end": END,
    "job_name": JOB_NAME,
    "total_batch_duration": TOTAL_BATCH_DURATION,
    "fp16": USE_FP16 and device.startswith("cuda"),
    "worker_index": WORKER_INDEX,
    "worker_count": WORKER_COUNT,
    "videos": 0,
    "errors": [],
}

print(f"[3/4] Reading remote ZIP directory: {url}", flush=True)
with RemoteZip(url) as archive:
    members = sorted([
        info
        for info in archive.infolist()
        if not info.is_dir()
        and PurePosixPath(info.filename).suffix.lower()
        in {".mp4", ".mkv", ".avi", ".mov", ".webm"}
    ], key=lambda info: info.filename)
    if WORKER_COUNT > 1:
        # Greedy size-balanced partition. File size is a useful proxy for video
        # duration and balances large S01 videos much better than round-robin.
        bins = [[] for _ in range(WORKER_COUNT)]
        bin_sizes = [0] * WORKER_COUNT
        for info in sorted(members, key=lambda item: (-item.file_size, item.filename)):
            destination = min(range(WORKER_COUNT), key=lambda index: bin_sizes[index])
            bins[destination].append(info)
            bin_sizes[destination] += info.file_size
        selected = sorted(bins[WORKER_INDEX], key=lambda info: info.filename)
        print(
            f"Found {len(members)} videos; worker {WORKER_INDEX}/{WORKER_COUNT} "
            f"gets {len(selected)} videos ({bin_sizes[WORKER_INDEX] / 1e9:.2f} GB)",
            flush=True,
        )
    else:
        selected = members[START:END]
        print(
            f"Found {len(members)} videos; processing [{START}:{END}] "
            f"({len(selected)} videos)",
            flush=True,
        )
    if not selected:
        raise RuntimeError("The selected range contains no videos")

    # Fail early rather than silently overwrite outputs for duplicate stems.
    stems = [PurePosixPath(info.filename).stem for info in selected]
    if len(stems) != len(set(stems)):
        raise RuntimeError("Duplicate video stems found in the selected ZIP range")

    started = time.time()
    for position, info in enumerate(selected, start=1):
        member_path = PurePosixPath(info.filename)
        video = member_path.stem
        output_path = OUT / f"asr_{video}.json"
        if output_path.exists():
            print(f"[{position}/{len(selected)}] skip {video} (already done)", flush=True)
            continue

        suffix = member_path.suffix.lower()
        token = hashlib.sha1(info.filename.encode("utf-8")).hexdigest()[:10]
        video_path = TMP / f"{token}{suffix}"
        wav_path = TMP / f"{token}.wav"

        try:
            print(f"[{position}/{len(selected)}] download {info.filename}", flush=True)
            with archive.open(info.filename) as source, video_path.open("wb") as target:
                shutil.copyfileobj(source, target, length=8 * 1024 * 1024)

            run([
                "ffmpeg", "-v", "error", "-y", "-i", str(video_path),
                "-vn", "-ac", "1", "-ar", "16000", str(wav_path),
            ])

            amp = (
                torch.autocast(device_type="cuda", dtype=torch.float16)
                if USE_FP16 and device.startswith("cuda")
                else nullcontext()
            )
            with amp:
                segments = model.endless_decode(
                    audio_path=str(wav_path),
                    chunk_size=64,
                    left_context_size=128,
                    right_context_size=128,
                    total_batch_duration=TOTAL_BATCH_DURATION,
                    return_timestamps=True,
                )
            rows = [
                {
                    "s": round(timestamp_to_seconds(segment["start"]), 2),
                    "e": round(timestamp_to_seconds(segment["end"]), 2),
                    "t": str(segment.get("decode", "")).strip(),
                }
                for segment in segments
            ]
            with output_path.open("w", encoding="utf-8") as handle:
                json.dump(rows, handle, ensure_ascii=False)
            stats["videos"] += 1
        except Exception as error:
            stats["errors"].append({"video": video, "error": str(error)[:500]})
            print(f"ERROR {video}: {error}", flush=True)
        finally:
            video_path.unlink(missing_ok=True)
            wav_path.unlink(missing_ok=True)

        stats["minutes"] = round((time.time() - started) / 60, 1)
        with (OUT / "asr_info.json").open("w", encoding="utf-8") as handle:
            json.dump(stats, handle, ensure_ascii=False, indent=2)

print("[4/4] Building asr_all.jsonl", flush=True)
with (OUT / "asr_all.jsonl").open("w", encoding="utf-8") as combined:
    for output_path in sorted(OUT.glob("asr_*.json")):
        if output_path.name == "asr_info.json":
            continue
        video = output_path.stem.removeprefix("asr_")
        with output_path.open("r", encoding="utf-8") as handle:
            segments = json.load(handle)
        combined.write(
            json.dumps({"video": video, "segments": segments}, ensure_ascii=False) + "\n"
        )

print(
    f"Done: {stats['videos']} videos, {len(stats['errors'])} errors. "
    f"Output: {OUT}",
    flush=True,
)
