import pytest
from pydantic import ValidationError

from api.routers.query_plan import normalize_query_plan
from api.schemas.query_plan import VisualQueryPlan


def _plan(events, **extra):
    return VisualQueryPlan.model_validate({
        "context": {"vi": "Một chương trình nấu ăn", "en": "A cooking show"},
        "events": events,
        **extra,
    })


def test_temporal_plan_gets_exactly_two_boundary_anchors_and_search_fallback():
    result = normalize_query_plan(_plan([
        {"vi": "Một tấm dạng lưới nằm trong chảo đỏ", "en": "A lattice sheet is in a red pan"},
        {"vi": "Tấm nguyên liệu nở thành màu trắng", "en": "The sheet expands and turns white"},
        {"vi": "Người phụ nữ đặt tấm lên đĩa trắng", "en": "A woman places it on a white plate"},
    ]))

    assert result.plan.recommended_mode == "temporal"
    assert [e.anchor for e in result.plan.events] == [True, False, True]
    assert result.plan.search_clauses == [e.vi for e in result.plan.events]
    assert result.plan.search_clauses_en == [e.en for e in result.plan.events]
    assert result.plan.max_gap_s == 120


def test_single_event_is_search_without_anchor_or_gap():
    result = normalize_query_plan(_plan([
        {"vi": "Một giáo viên đứng cạnh slide", "en": "A teacher stands beside a slide", "anchor": True},
    ], recommended_mode="temporal", max_gap_s=60))

    assert result.plan.recommended_mode == "search"
    assert result.plan.events[0].anchor is False
    assert result.plan.max_gap_s is None


def test_string_context_and_events_are_accepted_for_resilient_import():
    plan = VisualQueryPlan.model_validate({
        "context": "Một cuộc đua xe đạp",
        "events": ["Một tay đua áo vàng về đích", "Một tay đua áo xanh theo sau"],
    })
    result = normalize_query_plan(plan)

    assert result.plan.context.vi == "Một cuộc đua xe đạp"
    assert len(result.plan.events) == 2


def test_empty_event_is_rejected():
    with pytest.raises(ValidationError):
        _plan([{"vi": "", "en": ""}])


def test_context_is_optional_and_translations_stay_aligned():
    plan = VisualQueryPlan.model_validate({
        "events": [
            {"vi": "một người mở nồi", "en": "a person opens a pot"},
            {"vi": "một người mở nồi", "en": "a person removes food"},
        ],
        "search_clauses": ["một người mở nồi", "một người lấy thức ăn"],
        "search_clauses_en": ["a person opens a pot"],
    })

    result = normalize_query_plan(plan)

    assert result.plan.context.vi == ""
    assert result.plan.search_clauses_en == [
        "a person opens a pot",
        "a person removes food",
    ]


def test_global_ocr_and_asr_are_derived_from_events():
    result = normalize_query_plan(VisualQueryPlan.model_validate({
        "events": [{
            "vi": "slide hướng dẫn chấm điểm",
            "en": "a grading guide slide",
            "ocr": "mở bài thân bài kết bài",
            "asr": "duyên nợ với đề tài miền núi",
        }],
    }))

    assert result.plan.ocr_queries == ["mở bài thân bài kết bài"]
    assert result.plan.asr_queries == ["duyên nợ với đề tài miền núi"]
