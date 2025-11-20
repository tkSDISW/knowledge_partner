# se_agent/tools/name_artifact.py
from __future__ import annotations
from typing import Any, Dict


from se_agent.core.tool_patterns import register_tool, DisplayTool
from se_agent.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage


@register_tool
class NameArtifactTool(DisplayTool):
    """
    Assign a human-friendly name to an existing artifact so it can be recalled by name later.
    If both 'id' and 'type' are omitted, returns an error. If 'type' is provided, the most
    recent artifact of that type in the package is used.
    """

    TOOL_NAME   = "name_artifact"
    DESCRIPTION = "ASSIGN A NAME TO AN EXISTING ARTIFACT (LOOKUP BY ID OR LATEST OF TYPE)."
    CATEGORY    = "management"

    ARTIFACTS: Dict[str, Any] = {}  # no new artifact type defined

    IO_SCHEMA = {
        "inputs": {
            "name":    {"type": "string", "required": True,  "description": "Name to assign."},
            "id":      {"type": "string", "required": False, "description": "Artifact id to rename."},
            "type":    {"type": "string", "required": False, "description": "Artifact type; uses most recent if 'id' not given."},
            "package": {"type": "string", "required": False, "description": "Package to search (defaults to agent package)."},
        },
        "outputs": {
            # No artifact is created; we just rename. Returning identifiers in the result is enough.
        },
    }

    def run(self, input_data, artifacts: ArtifactRegistry, package_name=None, **kwargs):
        raw = input_data or {}
        new_name = raw.get("name")
        art_id   = raw.get("id")
        art_type = raw.get("type")
        pkg_name = raw.get("package") or package_name

        if not new_name:
            msg = "❌ Missing 'name'. Example: {\"type\":\"hierarchy\",\"name\":\"BOM\"}"
            return {"message": msg, "ui": msg, "html": msg}

        if not pkg_name:
            msg = "❌ No package selected. Pass `package` or use agent.use_package(...)."
            return {"message": msg, "ui": msg, "html": msg}

        pkg: ArtifactPackage | None = artifacts.get_package(pkg_name)
        if not pkg or not getattr(pkg, "artifacts", None):
            msg = f"❌ Package '{pkg_name}' not found or empty."
            return {"message": msg, "ui": msg, "html": msg}

        # Resolve target artifact
        target = None
        if art_id:
            target = pkg.artifacts.get(art_id)
            if not target:
                msg = f"❌ Artifact id '{art_id}' not found in '{pkg_name}'."
                return {"message": msg, "ui": msg, "html": msg}
        elif art_type:
            cands = [a for a in pkg.artifacts.values() if getattr(a, "type", None) == art_type]
            if not cands:
                msg = f"❌ No artifacts of type '{art_type}' found in '{pkg_name}'."
                return {"message": msg, "ui": msg, "html": msg}
            cands.sort(key=lambda a: getattr(a, "_created_at", ""), reverse=True)
            target = cands[0]
        else:
            msg = "❌ Provide 'id' or 'type'."
            return {"message": msg, "ui": msg, "html": msg}

        # Apply name
        target.name = new_name
        if isinstance(getattr(target, "metadata", None), dict):
            target.metadata["name"] = new_name

        short_id = (getattr(target, "id", "") or "")[:8]
        announce = (
            f"✅ Artifact 📋 assigned: name='{new_name}' id='{short_id}' "
            f"type='{target.type}' in package '{pkg_name}'"
        )
        setattr(target, "_announce", announce)

        msg = f"📋 artifact id='{short_id}' type='{target.type}' named '{new_name}'"
        html = "<div style='font-family:system-ui;line-height:1.35'>" + msg + "</div>"
        return {"message": msg, "ui": msg, "html": html, "artifact_id": target.id, "type": target.type, "name": target.name}



