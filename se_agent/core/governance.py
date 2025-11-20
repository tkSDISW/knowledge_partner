
# ------------------------------
# se_agent/core/governance.py
# ------------------------------
from __future__ import annotations
import json
from typing import Any, Dict
from .token_estimator import approx_tokens_from_json

POLICY = {
    "max_tokens_workspace_inject": 40_000,  # per injected object
    # Optional global cap can be enforced elsewhere before model call
}

FORBIDDEN_PHRASES = (
    "<system>", "ignore previous", "disregard prior", "you are chatgpt",
    "override instructions", "act as system", "reset role"
)


def check_token_budget(name: str, payload: Any, limit: int | None = None) -> Dict[str, Any]:
    limit = int(limit or POLICY["max_tokens_workspace_inject"])
    toks = approx_tokens_from_json(payload)
    if toks > limit:
        return {
            "ok": False,
            "tokens": toks,
            "limit": limit,
            "message": (
                f"⚠️ '{name}' is ~{toks:,} tokens, exceeding the workspace injection limit {limit:,}. "
                "Use a tool to filter/summarize or persist a smaller slice."
            ),
        }
    return {"ok": True, "tokens": toks, "limit": limit}


def sanitize_ok(payload: Any) -> Dict[str, Any]:
    try:
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    except Exception:
        text = str(payload)
    lower = text.lower()
    for p in FORBIDDEN_PHRASES:
        if p in lower:
            return {
                "ok": False,
                "message": (
                    "⚠️ Potential prompt-control phrases detected in injected content. "
                    "Sanitize or use a tool instead."
                ),
            }
    return {"ok": True}


def json_serializable(payload: Any) -> Dict[str, Any]:
    try:
        json.dumps(payload, ensure_ascii=False)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "message": f"❌ Value is not JSON-serializable: {e}"}


