"""
================================================================================
KAGGLE NOTEBOOK 01 — TRÍCH KEYFRAME (TransNetV2) + TÁCH AUDIO
================================================================================
Copy TOÀN BỘ file này vào 1 cell Kaggle Notebook rồi Run. Đây là bước NỀN TẢNG —
mọi bước sau (embed, OCR, caption, ASR) đều dùng lại output của notebook này nên
KHÔNG phải tải + trích lại video.

--------------------------------------------------------------------------------
CẤU HÌNH KAGGLE (bắt buộc):
  - Settings > Accelerator : GPU T4 x2 (hoặc P100)   [TransNetV2 chạy GPU nhanh hơn]
  - Settings > Internet    : ON                       [để tải video BTC]
  - Add Input (Datasets)   : thêm dataset chứa weights TransNetV2 (xem README_KAGGLE.md
                             mục "Chuẩn bị 1 lần") — VD tên "transnetv2-weights"

CHỌN SHARD ĐỂ CHẠY — 2 CÁCH:
  (A) ĐƠN GIẢN (khuyên dùng, mỗi account Kaggle chỉ cần đổi 1 số):
      sửa ACCOUNT = "0" | "1" | "2" | "3" | "4"  → mỗi số ứng với 1 nhóm 3 shard cố định
      (xem bảng ACCOUNT_GROUPS bên dưới). Notebook sẽ tự chạy TUẦN TỰ hết cả nhóm
      trong 1 lần Run/Commit — không cần đổi lại giữa chừng.
  (B) THỦ CÔNG: đặt ACCOUNT = tên shard cụ thể (VD "K01") để chạy đúng 1 shard đó.

ĐẦU RA (lưu ở /kaggle/working, rồi "Save Version" → thành Kaggle Dataset để dùng lại):
  /kaggle/working/out/<shard>/keyframes/<video>/<n:06d>.webp   ảnh keyframe (WebP q88, cạnh dài 384px)
  /kaggle/working/out/<shard>/maps/<video>.csv                 n,frame_idx,pts_time,fps (= số nộp BTC)
  /kaggle/working/out/<shard>/audio/<video>.opus               audio 16kHz mono (cho ChunkFormer ASR)
  /kaggle/working/out/<shard>/shard_info.json                  thống kê từng shard
  /kaggle/working/out/account_<ACCOUNT>_summary.json           thống kê tổng cả nhóm

VÌ SAO tự tính frame_idx được (không cần keyframe BTC): TransNetV2 phát hiện shot theo
CHÍNH frame gốc của video → frame_idx = chỉ số frame trong video gốc → khớp GT của BTC
(GT chấm frame_idx ∈ [s,e] theo đánh số gốc). fps đọc từ video thật.
================================================================================
"""

import os, sys, json, time, subprocess, shutil, glob
from pathlib import Path

VERSION = "01-keyframe v1 (2026)"
print(f">>> {VERSION}", flush=True)

# ============================ CẤU HÌNH ============================
# 15 shard batch-1 còn lại (L21_a đã chạy xong riêng) chia đều cho 5 account Kaggle.
ACCOUNT_GROUPS = {
    "0": ["L22_a", "L23_a", "L24_a"],
    "1": ["L25_a", "L25_a1", "L25_b"],
    "2": ["L26_a", "L26_b", "L26_c"],
    "3": ["L26_d", "L26_e", "L27_a"],
    "4": ["L28_a", "L29_a", "L30_a"],
}
ACCOUNT = os.environ.get("ACCOUNT", os.environ.get("SHARD", "0"))  # <<< SỬA Ở ĐÂY: "0".."4", hoặc tên shard (VD "K01")
SHARDS = ACCOUNT_GROUPS.get(ACCOUNT, [ACCOUNT])   # số 0-4 -> nhóm 3 shard; tên khác -> chạy đúng 1 shard đó
BASE_URL = "https://aic-data.ledo.io.vn"
print(f"  ACCOUNT={ACCOUNT} --> sẽ chạy tuần tự {len(SHARDS)} shard: {SHARDS}", flush=True)

# đường dẫn weights TransNetV2 (từ Kaggle Dataset đã add — dò tự động)
def find_weights():
    cands = glob.glob("/kaggle/input/**/transnetv2-weights", recursive=True)
    cands += glob.glob("/kaggle/input/**/saved_model.pb", recursive=True)
    for c in cands:
        d = c if os.path.isdir(c) else os.path.dirname(c)
        if os.path.exists(os.path.join(d, "saved_model.pb")):
            return d
    return None

# keyframe policy
KF_PER_SEC   = 0.5      # ~1 keyframe mỗi 2 giây trong 1 shot (mật độ dày để localize tốt)
KF_MIN, KF_MAX = 1, 6   # tối thiểu/tối đa keyframe mỗi shot
PHASH_HAMMING_MIN = 4   # loại keyframe gần trùng (Hamming distance pHash < ngưỡng này)
THUMB_LONG_EDGE = 384   # cạnh dài ảnh lưu (đủ cho MetaCLIP-2 378px + hiển thị UI)
WEBP_QUALITY = 88

WORK = Path("/kaggle/working")
DATA = Path("/kaggle/temp/data")           # /kaggle/temp KHÔNG tính vào 20GB output
OUT  = WORK / "out"                        # mỗi shard sẽ có OUT/<shard>/{keyframes,maps,audio}
DATA.mkdir(parents=True, exist_ok=True)


def sh(cmd, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and check:
        print(r.stdout[-1500:], r.stderr[-1500:], flush=True)
        raise RuntimeError(cmd)
    return r


# ==================== 1. CÀI ĐẶT ====================
print("=" * 60, "\n[1/5] Cài đặt phụ thuộc\n", "=" * 60, flush=True)
sh("apt-get -qq install -y aria2 ffmpeg >/dev/null 2>&1", check=False)
sh(f"{sys.executable} -m pip install -q decord imagehash ffmpeg-python pillow 2>/dev/null", check=False)

import numpy as np
import tensorflow as tf
from PIL import Image
import imagehash

WEIGHTS = find_weights()
if WEIGHTS is None:
    raise FileNotFoundError(
        "KHÔNG thấy weights TransNetV2. Hãy Add Input dataset chứa 'transnetv2-weights' "
        "(saved_model.pb + variables/). Xem README_KAGGLE.md mục 'Chuẩn bị 1 lần'.")
print(f"  weights TransNetV2: {WEIGHTS}", flush=True)
print(f"  GPU: {tf.config.list_physical_devices('GPU')}", flush=True)


# ==================== 2. NẠP TRANSNETV2 (1 lần dùng chung cho mọi shard) ====================
print("=" * 60, "\n[2/5] Nạp model TransNetV2\n", "=" * 60, flush=True)


class TransNetV2:
    """Inference TransNetV2 — COPY NGUYÊN logic từ soCzech/TransNetV2 (không sửa để tránh sai)."""
    def __init__(self, model_dir):
        self._input_size = (27, 48, 3)
        self._model = tf.saved_model.load(model_dir)

    def predict_raw(self, frames):
        assert len(frames.shape) == 5 and frames.shape[2:] == self._input_size
        frames = tf.cast(frames, tf.float32)
        logits, dict_ = self._model(frames)
        return tf.sigmoid(logits), tf.sigmoid(dict_["many_hot"])

    def predict_frames(self, frames):
        assert len(frames.shape) == 4 and frames.shape[1:] == self._input_size

        def input_iterator():
            no_pad_start = 25
            no_pad_end = 25 + 50 - (len(frames) % 50 if len(frames) % 50 != 0 else 50)
            start_frame = np.expand_dims(frames[0], 0)
            end_frame = np.expand_dims(frames[-1], 0)
            padded = np.concatenate(
                [start_frame] * no_pad_start + [frames] + [end_frame] * no_pad_end, 0)
            ptr = 0
            while ptr + 100 <= len(padded):
                yield padded[ptr:ptr + 100][np.newaxis]
                ptr += 50

        preds = []
        for inp in input_iterator():
            single, _all = self.predict_raw(inp)
            preds.append(single.numpy()[0, 25:75, 0])
        return np.concatenate(preds)[:len(frames)]

    def predict_video(self, video_fn):
        import ffmpeg
        stream, _ = (ffmpeg.input(video_fn)
                     .output("pipe:", format="rawvideo", pix_fmt="rgb24", s="48x27")
                     .run(capture_stdout=True, capture_stderr=True))
        video = np.frombuffer(stream, np.uint8).reshape([-1, 27, 48, 3])
        return video, self.predict_frames(video)

    @staticmethod
    def predictions_to_scenes(pred, threshold=0.5):
        p = (pred > threshold).astype(np.uint8)
        scenes, t, prev, start = [], 0, 0, 0
        for i, t in enumerate(p):
            if prev == 1 and t == 0:
                start = i
            if prev == 0 and t == 1 and i != 0:
                scenes.append([start, i])
            prev = t
        if t == 0:
            scenes.append([start, i])
        if not scenes:
            return np.array([[0, len(p) - 1]], np.int32)
        return np.array(scenes, np.int32)


model = TransNetV2(WEIGHTS)
print("  --> model sẵn sàng", flush=True)

import decord
decord.bridge.set_bridge("native")


def video_fps(fn):
    r = sh(f"ffprobe -v 0 -of csv=p=0 -select_streams v:0 -show_entries stream=r_frame_rate '{fn}'", check=False)
    try:
        num, den = r.stdout.strip().split("/")
        return float(num) / float(den)
    except Exception:
        return 25.0


def pick_keyframes(scenes, fps, total_frames):
    """Trả list frame_idx: mỗi shot lấy KF_PER_SEC*duration keyframe (clamp), phân bố đều."""
    idxs = []
    for s, e in scenes:
        e = min(e, total_frames - 1)
        if e < s:
            continue
        dur = (e - s + 1) / max(fps, 1e-6)
        n = int(round(dur * KF_PER_SEC))
        n = max(KF_MIN, min(KF_MAX, n))
        if n == 1:
            idxs.append((s + e) // 2)
        else:
            for k in range(n):
                idxs.append(int(s + (e - s) * (k + 0.5) / n))
    return sorted(set(idxs))


# ==================== 3+4. VỚI MỖI SHARD: TẢI VIDEO + TRÍCH KEYFRAME + AUDIO ====================
all_stats = []
t_all = time.time()
for si, SHARD in enumerate(SHARDS):
    print("\n" + "#" * 60, flush=True)
    print(f"### SHARD {si+1}/{len(SHARDS)}: {SHARD}", flush=True)
    print("#" * 60, flush=True)
    ZIP_NAME = f"Videos_{SHARD}.zip"
    shard_out = OUT / SHARD
    (shard_out / "keyframes").mkdir(parents=True, exist_ok=True)
    (shard_out / "maps").mkdir(parents=True, exist_ok=True)
    (shard_out / "audio").mkdir(parents=True, exist_ok=True)

    print("=" * 60, f"\n[3/5] Tải video shard: {ZIP_NAME}\n", "=" * 60, flush=True)
    VID_DIR = DATA / "videos" / SHARD
    VID_DIR.mkdir(parents=True, exist_ok=True)
    have = len(list(VID_DIR.glob("*.mp4")))
    if have >= 3:
        print(f"  BỎ QUA tải — đã có {have} video (restart kernel giữ /kaggle/temp)", flush=True)
    else:
        t = time.time()
        sh(f"aria2c -x16 -s16 -k1M -c --console-log-level=warn -d {DATA} '{BASE_URL}/{ZIP_NAME}'")
        print(f"  tải xong {(time.time()-t)/60:.1f} phút. Giải nén...", flush=True)
        if sh(f"unzip -tqq {DATA}/{ZIP_NAME}", check=False).returncode != 0:
            print(f"  [LỖI] {ZIP_NAME} HỎNG — bỏ qua shard này", flush=True)
            all_stats.append({"shard": SHARD, "videos": 0, "keyframes": 0, "skipped": [("ALL", "zip hỏng")]})
            (DATA / ZIP_NAME).unlink(missing_ok=True)
            continue
        sh(f"unzip -qq -o -j {DATA}/{ZIP_NAME} '*.mp4' -d {VID_DIR}", check=False)
        if len(list(VID_DIR.glob('*.mp4'))) == 0:
            sh(f"unzip -qq -o {DATA}/{ZIP_NAME} -d {DATA}/raw_{SHARD}", check=False)
            for p in Path(f"{DATA}/raw_{SHARD}").rglob("*.mp4"):
                shutil.move(str(p), VID_DIR / p.name)
        os.remove(DATA / ZIP_NAME)

    videos = sorted(VID_DIR.glob("*.mp4"))
    print(f"  --> {len(videos)} video sẵn sàng", flush=True)

    print("=" * 60, "\n[4/5] Trích keyframe + tách audio\n", "=" * 60, flush=True)
    stats = {"shard": SHARD, "videos": 0, "keyframes": 0, "skipped": []}
    t0 = time.time()
    for vi, vpath in enumerate(videos):
        vid = vpath.stem
        try:
            fps = video_fps(str(vpath))
            _, pred = model.predict_video(str(vpath))
            scenes = model.predictions_to_scenes(pred)
            vr = decord.VideoReader(str(vpath))
            total = len(vr)
            cand = [i for i in pick_keyframes(scenes, fps, total) if i < total]
            if not cand:
                stats["skipped"].append((vid, "no keyframe")); continue

            frames = vr.get_batch(cand).asnumpy()  # [K, H, W, 3]

            kf_dir = shard_out / "keyframes" / vid
            kf_dir.mkdir(parents=True, exist_ok=True)
            rows = []
            prev_hash = None
            n = 0
            for fidx, arr in zip(cand, frames):
                img = Image.fromarray(arr)
                h = imagehash.phash(img)
                if prev_hash is not None and (h - prev_hash) < PHASH_HAMMING_MIN:
                    continue
                prev_hash = h
                w, ht = img.size
                scale = THUMB_LONG_EDGE / max(w, ht)
                if scale < 1:
                    img = img.resize((max(1, int(w * scale)), max(1, int(ht * scale))), Image.LANCZOS)
                n += 1
                img.save(kf_dir / f"{n:06d}.webp", "WEBP", quality=WEBP_QUALITY)
                rows.append((n, int(fidx), round(fidx / fps, 3), round(fps, 3)))

            with open(shard_out / "maps" / f"{vid}.csv", "w") as f:
                f.write("n,frame_idx,pts_time,fps\n")
                for r in rows:
                    f.write(",".join(map(str, r)) + "\n")

            sh(f"ffmpeg -v 0 -y -i '{vpath}' -vn -ac 1 -ar 16000 -c:a libopus -b:a 24k "
               f"'{shard_out/'audio'/(vid+'.opus')}'", check=False)

            stats["videos"] += 1
            stats["keyframes"] += len(rows)
            os.remove(vpath)  # xoá video ngay để tiết kiệm đĩa
            if (vi + 1) % 5 == 0 or vi == len(videos) - 1:
                el = (time.time() - t0) / 60
                print(f"  [{vi+1}/{len(videos)}] {vid}: {len(rows)} kf | "
                      f"tổng {stats['keyframes']:,} kf | {el:.1f} phút", flush=True)
        except Exception as ex:
            stats["skipped"].append((vid, str(ex)[:120]))
            print(f"  [LỖI] {vid}: {ex}", flush=True)

    json.dump(stats, open(shard_out / "shard_info.json", "w"), ensure_ascii=False, indent=2)
    print(f"  >> Shard {SHARD} XONG: {stats['videos']} video, {stats['keyframes']:,} keyframe, "
          f"{len(stats['skipped'])} bỏ qua, {(time.time()-t0)/60:.1f} phút", flush=True)
    all_stats.append(stats)


# ==================== 5. TỔNG KẾT CẢ NHÓM ====================
print("\n" + "=" * 60, "\n[5/5] Tổng kết\n", "=" * 60, flush=True)
summary = {
    "account": ACCOUNT, "shards": SHARDS,
    "total_videos": sum(s["videos"] for s in all_stats),
    "total_keyframes": sum(s["keyframes"] for s in all_stats),
    "per_shard": all_stats,
}
json.dump(summary, open(OUT / f"account_{ACCOUNT}_summary.json", "w"), ensure_ascii=False, indent=2)
out_size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e9
for s in all_stats:
    print(f"  {s['shard']}: {s['videos']} video, {s['keyframes']:,} keyframe, {len(s['skipped'])} bỏ qua", flush=True)
print(f"  TỔNG: {summary['total_videos']} video, {summary['total_keyframes']:,} keyframe", flush=True)
print(f"  Dung lượng output: {out_size:.2f} GB (giới hạn Kaggle 20GB)", flush=True)
print(f"  Tổng thời gian cả nhóm: {(time.time()-t_all)/60:.1f} phút", flush=True)
print("\n>>> XONG. Giờ bấm 'Save Version' (Save & Run All / Quick Save) để tạo Kaggle Dataset "
      "(1 dataset gồm cả 3 shard, VD tên 'aic-kf-account0').", flush=True)
print(">>> Xem README_KAGGLE.md để biết cách lưu Dataset + notebook sau dùng lại.", flush=True)
