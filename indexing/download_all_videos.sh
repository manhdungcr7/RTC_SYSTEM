#!/bin/bash
# ================================================================================
# Tai toan bo 14 shard video CHINH THUC cua AIC 2026 (theo dung sheet "Batch1"
# trong "Du lieu cho vong So Tuyen AIC 2026.xlsx" cua BTC — file nay CHI CO 1
# sheet Batch1, KHONG co Batch2/K01-K20 nhu nam 2025) — RESUMABLE. Chay lai
# script nay bat cu luc nao (dut mang, tat may, Ctrl+C...) se TU DONG tiep tuc
# dung cho tung shard chua xong (aria2c -c) VA bo qua shard da xong (kiem tra
# dung luong khop truoc khi tai lai).
#
# GHI CHU quan trong ve L25 (da tu kiem chung bang cach doc truc tiep central
# directory cua zip qua HTTP Range, khong tai ca file): server con 2 file THUA
# "Videos_L25_a1.zip" (V001-V049) va "Videos_L25_b.zip" (V050-V088) — KHONG co
# trong sheet Batch1 chinh thuc cua AIC 2026, va noi dung uncompressed-size
# TRUNG KHOP tuyet doi voi "Videos_L25_a.zip" (dong nghia cung 1 video, chi
# đóng gói lại thanh 2 phan nho hon) — rat co the la file rac con sot tu nam
# 2025 (sheet AIC 2025 co liet ke ca 3). "Videos_L25_a.zip" MOT MINH da du
# tron 88 video (V001-V088), KHONG can tai them 2 file kia (đỡ ~12.7GB thua).
# ================================================================================
set -uo pipefail

BASE="https://aic-data.ledo.io.vn"
# DEST tính TƯƠNG ĐỐI theo vị trí script (aic-system/indexing/) — chạy được trên
# BẤT KỲ máy nào clone repo, không phụ thuộc đường dẫn tuyệt đối của máy dev gốc.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$SCRIPT_DIR/../data/videos_full"
LOG="$DEST/download_progress.log"
LOCK="$DEST/.download.lock"
mkdir -p "$DEST"

# ---- KHOA CHONG CHAY TRUNG (bai hoc dau xuong mau: TaskStop khong luon giet duoc
# tien trinh goc tren moi truong nay -> 2 ban script tung chay song song, ghi de
# len nhau lam HONG 6 file video ~40GB). Neu da co lock CON SONG (PID con ton tai
# that trong Task Manager) -> DUNG NGAY, khong chay tiep.
if [ -f "$LOCK" ]; then
  old_pid=$(cat "$LOCK" 2>/dev/null)
  if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
    echo "!!! DA CO 1 BAN SCRIPT DANG CHAY (PID $old_pid) — DUNG, khong chay trung." | tee -a "$LOG"
    exit 1
  else
    echo "  (lock cu PID $old_pid da chet, don lock roi chay tiep)" | tee -a "$LOG"
  fi
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT INT TERM

# ten shard + kich thuoc THAT (byte) da do truoc — dung de xac nhan tai xong,
# khong dua vao aria2c doan (tranh truong hop file loi/thieu ma tuong da xong)
declare -A SIZES=(
  [L21_a]=3378949330   [L22_a]=4154534912   [L23_a]=2043042826  [L24_a]=5796204890
  [L25_a]=12849314154  [L26_a]=6587402599   [L26_b]=6839785125  [L26_c]=6902904211
  [L26_d]=6773208922   [L26_e]=6939942702   [L27_a]=2539791837  [L28_a]=7274485525
  [L29_a]=6767159141   [L30_a]=4137461892
)

ORDER="L21_a L22_a L23_a L24_a L25_a L26_a L26_b L26_c L26_d L26_e L27_a L28_a L29_a L30_a"

total_shards=$(echo $ORDER | wc -w)
i=0
t_all=$(date +%s)

for s in $ORDER; do
  i=$((i+1))
  f="$DEST/Videos_${s}.zip"
  expect=${SIZES[$s]}

  if [ -f "$f" ]; then
    have=$(stat -c%s "$f" 2>/dev/null || echo 0)
    if [ "$have" = "$expect" ]; then
      echo "[$i/$total_shards] $s: DA CO DU ($((have/1048576))MB) -> bo qua" | tee -a "$LOG"
      continue
    fi
  fi

  echo "[$i/$total_shards] $s: dang tai/resume..." | tee -a "$LOG"
  t0=$(date +%s)
  aria2c -x16 -s16 -k1M -c --console-log-level=warn \
    -d "$DEST" -o "Videos_${s}.zip" "$BASE/Videos_${s}.zip" 2>&1 | tail -3 | tee -a "$LOG"
  t1=$(date +%s)

  have=$(stat -c%s "$f" 2>/dev/null || echo 0)
  if [ "$have" = "$expect" ]; then
    echo "[$i/$total_shards] $s: XONG ($((have/1048576))MB, $((t1-t0))s)" | tee -a "$LOG"
  else
    echo "[$i/$total_shards] $s: !!! CHUA DU ($have / $expect byte) — se thu lai lan chay sau" | tee -a "$LOG"
  fi
  elapsed_all=$(( $(date +%s) - t_all ))
  echo "  -> da chay tong ${elapsed_all}s ($(( elapsed_all/60 )) phut)" | tee -a "$LOG"
done

echo "================================================================" | tee -a "$LOG"
echo ">>> HOAN TAT vong lap. Kiem tra lai bang cach chay lai script nay" | tee -a "$LOG"
echo ">>> neu co shard nao bi loi mang giua chung se tu resume." | tee -a "$LOG"
