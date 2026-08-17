/**
 * ĐỒNG HỒ FRAME_IDX THỜI GIAN THỰC — đòn bẩy thủ công quan trọng nhất.
 *
 * Vì sao cần: keyframe là THƯA (167.850 khung cho 873 video). Khoảnh khắc cần
 * nộp có thể rơi vào GIỮA hai keyframe, hoặc bạn muốn chốt chính xác hơn khung
 * mà hệ thống chọn sẵn. Hook này cho phép tự tua tay rồi đọc ra con số
 * frame_idx CHÍNH XÁC để nộp — không phụ thuộc vào keyframe có sẵn.
 *
 * ĐỘ CHÍNH XÁC (làm đúng chứ không xấp xỉ):
 *  1. Dùng requestVideoFrameCallback -> `mediaTime` là thời điểm của ĐÚNG khung
 *     hình ĐANG HIỂN THỊ, không phải ước lượng của bộ đếm currentTime. Sai số
 *     gần như bằng 0. Trình duyệt không hỗ trợ thì rơi về rAF + currentTime.
 *  2. ĐỐI CHIẾU CHÉO chống video biến thiên tốc độ khung (VFR): so
 *     round(mediaTime*fps) với frame_idx THẬT của keyframe gần nhất. Lệch quá
 *     ngưỡng -> chuyển sang NỘI SUY TUYẾN TÍNH từ hai keyframe kề (dùng
 *     pts_time/frame_idx đo thật) và bật cảnh báo. Video tin tức đôi khi là VFR
 *     — bỏ qua chuyện này sẽ nộp sai frame mà không hiểu vì sao.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import type { VideoMap, VideoMapRow } from "../../types/api";

export type FrameSource = "measured" | "keyframe" | "interpolated";

export interface FrameReading {
  frameIdx: number;
  mediaTime: number;
  source: FrameSource;
  nearestKeyframe: VideoMapRow | null;
  deltaToNearest: number;
  vfrWarning: boolean;
}

/** Lệch quá số khung này giữa "tính theo fps" và "keyframe đo thật" -> nghi VFR. */
const VFR_TOLERANCE_FRAMES = 2;
/** Coi là "đang đứng đúng keyframe" khi cách nó dưới ngần này giây. */
const ON_KEYFRAME_EPS_S = 0.04;

/** Tìm 2 keyframe kề (trước, sau) theo thời gian — bảng đã sort tăng dần theo n. */
function bracket(rows: VideoMapRow[], t: number): [VideoMapRow | null, VideoMapRow | null] {
  if (rows.length === 0) return [null, null];
  let lo = 0, hi = rows.length - 1;
  if (t <= rows[0].pts_time) return [null, rows[0]];
  if (t >= rows[hi].pts_time) return [rows[hi], null];
  while (lo + 1 < hi) {
    const mid = (lo + hi) >> 1;
    if (rows[mid].pts_time <= t) lo = mid;
    else hi = mid;
  }
  return [rows[lo], rows[hi]];
}

function nearestRow(rows: VideoMapRow[], t: number): VideoMapRow | null {
  const [a, b] = bracket(rows, t);
  if (a && b) return Math.abs(a.pts_time - t) <= Math.abs(b.pts_time - t) ? a : b;
  return a ?? b;
}

export function computeReading(map: VideoMap | undefined, t: number): FrameReading {
  if (!map || map.rows.length === 0) {
    return {
      frameIdx: 1, mediaTime: t, source: "measured",
      nearestKeyframe: null, deltaToNearest: 0, vfrWarning: false,
    };
  }
  const fps = map.fps > 0 ? map.fps : 25;
  // +1: khung ĐẦU TIÊN (t=0) là frame 1, không phải 0 — khớp Media Player
  // Classic/BTC (xem core/media_index.py, nơi map.rows.*.frame_idx đã +1 từ
  // backend). Công thức tự tính tay ở đây phải cùng quy ước, không thì lệch
  // hẳn 1 khung so với dữ liệu keyframe thật, kích hoạt báo VFR giả.
  const byFps = Math.round(t * fps) + 1;
  const near = nearestRow(map.rows, t);

  // Đang đứng đúng một keyframe -> dùng thẳng frame_idx ĐO THẬT của nó (an toàn
  // nhất, không qua phép nhân nào).
  if (near && Math.abs(near.pts_time - t) <= ON_KEYFRAME_EPS_S) {
    return {
      frameIdx: near.frame_idx, mediaTime: t, source: "keyframe",
      nearestKeyframe: near, deltaToNearest: 0, vfrWarning: false,
    };
  }

  // Đối chiếu chéo: nếu công thức t*fps lệch nhiều so với keyframe đo thật gần
  // đó thì fps không đáng tin -> nội suy tuyến tính giữa 2 keyframe kề.
  let vfr = false;
  if (near) {
    const expectedAtNear = Math.round(near.pts_time * fps) + 1;
    if (Math.abs(expectedAtNear - near.frame_idx) > VFR_TOLERANCE_FRAMES) vfr = true;
  }

  if (vfr) {
    const [a, b] = bracket(map.rows, t);
    if (a && b && b.pts_time > a.pts_time) {
      const ratio = (t - a.pts_time) / (b.pts_time - a.pts_time);
      const interp = Math.round(a.frame_idx + ratio * (b.frame_idx - a.frame_idx));
      return {
        frameIdx: interp, mediaTime: t, source: "interpolated",
        nearestKeyframe: near, deltaToNearest: interp - (near?.frame_idx ?? interp),
        vfrWarning: true,
      };
    }
  }

  return {
    frameIdx: byFps, mediaTime: t, source: "measured",
    nearestKeyframe: near,
    deltaToNearest: near ? byFps - near.frame_idx : 0,
    vfrWarning: vfr,
  };
}

interface VideoFrameMeta { mediaTime: number }
/** requestVideoFrameCallback chưa có trong lib DOM của TS ở mọi phiên bản, và
 *  Safari cũ không hỗ trợ — khai báo dạng tuỳ chọn rồi kiểm tra lúc chạy. */
type VideoElWithRVFC = HTMLVideoElement & {
  requestVideoFrameCallback?: (cb: (now: number, meta: VideoFrameMeta) => void) => number;
  cancelVideoFrameCallback?: (h: number) => void;
};

export function useFrameIndex(videoRef: React.RefObject<HTMLVideoElement | null>,
                               map: VideoMap | undefined) {
  const [reading, setReading] = useState<FrameReading>(() => computeReading(map, 0));
  const rafRef = useRef<number | null>(null);
  const rvfcRef = useRef<number | null>(null);

  useEffect(() => {
    const el = videoRef.current as VideoElWithRVFC | null;
    if (!el) return;
    let stopped = false;

    const update = (t: number) => {
      if (!stopped) setReading(computeReading(map, t));
    };

    if (typeof el.requestVideoFrameCallback === "function") {
      const step = (_now: number, meta: VideoFrameMeta) => {
        update(meta.mediaTime);
        if (!stopped) rvfcRef.current = el.requestVideoFrameCallback!(step);
      };
      rvfcRef.current = el.requestVideoFrameCallback(step);
    } else {
      // Dự phòng: currentTime là ước lượng của bộ đếm, kém chính xác hơn mediaTime
      // nhưng vẫn dùng được (và vẫn hưởng đối chiếu chéo chống VFR ở trên).
      const loop = () => {
        update(el.currentTime);
        if (!stopped) rafRef.current = requestAnimationFrame(loop);
      };
      rafRef.current = requestAnimationFrame(loop);
    }

    // Tua khi đang tạm dừng KHÔNG sinh khung mới -> rVFC không bắn. Bám thêm
    // các sự kiện này để đồng hồ vẫn cập nhật lúc kéo thanh thời gian.
    const onSeek = () => update(el.currentTime);
    el.addEventListener("seeked", onSeek);
    el.addEventListener("timeupdate", onSeek);
    el.addEventListener("loadedmetadata", onSeek);

    return () => {
      stopped = true;
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      if (rvfcRef.current !== null && typeof el.cancelVideoFrameCallback === "function")
        el.cancelVideoFrameCallback(rvfcRef.current);
      el.removeEventListener("seeked", onSeek);
      el.removeEventListener("timeupdate", onSeek);
      el.removeEventListener("loadedmetadata", onSeek);
    };
  }, [videoRef, map]);

  /** Nhảy ĐÚNG ±k khung hình. Cộng nửa khung (epsilon) để trình duyệt seek tới
   *  khung mong muốn thay vì khung ngay trước nó. */
  const stepFrames = useCallback((delta: number) => {
    const el = videoRef.current;
    if (!el || !map) return;
    const fps = map.fps > 0 ? map.fps : 25;
    el.pause();
    const targetFrame = Math.max(0, Math.round(el.currentTime * fps) + delta);
    el.currentTime = targetFrame / fps + 0.5 / fps;
  }, [videoRef, map]);

  const seekTo = useCallback((t: number) => {
    const el = videoRef.current;
    if (el) el.currentTime = Math.max(0, t);
  }, [videoRef]);

  const seekToFrameIdx = useCallback((frameIdx: number) => {
    const el = videoRef.current;
    if (!el || !map) return;
    // Ưu tiên pts_time ĐO THẬT của keyframe trùng frame_idx (chính xác tuyệt đối);
    // không có thì mới quy đổi qua fps. frameIdx là 1-based (frame 1 = t=0) nên
    // trừ 1 trước khi chia fps.
    const exact = map.rows.find((r) => r.frame_idx === frameIdx);
    const fps = map.fps > 0 ? map.fps : 25;
    el.currentTime = exact ? exact.pts_time : (frameIdx - 1) / fps + 0.5 / fps;
  }, [videoRef, map]);

  return { reading, stepFrames, seekTo, seekToFrameIdx };
}

/** mm:ss.mmm — định dạng timecode kiểu thiết bị dựng phim. */
export function formatTimecode(t: number): string {
  if (!Number.isFinite(t) || t < 0) return "00:00.000";
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  const ms = Math.round((t - Math.floor(t)) * 1000);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(ms).padStart(3, "0")}`;
}
