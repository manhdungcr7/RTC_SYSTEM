"""Kiểm tra/chuẩn hoá JSON xuất từ GPT Explore trước khi dùng để retrieval."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from api.schemas.query_plan import (QueryPlanImportRequest, QueryPlanValidationResponse,
                                    VisualQueryPlan)

router = APIRouter(prefix="/query/plan", tags=["query-plan"])


def _clean_list(values: list[str], limit: int) -> list[str]:
    return list(dict.fromkeys(str(x).strip() for x in values if str(x).strip()))[:limit]


def _aligned_translations(plan: VisualQueryPlan) -> list[str]:
    """Giữ đúng vị trí bản dịch so với search_clauses, kể cả khi hai câu trùng nhau."""
    supplied = [str(x).strip() for x in plan.search_clauses_en]
    event_fallbacks = [event.en.strip() for event in plan.events]
    aligned: list[str] = []
    for i, clause in enumerate(plan.search_clauses):
        translated = supplied[i] if i < len(supplied) else ""
        if not translated and i < len(event_fallbacks):
            translated = event_fallbacks[i]
        aligned.append(translated or clause)
    return aligned


def normalize_query_plan(plan: VisualQueryPlan) -> QueryPlanValidationResponse:
    """Chuẩn hoá quyết định có thể suy ra chắc chắn; không tự bịa thêm nội dung."""
    warnings: list[str] = []
    plan.original_query = plan.original_query.strip()
    plan.distinctive_features = _clean_list(plan.distinctive_features, 12)
    plan.possible_confusions = _clean_list(plan.possible_confusions, 12)
    plan.ocr_queries = _clean_list(plan.ocr_queries, 8)
    plan.asr_queries = _clean_list(plan.asr_queries, 8)

    # Trường theo-event là nguồn chính cho Temporal; hai mảng tổng hợp phục vụ
    # Search. GPT đôi khi chỉ điền một phía, nên suy ra phía tổng hợp mà không
    # phát minh thêm từ khóa.
    if not plan.ocr_queries:
        plan.ocr_queries = _clean_list([event.ocr for event in plan.events], 8)
    if not plan.asr_queries:
        plan.asr_queries = _clean_list([event.asr for event in plan.events], 8)

    # Search cần các mệnh đề độc lập. Nếu GPT không sinh riêng, dùng từng sự kiện
    # làm fallback có kiểm soát thay vì gọi lại model mini và làm mất phân tích.
    if not plan.search_clauses:
        plan.search_clauses = [e.vi or e.en for e in plan.events]
        warnings.append("Thiếu search_clauses; đã dùng nội dung từng sự kiện.")
    plan.search_clauses = _clean_list(plan.search_clauses, 8)

    supplied_translation_count = len([x for x in plan.search_clauses_en if str(x).strip()])
    plan.search_clauses_en = _aligned_translations(plan)
    if supplied_translation_count < len(plan.search_clauses):
        warnings.append("Thiếu một số bản dịch tiếng Anh; đã dùng bản dịch sự kiện hoặc nguyên văn làm dự phòng.")

    # Không tin recommended_mode do GPT tự ghi khi cấu trúc đã cho câu trả lời chắc chắn.
    plan.recommended_mode = "temporal" if len(plan.events) >= 2 else "search"

    if len(plan.events) == 1:
        plan.events[0].anchor = False
        plan.max_gap_s = None
    else:
        selected = [i for i, event in enumerate(plan.events) if event.anchor]
        if len(selected) != 2:
            for event in plan.events:
                event.anchor = False
            plan.events[0].anchor = True
            plan.events[-1].anchor = True
            warnings.append("Cần đúng hai neo; đã chọn sự kiện đầu và cuối.")
        if plan.max_gap_s in (None, 0):
            plan.max_gap_s = 120

    if not plan.context.vi and plan.context.en:
        warnings.append("Kế hoạch chỉ có bối cảnh tiếng Anh; MetaCLIP-2 vẫn dùng được nhưng UI sẽ ít dễ kiểm tra hơn.")
    elif not plan.context.vi and not plan.context.en:
        warnings.append("Không có bối cảnh chung; hệ thống sẽ chỉ tìm theo từng sự kiện.")

    return QueryPlanValidationResponse(plan=plan, warnings=warnings)


@router.post("/validate", response_model=QueryPlanValidationResponse)
def validate_query_plan(req: QueryPlanImportRequest) -> QueryPlanValidationResponse:
    try:
        plan = VisualQueryPlan.model_validate(req.plan)
    except ValidationError as exc:
        errors = [
            {"field": ".".join(str(x) for x in e["loc"]), "message": e["msg"]}
            for e in exc.errors(include_url=False)
        ]
        raise HTTPException(status_code=422, detail={"message": "JSON kế hoạch không hợp lệ", "errors": errors})
    return normalize_query_plan(plan)
