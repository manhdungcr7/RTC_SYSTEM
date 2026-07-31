"""Xử lý câu truy vấn: tách mệnh đề, dịch, LLM query-expansion/entity/route/vision-
rerank. Port từ `system/aic/llm.py` (đa provider Anthropic/OpenAI/Gemini, cache đĩa,
fallback envit5 khi không có key) + `system/aic/query.py` (`_split_clauses`) — hợp
nhất vào 1 file vì ở kiến trúc mới, việc "chọn clause nào cho nhánh nào" (mục
"Xử lý query vượt max-token" trong plan) cần nhìn thấy cả 2 phía cùng lúc.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

from config import settings
from core import translate as _translate

# ==================== load .env (port nguyên từ llm.py) ====================


def _load_env():
    for base in (settings.ROOT.parent, Path.cwd()):
        f = base / ".env"
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip().lower().replace("-", "_")
            v = v.strip().strip('"').strip("'")
            if not v:
                continue
            alias = {
                "openai_key": "OPENAI_API_KEY", "openai_api_key": "OPENAI_API_KEY",
                "anthropic_key": "ANTHROPIC_API_KEY", "anthropic_api_key": "ANTHROPIC_API_KEY",
                "gemini_key": "GEMINI_API_KEY", "gemini_api_key": "GEMINI_API_KEY",
                "google_api_key": "GEMINI_API_KEY", "aic_llm_model": "AIC_LLM_MODEL",
            }.get(k)
            if alias and not os.environ.get(alias):
                os.environ[alias] = v


_load_env()

SYSTEM = (
    "Bạn hỗ trợ một hệ thống tìm kiếm video bằng CLIP đa ngữ. "
    "Người dùng đưa mô tả tiếng Việt về một cảnh trong video. "
    "Nhiệm vụ: chuyển thành các mô tả THỊ GIÁC ngắn bằng TIẾNG ANH để tìm ảnh."
)

PROMPT = """Mô tả cảnh (tiếng Việt):
\"\"\"{q}\"\"\"

Hãy trả về JSON: {{"clauses": ["...", "..."]}}

Quy tắc:
- Dịch sang tiếng Anh và tách thành các mệnh đề thị giác. Mỗi phần tử tả MỘT chi tiết nhìn thấy được trong khung hình.
- GIỮ NGUYÊN mọi chi tiết phân biệt: màu sắc, số lượng, vị trí (trái/phải/giữa), tư thế, quần áo, vật thể cụ thể, chữ trên màn hình. ĐỪNG tóm gọn hay bỏ bớt chi tiết — chi tiết càng nhiều càng dễ tìm đúng.
- Chỉ bỏ: câu hỏi, phần suy luận/kiến thức ngoài hình (thứ không nhìn thấy trực tiếp).
- Mỗi mệnh đề nên đầy đủ (8-20 từ), không phải cụm ngắn cụt.
- Tối đa 8 phần tử. Chỉ trả JSON, không giải thích."""


def _provider() -> str | None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    return None


def available() -> bool:
    return _provider() is not None


def _call(prompt: str) -> str:
    p = _provider()
    if p == "anthropic":
        import anthropic
        c = anthropic.Anthropic()
        r = c.messages.create(
            model=os.environ.get("AIC_LLM_MODEL", "claude-sonnet-4-5"),
            max_tokens=800, system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return r.content[0].text
    if p == "openai":
        from openai import OpenAI
        c = OpenAI()
        r = c.chat.completions.create(
            model=os.environ.get("AIC_LLM_MODEL", "gpt-4o-mini"),
            temperature=0,
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": prompt}],
        )
        return r.choices[0].message.content
    if p == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        m = genai.GenerativeModel(os.environ.get("AIC_LLM_MODEL", "gemini-2.0-flash"),
                                  system_instruction=SYSTEM)
        return m.generate_content(prompt).text
    raise RuntimeError("không có API key")


def _parse_clauses(txt: str) -> list[str]:
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return [str(c).strip() for c in data.get("clauses", []) if str(c).strip()][:6]


# ---- cache đĩa: LLM tốn tiền, đừng gọi lại mỗi lần chạy ----
_cache_mem: dict | None = None


def _cache_get(key: str):
    global _cache_mem
    if _cache_mem is None:
        _cache_mem = {}
        if settings.LLM_CACHE_PATH.exists():
            try:
                _cache_mem = json.loads(settings.LLM_CACHE_PATH.read_text(encoding="utf-8"))
            except Exception:
                _cache_mem = {}
    return _cache_mem.get(key)


def _cache_put(key: str, val):
    _cache_mem[key] = val
    settings.LLM_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    settings.LLM_CACHE_PATH.write_text(json.dumps(_cache_mem, ensure_ascii=False), encoding="utf-8")


@lru_cache(maxsize=512)
def _cached_clauses_en(q: str) -> tuple:
    return tuple(_parse_clauses(_call(PROMPT.format(q=q))))


# ==================== tách mệnh đề không-LLM (port từ system/aic/query.py) ====================


def split_clauses(text: str) -> list[str]:
    """Tách mô tả dài thành mệnh đề ngắn — dùng cho fallback không-LLM VÀ cho nhánh
    metaclip2 (đa ngữ, KHÔNG dịch — xem core.config.TRANSLATE_FOR). Đo thực tế: toàn
    văn 70 từ -> GT không lọt top-100; mệnh đề tách riêng -> GT hạng 11 (loãng tín
    hiệu khi encode nguyên khối)."""
    parts = re.split(r"[\n.;]+", text)
    out = []
    for p in parts:
        p = p.strip(" .,;\t")
        if len(p) >= 8:
            out.append(p)
    return out if out else [text.strip()]


_TEMPORAL_FRAMING_RE = re.compile(
    r"^\s*khoảnh khắc\s*(đầu tiên|tiếp theo|kế tiếp|cuối cùng)?\s*(thấy|nhìn thấy)?\s*",
    re.IGNORECASE,
)


def strip_temporal_framing(event_text: str) -> str:
    """Cắt bỏ khung mẫu câu TRAKE của BTC ("Khoảnh khắc đầu tiên/cuối cùng thấy...")
    trước khi dùng làm QUERY OCR/ASR (BM25/ngram khớp CHỮ THẬT, không phải ngữ
    nghĩa) — ĐO THẬT: query nguyên câu "Khoảnh khắc đầu tiên cắt củ năng." khớp 9
    frame trong 1 video (toàn khớp nhờ từ chung "khoảnh khắc/đầu tiên/cắt" xuất
    hiện ở MỌI cảnh cắt gọt), trong khi chỉ "củ năng" khớp ĐÚNG 1 frame — và đó
    KHÔNG phải frame mà hệ thống (chưa vá) đã chọn. Từ chung lấn át từ phân biệt.
    Dùng CẢ cho encode thị giác (metaclip2) — cùng lý do "câu dài loãng tín hiệu"
    đã ghi trong split_clauses()."""
    return _TEMPORAL_FRAMING_RE.sub("", event_text).strip()


def clauses_en(query_vi: str) -> list[str]:
    """Query tiếng Việt -> list mô tả thị giác TIẾNG ANH (dùng cho beit3/pecore).
    Không có key (hoặc lỗi API) -> fallback split_clauses + translate.vi2en — đây
    là đường đi MẶC ĐỊNH, không phải trường hợp hỏng."""
    if available():
        try:
            cl = list(_cached_clauses_en(query_vi))
            if cl:
                return cl
        except Exception as e:
            print(f"[query_service] lỗi API ({type(e).__name__}) -> dùng envit5")
    cl = split_clauses(query_vi)
    return _translate.vi2en(cl)


def clauses_metaclip2(query_vi: str, use_expansion: bool = True) -> list[str]:
    """Clause cho nhánh metaclip2 (đa ngữ) — KHÔNG dịch bắt buộc. Nếu LLM sẵn có VÀ
    USE_QUERY_EXPANSION: dùng biến thể tiếng Anh đa dạng của expand_query() (model
    vẫn hiểu tốt, và đa dạng hoá giúp max-pool); nếu không: tách mệnh đề tiếng Việt
    trực tiếp qua split_clauses() — đúng lý do MetaCLIP-2-worldwide được chọn."""
    if use_expansion and available():
        variants = expand_query(query_vi)
        if variants:
            return variants
    return split_clauses(query_vi)


EXPAND_PROMPT = """Mô tả cảnh video (tiếng Việt hoặc Anh):
\"\"\"{q}\"\"\"

Sinh {n} câu mô tả THỊ GIÁC bằng TIẾNG ANH cho đúng cảnh này, ĐA DẠNG góc nhìn để
tìm ảnh (mỗi câu ≤ 18 từ, độc lập). Trả JSON: {{"variants": ["...", ...]}}

Mỗi câu nhấn một khía cạnh khác nhau:
- chủ thể + hành động chính (literal)
- bối cảnh / địa điểm / loại chương trình (news studio, lecture, outdoor...)
- màu sắc + vị trí + số lượng đối tượng nổi bật
- nếu có chữ/logo/tiêu đề trên màn hình: mô tả nội dung chữ đó
- một cách diễn đạt đồng nghĩa (paraphrase)
GIỮ chi tiết phân biệt (màu/số/vị trí). Chỉ trả JSON."""


def expand_query(query: str, n: int = 6) -> list[str]:
    """Query (Việt/Anh) -> n biến thể caption tiếng Anh, đa dạng góc nhìn. Dùng cho
    multi-query MAX-pool (core.fusion.maxmean_clauses). Có cache đĩa."""
    if not available():
        return []
    key = f"expand::{n}::{query}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        raw = _call(EXPAND_PROMPT.format(q=query, n=n))
        m = re.search(r"\{.*\}", raw, re.S)
        out = []
        if m:
            data = json.loads(m.group(0))
            out = [str(v).strip() for v in data.get("variants", []) if str(v).strip()][:n]
    except Exception as e:
        print(f"[query_service] expand lỗi ({type(e).__name__})")
        out = []
    _cache_put(key, out)
    return out


_OCR_KEYWORDS_PROMPT = """Câu truy vấn tìm một khung hình video (tiếng Việt):
\"\"\"{q}\"\"\"

Trích CHỈ những TÊN RIÊNG/CON SỐ CỤ THỂ mà câu này ĐÃ NÊU RÕ (không suy luận thêm —
khác việc suy luận tên ẩn) và GẦN CHẮC CHẮN xuất hiện DƯỚI DẠNG CHỮ IN TRÊN MÀN HÌNH
(banner, tiêu đề tin tức, phụ đề, biển hiệu, slide, logo, bảng giá) — vd tên tổ
chức/công ty/CLB, tên người/nhân vật cụ thể, tên địa danh (tỉnh/xã/thành phố), số
liệu/ngày tháng/giá cụ thể, tên chương trình/sự kiện.

TUYỆT ĐỐI KHÔNG trích: mô tả MÀU SẮC/TRANG PHỤC (vd "áo trắng", "quần vàng xanh",
"nón đỏ"), mô tả VẬT THỂ/HÀNH ĐỘNG/SỐ LƯỢNG người-vật chung chung (vd "3 tay đua",
"hai người đàn ông"), hay bất kỳ cụm mô tả CẢNH/HÌNH ẢNH nào — những thứ này KHÔNG
phải chữ viết, dù câu có nêu rõ. Chỉ trích nếu bản thân cụm từ đó là loại thường
được IN THÀNH CHỮ (tên riêng/số liệu), không phải thứ người ta MÔ TẢ BẰNG MẮT.

QUAN TRỌNG — KHÔNG trích DANH TỪ CHUNG dù nó có thể xuất hiện trên màn hình dưới
dạng chữ (vd "robot", "máy tính", "xe đạp", "trường học", "bệnh viện", "công ty",
"nghiên cứu"): những từ này QUÁ PHỔ BIẾN, xuất hiện lặp lại ở rất nhiều video
KHÔNG liên quan (đã đo thật: "robot" kéo nhầm cả loạt video tin tức về robot khác
hẳn chủ đề câu hỏi). CHỈ trích khi đó là TÊN RIÊNG CỤ THỂ (viết hoa đầu, định danh
duy nhất — tên người/tổ chức/địa danh/sản phẩm cụ thể) hoặc CON SỐ/NGÀY THÁNG cụ
thể — không phải khái niệm/danh từ chung chung dù có liên quan tới câu hỏi.

Trả JSON: {{"keywords": ["...", ...]}} — tối đa 5 cụm, MỖI cụm NGẮN GỌN (chỉ đúng
tên riêng/số liệu, KHÔNG kèm từ thừa như "một", "tỉnh", "câu lạc bộ"...). Rỗng nếu
câu không nêu tên riêng/số liệu cụ thể nào — RỖNG LÀ BÌNH THƯỜNG, đừng cố trích ép
mô tả cảnh thành "chữ". Chỉ trả JSON, không giải thích."""


def extract_ocr_keywords(query: str) -> list[str]:
    """Trích tên riêng/số liệu ĐÃ NÊU RÕ trong câu (khác resolve_entity() — cái đó
    SUY LUẬN tên ẨN). ĐÃ ĐO THẬT lý do cần hàm này: câu dài tra OCR nguyên văn làm
    LOÃNG tín hiệu — ví dụ "FANA" (tên CLB, chỉ khớp ĐÚNG 2 frame/167,850) bị chìm
    ngoài top-500 khi tra nguyên câu ~40 từ, nhưng tra riêng "FANA" thì trúng ngay
    hạng 1-2. Caller PHẢI tra RIÊNG TỪNG từ khoá (KHÔNG nối chung thành 1 câu) rồi
    fuse qua RRF — đã đo: nối chung "FANA Khánh Hòa" vẫn bị từ phổ biến hơn
    ("Khánh Hòa", 1516 frame khớp) áp đảo mất tín hiệu hiếm ("FANA", 2 frame).
    Trả [] nếu không có API hoặc câu không có tên riêng/số liệu rõ ràng. Có cache đĩa."""
    if not available():
        return []
    key = f"ocrkw::{query}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        raw = _call(_OCR_KEYWORDS_PROMPT.format(q=query))
        m = re.search(r"\{.*\}", raw, re.S)
        d = json.loads(m.group(0)) if m else {}
        out = [str(k).strip() for k in d.get("keywords", []) if str(k).strip()][:5]
    except Exception as e:
        print(f"[query_service] extract_ocr_keywords lỗi ({type(e).__name__})")
        out = []
    _cache_put(key, out)
    return out


_ASR_PARAPHRASE_PROMPT = """Câu truy vấn tìm một khung hình video (tiếng Việt), có thể mô tả chủ
đề/nội dung một bản tin/phóng sự đang được THUYẾT MINH/NÓI:
\"\"\"{q}\"\"\"

Lời thuyết minh THẬT trong video (transcript ASR) hiếm khi dùng ĐÚNG từ ngữ của câu
truy vấn — người dẫn/phóng viên diễn đạt theo cách nói tự nhiên, có thể dùng từ
đồng nghĩa, tên riêng phiên âm khác, hoặc câu chữ hoàn toàn khác dù CÙNG Ý NGHĨA.

Hãy tưởng tượng bạn là phóng viên đang thuyết minh đúng nội dung câu truy vấn mô
tả, viết ra 3-5 CÂU/CỤM NGẮN khác nhau (mỗi câu 5-15 từ) mà một bản tin THẬT có
thể nói ra để truyền tải đúng ý nghĩa đó — có thể diễn đạt lại bằng từ đồng nghĩa,
tên riêng phiên âm kiểu Việt (vd "Lausanne" -> "Lô-dan"), hoặc cách nói khác nhau
cho CÙNG một sự việc/chủ đề. KHÔNG cần giữ nguyên câu gốc.

BẮT BUỘC viết TOÀN BỘ bằng TIẾNG VIỆT (kể cả tên riêng nước ngoài phải phiên âm
kiểu người dẫn chương trình Việt Nam hay nói, KHÔNG giữ nguyên tiếng Anh) — vì
transcript ASR thật của bản tin Việt Nam luôn là tiếng Việt, câu tiếng Anh sẽ
KHÔNG khớp được gì cả.

Trả JSON: {{"paraphrases": ["...", ...]}}. Chỉ trả JSON, không giải thích."""


def expand_asr_queries(query: str) -> list[str]:
    """Sinh vài biến thể "giọng bản tin" của câu truy vấn để tra ASR (BM25) theo Ý
    NGHĨA thay vì chỉ khớp đúng từ — ASR không có tầng vector riêng (tránh thêm
    index FAISS mới, tốn RAM), nên bù bằng cách nới rộng phía TỪ KHOÁ trước
    khi tra BM25 (LLM đóng vai "phóng viên" diễn đạt lại). Trả [] nếu không có API
    hoặc lỗi. Có cache đĩa."""
    if not available():
        return []
    key = f"asrpara::{query}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        raw = _call(_ASR_PARAPHRASE_PROMPT.format(q=query))
        m = re.search(r"\{.*\}", raw, re.S)
        d = json.loads(m.group(0)) if m else {}
        out = [str(p).strip() for p in d.get("paraphrases", []) if str(p).strip()][:5]
    except Exception as e:
        print(f"[query_service] expand_asr_queries lỗi ({type(e).__name__})")
        out = []
    _cache_put(key, out)
    return out


_ROUTE_PROMPT = """Câu truy vấn tìm một khung hình video (tiếng Việt):
\"\"\"{q}\"\"\"

Hệ thống tìm kiếm có 3 tín hiệu phụ ngoài hình ảnh. Hãy chấm MỖI tín hiệu có HỮU ÍCH
để tìm ĐÚNG khung hình này không, thang 0.0-2.0 (0=vô ích, cao=rất quan trọng):
- "ocr": CHỮ HIỆN TRÊN MÀN HÌNH (biển hiệu, slide, băng rôn, tên chương trình, số
  liệu, giá, bảng biểu). Cao khi câu nhắc tới chữ/số/nhãn nhìn thấy trong khung hình.
- "asr": LỜI NÓI/THUYẾT MINH (chủ đề mẩu tin, tên riêng người/nơi được NÓI chứ không
  hiện trên hình). Cao khi câu hỏi về chủ đề/thông tin mà người dẫn sẽ đọc.
- "object": VẬT THỂ CỤ THỂ + MÀU + VỊ TRÍ đếm được (vd "2 quả cà chua", "áo đỏ bên trái").
  Cao khi câu tả rõ vật thể/màu/số lượng; thấp khi câu tả cảnh/không khí chung chung.
Chỉ trả JSON: {{"ocr": x, "asr": y, "object": z}}"""


def route_query(query: str) -> dict | None:
    """Phân tích TRỌNG TÂM của query -> trọng số động cho OCR/ASR/object. Trả None
    nếu không có API -> caller fallback về trọng số tĩnh theo kind."""
    if not available():
        return None
    key = f"route::{query}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        raw = _call(_ROUTE_PROMPT.format(q=query))
        m = re.search(r"\{.*\}", raw, re.S)
        d = json.loads(m.group(0)) if m else {}
        out = {k: max(0.0, min(2.0, float(d.get(k, 0)))) for k in ("ocr", "asr", "object")}
    except Exception as e:
        print(f"[query_service] route lỗi ({type(e).__name__})")
        out = None
    _cache_put(key, out)
    return out


_ENTITY_PROMPT = """Câu truy vấn tìm một khung hình video (tiếng Việt), có thể chứa MÔ TẢ MƠ HỒ
cần SUY LUẬN TRI THỨC THẾ GIỚI để suy ra thực thể cụ thể (tên riêng người/nơi/sự kiện/số liệu),
thay vì mô tả trực tiếp thứ nhìn thấy được:
\"\"\"{q}\"\"\"

Nếu câu có phần như vậy (vd "chí sĩ yêu nước dạy làm báo đầu TK20" -> "Huỳnh Thúc Kháng";
"giải Nobel 2019 cho vật dụng quen thuộc" -> "pin lithium-ion"; "rừng nhiệt đới lớn nhất thế
giới" -> "rừng Amazon"), hãy SUY RA thực thể cụ thể đó. Đây là TÊN RIÊNG/SỰ VIỆC CÓ THỂ XUẤT
HIỆN DẠNG CHỮ trên màn hình (banner/tiêu đề tin tức) hoặc trong lời thuyết minh -> dùng để tìm
bằng OCR/ASR, KHÔNG phải để mô tả hình ảnh.

Trả JSON: {{"entities": ["...", ...], "confidence": "high"/"medium"/"low"}}
- "entities": TỐI ĐA 3 cụm từ/tên riêng NGẮN GỌN (tiếng Việt, đúng cách viết có khả năng xuất
  hiện trên banner tin tức thật) mà câu này CÓ THỂ đang ám chỉ. Rỗng nếu câu không có phần cần
  suy luận tri thức nào (chỉ mô tả thị giác trực tiếp).
- "confidence": mức tự tin của SUY LUẬN (không phải mức chắc chắn có OCR khớp).
Chỉ trả JSON, không giải thích."""


def resolve_entity(query: str) -> dict | None:
    """Suy luận TRI THỨC THẾ GIỚI trong query mơ hồ -> tên riêng/thực thể cụ thể có
    thể tìm bằng OCR/ASR. Trả None nếu không có API. Có cache đĩa."""
    if not available():
        return None
    key = f"entity::{query}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        raw = _call(_ENTITY_PROMPT.format(q=query))
        m = re.search(r"\{.*\}", raw, re.S)
        d = json.loads(m.group(0)) if m else {}
        ents = [str(e).strip() for e in d.get("entities", []) if str(e).strip()][:3]
        out = {"entities": ents, "confidence": str(d.get("confidence", "low"))}
    except Exception as e:
        print(f"[query_service] resolve_entity lỗi ({type(e).__name__})")
        out = None
    _cache_put(key, out)
    return out


def _img_data_url(path, max_side: int = 768) -> str:
    import base64
    import io

    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.size
    if max(w, h) > max_side:
        s = max_side / max(w, h)
        im = im.resize((int(w * s), int(h * s)))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


_RERANK_SYS = ("Bạn là giám khảo truy vấn ảnh. Với MỖI ảnh, chấm 0-100 mức khớp với "
               "mô tả (100 = khớp mọi chi tiết; 0 = không liên quan). Xét kỹ các chi "
               "tiết nhỏ: màu áo, vật cầm trên tay, số lượng người, chữ trên màn hình. "
               "CHỈ trả JSON: {\"scores\": [số, ...]} đúng thứ tự ảnh, không giải thích.")


def rerank_vision(query_vi: str, image_paths, detail: str = "low",
                  max_side: int = 768) -> list[float] | None:
    """Chấm lại 1 danh sách ảnh ứng viên theo query (gpt-4o-mini vision, prototype
    chỉ OpenAI). Trả list điểm 0-100 (cùng thứ tự), hoặc None nếu không gọi được."""
    if _provider() != "openai":
        return None
    try:
        from openai import OpenAI
        c = OpenAI()
        content = [{"type": "text",
                    "text": f"Mô tả cần tìm:\n\"{query_vi}\"\n\nChấm {len(image_paths)} "
                            f"ảnh dưới đây theo đúng thứ tự."}]
        for p in image_paths:
            content.append({"type": "image_url",
                            "image_url": {"url": _img_data_url(p, max_side),
                                          "detail": detail}})
        r = c.chat.completions.create(
            model=os.environ.get("AIC_LLM_MODEL", "gpt-4o-mini"), temperature=0,
            messages=[{"role": "system", "content": _RERANK_SYS},
                      {"role": "user", "content": content}],
        )
        m = re.search(r"\{.*\}", r.choices[0].message.content, re.S)
        scores = json.loads(m.group(0)).get("scores", []) if m else []
        scores = [float(x) for x in scores]
        if len(scores) != len(image_paths):
            print(f"[rerank] LLM trả {len(scores)} điểm cho {len(image_paths)} ảnh -> bỏ")
            return None
        return scores
    except Exception as e:
        print(f"[rerank] lỗi ({type(e).__name__}: {e})")
        return None
