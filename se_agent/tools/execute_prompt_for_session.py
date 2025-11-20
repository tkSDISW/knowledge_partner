# se_agent/tools/execute_prompt_for_session.py
from __future__ import annotations
from typing import Any, Dict, Optional, List
from se_agent.core.tool_patterns import register_tool, TransformTool
from se_agent.mcp.artifact_registry import ArtifactRegistry, Artifact
from se_agent.tools.workspace_store import _load_ws, _save_ws, _now_iso
from se_agent.core.session_manager import SessionManager

def _find_by_name_ci(reg: ArtifactRegistry, pkg: str, name: str) -> Optional[Artifact]:
    a = reg.get_artifact_by_name(pkg, name)
    if a: return a
    p = reg.get_package(pkg)
    if not p: return None
    target = (name or "").strip().lower()
    for x in p.artifacts.values():
        if (x.name or "").lower() == target:
            return x
    return None

@register_tool
class ExecutePromptForSession(TransformTool):
    name = "execute_prompt_for_session"
    description = "Start a Guided Session from a required prompt artifact; optionally attach other artifacts (incl. file_reference) into Session Workspace Memory."
    TOOL_NAME   = name
    DESCRIPTION = description
    CATEGORY = "transform"
    IO_SCHEMA = {
        "inputs": {
            "prompt_artifact_name": {"type": "string", "required": True},
            "include_artifact_names": {"type": "array", "items": {"type":"string"}, "required": False},
            "include_latest_by_types": {"type": "array", "items": {"type":"string"}, "required": False}
        },
        "outputs": {
            "switch_contract": {"type": "string", "remember": False},
            "session_type": {"type": "string", "remember": False},
            "session_id": {"type": "string", "remember": False},
            "next_prompt": {"type": "string", "remember": False},
            "progress": {"type": "object", "remember": False},
            "ui": {"type": "string", "remember": False},
            "attached": {"type": "array", "remember": False}
        }
    }

    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry, package_name: Optional[str] = None, **_):
        pkg = artifacts.get_active_package().name if not package_name else package_name
        name = (input_data.get("prompt_artifact_name") or "").strip()
        if not name:
            return {"message": "❌ 'prompt_artifact_name' is required."}
    
        prompt_art = _find_by_name_ci(artifacts, pkg, name)
        if not prompt_art:
            return {"message": f"❌ Prompt artifact '{name}' not found."}
    
        seed = getattr(prompt_art, "content", None)
        if not isinstance(seed, str) or not seed.strip():
            return {"message": f"❌ Prompt artifact '{name}' has no text content."}
    
        # optional attachments (unchanged)
        attach: List[Artifact] = []
        for nm in (input_data.get("include_artifact_names") or []):
            a = _find_by_name_ci(artifacts, pkg, nm)
            if a: attach.append(a)
        for typ in (input_data.get("include_latest_by_types") or []):
            a = artifacts.get_latest_by_type(pkg, typ)
            if a: attach.append(a)
    
        # tiny shim spec (just for artifact naming later)
        spec = {
            "title": prompt_art.name,
            "session": {"type": "freeform", "steps": []},
            "artifact": {
                "type": "session_summary",
                "name_template": "Session Summary: {{ title }} ({{ now }})",
                "content_template": "{{ answers | tojson(indent=2) }}"  # not used; Agent will LLM-summarize transcript
            }
        }
    
        mgr = SessionManager(_load_ws, _save_ws, _now_iso)
        sess = mgr.start(artifacts, pkg, prompt_spec=spec, prompt_name=prompt_art.name, attachments=attach)
        sess.llm_mode = True
        sess.llm_seed = seed
        sess.llm_style = "freeform"
        mgr.store(artifacts, pkg, sess)
    
        # No plan, no auto-question. Just tell the user how to proceed.
        return {
            "switch_contract": "SESSION",
            "session_type": "freeform",
            "session_id": sess.sid,
            "ui": (
                "**Freeform session started.**<br>"
                "I’ll facilitate; you can brainstorm, outline, or think aloud. "
                "Type **`finish`** anytime to synthesize a summary artifact, or **`cancel`** to abort."
            ),
            "attached": [
                {"name": getattr(a, "name", None), "type": getattr(a, "type", None)}
                for a in attach
            ],
            "seed": seed,  # 👈 add this
        }

