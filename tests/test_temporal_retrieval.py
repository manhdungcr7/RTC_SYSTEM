import numpy as np
import pytest

from core.temporal import _rank_candidate_videos, _run_dp, _text_candidate_videos, search_temporal


class FakeFaiss:
    def __init__(self, rankings, videos):
        self.rankings = rankings
        self.videos = videos

    def videos_from_topk(self, collection, vector, per_event):
        del collection, per_event
        return list(self.rankings[int(np.argmax(vector))])

    def fetch_video_vectors(self, collection, video):
        del collection
        vecs = np.asarray(self.videos[video], dtype=np.float32)
        count = len(vecs)
        return (
            [f"{video}:{i + 1:06d}" for i in range(count)],
            list(range(1, count + 1)),
            list(range(1, count + 1)),
            vecs,
        )

    def has_branch(self, branch):
        del branch
        return False


class FakeMediaIndex:
    def __init__(self, points):
        self.points = points

    def pts_time(self, video, n):
        return self.points[video][n - 1]

    def video_ns_pts(self, video):
        return [(i + 1, t) for i, t in enumerate(self.points[video])]


class FakeTextRepo:
    def __init__(self, ocr=None, asr=None):
        self.ocr = ocr or {}
        self.asr = asr or {}
        self.calls = []

    def search_frames(self, field, query, size):
        self.calls.append(("ocr", query))
        return self.ocr.get(query, [])

    def search_asr(self, query, size):
        self.calls.append(("asr", query))
        return [(video, 10.0, 10.0, 1.0) for video in self.asr.get(query, [])]


@pytest.mark.parametrize("channel", ["ocr", "asr"])
def test_text_candidate_retrieval_skips_leading_and_middle_empty_slots(channel):
    queries = ["", "first", " \t", "second", ""]
    repo = FakeTextRepo(ocr={"first": ["video-1:000001"], "second": ["video-2:000002"]},
                        asr={"first": ["video-1"], "second": ["video-2"]})

    result = _text_candidate_videos(repo, queries if channel == "ocr" else [],
                                   queries if channel == "asr" else [])

    assert result == ["video-1", "video-2"]
    assert repo.calls == [(channel, "first"), (channel, "second")]


def test_text_candidate_retrieval_continues_from_empty_ocr_to_later_asr():
    repo = FakeTextRepo(asr={"muối": ["asr-only"]})
    assert _text_candidate_videos(repo, ["", " "], ["", "muối"]) == ["asr-only"]
    assert repo.calls == [("asr", "muối")]


@pytest.mark.parametrize("max_videos, expected", [(0, []), (2, ["video-1", "video-2"]),
                                                   (3, ["video-1", "video-2", "video-3"])])
def test_text_candidate_limit_counts_unique_videos_and_stops_further_queries(max_videos, expected):
    repo = FakeTextRepo(ocr={"first": ["video-1:000001", "video-1:000002", "video-2:000001",
                                     "video-3:000001", "video-4:000001"]},
                        asr={"later": ["asr-only"]})
    result = _text_candidate_videos(repo, ["", "first", "unused"], ["later"],
                                   max_videos=max_videos)
    assert result == expected
    assert repo.calls == ([("ocr", "first")] if max_videos else [])


def test_router_empty_first_slot_keeps_text_only_winner_in_later_event():
    from types import SimpleNamespace

    from api.routers.temporal import temporal
    from api.schemas.temporal import TemporalRequest

    class TextRepo(FakeTextRepo):
        def search_frames_scored(self, field, query, video, size, strict):
            self.calls.append(("ocr-bonus", query))
            return {"text-only:000002": 0.8} if video == "text-only" else {}

        def search_asr_in_video(self, video, query, size, strict):
            self.calls.append(("asr-bonus", query))
            return [(10.0, 10.0, 0.7)] if video == "text-only" else []

        def get_frame_docs(self, ids):
            return {}

    identity = np.eye(2, dtype=np.float32)
    faiss = FakeFaiss(rankings={0: ["visual-only"], 1: ["visual-only"]},
                      videos={"visual-only": identity * 0.5, "text-only": identity})
    meili = TextRepo(ocr={"1,5 lít": ["text-only:000002"]}, asr={"nước": ["text-only"]})
    media = FakeMediaIndex({"visual-only": [0.0, 10.0], "text-only": [0.0, 10.0]})
    req = TemporalRequest(events=["Đảo thức ăn", "Thêm nước"], split_clauses=False,
                          ocr_queries=["", "1,5 lít"], asr_queries=["", "nước"])
    encoders = SimpleNamespace(metaclip2=SimpleNamespace(encode=lambda texts: identity))

    response = temporal(req, faiss=faiss, meili=meili, encoders=encoders, media_index=media)

    assert response.candidates[0].video == "text-only"
    assert [h.n for h in response.candidates[0].hits] == [1, 2]
    assert ("ocr", "1,5 lít") in meili.calls
    assert ("asr", "nước") in meili.calls
    assert all(query in {"1,5 lít", "nước"} for _, query in meili.calls)


def test_candidate_ranking_covers_all_events_and_preserves_text_lane():
    event_sources = [
        [(["common", "event-0"], 1.0)],
        [(["common", "event-1"], 1.0)],
        [(["common", "event-2"], 1.0)],
    ]

    ranked = _rank_candidate_videos(
        event_sources,
        limit=6,
        anchor_indices=(0, 2),
        text_videos=["text-only"],
    )

    assert ranked[0] == "common"
    assert {"event-0", "event-1", "event-2", "text-only"}.issubset(ranked)


def test_middle_event_can_introduce_the_winning_video():
    identity = np.eye(3, dtype=np.float32)
    repo = FakeFaiss(
        rankings={0: ["boundary"], 1: ["middle"], 2: ["boundary"]},
        videos={"boundary": identity * 0.5, "middle": identity},
    )
    events = [identity[i : i + 1] for i in range(3)]

    results = search_temporal(events, repo, "metaclip2", per_event=10, topk=10)

    assert [hits[0].video for _, hits, _ in results][0] == "middle"


def test_small_explicit_scope_is_evaluated_even_without_global_hit():
    identity = np.eye(2, dtype=np.float32)
    repo = FakeFaiss(
        rankings={0: ["global"], 1: ["global"]},
        videos={"global": identity * 0.5, "scope-only": identity},
    )
    events = [identity[i : i + 1] for i in range(2)]

    results = search_temporal(
        events,
        repo,
        "metaclip2",
        per_event=10,
        topk=10,
        video_scope=["scope-only"],
    )

    assert len(results) == 1
    assert results[0][1][0].video == "scope-only"


def test_max_gap_avoids_distant_high_score_match():
    event_vectors = np.eye(2, dtype=np.float32)
    frames = np.asarray([[1.0, 0.0], [0.2, 0.5], [0.0, 1.0]], dtype=np.float32)
    repo = FakeFaiss(
        rankings={0: ["video"], 1: ["video"]},
        videos={"video": frames},
    )
    events = [event_vectors[i : i + 1] for i in range(2)]
    media = FakeMediaIndex({"video": [0.0, 10.0, 200.0]})

    unrestricted = search_temporal(
        events, repo, "metaclip2", topk=1, media_index=media
    )
    constrained = search_temporal(
        events, repo, "metaclip2", topk=1, media_index=media, max_gap_s=120.0
    )

    assert unrestricted[0][1][1].n == 3
    assert constrained[0][1][1].n == 2


def test_linear_gap_dp_matches_bruteforce_reference():
    rng = np.random.default_rng(7)
    sub = rng.normal(size=(4, 30))
    pts = [float(i * 3) for i in range(30)]
    gaps = {1: (0.0, 24.0), 2: (6.0, 30.0), 3: (0.0, 18.0)}
    lam = 0.001

    actual_best, actual_back = _run_dp(sub, lam, gaps, pts)
    expected_best = np.full_like(actual_best, -np.inf)
    expected_back = np.zeros_like(actual_back)
    expected_best[0] = sub[0]
    for event_idx in range(1, len(sub)):
        lo_s, hi_s = gaps[event_idx]
        for t in range(1, sub.shape[1]):
            choices = [
                tau for tau in range(t)
                if lo_s <= pts[t] - pts[tau] <= hi_s
            ]
            if not choices:
                continue
            tau = max(choices, key=lambda x: expected_best[event_idx - 1, x] + lam * x)
            expected_best[event_idx, t] = (
                sub[event_idx, t] + expected_best[event_idx - 1, tau] + lam * tau - lam * t
            )
            expected_back[event_idx, t] = tau

    np.testing.assert_allclose(actual_best, expected_best)
    np.testing.assert_array_equal(actual_back, expected_back)
