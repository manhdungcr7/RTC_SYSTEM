#!/bin/bash
# ================================================================================
# Tai toan bo 36 shard video (batch 1 + batch 2, ~257.9GB) ve F: — RESUMABLE.
# Chay lai script nay bat cu luc nao (dut mang, tat may, Ctrl+C...) se TU DONG
# tiep tuc dung cho tung shard chua xong (aria2c -c) VA bo qua shard da xong
# (kiem tra dung luong khop truoc khi tai lai).
# ================================================================================
set -uo pipefail

BASE="https://aic-data.ledo.io.vn"
DEST="/f/AI_Challenge_Video_Image_Retrieval/aic-system/data/videos_full"
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
  [L25_a]=12849314154  [L25_a1]=7213646123  [L25_b]=5505405349  [L26_a]=6587402599
  [L26_b]=6839785125   [L26_c]=6902904211   [L26_d]=6773208922  [L26_e]=6939942702
  [L27_a]=2539791837   [L28_a]=7274485525   [L29_a]=6767159141  [L30_a]=4137461892
  [K01]=10080837769    [K02]=8873807689     [K03]=6202983564    [K04]=6914692432
  [K05]=8235968560     [K06]=8393787349     [K07]=9599993196    [K08]=10118877395
  [K09]=9244712163     [K10]=9781033421     [K11]=7321491966    [K12]=8567151014
  [K13]=7519438212     [K14]=7832550635     [K15]=6696696132    [K16]=7841706808
  [K17]=6521740715     [K18]=6510257110     [K19]=8352893186    [K20]=7553173294
)

ORDER="L21_a L22_a L23_a L24_a L25_a L25_a1 L25_b L26_a L26_b L26_c L26_d L26_e L27_a L28_a L29_a L30_a"
# batch 2 (K01..K20) TAM KHONG tai — chi lay batch 1 theo yeu cau. Muon tai them
# thi mo lai dong ORDER cu (con luu trong SIZES ben tren, khong xoa de dung sau).

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
