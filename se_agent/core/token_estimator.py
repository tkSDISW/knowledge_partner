
# ------------------------------
# se_agent/core/token_estimator.py
# ------------------------------
from __future__ import annotations
import json

def approx_tokens_from_text(s: str) -> int:
    try:
        n = len(s.encode("utf-8"))
    except Exception:
        n = len(str(s))
    return max(1, n // 4)  # ~4 chars/token heuristic


def approx_tokens_from_json(obj) -> int:
    try:
        s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        s = str(obj)
    return approx_tokens_from_text(s)

