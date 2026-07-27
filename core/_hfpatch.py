"""Vá lỗi mạng của transformers 4.57 khi nạp tokenizer. Port nguyên từ
`system/aic/_hfpatch.py`.

Bug: PreTrainedTokenizerBase._patch_mistral_regex gọi huggingface_hub.model_info
(một request MẠNG) một cách VÔ ĐIỀU KIỆN với model không phải đường dẫn cục bộ —
bất kể local_files_only=True. Khi mạng chậm / HF trả 504 thì cả pipeline treo/chết,
dù model đã có sẵn trong cache.

import module này TRƯỚC khi nạp bất kỳ tokenizer nào.
"""
from __future__ import annotations


def apply():
    try:
        from transformers.tokenization_utils_base import PreTrainedTokenizerBase
    except Exception:
        return
    orig = getattr(PreTrainedTokenizerBase, "_patch_mistral_regex", None)
    if orig is None:
        return
    if getattr(orig, "_aic_patched", False):
        return

    def _noop(cls, tokenizer, *a, **k):
        return tokenizer

    _noop._aic_patched = True
    PreTrainedTokenizerBase._patch_mistral_regex = classmethod(_noop)


apply()
