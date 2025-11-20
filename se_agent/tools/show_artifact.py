# se_agent/tools/show_artifact.py
from __future__ import annotations
from typing import Any, Dict, Optional

from se_agent.core.tool_patterns import register_tool, DisplayTool
from se_agent.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage


@register_tool
class ShowArtifactTool(DisplayTool):
    """
    Display a stored artifact by id, name, or type in RAW format.
    Returns the artifact's content verbatim along with id/type/name/metadata.
    """

    TOOL_NAME   = "show_artifact"
    DESCRIPTION = "DISPLAY A STORED ARTIFACT (RAW CONTENT) BY ID, NAME, OR TYPE."
    CATEGORY    = "display"

    ARTIFACTS: Dict[str, Any] = {}

    IO_SCHEMA = {
        "inputs": {
            "id":      {"type": "string", "required": False, "description": "Artifact id to show."},
            "name":    {"type": "string", "required": False, "description": "Artifact name (shows most recent)."},
            "type":    {"type": "string", "required": False, "description": "Artifact type (shows most recent)."},
            "package": {"type": "string", "required": False, "description": "Package to search (defaults to agent package)."},
        },
        "outputs": {
            # returns structured dict with raw "content"
        },
    }

    def run(self, input_data, artifacts: ArtifactRegistry, package_name: Optional[str] = None, **kwargs):
        raw = input_data or {}
        pkg_name = raw.get("package") or package_name
        if not pkg_name:
            msg = "❌ No package selected. Pass `package` or use agent.use_package(...)."
            return {"message": msg}

        pkg: ArtifactPackage | None = artifacts.get_package(pkg_name)
        if not pkg:
            msg = f"❌ Package '{pkg_name}' not found."
            return {"message": msg}

        art = None

        # Lookup by id
        if raw.get("id"):
            art = pkg.artifacts.get(raw["id"])
            if not art:
                return {"message": f"No artifact with id '{raw['id']}'."}

        # Lookup by name (most recent)
        if art is None and raw.get("name"):
            name = raw["name"]
            arts = [a for a in pkg.artifacts.values() if a.name == name]
            if not arts:
                return {"message": f"No artifact with name '{name}'."}
            arts.sort(key=lambda a: getattr(a, "_created_at", ""), reverse=True)
            art = arts[0]

        # Lookup by type (most recent)
        if art is None and raw.get("type"):
            t = raw["type"]
            arts = [a for a in pkg.artifacts.values() if a.type == t]
            if not arts:
                return {"message": f"No artifacts of type '{t}'."}
            arts.sort(key=lambda a: getattr(a, "_created_at", ""), reverse=True)
            art = arts[0]

        if art is None:
            return {"message": "❌ Must provide one of 'id', 'name', or 'type'."}

        # ✅ RAW return — no HTML/UI formatting
        return {
            "message": f"Artifact 📋: {art.name or art.id}",
            "artifact_id": art.id,
            "type": art.type,
            "name": getattr(art, "name", None),
            "metadata": art.metadata or {},
            "content": art.content,  # <-- raw, unmodified
        }

