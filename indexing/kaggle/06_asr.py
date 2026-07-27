"""
================================================================================
KAGGLE NOTEBOOK 06 — ASR (ChunkFormer) từ audio đã tách ở notebook 01
================================================================================
Chạy độc lập với 02/03/04/05. KHÔNG cần video/keyframe — chỉ cần audio (.opus, nhẹ)
→ nhanh. ChunkFormer (ICASSP 2025, khanhld/chunkformer-ctc-large-vie) đã CHỐT làm
model ASR (WER 8.31% cùng benchmark thắng PhoWhisper-large 8.85%, nhẹ 110M, đội vô
địch dùng — xem NGHIEN_CUU_KIEN_TRUC.md P9.2). Model tự xử lý audio DÀI (tới 16 giờ)
bằng cơ chế chunk-wise riêng — KHÔNG cần Silero VAD cắt đoạn trước.

CẤU HÌNH KAGGLE:
  - Accelerator : GPU T4 x2 (hoặc P100)
  - Internet    : ON (cài `chunkformer` từ PyPI + tải checkpoint từ HF lần đầu)
  - Add Input   : dataset keyframe gộp từ notebook 01 (VD aic-kf-batch1-all — có
                  kèm audio/ trong mỗi shard)

CHIA CHO NHIỀU ACCOUNT: chỉ cần đổi biến ACCOUNT = "1" | "2" | "3" (mỗi số ứng 1 nhóm
shard cố định — xem ACCOUNT_GROUPS bên dưới). Để trống = chạy hết 16 shard 1 account.

ĐẦU RA (/kaggle/working/asr → Save Version → Kaggle Dataset "aic-asr-batch1"):
  asr_<video>.json      list[{"s": start_sec, "e": end_sec, "t": text}] mỗi video
  asr_all.jsonl         gộp 1 dòng/video: {"video":..., "segments":[...]}
  asr_info.json         thống kê tổng
================================================================================
"""
import os, sys, json, time, glob, subprocess
from pathlib import Path

VERSION = "06-asr-chunkformer v1"
print(f">>> {VERSION}", flush=True)

# ============================ CẤU HÌNH ============================
MODEL_ID = os.environ.get("MODEL_ID", "khanhld/chunkformer-ctc-large-vie")
AUDIO_ROOT_GLOB = "/kaggle/input/**/audio"

# CHIA CHO NHIEU ACCOUNT — chi can doi 1 SO (giong 01_extract_keyframes.py):
#   ACCOUNT = "1" | "2" | "3"  -> nhom shard co dinh ben duoi (16 shard batch 1 chia lam 3)
#   ACCOUNT = ten shard cu the (VD "K01") -> chi chay 1 shard do (dung cho batch 2 sau nay)
#   De trong -> chay HET moi shard tim thay (khong chia)
ACCOUNT_GROUPS = {
    "1": ["L21_a", "L22_a", "L23_a", "L24_a", "L25_a", "L25_a1"],
    "2": ["L25_b", "L26_a", "L26_b", "L26_c", "L26_d", "L26_e"],
    "3": ["L27_a", "L28_a", "L29_a", "L30_a"],
}
ACCOUNT = os.environ.get("ACCOUNT", os.environ.get("SHARDS", "1"))  # <<< SUA O DAY: "1"/"2"/"3"
if ACCOUNT in ACCOUNT_GROUPS:
    _SHARDS_FILTER = ACCOUNT_GROUPS[ACCOUNT]
elif ACCOUNT.strip():
    _SHARDS_FILTER = [s.strip() for s in ACCOUNT.split(",") if s.strip()]  # SHARDS="L21_a,L22_a" thu cong
else:
    _SHARDS_FILTER = []  # chay het
if _SHARDS_FILTER:
    print(f"  ACCOUNT={ACCOUNT!r} --> chi xu ly {len(_SHARDS_FILTER)} shard: {_SHARDS_FILTER}", flush=True)

WORK = Path("/kaggle/working"); OUT = WORK / "asr"; OUT.mkdir(parents=True, exist_ok=True)
WAV_DIR = WORK / "wav_tmp"; WAV_DIR.mkdir(parents=True, exist_ok=True)


def sh(cmd, check=False):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and check:
        print(r.stdout[-1500:], r.stderr[-1500:], flush=True)
        raise RuntimeError(cmd)
    return r


# ==================== 1. CÀI ĐẶT + NẠP MODEL ====================
print("=" * 60, "\n[1/3] Cai dat + nap ChunkFormer\n", "=" * 60, flush=True)
sh("apt-get -qq install -y ffmpeg >/dev/null 2>&1", check=False)
sh(f"{sys.executable} -m pip install -q chunkformer")

import torch
from chunkformer import ChunkFormerModel

dev = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"  GPU: {torch.cuda.get_device_name(0) if dev.startswith('cuda') else 'KHONG CO GPU!'}", flush=True)

t0 = time.time()
model = ChunkFormerModel.from_pretrained(MODEL_ID).to(dev)
print(f"  --> nap xong {MODEL_ID} ({time.time()-t0:.1f}s)", flush=True)

# Nếu dataset input là bản GỘP (.tar từ merge_keyframe_datasets.py) → giải nén trước.
# CHỈ giải nén phần "audio/" (ASR không cần keyframes/maps) — tar gộp cả 3 thứ, nếu
# extractall() toàn bộ sẽ giải nén luôn hàng trăm nghìn ảnh keyframe không cần thiết,
# RẤT CHẬM (đã gặp thật: tưởng treo máy vì không log tiến độ, thực ra đang giải nén ảnh thừa).
_tar_files = glob.glob("/kaggle/input/**/archives/*.tar", recursive=True)
if _SHARDS_FILTER:
    _tar_files = [tf for tf in _tar_files if Path(tf).stem in _SHARDS_FILTER]
if _tar_files:
    import tarfile
    LOCAL_KF = WORK / "kf_extracted"; LOCAL_KF.mkdir(parents=True, exist_ok=True)
    print(f"  Phat hien {len(_tar_files)} file .tar can dung — giai nen CHI phan audio/...", flush=True)
    for i, tf in enumerate(_tar_files):
        t0e = time.time()
        with tarfile.open(tf) as t:
            members = [m for m in t.getmembers() if "/audio/" in m.name or m.name.endswith("/audio")]
            t.extractall(LOCAL_KF, members=members)
        print(f"  [{i+1}/{len(_tar_files)}] {Path(tf).name}: {len(members)} file audio "
              f"({time.time()-t0e:.1f}s)", flush=True)
    AUDIO_ROOT_GLOB = f"{LOCAL_KF}/**/audio"


# ==================== 2. GOM DANH SÁCH AUDIO ====================
print("=" * 60, "\n[2/3] Gom danh sach audio\n", "=" * 60, flush=True)
audio_roots = glob.glob(AUDIO_ROOT_GLOB, recursive=True)
if _SHARDS_FILTER:
    before = len(audio_roots)
    audio_roots = [a for a in audio_roots if Path(a).parent.name in _SHARDS_FILTER]
    print(f"  SHARDS filter: {_SHARDS_FILTER} -> giu {len(audio_roots)}/{before} thu muc audio", flush=True)
if not audio_roots:
    raise FileNotFoundError("Khong thay thu muc 'audio' trong /kaggle/input — nho Add dataset tu notebook 01.")

audio_files = []  # (video, path)
for aroot in audio_roots:
    for p in sorted(Path(aroot).glob("*.opus")):
        audio_files.append((p.stem, p))
print(f"  --> {len(audio_files):,} file audio se ASR", flush=True)
if not audio_files:
    raise RuntimeError("0 file audio tim thay — kiem tra dataset input.")


# ==================== 3. CHẠY ASR ====================
print("=" * 60, "\n[3/3] Chay ASR (ChunkFormer endless_decode)\n", "=" * 60, flush=True)
stats = {"videos": 0, "errors": [], "total_audio_sec": 0.0}
t0 = time.time()
all_lines = []

for vi, (video, opus_path) in enumerate(audio_files):
    try:
        # ChunkFormer doc vi du dung .wav/.mp3/... — chuyen opus -> wav truoc cho an toan
        wav_path = WAV_DIR / f"{video}.wav"
        sh(f"ffmpeg -v 0 -y -i '{opus_path}' -ac 1 -ar 16000 '{wav_path}'", check=False)
        if not wav_path.exists():
            stats["errors"].append((video, "ffmpeg convert failed")); continue

        segs = model.endless_decode(
            audio_path=str(wav_path),
            chunk_size=64, left_context_size=128, right_context_size=128,
            total_batch_duration=1800,   # giay — giam neu OOM
            return_timestamps=True,
        )
        # ChunkFormer tra ve list[{"start","end","decode"}], start/end dang CHUOI
        # "HH:MM:SS:mmm" (khong phai so giay) — xac nhan tu chinh source
        # (chunkformer/utils/model_utils.py: milliseconds_to_hhmmssms, fixed-width
        # f"{h:02}:{m:02}:{s:02}:{ms:03}"). Phai parse chuoi nay ve giay (float).
        def _ts_to_sec(ts: str) -> float:
            h, m, sec, ms = ts.split(":")
            return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000

        rows = []
        for s in segs:
            rows.append({"s": round(_ts_to_sec(s["start"]), 2),
                         "e": round(_ts_to_sec(s["end"]), 2),
                         "t": str(s.get("decode", "")).strip()})

        json.dump(rows, open(OUT / f"asr_{video}.json", "w"), ensure_ascii=False)
        all_lines.append(json.dumps({"video": video, "segments": rows}, ensure_ascii=False))
        wav_path.unlink(missing_ok=True)

        stats["videos"] += 1
        if (vi + 1) % 20 == 0 or vi == len(audio_files) - 1:
            el = (time.time() - t0) / 60
            print(f"  [{vi+1}/{len(audio_files)}] {video}: {len(rows)} doan | {el:.1f} phut", flush=True)
    except Exception as ex:
        stats["errors"].append((video, str(ex)[:150]))
        print(f"  [LOI] {video}: {ex}", flush=True)

with open(OUT / "asr_all.jsonl", "w", encoding="utf-8") as f:
    f.write("\n".join(all_lines))

stats["minutes"] = round((time.time() - t0) / 60, 1)
json.dump(stats, open(OUT / "asr_info.json", "w"), ensure_ascii=False, indent=2)
print(f"\n  Xong: {stats['videos']} video, {len(stats['errors'])} loi, {stats['minutes']} phut", flush=True)
print("\n>>> XONG. Save Version -> tao Dataset 'aic-asr-batch1' (hoac theo SHARDS neu chia account).", flush=True)
