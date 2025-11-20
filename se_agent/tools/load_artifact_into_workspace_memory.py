# se_agent/tools/load_artifact_into_workspace_memory.py
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
import json
from datetime import datetime, timezone

from se_agent.core.tool_patterns import register_tool, TransformTool
from se_agent.mcp.artifact_registry import ArtifactRegistry, Artifact
from .workspace_store import _pkg_name, _load_ws, _save_ws, _now_iso
from se_agent.core.governance import check_token_budget, sanitize_ok, json_serializable

def _err(msg: str) -> Dict[str, Any]:
    return {"message": f"❌ {msg}"}

def _extract(art: Artifact) -> Tuple[Any, str, str]:
    """Return (value, name, type) for your Artifact class."""
    if not isinstance(art, Artifact):
        # ultra-defensive: allow dict-like records if they ever appear
        t = getattr(art, "type", None) or (art.get("type") if isinstance(art, dict) else "value")
        nm = getattr(art, "name", None) if hasattr(art, "name") else (
            (art.get("metadata", {}) or {}).get("name") if isinstance(art, dict) else None
        )
        val = getattr(art, "content", None) if hasattr(art, "content") else (art.get("content") if isinstance(art, dict) else art)
        return val, (nm or "artifact"), (t or "value")
    return art.content, (art.name or "artifact"), (art.type or "value")

def _first_or_none(seq):
    return next(iter(seq), None)

@register_tool
class LoadArtifactWorkspaceMemoryTool(TransformTool):
    """
    Load an artifact (by explicit name OR latest of a given type) into workspace memory.
    Optional rename via new_name. Also returns a one-shot prompt injection.
    """
    TOOL_NAME = "load_artifact_into_workspace_memory"
    DESCRIPTION = "Load an artifact into workspace ⚙️ memory by name or latest type; optional rename; returns one-shot injection."
    CATEGORY = "transform"
    ARTIFACTS: Dict[str, Any] = {}

    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "artifact_name": {"type": "string", "required": False, "description": "Exact artifact name to load (case-insensitive fallback)."},
            "recent_type":   {"type": "string", "required": False, "description": "Artifact type to fetch latest of (exact match to Artifact.type)."},
            "new_name":      {"type": "string", "required": False, "description": "Optional workspace key; defaults to artifact name."},
            "type":          {"type": "string", "required": False, "description": "Optional semantic type override for the workspace entry."},
            "value":         {"type": "any",    "required": False, "description": "Direct value to store; bypass lookup entirely."},
            "max_tokens":    {"type": "integer","required": False, "description": "Token budget for injection governance override."},
        },
        "outputs": {
            "inject_once": {"type": "string", "remember": False},
            "tokens":      {"type": "integer","remember": False},
            "origin_name": {"type": "string", "remember": False},
            "saved_as":    {"type": "string", "remember": False},
            "origin_type": {"type": "string", "remember": False},
        },
    }

    name = TOOL_NAME
    description = DESCRIPTION

    # --- helpers bound to your ArtifactRegistry API ---
    def _by_name(self, reg: ArtifactRegistry, pkg_name: str, name: str) -> Optional[Artifact]:
        art = reg.get_artifact_by_name(pkg_name, name)
        if art:
            return art
        # fallback: case-insensitive scan of names within the package
        pkg = reg.get_package(pkg_name)
        if not pkg:
            return None
        target = name.strip().lower()
        matches = [a for a in pkg.artifacts.values() if (a.name or "").lower() == target]
        return _first_or_none(sorted(matches, key=lambda a: getattr(a, "_created_at", ""), reverse=True)) or None

    def _latest_of_type(self, reg: ArtifactRegistry, pkg_name: str, type_: str) -> Optional[Artifact]:
        if not type_:
            return None
        return reg.get_latest_by_type(pkg_name, type_)

    # --- main run ---
    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry, package_name: Optional[str] = None, **_: Any) -> Dict[str, Any]:
        pkg = artifacts.get_active_package()
        if not pkg and package_name:
            pkg = artifacts.get_package(package_name)
        if not pkg:
            return _err("No active package. (use_package before calling this tool)")

        artifact_name: Optional[str] = input_data.get("artifact_name")
        recent_type:  Optional[str]  = input_data.get("recent_type")
        new_name:     Optional[str]  = input_data.get("new_name")
        explicit_type:Optional[str]  = input_data.get("type")
        direct_value                = input_data.get("value")
        max_tokens                  = input_data.get("max_tokens")

        origin_name = ""
        origin_type = ""
        value       = None

        if direct_value is not None:
            # bypass lookup entirely
            value = direct_value
            origin_name = artifact_name or new_name or "value"
            origin_type = explicit_type or "value"
        else:
            # resolve via registry
            art: Optional[Artifact] = None
            if artifact_name:
                art = self._by_name(artifacts, pkg.name, artifact_name)
                if not art:
                    # show a few known names to help user
                    known = [a.name for a in pkg.artifacts.values() if a.name][:18]
                    hint = ", ".join(known[:15]) + (" ..." if len(known) > 15 else "")
                    return _err(f"Artifact named '{artifact_name}' not found in package '{pkg.name}'. Known names: {hint or 'none'}")
            elif recent_type:
                art = self._latest_of_type(artifacts, pkg.name, recent_type)
                if not art:
                    # show available types
                    types = sorted({a.type for a in pkg.artifacts.values() if a.type})
                    hint = ", ".join(types[:15]) + (" ..." if len(types) > 15 else "")
                    return _err(f"No artifact of type '{recent_type}' found. Available types: {hint or 'none'}")
            else:
                return _err("Provide either 'artifact_name', 'recent_type', or 'value'.")

            value, origin_name, origin_type = _extract(art)
            if explicit_type:
                origin_type = explicit_type

        ws_key = (new_name or origin_name or artifact_name or "workspace_item").strip()

        # governance
        ser = json_serializable(value)
        if not ser["ok"]:
            return _err(ser["message"])
        safe = sanitize_ok(value)
        if not safe["ok"]:
            return _err(safe["message"])
        budget = check_token_budget(ws_key, value, max_tokens)
        if not budget["ok"]:
            return _err(budget["message"])

        # save into workspace store
        ws_art, ws = _load_ws(artifacts, pkg.name)
        ws.setdefault("memory", {})
        ws["memory"][ws_key] = {
            "type": explicit_type or origin_type or "value",
            "value": value,
            "updated_at": _now_iso(),
            "origin_artifact": origin_name or artifact_name or "",
        }

        # one-shot injection
        try:
            as_text = json.dumps(value, ensure_ascii=False)
        except Exception:
            as_text = str(value)
        ws.setdefault("injections_once", {})[ws_key] = as_text[:64]  # small digest/token
        _save_ws(artifacts, pkg.name, ws_art, ws)

        snippet = (
            f"Workspace memory: {ws_key} (type={explicit_type or origin_type or 'value'})\n"
            f"Content:\n{as_text}"
        )

        return {
            "message": (
                f"✅ Loaded '{origin_name or artifact_name}' as '{ws_key}' into workspace memory ⚙️ "
                f"(type={explicit_type or origin_type or 'value'}, tokens~{budget['tokens']:,})."
            ),
            "inject_once": snippet,
            "tokens": budget["tokens"],
            "origin_name": origin_name or artifact_name or "",
            "saved_as": ws_key,
            "origin_type": explicit_type or origin_type or "value",
        }
