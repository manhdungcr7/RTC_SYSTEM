export const DEFAULT_VIDEO_LIMIT = 70;

/** Top N applies after deduplication, retaining the first ranked occurrence. */
export function rankedVideoList(videoIds: readonly string[], limit: number): string[] {
  const topN = Number.isFinite(limit) && limit >= 1
    ? Math.floor(limit)
    : DEFAULT_VIDEO_LIMIT;
  return [...new Set(videoIds.map((id) => id.trim()).filter(Boolean))].slice(0, topN);
}

export function formatVideoList(videoIds: readonly string[], limit: number): string {
  return rankedVideoList(videoIds, limit).join(", ");
}
