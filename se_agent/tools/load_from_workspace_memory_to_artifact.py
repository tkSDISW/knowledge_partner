
# ------------------------------
# se_agent/tools/recall_from_workspace_memory_to_artifact.py
# ------------------------------
from __future__ import annotations
from typing import Any, Dict, Optional
from se_agent.core.tool_patterns import register_tool, TransformTool
from se_agent.mcp.artifact_registry import ArtifactRegistry
from .workspace_store import _pkg_name, _load_ws, _save_ws, _now_iso
from se_agent.core.governance import json_serializable

__all__ = ["LaadFromWorkspaceMemoryToArtifactTool"]

@register_tool
class LoadFromWorkspaceMemoryToArtifactTool(TransformTool):
    """
    Creates a registry artifact from a workspace memory entry, enabling tools to consume it.
    """
    TOOL_NAME = "load_from_workspace_memory_to_artifact"
    DESCRIPTION = "LOAD A WORKSPACE MEMORY ENTRY AS A TYPED ARTIFACT (FOR TOOL USE)."
    CATEGORY = "transform"

    ARTIFACTS: Dict[str, Any] = {}

    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "name": {"type": "string", "required": True, "description": "Workspace memory entry name."},
            "artifact_type": {"type": "string", "required": True, "description": "Target artifact type (e.g., 'table','capella_fabric')."},
            "persist_name": {"type": "string", "required": False, "description": "Name to assign to the new artifact (defaults to entry name)."},
        },
        "outputs": {
            "artifact_id": {"type": "string", "remember": True},
        },
    }

    name = TOOL_NAME
    description = DESCRIPTION

    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry, package_name: Optional[str] = None, **_: Any) -> Dict[str, Any]:
        pkg = _pkg_name(artifacts, package_name)
        if not pkg:
            return {"message": "❌ No active package."}

        entry_name = input_data.get("name")
        target_type = input_data.get("artifact_type")
        persist_name = input_data.get("persist_name") or entry_name

        ws_art, ws = _load_ws(artifacts, pkg)
        entry = ws.get("memory", {}).get(entry_name)
        if not entry:
            return {"message": f"❌ Workspace memory entry '{entry_name}' not found."}

        value = entry.get("value")
        ser = json_serializable(value)
        if not ser["ok"]:
            return {"message": ser["message"]}

        meta = {"ui_summary": f"Artifact 📋 created from workspace memory ⚙️ '{entry_name}'", "name": persist_name}
        new_art = artifacts.add_artifact(pkg, target_type, value, meta)
        # Optionally stamp provenance back into the workspace entry
        entry["materialized_at"] = _now_iso()
        entry["artifact_id"] = getattr(new_art, "id", None)
        _save_ws(artifacts, pkg, ws_art, ws)

        return {
            "message": f"✅ Created artifact 📋'{persist_name}' (type={target_type}).",
            "artifact_id": getattr(new_art, "id", None),
        }

