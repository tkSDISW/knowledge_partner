# se_agent/tools/create_capella_model_artifact.py
from __future__ import annotations
from typing import Any, Dict

from se_agent.core.tool_patterns import register_tool, ImportTool
from se_agent.mcp.artifact_registry import ArtifactRegistry


@register_tool
class CreateCapellaModelArtifactTool(ImportTool):
    """
    Create a single capella_model artifact that bundles the .aird path and the
    Capella resources dict. Downstream tools (e.g., query_capella_model) can
    reference this artifact by name or id instead of juggling two artifacts.
    """

    TOOL_NAME   = "create_capella_model_artifact"
    DESCRIPTION = "CREATE A SINGLE CAPELLA_MODEL ARTIFACT FROM PATH AND RESOURCES."
    CATEGORY    = "import"

    ARTIFACTS: Dict[str, Any] = {
        "capella_model": {
            "fields": {
                "path": {"type": "path", "description": "Absolute or project-relative .aird path"},
                "resources": {"type": "dict", "description": "capellambse resources mapping"},
            },
            "schema_version": "1.0",
            "description": "Bundled Capella model reference (path + resources).",
        }
    }

    IO_SCHEMA = {
        "inputs": {
            "path_to_model": {
                "type": "path",
                "required": True,
                "description": "Path to the Capella .aird file.",
            },
            "resources": {
                "type": "dict",
                "required": True,
                "description": "capellambse resources mapping for the model.",
            },
            "name": {
                "type": "string",
                "required": False,
                "description": "Optional friendly name to assign to the artifact.",
            },
            "package": {
                "type": "string",
                "required": False,
                "description": "Target package (defaults to agent package).",
            },
        },
        "outputs": {
            "capella_model_artifact_id": {
                "type": "capella_model",
                "remember": True,  # keep handy for planning / follow-ups
                "description": "The created capella_model artifact id.",
            }
        },
    }

    def run(self, input_data, artifacts: ArtifactRegistry, package_name=None, **kwargs):
        raw = input_data or {}
        path_to_model = raw.get("path_to_model") or raw.get("path")
        resources = raw.get("resources")
        name = raw.get("name")
        pkg_name = raw.get("package") or package_name

        if not path_to_model:
            return {"error": "Missing 'path_to_model' (or 'path')."}
        if resources is None or not isinstance(resources, dict):
            return {"error": "Missing or invalid 'resources' (must be a dict)."}
        if not pkg_name:
            return {"error": "No package selected. Pass `package` or use agent.use_package(...)."}

        content = {"path": path_to_model, "resources": resources}
        meta = {"name": name} if name else {}
        art = artifacts.add_artifact(
            package_name=pkg_name,
            type_="capella_model",
            content=content,
            metadata=meta,
        )
        # Assign name field to artifact object if provided
        if name:
            art.name = name

        msg = f"✅ Created capella_model artifact 📋 from '{path_to_model}'."
        return {
            "message": msg,
            "artifact_ids": {"capella_model_artifact_id": art.id},
            "path": path_to_model,
            "named": bool(name),
        }
