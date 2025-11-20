# se_agent/tools/save_prompt_artifact.py
from __future__ import annotations
from datetime import datetime, timezone
from se_agent.core.tool_patterns import register_tool, TransformTool
from se_agent.mcp.artifact_registry import Artifact  # type: ignore

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

@register_tool
class SavePromptArtifact(TransformTool):

    name = "save_prompt_artifact"
    TOOL_NAME = name
    DESCRIPTION = (
        "RENDERS A PROMPT FROM A PROMPT_SPEC ARTIFACT USING QUOTED STRINGS OR A VARIABLES DICT; CAN PERSIST AS A PROMPT ARTIFACT."
    )
    description =  DESCRIPTION
    
    IO_SCHEMA = {
        "inputs": {
            "name": {"type":"string","required":True,"description":"Artifact name"},
            "text": {"type":"string","required":True,"description":"Rendered prompt text"},
            "source_path": {"type":"string","required":False,"description":"Original file path of template (optional)"},
            "template_name": {"type":"string","required":False,"description":"Template base name (optional)"},
            "tags": {"type":"array","required":False,"description":"List of tags"},
        },
        "outputs": {
            "message":{"type":"string","remember":False},
            "artifact_id":{"type":"string","remember":False},
            "artifact_name":{"type":"string","remember":False},
            "artifact_type":{"type":"string","remember":False},
        },
    }

    def run(self, input_data, artifacts, package_name=None, **_):
        name = (input_data.get("name") or "").strip()
        text = input_data.get("text") or ""
        if not name or not text:
            return {"message": "❌ name and text are required"}

        meta = {
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "tags": input_data.get("tags") or [],
        }
        if input_data.get("source_path"):
            meta["source_path"] = input_data["source_path"]
        if input_data.get("template_name"):
            meta["template_name"] = input_data["template_name"]

        art = Artifact(type_="prompt", name=name, content=text, metadata=meta)
        pkg = artifacts.get_active_package()
        pkg.add_artifact(art)

        return {
            "message": f"📝 Saved prompt artifact '{name}'.",
            "artifact_id": getattr(art, "id", ""),
            "artifact_name": name,
            "artifact_type": "prompt",
        }

