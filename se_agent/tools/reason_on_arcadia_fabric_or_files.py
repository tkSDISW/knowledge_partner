# se_agent/tools/reason_on_arcadia_fabric_or_files.py
from __future__ import annotations

import os
import io
from contextlib import redirect_stdout
from typing import Any, Dict, List, Optional

from se_agent.core.tool_patterns import register_tool, DisplayTool
from se_agent.mcp.artifact_registry import ArtifactRegistry


@register_tool
class ReasonOnArcadiaFabricOrFilesTool(DisplayTool):
    """
    Reason on an optional arcadia_fabric artifact and/or file_reference artifacts.
    Requires at least one input (fabric or file). Optionally primes the reasoning
    with a prompt artifact.
    """
    TOOL_NAME = "reason_on_arcadia_fabric_or_files"
    DESCRIPTION = "Reason on an arcadia_fabric and/or file_reference artifacts using ChatGPTAnalyzer."
    CATEGORY = "display"
    name = TOOL_NAME
    description = DESCRIPTION
    CATEGORY = "display"

    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "arcadia_fabric_name":  {"type": "string", "required": False, "description": "Name of an arcadia_fabric artifact."},
            "arcadia_fabric_id":    {"type": "string", "required": False, "description": "ID of an arcadia_fabric artifact."},
            "prompt_name":          {"type": "string", "required": False, "description": "Name of a prompt artifact (from render_prompt)."},
            "prompt_id":            {"type": "string", "required": False, "description": "ID of a prompt artifact (from render_prompt)."},
            "file_reference_names": {"type": "array",  "required": False, "description": "List of file_reference artifact names to include."},
            "file_reference_ids":   {"type": "array",  "required": False, "description": "List of file_reference artifact IDs to include."},
            "question":             {"type": "string", "required": False, "description": "Optional user question to seed reasoning."},
        },
        "outputs": {
            "message": {"type": "string", "remember": False},
            "html":    {"type": "string", "remember": False},
            "sources": {"type": "array",  "remember": False},
        }
    }

    # ---------- helpers ----------
    def _pkg(self, artifacts: ArtifactRegistry, package_name: Optional[str]) -> str:
        return package_name or getattr(artifacts, "active_package", None)

    def _get_art_by_name(self, artifacts: ArtifactRegistry, pkg_name: str, name: str):
        try:
            pkg = artifacts.get_package(pkg_name)
            if not pkg or not hasattr(pkg, "artifacts"): return None
            matches = [a for a in pkg.artifacts.values() if getattr(a, "name", None) == name]
            if not matches: return None
            matches.sort(key=lambda a: getattr(a, "_created_at", 0), reverse=True)
            return matches[0]
        except Exception:
            return None

    def _get_art_by_id(self, artifacts: ArtifactRegistry, pkg_name: str, art_id: str):
        try:
            return artifacts.get_artifact(pkg_name, art_id)
        except Exception:
            return None

    def _collect_all_of_type(self, artifacts: ArtifactRegistry, pkg_name: str, type_name: str):
        try:
            pkg = artifacts.get_package(pkg_name)
            if not pkg: return []
            return [a for a in pkg.artifacts.values() if getattr(a, "type", "") == type_name]
        except Exception:
            return []

    # ---------- core ----------
    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry, package_name: Optional[str] = None, **_: Any) -> Dict[str, Any]:
        pkg = self._pkg(artifacts, package_name)
        if not pkg:
            return {"message": "❌ No active package.", "displayed": False}

        # --- optional fabric selection ---
        fab_name = input_data.get("arcadia_fabric_name")
        fab_id   = input_data.get("arcadia_fabric_id")
        fabric = None
        if fab_name:
            fabric = self._get_art_by_name(artifacts, pkg, fab_name)
        if not fabric and fab_id:
            fabric = self._get_art_by_id(artifacts, pkg, fab_id)
        if fabric and getattr(fabric, "type", None) != "arcadia_fabric":
            return {"message": f"❌ '{fab_name or fab_id}' is not of type 'arcadia_fabric'.", "displayed": False}

        fab_content = getattr(fabric, "content", {}) if fabric else {}
        yaml_text   = fab_content.get("yaml", "") if fab_content else ""


        # --- prompt selection ---
        prompt_text = ""
        prompt = None
        pr_name = input_data.get("prompt_name")
        pr_id   = input_data.get("prompt_id")
        if pr_name:
            prompt = self._get_art_by_name(artifacts, pkg, pr_name)
        if not prompt and pr_id:
            prompt = self._get_art_by_id(artifacts, pkg, pr_id)
        
        if prompt:
            if getattr(prompt, "type", None) != "prompt":
                return {"message": "❌ Provided prompt is not of type 'prompt'.", "displayed": False}
        
            pcontent = getattr(prompt, "content", None)
        
            # 🔧 be tolerant about content shape:
            if isinstance(pcontent, str):
                # content is just the prompt text
                prompt_text = pcontent
            elif isinstance(pcontent, dict):
                # content is a dict; look for common keys
                prompt_text = str(
                    pcontent.get("text")
                    or pcontent.get("prompt")
                    or pcontent.get("value")
                    or ""
                )
            else:
                # fallback: just stringify whatever is there
                prompt_text = str(pcontent or "")
        
            if not prompt_text:
                return {
                    "message": "⚠️ Prompt artifact has no usable text content; please check it.",
                    "displayed": False,
                }
        # --- file_reference selection ---
        selected_files: List[Dict[str, str]] = []
        req_names = input_data.get("file_reference_names") or []
        req_ids   = input_data.get("file_reference_ids") or []

        all_files = self._collect_all_of_type(artifacts, pkg, "file_reference")
        if req_names or req_ids:
            name_set = {str(n) for n in req_names}
            id_set = {str(i) for i in req_ids}
            for a in all_files:
                if getattr(a, "name", None) in name_set or getattr(a, "id", "") in id_set:
                    path = (getattr(a, "content", {}) or {}).get("file_path")
                    if path and os.path.exists(path):
                        selected_files.append({"name": getattr(a, "name", None) or getattr(a, "id", "")[:8], "path": path})
        else:
            # Default: include all
            for a in all_files:
                path = (getattr(a, "content", {}) or {}).get("file_path")
                if path and os.path.exists(path):
                    selected_files.append({"name": getattr(a, "name", None) or getattr(a, "id", "")[:8], "path": path})

        # --- validation: must have at least one fabric or file ---
        if not fabric and not selected_files:
            return {"message": "❌ Must provide at least one 'arcadia_fabric' or 'file_reference' artifact.", "displayed": False}

        # --- analyzer wiring ---
        try:
            from capella_tools import Open_AI_RAG_manager
        except Exception as e:
            return {"message": f"❌ Failed to import Open_AI_RAG_manager: {e}", "displayed": False}

        sources: List[Dict[str, Any]] = []
        if fabric:
            sources.append({"type": "arcadia_fabric", "name": getattr(fabric, "name", None) or getattr(fabric, "id", "")[:8]})

        try:
            fmt = Open_AI_RAG_manager.ChatGPTAnalyzer(yaml_content=yaml_text if fabric else "")

            # prompt first if provided
            if prompt_text.strip():
                try:
                    fmt.initial_prompt(prompt_text)
                    sources.append({"type": "prompt", "name": getattr(prompt, "name", None) or getattr(prompt, "id", "")[:8], "used": True})
                except Exception as e:
                    sources.append({"type": "prompt", "name": getattr(prompt, "name", None) or getattr(prompt, "id", "")[:8], "used": False, "error": str(e)})

            # add files
            for fr in selected_files:
                try:
                    fmt.add_text_file_to_messages(fr["path"])
                    sources.append({"type": "file_reference", "name": fr["name"], "path": fr["path"], "used": True})
                except Exception as e:
                    sources.append({"type": "file_reference", "name": fr["name"], "path": fr["path"], "used": False, "error": str(e)})

            buf = io.StringIO()
            with redirect_stdout(buf):
                html = fmt.get_response()

            msg_parts = []
            if fabric:
                msg_parts.append(f"fabric '{getattr(fabric, 'name', '')}'")
            if selected_files:
                msg_parts.append(f"{len(selected_files)} file(s)")
            summary = " and ".join(msg_parts)

            return {
                "message": f"🧠 Reasoned on {summary}{' with prompt' if prompt_text else ''}.",
                "html": html,
                "sources": sources,
            }

        except Exception as e:
            return {"message": f"❌ Reasoning failed: {e}", "displayed": False}
