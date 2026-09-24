"""Resolve a flat video name to the public CloudFront origin."""
from __future__ import annotations

import re
from threading import Lock
from urllib.parse import quote

import requests


_VIDEO_NAME = re.compile(r"^[A-Za-z0-9_-]+(?:\.(?:mp4|mov))?$", re.IGNORECASE)
_resolved: dict[tuple[str, str], str] = {}
_resolved_lock = Lock()


def valid_video_name(video: str) -> bool:
    return bool(_VIDEO_NAME.fullmatch(video))


def resolve_cdn_video_url(base_url: str, video: str) -> str | None:
    """Try the expected extension first, then the other one; cache successful lookups."""
    if not base_url or not valid_video_name(video):
        return None
    cache_key = (base_url, video)
    with _resolved_lock:
        if cache_key in _resolved:
            return _resolved[cache_key]
    if video.lower().endswith((".mp4", ".mov")):
        names = (video,)
    else:
        extensions = (".mov", ".mp4") if re.match(r"^N\d", video, re.I) else (".mp4", ".mov")
        names = tuple(video + ext for ext in extensions)
    for name in names:
        url = f"{base_url.rstrip('/')}/{quote(name, safe='')}"
        try:
            response = requests.head(url, timeout=5, allow_redirects=False)
        except requests.RequestException:
            continue
        if response.status_code == 200:
            with _resolved_lock:
                _resolved[cache_key] = url
            return url
    return None
