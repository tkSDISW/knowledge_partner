# se_agent/tools/import_file_artifact.py
from __future__ import annotations
from typing import Any, Dict, Optional
import os
from datetime import datetime, timezone
from se_agent.core.tool_patterns import register_tool, TransformTool
from se_agent.mcp.artifact_registry import ArtifactRegistry, Artifact  # type: ignore

def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

@register_tool
class ImportFileArtifactTool(TransformTool):
    """
    Register a local file as a 'file_reference' artifact (no parsing).
    Works for PDFs, YAML, JSON, CSV, images, etc.; analyzer can ingest later.
    """

    TOOL_NAME   = "import_file_artifact"
    DESCRIPTION = "Register a local file as a 'file_reference' artifact (path + metadata)."
    description = DESCRIPTION
    name = TOOL_NAME 
    CATEGORY    = "import"
    
    CATEGORY = "transform"

    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "file_path": {"type": "path", "required": True,  "description": "Absolute or working-dir path to the file."},
            "name":      {"type": "string", "required": False, "description": "Artifact name (defaults to filename stem)."},
        },
        "outputs": {
            "message":       {"type": "string", "remember": False},
            "artifact_id":   {"type": "string", "remember": False},
            "artifact_name": {"type": "string", "remember": False},
            "artifact_type": {"type": "string", "remember": False},
        },
    }

    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry, package_name: Optional[str] = None, **_) -> Dict[str, Any]:
        path = input_data.get("file_path")
        if not path or not os.path.exists(path):
            return {"message": f"❌ File not found: {path}"}

        base = os.path.basename(path)
        stem, ext = os.path.splitext(base)
        name = (input_data.get("name") or stem).strip() or stem

        meta = {
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "source_path": os.path.abspath(path),
            "original_filename": base,
            "file_ext": ext.lower(),
            "size_bytes": os.path.getsize(path),
        }

        art = Artifact(
            type_="file_reference",
            name=name,
            content={"file_path": meta["source_path"]},
            metadata=meta
        )
        pkg = artifacts.get_active_package()
        pkg.add_artifact(art)

        return {
            "message": f"📎 Registered '{base}' as file_reference '{name}'.",
            "artifact_id": getattr(art, "id", ""),
            "artifact_name": name,
            "artifact_type": "file_reference",
        }
