from __future__ import annotations

from typing import Any, Dict, Optional

from se_agent.core.tool_registry import BaseTool
from se_agent.core.tool_patterns import register_tool
from se_agent.mcp.artifact_registry import ArtifactRegistry


@register_tool
class CreateArtifactTool(BaseTool):
    """
    Generic artifact creation tool.

    Creates an artifact in the specified (or active) package,
    with a caller-supplied name, type, and content.
    """

    TOOL_NAME   = "create_artifact"
    DESCRIPTION = "Create a new artifact with the given name, type, and content in the target package."
    CATEGORY    = "transform"

    # No new artifact *schema* here – this tool is generic by design.
    ARTIFACTS: Dict[str, Any] = {}

    IO_SCHEMA = {
        "inputs": {
            "name": {
                "type": "string",
                "description": "Logical name of the new artifact (stored in metadata).",
                "required": True,
            },
            "type": {
                "type": "string",
                "description": "Artifact type (e.g., 'personality_profile', 'prompt_spec', 'session_summary').",
                "required": True,
            },
            "content": {
                "type": "any",
                "description": "Artifact content. May be string, dict, or other JSON-serializable structure.",
                "required": True,
            },
            "package": {
                "type": "string",
                "description": "Optional package name. If omitted, the agent's active package is used.",
                "required": False,
            },
            "metadata": {
                "type": "dict",
                "description": "Optional extra metadata to attach to the artifact.",
                "required": False,
            },
        },
        "outputs": {
            "artifact_id": {
                "type": "string",
                "remember": True,   # let the agent keep a reference in conversation memory
                "description": "ID of the created artifact.",
            },
            "artifact_name": {
                "type": "string",
                "remember": False,
                "description": "Name of the created artifact.",
            },
            "artifact_type": {
                "type": "string",
                "remember": False,
                "description": "Type of the created artifact.",
            },
        },
    }

    def run(
        self,
        input_data: Dict[str, Any],
        artifacts: ArtifactRegistry | None = None,
        package_name: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        #
        # 1) Basic validation and package selection
        #
        if artifacts is None:
            return {"message": "❌ No ArtifactRegistry provided; cannot create artifact."}

        data = input_data or {}
        name    = (data.get("name") or "").strip()
        type_   = (data.get("type") or "").strip()
        content = data.get("content")
        pkg_in  = (data.get("package") or "").strip()
        meta_in = data.get("metadata") or {}

        if not name:
            return {"message": "❌ 'name' is required to create an artifact."}
        if not type_:
            return {"message": "❌ 'type' is required to create an artifact."}

        target_pkg = pkg_in or (package_name or "").strip()
        if not target_pkg:
            return {"message": "❌ No target package specified and no active package available."}

        #
        # 2) Merge name into metadata (your Artifact class reads name from metadata)
        #
        metadata = dict(meta_in or {})
        # ensure the logical name is present
        metadata.setdefault("name", name)

        #
        # 3) Delegate to ArtifactRegistry
        #
        try:
            new_art = artifacts.add_artifact(
                package_name=target_pkg,
                type_=type_,
                content=content,
                metadata=metadata,
            )
        except Exception as e:
            return {"message": f"❌ Failed to create artifact: {e!r}"}

        msg = f"✅ Artifact '{new_art.name}' (type: {new_art.type}) created in package '{target_pkg}'."
        ui  = f"**Created**: `{new_art.name}`<br><i>(type: {new_art.type}, package: {target_pkg})</i>"

        return {
            "message": msg,
            "ui": ui,
            "artifact_id": getattr(new_art, "id", None),
            "artifact_name": new_art.name,
            "artifact_type": new_art.type,
        }
